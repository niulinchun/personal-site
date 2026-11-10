"""
blog 视图与 JSON API。

页面：
- /blog/                 三栏知识库布局首页
- /blog/<id>/            同一布局并预选中该文章（URL 可分享收藏）
- /blog/manage/          文章管理列表（需登录）
- /blog/manage/new/      新建文章（需登录）
- /blog/manage/<id>/edit/ 编辑文章（需登录）

API（原生 fetch 使用，返回 JSON）：
- GET     /blog/api/posts/?category=&q=&page=
- GET     /blog/api/posts/<id>/       （浏览量 +1）
- POST    /blog/api/posts/<id>/like/
- GET/POST /blog/api/posts/<id>/comments/
- POST    /blog/api/upload/           （需登录）
"""
import json
import os
import re

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, F
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST, require_http_methods

from blog.forms import PostForm
from blog.models import Category, Comment, Image, Post

PAGE_SIZE = 20  # 中栏"加载更多"单页数量
MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 单张图片上限

# 允许的图片扩展名（与 image/* content-type 双重校验）
ALLOWED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"}

# Markdown 图片语法：![任意 alt](url)
IMAGE_MD_RE = re.compile(r"!\[[^\]]*\]\(\s*<?([^)\s<>]+)>?\s*\)")


def _catalog_context():
    """左栏分类列表（含各分类文章数）与文章总数。"""
    return {
        "categories": Category.objects.annotate(count=Count("posts")),
        "post_count": Post.objects.count(),
    }


# ---------------------------------------------------------------------------
# 页面
# ---------------------------------------------------------------------------


def blog_home(request):
    """博客首页：三栏布局，默认不选中任何文章。"""
    context = _catalog_context()
    context["selected_post"] = None
    return render(request, "blog/index.html", context)


def blog_post_page(request, pk):
    """与首页同一布局，但预选中指定文章（可直接分享/收藏）。"""
    context = _catalog_context()
    context["selected_post"] = get_object_or_404(Post, pk=pk)
    return render(request, "blog/index.html", context)


# ---------------------------------------------------------------------------
# JSON API（前台公开）
# ---------------------------------------------------------------------------


def _filter_posts_queryset(request):
    """按分类 / 标题模糊搜索过滤文章。"""
    qs = Post.objects.select_related("category")
    category_id = request.GET.get("category")
    if category_id and category_id != "all":
        if str(category_id).isdigit():
            qs = qs.filter(category_id=int(category_id))
        else:
            qs = qs.none()
    q = request.GET.get("q")
    if q:
        qs = qs.filter(title__icontains=q)
    return qs


@require_http_methods(["GET"])
def api_post_list(request):
    """中栏文章列表；page 为页码，前端用“加载更多”按钮追加。"""
    try:
        page = max(1, int(request.GET.get("page", "1")))
    except (TypeError, ValueError):
        page = 1
    qs = _filter_posts_queryset(request)
    start = (page - 1) * PAGE_SIZE
    posts = list(qs[start : start + PAGE_SIZE + 1])  # 多取一条判断 has_next
    has_next = len(posts) > PAGE_SIZE
    posts = posts[:PAGE_SIZE]
    items = [
        {
            "id": p.id,
            "title": p.title,
            "date": p.published_at.strftime("%Y/%m/%d"),
            "category": p.category.name if p.category else None,
        }
        for p in posts
    ]
    return JsonResponse(
        {"items": items, "has_next": has_next, "next_page": page + 1 if has_next else None}
    )


@require_http_methods(["GET"])
def api_post_detail(request, pk):
    """右栏文章详情；浏览量原子 +1（避免并发覆盖）。"""
    post = get_object_or_404(Post, pk=pk)
    Post.objects.filter(pk=post.pk).update(views=F("views") + 1)
    return JsonResponse(
        {
            "id": post.id,
            "title": post.title,
            "category": post.category.name if post.category else None,
            "published_at": post.published_at.strftime("%Y/%m/%d %H:%M"),
            "views": post.views + 1,
            "likes": post.likes,
            "content_md": post.content_md,
        }
    )


@require_POST
def api_post_like(request, pk):
    """点赞 +1（防重复点由前端 localStorage 控制）。"""
    post = get_object_or_404(Post, pk=pk)
    Post.objects.filter(pk=post.pk).update(likes=F("likes") + 1)
    post.refresh_from_db(fields=["likes"])
    return JsonResponse({"likes": post.likes})


def _comment_payload(comment: Comment):
    return {
        "id": comment.id,
        "nickname": comment.nickname,
        "content": comment.content,
        "created_at": comment.created_at.strftime("%Y/%m/%d %H:%M"),
    }


@require_http_methods(["GET", "POST"])
def api_post_comments(request, pk):
    """评论列表 + 发表评论（免登录，昵称 + 内容）。"""
    post = get_object_or_404(Post, pk=pk)

    if request.method == "GET":
        comments = post.comments.all()[:200]
        return JsonResponse({"items": [_comment_payload(c) for c in comments]})

    if request.content_type and "json" in request.content_type:
        try:
            data = json.loads(request.body.decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError):
            return JsonResponse({"error": "请求体不是合法 JSON"}, status=400)
    else:
        data = request.POST

    nickname = (data.get("nickname") or "").strip()
    content = (data.get("content") or "").strip()
    if not nickname:
        return JsonResponse({"error": "请填写昵称"}, status=400)
    if not content:
        return JsonResponse({"error": "请填写评论内容"}, status=400)
    if len(nickname) > 32:
        return JsonResponse({"error": "昵称最多 32 个字符"}, status=400)
    if len(content) > 2000:
        return JsonResponse({"error": "评论最多 2000 字"}, status=400)

    comment = Comment.objects.create(post=post, nickname=nickname, content=content)
    return JsonResponse({"comment": _comment_payload(comment)}, status=201)


# ---------------------------------------------------------------------------
# 图片上传与归属管理
# ---------------------------------------------------------------------------


def _extract_media_names(content_md: str):
    """
    从 Markdown 正文解析本站图片的存储路径（相对 MEDIA_ROOT）。
    仅认…/media/uploads/… 形式的 URL；host 部分任意（本地/域名都行）。
    """
    names = set()
    if not content_md:
        return names
    for match in IMAGE_MD_RE.finditer(content_md):
        url = match.group(1)
        if url.startswith("//"):
            continue
        idx = url.find("media/")
        if idx == -1:
            continue
        path = url[idx + len("media/") :].split("?")[0].split("#")[0]
        if path.startswith("uploads/"):
            names.add(path)
    return names


def sync_post_images(post: Post):
    """
    保存文章后同步图片归属：
    1) 正文仍在引用的图片 → post=本文；（首次保存即建立归属）
    2) 本文本原先拥有、但正文已不引用的图片 → post=None 置空
      （不立即删文件，避免“剪切图片到另一篇文章”被误删；
       文件由 cleanup_images 命令按保留期清理）
    """
    linked_names = _extract_media_names(post.content_md)

    for image in Image.objects.filter(post=post):
        if image.file.name in linked_names:
            linked_names.discard(image.file.name)  # 归属不变
        else:
            image.post = None
            image.save(update_fields=["post"])

    # 剩余的是新引用：认领（哪怕它当前挂靠在别的文章名下）
    for name in linked_names:
        image = Image.objects.filter(file=name).first()
        if image is not None and image.post_id != post.pk:
            image.post = post
            image.save(update_fields=["post"])


@login_required
@require_POST
def api_upload(request):
    """
    上传图片（仅 admin 登录可用）。
    校验：content-type 必须为图片、扩展名白名单、单张 ≤10MB。
    返回 {"url": "/media/uploads/YYYY/MM/<uuid>.<ext>"}，编辑器直接插入 Markdown。
    """
    upload = request.FILES.get("file")
    if upload is None:
        return JsonResponse({"error": "未收到文件（字段名 file）"}, status=400)

    ctype = (upload.content_type or "").lower()
    name = upload.name or ""
    ext = os.path.splitext(name)[1].lower()

    if not ctype.startswith("image/"):
        return JsonResponse({"error": "仅支持上传图片文件"}, status=400)
    if ext and ext not in ALLOWED_IMAGE_EXTS:
        return JsonResponse({"error": "不支持的扩展名：" + ext}, status=400)
    if upload.size > MAX_IMAGE_BYTES:
        return JsonResponse({"error": "图片不能超过 10MB"}, status=400)

    image = Image(file=upload)
    image.save()
    return JsonResponse({"url": image.file.url})


# ---------------------------------------------------------------------------
# 文章管理（需登录）
# ---------------------------------------------------------------------------


@login_required
def manage_post_list(request):
    posts = Post.objects.select_related("category").only(
        "id", "title", "published_at", "views", "likes", "category__name"
    )
    return render(
        request,
        "blog/manage.html",
        {"posts": posts, "categories": Category.objects.all(), **_catalog_context()},
    )


@login_required
def manage_post_create(request):
    if request.method == "POST":
        form = PostForm(request.POST)
        if form.is_valid():
            post = form.save()
            sync_post_images(post)
            messages.success(request, "文章已创建")
            return redirect("blog:manage_edit", pk=post.pk)
    else:
        form = PostForm(initial={"published_at": timezone.now})
    return render(
        request,
        "blog/manage_form.html",
        {"form": form, "editing": False, "categories": Category.objects.all()},
    )


@login_required
def manage_post_edit(request, pk):
    post = get_object_or_404(Post, pk=pk)
    if request.method == "POST":
        form = PostForm(request.POST, instance=post)
        if form.is_valid():
            post = form.save()
            sync_post_images(post)
            messages.success(request, "文章已保存")
            return redirect("blog:manage_edit", pk=post.pk)
    else:
        form = PostForm(instance=post)
    return render(
        request,
        "blog/manage_form.html",
        {"form": form, "editing": True, "post": post, "categories": Category.objects.all()},
    )


@login_required
@require_POST
def manage_post_delete(request, pk):
    """删除文章；信号会级联删除关联图片的记录与物理文件。"""
    post = get_object_or_404(Post, pk=pk)
    post.delete()
    messages.success(request, "文章已删除（关联图片文件一并清理）")
    return redirect("blog:manage")
