from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from blog.models import Image


class Command(BaseCommand):
    help = "清理孤儿图片（未被任何文章正文引用、超过保留期的上传图片），删除记录和物理文件"

    def add_arguments(self, parser):
        parser.add_argument(
            "--grace-days",
            type=int,
            default=7,
            help="保留天数：上传后超过该天数仍无归属的图片才会被删除（默认 7 天）",
        )
        parser.add_argument("--dry-run", action="store_true", help="只列出待清理项，不真正删除")

    def handle(self, *args, **options):
        grace_days = options["grace_days"]
        cutoff = timezone.now() - timedelta(days=grace_days)
        orphans = Image.objects.filter(post__isnull=True, uploaded_at__lt=cutoff)
        total = orphans.count()

        if total == 0:
            self.stdout.write(self.style.SUCCESS("没有需要清理的孤儿图片"))
            return

        if options["dry_run"]:
            self.stdout.write(f"[dry-run] 待清理孤儿图片 {total} 个：")
            for image in orphans:
                self.stdout.write(f"  - {image.file.name}（上传于 {image.uploaded_at:%Y-%m-%d %H:%M}）")
            return

        deleted = 0
        for image in orphans:
            file = image.file
            try:
                if file and file.storage.exists(file.name):
                    file.storage.delete(file.name)
            except Exception as exc:  # 文件系统异常不应中断清理
                self.stderr.write(f"删除文件失败 {file.name}: {exc}")
            image.delete()  # Image.post_delete 信号会尝试删物理文件，前面已删则跳过
            deleted += 1

        self.stdout.write(self.style.SUCCESS(f"已清理 {deleted}/{total} 个孤儿图片（保留期 {grace_days} 天）"))
