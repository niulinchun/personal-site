"""
import_old_blog / import_backup_sql 管理命令的离线测试（mock pymysql + 本地构造 dump 文件）。
"""
import base64
import io
import tempfile
import os
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from blog.models import Category, Post


def _fake_conn(rows_sequence):
    conn = MagicMock()
    conn.db = "oldblog"
    conn.host = "127.0.0.1"
    conn.port = 3306
    cursor = MagicMock()
    # with conn.cursor() as c → 返回同一 cursor；fetchall 按次序吐结果
    cursor.__enter__.return_value = cursor
    cursor.fetchall.side_effect = rows_sequence
    conn.cursor.return_value = cursor
    return conn


class ImportOldBlogTests(TestCase):
    @patch("blog.management.commands.import_old_blog.pymysql.connect")
    def test_import_maps_categories_and_posts(self, connect_mock):
        connect_mock.return_value = _fake_conn([
            # article 表结构
            [("id",), ("title",), ("content",), ("category_id",)],
            # category 表结构
            [("id",), ("name",)],
            # 分类数据
            [(1, "程序人生"), (2, "Java")],
            # 文章数据
            [(101, "第一篇", "内容甲", 1), (102, "第二篇", "内容乙", 2)],
        ])

        call_command("import_old_blog", "--dsn", "mysql://u:p@127.0.0.1:3306/oldblog", stdout=io.StringIO())

        self.assertEqual(Category.objects.count(), 2)
        posts = list(Post.objects.order_by("id"))
        self.assertEqual(len(posts), 2)
        self.assertEqual(posts[0].category.name, "程序人生")
        self.assertEqual(posts[1].category.name, "Java")
        self.assertEqual(posts[0].content_md, "内容甲")
        self.assertEqual(posts[0].views, 0)  # 浏览量从 0 起步
        self.assertEqual(posts[0].likes, 0)

    @patch("blog.management.commands.import_old_blog.pymysql.connect")
    def test_column_override_and_missing_optional_columns(self, connect_mock):
        # 旧表字段名不同，可选时间列不存在
        connect_mock.return_value = _fake_conn([
            [("aid",), ("atitle",), ("abody",)],          # 没有 category 列、没有时间列
            [("cid",), ("cname",)],
            [(9, "唯一分类")],
            [(7, "旧文", "正文")],
        ])
        call_command(
            "import_old_blog",
            "--dsn", "mysql://u:p@127.0.0.1:3306/oldblog",
            "--article-table", "posts",
            "--category-table", "cats",
            "--article-id-col", "aid",
            "--article-title-col", "atitle",
            "--article-content-col", "abody",
            "--category-id-col", "cid",
            "--category-name-col", "cname",
            stdout=io.StringIO(),
        )
        posts = list(Post.objects.all())
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0].category_id, None)  # 旧表没有分类列
        self.assertEqual(posts[0].title, "旧文")

    @patch("blog.management.commands.import_old_blog.pymysql.connect")
    def test_missing_required_column_raises(self, connect_mock):
        connect_mock.return_value = _fake_conn([
            [("id",), ("name",)],            # article 表缺 title/content
            [("id",), ("name",)],
        ])
        with self.assertRaisesMessage(CommandError, "缺少列"):
            call_command("import_old_blog", "--dsn", "mysql://u:p@127.0.0.1:3306/oldblog", stdout=io.StringIO())

    @patch("blog.management.commands.import_old_blog.pymysql.connect")
    def test_dry_run_does_not_write(self, connect_mock):
        connect_mock.return_value = _fake_conn([
            [("id",), ("title",), ("content",)],
            [("id",), ("name",)],
            [(1, "x")],           # dry-run 只统计 id 列
        ])
        out = io.StringIO()
        call_command("import_old_blog", "--dsn", "mysql://u:p@127.0.0.1:3306/oldblog", "--dry-run", stdout=out)
        self.assertEqual(Post.objects.count(), 0)
        self.assertEqual(Category.objects.count(), 0)

    def test_bad_dsn(self):
        with self.assertRaisesMessage(CommandError, "mysql://"):
            call_command("import_old_blog", "--dsn", "https://x/x", stdout=io.StringIO())

# ==================================================================
# import_backup_sql：mysqldump 文件直读（Base32 解码）
# ==================================================================
class ImportBackupSqlTests(TestCase):
    @staticmethod
    def _b32(text: str) -> str:
        return base64.b32encode(text.encode("utf-8")).decode("ascii")

    def _write_dump(self, rows, table="article"):
        body = ",".join(
            "('{bt}','{bc}','{bc2}')".format(
                bt=self._b32(title), bc=self._b32(cat), bc2=self._b32(content)
            )
            for title, cat, content in rows
        )
        content = (
            "-- MySQL dump 10.13\n"
            "DROP TABLE IF EXISTS `{t}`;\n"
            "CREATE TABLE `{t}` (\n"
            "  `article_title` varchar(255) NOT NULL,\n"
            "  `article_category` varchar(255) NOT NULL,\n"
            "  `article_content` text NOT NULL\n"
            ") ENGINE=InnoDB;\n"
            "INSERT INTO `{t}` VALUES {body};\n"
            "UNLOCK TABLES;\n"
        ).format(t=table, body=body)
        fd, path = tempfile.mkstemp(suffix=".sql")
        with os.fdopen(fd, "wb") as fh:
            fh.write(content.encode("utf-8"))
        self.addCleanup(lambda: (os.path.exists(path) and os.remove(path)))
        return path

    def test_import_decodes_and_creates(self):
        path = self._write_dump([
            ("深拷贝与浅拷贝", "Java", "# 深拷贝\n\n```java\npublic class A {}\n```"),
            ("滚动条样式", "CSS", "给 articleBox 设置样式"),
        ])
        out = io.StringIO()
        call_command("import_backup_sql", "--file", path, stdout=out)
        self.assertEqual(Post.objects.count(), 2)
        self.assertEqual(Category.objects.count(), 2)
        post = Post.objects.get(title="深拷贝与浅拷贝")
        self.assertEqual(post.category.name, "Java")
        self.assertIn("public class A", post.content_md)
        self.assertEqual(post.views, 0)
        self.assertEqual(post.likes, 0)
        self.assertIsNotNone(post.published_at)

    def test_idempotent(self):
        path = self._write_dump([("唯一标题", "Java", "内容")])
        call_command("import_backup_sql", "--file", path, stdout=io.StringIO())
        call_command("import_backup_sql", "--file", path, stdout=io.StringIO())
        self.assertEqual(Post.objects.count(), 1)
        self.assertEqual(Category.objects.count(), 1)

    def test_limit(self):
        path = self._write_dump([
            ("T1", "Java", "c1"), ("T2", "Java", "c2"), ("T3", "Java", "c3"),
        ])
        call_command("import_backup_sql", "--file", path, "--limit", "2", stdout=io.StringIO())
        self.assertEqual(Post.objects.count(), 2)

    def test_dry_run_no_write(self):
        path = self._write_dump([("T", "CSS", "C")])
        call_command("import_backup_sql", "--file", path, "--dry-run", stdout=io.StringIO())
        self.assertEqual(Post.objects.count(), 0)
        self.assertEqual(Category.objects.count(), 0)

    def test_plain_decode(self):
        fd, path = tempfile.mkstemp(suffix=".sql")
        with os.fdopen(fd, "wb") as fh:
            fh.write(
                "INSERT INTO `article` VALUES ('明文标题','Java','正文');\n".encode("utf-8")
            )
        self.addCleanup(lambda: (os.path.exists(path) and os.remove(path)))
        call_command("import_backup_sql", "--file", path, "--decode", "plain", stdout=io.StringIO())
        post = Post.objects.first()
        self.assertEqual(post.title, "明文标题")
        self.assertEqual(post.content_md, "正文")

    def test_wrong_table_raises(self):
        fd, path = tempfile.mkstemp(suffix=".sql")
        with os.fdopen(fd, "wb") as fh:
            fh.write(b"INSERT INTO `other` VALUES ('a','b','c');\n")
        self.addCleanup(lambda: (os.path.exists(path) and os.remove(path)))
        with self.assertRaisesMessage(CommandError, "没找到表"):
            call_command("import_backup_sql", "--file", path, stdout=io.StringIO())
