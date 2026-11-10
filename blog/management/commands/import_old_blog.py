"""
旧 Java 博客数据导入：

    python manage.py import_old_blog --dsn mysql://user:password@127.0.0.1:3306/oldblog

- 默认按 article(id,title,content,category_id) / category(id,name) 表结构读取，
  表名/字段名都可通过命令行参数覆盖（待旧库 .sql 提供后调整默认值即可）。
- 先导分类，再按旧分类外键映射导入文章。
- 只迁移 类别/标题/内容；published_at 缺失时取导入时间；views/likes 归 0。
- 幂等：同标题且同内容的文章会跳过，可重复执行。
"""
import datetime as dt
from urllib.parse import parse_qs, unquote, urlparse

import pymysql
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from blog.models import Category, Post


def _coerce_datetime(value):
    """把旧库的时间列尽量稳妥地转成 aware datetime（旧数据按东八区理解）。"""
    if isinstance(value, dt.datetime):
        result = value
    elif isinstance(value, dt.date):
        result = dt.datetime.combine(value, dt.time(12, 0))
    elif isinstance(value, str):
        text = value.strip()
        result = None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                result = dt.datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        if result is None:
            return timezone.now()
    else:
        return timezone.now()
    if timezone.is_naive(result):
        return timezone.make_aware(result, timezone.get_default_timezone())
    return result


class Command(BaseCommand):
    help = "从旧 Java 博客 MySQL 库导入分类与文章（只迁标题/分类/内容）"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dsn",
            required=True,
            help="旧库连接串，如 mysql://root:123456@127.0.0.1:3306/oldblog",
        )
        parser.add_argument("--article-table", default="article", help="旧文章表名（默认 article）")
        parser.add_argument("--category-table", default="category", help="旧分类表名（默认 category）")
        # 旧表字段名（可用参数覆盖；拿 .sql 比对后可改默认值）
        parser.add_argument("--article-id-col", default="id")
        parser.add_argument("--article-title-col", default="title")
        parser.add_argument("--article-content-col", default="content")
        parser.add_argument("--article-category-col", default="category_id")
        parser.add_argument("--article-date-col", default="", help="旧发布时间列（可选；缺省不迁时间）")
        parser.add_argument("--category-id-col", default="id")
        parser.add_argument("--category-name-col", default="name")
        parser.add_argument("--limit", type=int, default=0, help="只导前 N 篇（调试用，0=不限）")
        parser.add_argument("--dry-run", action="store_true", help="只统计，不写入")

    # ------------------------------------------------------------------
    @staticmethod
    def _connect(dsn: str):
        parsed = urlparse(dsn)
        if parsed.scheme not in ("mysql", "mariadb"):
            raise CommandError("--dsn 必须形如 mysql://user:password@host:3306/dbname")
        database = parsed.path.lstrip("/")
        if not database:
            raise CommandError("连接串缺少库名，例如 mysql://user:pass@host:3306/oldblog")
        params = {
            "host": parsed.hostname or "127.0.0.1",
            "port": parsed.port or 3306,
            "user": unquote(parsed.username or "root"),
            "password": unquote(parsed.password or ""),
            "database": database,
            "charset": parse_qs(parsed.query).get("charset", ["utf8mb4"])[0],
        }
        try:
            return pymysql.connect(**params)
        except Exception as exc:
            raise CommandError(f"连接旧库失败：{exc}")

    @staticmethod
    def _columns(conn, database: str, table: str):
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = %s AND table_name = %s",
                (database, table),
            )
            columns = {row[0] for row in cursor.fetchall()}
        if not columns:
            raise CommandError(f"旧表不存在或没有列：{table}")
        return columns

    @staticmethod
    def _select(conn, table: str, cols, order_col=None, limit=0):
        quoted = ", ".join(f"`{c}`" for c in cols)
        sql = f"SELECT {quoted} FROM `{table}`"
        if order_col:
            sql += f" ORDER BY `{order_col}`"
        if limit:
            sql += f" LIMIT {int(limit)}"
        with conn.cursor() as cursor:
            cursor.execute(sql)
            return cursor.fetchall()

    @staticmethod
    def _require(columns, table: str, needed):
        missing = [col for col in needed if col not in columns]
        if missing:
            raise CommandError(
                f"表 {table} 缺少列 {missing}（现有列：{sorted(columns)}）。"
                f"可用 --article-* / --category-* 参数覆盖列名"
            )

    # ------------------------------------------------------------------
    def handle(self, *args, **options):
        article_table = options["article_table"]
        category_table = options["category_table"]

        conn = self._connect(options["dsn"])
        try:
            article_cols = self._columns(conn, conn.db, article_table)
            category_cols = self._columns(conn, conn.db, category_table)
        except CommandError:
            raise
        except Exception as exc:
            raise CommandError(f"读取旧表结构失败：{exc}")

        # ---------- 关键列校验 ----------
        self._require(
            article_cols,
            article_table,
            [
                options["article_id_col"],
                options["article_title_col"],
                options["article_content_col"],
            ],
        )
        self._require(
            category_cols,
            category_table,
            [options["category_id_col"], options["category_name_col"]],
        )

        art_cat_col = options["article_category_col"]
        has_article_category = art_cat_col in article_cols
        date_col = options["article_date_col"] or None
        has_date = bool(date_col and date_col in article_cols)
        if options["article_date_col"] and not has_date:
            self.stdout.write(
                self.style.WARNING(f"文章表没有时间列 {date_col}，发布时间将取导入时间")
            )

        self.stdout.write(
            f"已连接：{conn.host}:{conn.port}/{conn.db.decode() if isinstance(conn.db, bytes) else conn.db}"
            f"  文章表={article_table}（分类列={'有' if has_article_category else '无'}，"
            f"时间列={date_col if has_date else '无'}）"
        )

        # ---------- dry-run ----------
        if options["dry_run"]:
            rows = self._select(conn, article_table, [options["article_id_col"]], options["article_id_col"], options["limit"])
            self.stdout.write(self.style.SUCCESS(f"[dry-run] 旧文章 {len(rows)} 篇，未写入"))
            conn.close()
            return

        # ---------- 1. 导入分类 ----------
        cat_id_col = options["category_id_col"]
        cat_name_col = options["category_name_col"]
        cat_rows = self._select(conn, category_table, [cat_id_col, cat_name_col], cat_id_col, options["limit"])
        old_cat_to_pk = {}
        created_categories = 0
        for old_id, name in cat_rows:
            if name is None or not str(name).strip():
                continue
            category, created = Category.objects.get_or_create(name=str(name).strip())
            old_cat_to_pk[str(old_id)] = category.pk
            created_categories += 1 if created else 0
        self.stdout.write(
            self.style.SUCCESS(f"分类完成：旧表 {len(cat_rows)} 行，新建 {created_categories} 个")
        )

        # ---------- 2. 拼选文章列 ----------
        title_col = options["article_title_col"]
        content_col = options["article_content_col"]
        select_cols = [options["article_id_col"], title_col, content_col]
        if has_article_category:
            select_cols.append(art_cat_col)
        if has_date:
            select_cols.append(date_col)

        rows = self._select(conn, article_table, select_cols, options["article_id_col"], options["limit"])

        # ---------- 3. 导入文章 ----------
        created_posts = 0
        skipped = 0
        fallback_time = timezone.now()
        for row in rows:
            row_map = dict(zip(select_cols, row))
            title = (row_map.get(title_col) or "").strip()
            content = row_map.get(content_col) or ""
            if not title:
                skipped += 1
                continue
            if Post.objects.filter(title=title, content_md=content).exists():
                skipped += 1
                continue

            category_pk = None
            if has_article_category and row_map.get(art_cat_col) is not None:
                category_pk = old_cat_to_pk.get(str(row_map[art_cat_col]))

            published_at = fallback_time
            if has_date and row_map.get(date_col) is not None:
                published_at = _coerce_datetime(row_map[date_col])

            Post.objects.create(
                title=title,
                content_md=content,
                category_id=category_pk,
                published_at=published_at,
                views=0,
                likes=0,
            )
            created_posts += 1

        conn.close()
        self.stdout.write(
            self.style.SUCCESS(
                f"导入完成：新增 {created_posts} 篇，跳过 {skipped} 篇（重复或无标题）"
            )
        )
