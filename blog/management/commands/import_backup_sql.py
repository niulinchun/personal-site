"""
旧 Java 博客 mysqldump 文件直读导入（不需要本地 MySQL）。

实测结构（2023-09 的 blog 备份）：
    CREATE TABLE article(article_title, article_category, article_content)
    - 三个字段均为“标准 Base32(RFC4648) 编码的 UTF-8 文本”
    - 分类是名称字符串（无独立 category 表），共 31 类 / 239 篇

用法（项目根目录）：
    python manage.py import_backup_sql --file backup.sql --dry-run
    python manage.py import_backup_sql --file backup.sql            # 正式导入
    python manage.py import_backup_sql --file backup.sql --limit 20 # 先试 20 篇
    python manage.py import_backup_sql --file backup.sql --decode none   # 不解码（明文 dump）

规则：只迁 类别/标题/内容；published_at 取导入时间；views/likes 归 0；
      同标题+同内容跳过（幂等，可重复执行）。
"""
import base64
import re

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from blog.models import Category, Post

_INSERT_RE = re.compile(
    r"INSERT\s+INTO\s+`(?P<table>[^`]+)`\s+VALUES\s*(?P<body>\([\s\S]*?\)[\s\S]*?;)",
    re.IGNORECASE,
)


class Command(BaseCommand):
    help = "从旧博客 mysqldump 文件（backup.sql）导入文章：自动 Base32 解码（实测旧站字段全编码）"

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True, help="备份 .sql 文件路径（项目根目录的 backup.sql）")
        parser.add_argument("--table", default="article", help="文章表名（默认 article）")
        parser.add_argument("--decode", default="base32", choices=["base32", "plain"],
                            help="字段解码方式：base32=按 RFC4648 Base32 解码（默认，实测旧站就是它）；"
                                 "plain=不解码，直接当明文。")
        parser.add_argument("--input-charset", default="auto",
                            help="dump 文件编码：utf-8 / gb18030 / auto（默认 auto：utf-8 优先，失败回 gb18030）")
        parser.add_argument("--limit", type=int, default=0, help="只导前 N 篇（调试用，0=不限）")
        parser.add_argument("--dry-run", action="store_true", help="只统计不写入")

    # ------------------------------------------------------------------ 文件
    @staticmethod
    def _read_text(path: str, charset: str) -> str:
        data = open(path, "rb").read()
        if charset == "auto":
            for name in ("utf-8", "gb18030"):
                try:
                    return data.decode(name)
                except UnicodeDecodeError:
                    continue
            return data.decode("utf-8", errors="replace")
        try:
            return data.decode(charset)
        except UnicodeDecodeError as exc:
            raise CommandError(f"按 {charset} 解码文件失败：{exc}；可改 --input-charset auto") from exc

    # ------------------------------------------------------------------ SQL 解析
    @staticmethod
    def _sql_unescape(s: str) -> str:
        """mysqldump 字符串反转义：\\' \\" \\\\ \\n \\r \\t \\b \\0 \\Z。"""
        if "\\" not in s:
            return s
        mapping = {
            "\"": "\"", "\\": "\\", "n": "\n", "r": "\r", "t": "\t",
            "b": "\b", "0": "\0", "Z": "\x1a", "'": "'", "_": "\\", "%": "\\",
        }
        out = []
        i = 0
        while i < len(s):
            ch = s[i]
            if ch == "\\" and i + 1 < len(s):
                next_ch = s[i + 1]
                out.append(mapping.get(next_ch, "\\" + next_ch))
                i += 2
            else:
                out.append(ch)
                i += 1
        return "".join(out)

    @staticmethod
    def _split_top_level(body: str):
        """按顶层 '),(' 切分 VALUES 元组；引号内（含 \\ 转义）不切。"""
        parts = []
        buf = []
        in_string = False
        i = 0
        n = len(body)
        while i < n:
            ch = body[i]
            if in_string:
                if ch == "\\" and i + 1 < n:
                    buf.append(ch)
                    buf.append(body[i + 1])
                    i += 2
                    continue
                if ch == "'":
                    # 处理 SQL 的单引号转义 ''
                    if i + 1 < n and body[i + 1] == "'":
                        buf.append("''")
                        i += 2
                        continue
                    in_string = False
                buf.append(ch)
                i += 1
                continue
            if ch == "'":
                in_string = True
                buf.append(ch)
                i += 1
                continue
            if ch == ")" :
                # 候选行分隔：),  (  —— 允许中间空格
                j = i + 1
                while j < n and body[j] in " \t\r\n":
                    j += 1
                if j < n and body[j] == ",":
                    k = j + 1
                    while k < n and body[k] in " \t\r\n":
                        k += 1
                    if k < n and body[k] == "(":
                        parts.append("".join(buf))
                        buf = []
                        i = k + 1  # 吃掉 '('
                        continue
            buf.append(ch)
            i += 1
        if buf:
            parts.append("".join(buf))
        cleaned = []
        for part in parts:
            text = part.strip()
            # 1) 剥语句结尾 ;
            while text.endswith(";"):
                text = text[:-1].rstrip()
            # 2) 无条件剥结构性的头尾括号（各一层）：
            #    元组外层括号是 SQL 语法结构，合法内容（含 base32/引号）不会以裸 ) 结束
            if text.startswith("("):
                text = text[1:].lstrip()
            if text.endswith(")"):
                text = text[:-1].rstrip()
            cleaned.append(text)
        return cleaned

    @staticmethod
    def _split_fields(tuple_body: str):
        """引号外按 ',' 切字段；返回原始(未反转义)字符串列表。"""
        fields = []
        buf = []
        in_string = False
        i = 0
        n = len(tuple_body)
        while i < n:
            ch = tuple_body[i]
            if in_string:
                if ch == "\\" and i + 1 < n:
                    buf.append(ch)
                    buf.append(tuple_body[i + 1])
                    i += 2
                    continue
                if ch == "'":
                    if i + 1 < n and tuple_body[i + 1] == "'":
                        buf.append("''")
                        i += 2
                        continue
                    in_string = False
                buf.append(ch)
                i += 1
                continue
            if ch == "'":
                in_string = True
                buf.append(ch)
                i += 1
                continue
            if ch == ",":
                fields.append("".join(buf))
                buf = []
                i += 1
                continue
            buf.append(ch)
            i += 1
        if buf:
            fields.append("".join(buf))
        out = []
        for raw in fields:
            raw = raw.strip()
            if raw.startswith("'") and raw.endswith("'") and len(raw) >= 2:
                raw = raw[1:-1]
                out.append(Command._sql_unescape(raw))
            elif raw.upper() == "NULL":
                out.append(None)
            else:
                out.append(raw)
        return out

    # ------------------------------------------------------------------ 解码
    @staticmethod
    def _b32_decode(value: str):
        """Base32 → utf-8（gbk 兜底）。失败返回 None。"""
        try:
            data = base64.b32decode(value.strip(), casefold=True)
        except Exception:
            return None
        for name in ("utf-8", "gb18030"):
            try:
                return data.decode(name)
            except UnicodeDecodeError:
                continue
        return data.decode("utf-8", errors="replace")

    def _decode_field(self, raw, mode: str):
        if raw is None:
            return ""
        if mode == "plain":
            return raw
        decoded = self._b32_decode(raw)
        return decoded if decoded is not None else raw

    # ------------------------------------------------------------------ 主逻辑
    def handle(self, *args, **options):
        path = options["file"]
        table = options["table"]
        decode_mode = options["decode"]
        limit = options["limit"]

        try:
            text = self._read_text(path, options["input_charset"])
        except FileNotFoundError:
            raise CommandError(f"找不到文件：{path}")

        matches = [
            m for m in _INSERT_RE.finditer(text)
            if m.group("table").lower() == table.lower()
        ]
        if not matches:
            raise CommandError(
                f"文件里没找到表 {table} 的 INSERT 语句。可用 --table 覆盖；"
                f"文件里的建表：{sorted(set(re.findall(r'CREATE TABLE `([^`]+)`', text)))}"
            )

        titles, categories, contents = [], [], []
        rows = 0
        for m in matches:
            tuples = self._split_top_level(m.group("body"))
            for tuple_body in tuples:
                fields = self._split_fields(tuple_body)
                if len(fields) < 3:
                    continue  # 列数不符的行直接跳过
                title = self._decode_field(fields[0], decode_mode).strip()
                category = self._decode_field(fields[1], decode_mode).strip()
                content = self._decode_field(fields[2], decode_mode)
                rows += 1
                titles.append(title)
                categories.append(category)
                contents.append(content)

        # 统计（分类分布给 dry-run 参考）
        from collections import Counter
        cat_counter = Counter(c for c in categories if c)

        self.stdout.write(f"[解析] 数据行 {rows} 行，分类 {len(cat_counter)} 个，"
                          f"TOP10：{cat_counter.most_common(10)}")

        if options["dry_run"]:
            sample = [t for t in titles if t][:5]
            self.stdout.write(self.style.SUCCESS(f"[dry-run] 前 5 条标题：{sample}（未写入）"))
            return

        # 先建分类
        cat_name_to_pk = {}
        created_cat = 0
        for name in cat_counter:
            if not name:
                continue
            category, created = Category.objects.get_or_create(name=name[:64])
            cat_name_to_pk[name] = category.pk
            created_cat += 1 if created else 0

        # 再导文章
        created_posts = skipped = 0
        fallback_time = timezone.now()
        total = len(titles)
        for idx in range(total):
            title = titles[idx]
            content = contents[idx]
            category_name = categories[idx]
            if limit and created_posts >= limit:
                break
            if not title:
                skipped += 1
                continue
            if Post.objects.filter(title=title, content_md=content).exists():
                skipped += 1
                continue
            Post.objects.create(
                title=title[:200],
                content_md=content,
                category_id=cat_name_to_pk.get(category_name),
                published_at=fallback_time,
                views=0,
                likes=0,
            )
            created_posts += 1

        self.stdout.write(self.style.SUCCESS(
            f"导入完成：新增 {created_posts} 篇，跳过 {skipped} 篇（重复/无标题）；"
            f"新建分类 {created_cat} 个，现库分类 {Category.objects.count()} 个"
        ))
