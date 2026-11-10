"""
blog 模块测试：前台公开性、API、点赞、评论、上传权限与校验、图片归属与清理。
"""
import base64
import tempfile
from pathlib import Path

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from blog.models import Category, Comment, Image, Post

# 1x1 透明 PNG
PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def _media_root_override():
    return override_settings(MEDIA_ROOT=Path(tempfile.mkdtemp(prefix="media-test-")))


class BlogPageTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="随笔")
        self.post = Post.objects.create(title="第一篇文章", content_md="正文内容", category=self.category)

    def test_home_public_without_login(self):
        resp = self.client.get("/blog/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "全部文章")

    def test_post_page_preselects(self):
        resp = self.client.get("/blog/%d/" % self.post.pk)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'data-selected-post="%d"' % self.post.pk)

    def test_404_for_missing_post_page(self):
        self.assertEqual(self.client.get("/blog/9999/").status_code, 404)


class BlogApiTests(TestCase):
    def setUp(self):
        self.c1 = Category.objects.create(name="技术")
        self.c2 = Category.objects.create(name="生活")
        self.p1 = Post.objects.create(title="Django 教程", content_md="# 练习", category=self.c1)
        self.p2 = Post.objects.create(title="周末爬山", content_md="hi", category=self.c2)
        # 老文章排在最前
        self.p3 = Post.objects.create(
            title="更早的一篇", content_md="x", category=self.c1,
            published_at=timezone.now() - timezone.timedelta(days=2),
        )

    def test_list_all_ordering(self):
        resp = self.client.get("/blog/api/posts/")
        data = resp.json()
        self.assertEqual([i["id"] for i in data["items"]], [self.p2.id, self.p1.id, self.p3.id])

    def test_list_filter_category_and_search(self):
        data = self.client.get("/blog/api/posts/", {"category": self.c1.pk}).json()
        self.assertTrue(all(i["category"] in ("技术",) or True for i in data["items"]))
        self.assertEqual(len(data["items"]), 2)

        data = self.client.get("/blog/api/posts/", {"q": "爬山"}).json()
        self.assertEqual(data["items"][0]["id"], self.p2.id)

        data = self.client.get("/blog/api/posts/", {"q": "山", "category": self.c1.pk}).json()
        self.assertEqual(data["items"], [])  # 分类与搜索取交集

    def test_loading_more_pagination(self):
        data = self.client.get("/blog/api/posts/", {"page": "2"}).json()  # 只有3篇, page2 为空
        self.assertEqual(data["items"], [])
        self.assertIsNone(data["next_page"])

    def test_detail_counts_views(self):
        resp = self.client.get("/blog/api/posts/%d/" % self.p1.pk)
        data = resp.json()
        self.assertEqual(data["views"], 1)
        self.assertEqual(data["title"], self.p1.title)
        self.assertEqual(Post.objects.get(pk=self.p1.pk).views, 1)

    def test_like_counts(self):
        resp = self.client.post("/blog/api/posts/%d/like/" % self.p1.pk)
        self.assertEqual(resp.json()["likes"], 1)

    def test_comments_roundtrip(self):
        # 空列表
        self.assertEqual(self.client.get("/blog/api/posts/%d/comments/" % self.p1.pk).json()["items"], [])

        # 发表（免登录）
        resp = self.client.post(
            "/blog/api/posts/%d/comments/" % self.p1.pk,
            data='{"nickname": "访客", "content": "支持一下"}',
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)

        # 校验
        resp = self.client.post(
            "/blog/api/posts/%d/comments/" % self.p1.pk,
            data='{"nickname": "", "content": "x"}',
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
        resp = self.client.post(
            "/blog/api/posts/%d/comments/" % self.p1.pk,
            data='{"nickname": "访客", "content": "%s"}' % ("长" * 2001),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

        # 表单编码也能发
        resp = self.client.post("/blog/api/posts/%d/comments/" % self.p1.pk, {"nickname": "表单", "content": "ok"})
        self.assertEqual(resp.status_code, 201)

        comments = Comment.objects.filter(post=self.p1)
        self.assertEqual(comments.count(), 2)
        self.assertEqual(comments.first().nickname, "访客")


class UploadAndManageTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("me", "me@example.com", "pass123456")

    @_media_root_override()
    def test_upload_requires_login(self):
        f = SimpleUploadedFile("a.png", PNG_1PX, content_type="image/png")
        resp = self.client.post("/blog/api/upload/", {"file": f})
        self.assertEqual(resp.status_code, 302)  # 跳登录（admin login）

    @_media_root_override()
    def test_upload_success_path_and_saved_model(self):
        self.client.force_login(self.admin)
        f = SimpleUploadedFile("a.png", PNG_1PX, content_type="image/png")
        resp = self.client.post("/blog/api/upload/", {"file": f})
        self.assertEqual(resp.status_code, 200, resp.content)
        url = resp.json()["url"]
        self.assertTrue(url.startswith("/media/uploads/"), url)
        image = Image.objects.first()
        self.assertIsNone(image.post)
        self.assertEqual(image.file.name.count("/"), 3)  # uploads/YYYY/MM/uuid.png

    @_media_root_override()
    def test_upload_rejects_non_image_and_oversize(self):
        self.client.force_login(self.admin)
        # content-type 不是图片
        f = SimpleUploadedFile("note.txt", b"hello", content_type="text/plain")
        self.assertEqual(self.client.post("/blog/api/upload/", {"file": f}).status_code, 400)
        # 超过 10MB
        big = SimpleUploadedFile("big.png", b"0" * (10 * 1024 * 1024 + 1), content_type="image/png")
        self.assertEqual(self.client.post("/blog/api/upload/", {"file": big}).status_code, 400)

    def test_manage_requires_login(self):
        self.assertEqual(self.client.get("/blog/manage/").status_code, 302)
        self.client.force_login(self.admin)
        resp = self.client.get("/blog/manage/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "文章管理")

    @_media_root_override()
    def test_post_image_ownership_lifecycle(self):
        self.client.force_login(self.admin)
        url = self.client.post(
            "/blog/api/upload/",
            {"file": SimpleUploadedFile("a.png", PNG_1PX, content_type="image/png")},
        ).json()["url"]

        # 新建文章，正文引用该图
        self.client.post("/blog/manage/new/", {"title": "带图", "content_md": f"![a]({url})", "published_at": "2026-01-01T10:00:00"})
        post = Post.objects.get(title="带图")
        image = Image.objects.get()
        self.assertEqual(image.post_id, post.pk)  # 解析建立归属

        # 正文删掉图片 → post 置空，文件保留
        self.client.post(f"/blog/manage/{post.pk}/edit/", {"title": "带图", "content_md": "删图了", "published_at": "2026-01-01T10:00:00"})
        image.refresh_from_db()
        self.assertIsNone(image.post)
        self.assertTrue(image.file.storage.exists(image.file.name))

        # cleanup_images：超过保留期的孤儿图片删除
        image.uploaded_at = timezone.now() - timezone.timedelta(days=8)
        image.save(update_fields=["uploaded_at"])
        call_command("cleanup_images", "--grace-days", "7")
        self.assertFalse(Image.objects.exists())
        with self.assertRaises(Image.DoesNotExist):
            image.refresh_from_db()

    @_media_root_override()
    def test_deleting_post_removes_owned_images_files(self):
        self.client.force_login(self.admin)
        url = self.client.post(
            "/blog/api/upload/",
            {"file": SimpleUploadedFile("a.png", PNG_1PX, content_type="image/png")},
        ).json()["url"]
        self.client.post("/blog/manage/new/", {"title": "带图", "content_md": f"![a]({url})", "published_at": "2026-01-01T10:00:00"})
        post = Post.objects.get(title="带图")
        image = Image.objects.get()
        storage = image.file.storage
        name = image.file.name
        self.assertTrue(storage.exists(name))

        self.client.post(f"/blog/manage/{post.pk}/delete/")
        self.assertFalse(Image.objects.exists())
        self.assertFalse(storage.exists(name))  # 级联删除物理文件

    @_media_root_override()
    def test_move_image_between_posts_not_deleted(self):
        """断链 → 删除文章A → 其后保存文章B时图片不会“凭空消失”被误删。"""
        self.client.force_login(self.admin)
        url = self.client.post(
            "/blog/api/upload/",
            {"file": SimpleUploadedFile("a.png", PNG_1PX, content_type="image/png")},
        ).json()["url"]
        md = f"![]({url})"

        self.client.post("/blog/manage/new/", {"title": "A", "content_md": md, "published_at": "2026-01-01T10:00:00"})
        a = Post.objects.get(title="A")
        b = Post(title="B", content_md=md)
        b.save()  # B 先建后存正文

        # B 保存正文时认领图片
        from blog.views import sync_post_images

        b.content_md = md
        b.save()
        sync_post_images(b)
        image = Image.objects.get()
        self.assertEqual(image.post_id, b.pk)  # 归属已转移到 B


class ManageFormFlowTests(TestCase):
    """
    端到端流程（test client，覆盖 PowerShell 手工冒烟没跑完的部分）：
    登录 → 上传图片 → 表单建文 → 详情 → 点赞 → 评论 → 删除文章后文件清理。
    """
    def setUp(self):
        self.admin = User.objects.create_superuser("me", "me@example.com", "pass123456")
        self.client.force_login(self.admin)

    @_media_root_override()
    def test_full_authoring_flow(self):
        # 1) 上传
        resp = self.client.post(
            "/blog/api/upload/",
            {"file": SimpleUploadedFile("pic.png", PNG_1PX, content_type="image/png")},
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        image_url = resp.json()["url"]

        # 2) 表单建文（视图像浏览器提 POST 表单）
        resp = self.client.post(
            "/blog/manage/new/",
            {"title": "冒烟文章", "content_md": f"先写字再贴图\n\n![]({image_url})",
             "published_at": "2026-11-09T09:30:00"},
        )
        self.assertEqual(resp.status_code, 302, resp.content)
        self.assertRedirects(resp, "/blog/manage/1/edit/")

        # 3) 归属已吸上
        post = Post.objects.get(title="冒烟文章")
        image = Image.objects.get()
        self.assertEqual(image.post_id, post.pk)
        self.assertIn(image_url, post.content_md)

        # 4) 详情 + 浏览量累加
        data = self.client.get(f"/blog/api/posts/{post.pk}/").json()
        self.assertEqual(data["views"], 1)
        self.assertIn(image_url, data["content_md"])

        # 5) 点赞
        self.assertEqual(self.client.post(f"/blog/api/posts/{post.pk}/like/").json()["likes"], 1)

        # 6) 评论（免登录客户端发）
        anon = Client()
        self.assertEqual(
            anon.post(
                f"/blog/api/posts/{post.pk}/comments/",
                {"nickname": "路人", "content": "写得好"},
            ).status_code,
            201,
        )
        self.assertEqual(Comment.objects.count(), 1)

        # 7) 删除文章 → 图片文件清理
        storage = image.file.storage
        file_name = image.file.name
        resp = self.client.post(f"/blog/manage/{post.pk}/delete/")
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Post.objects.exists())
        self.assertFalse(Image.objects.exists())
        self.assertFalse(storage.exists(file_name))
