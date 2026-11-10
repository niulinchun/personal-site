from django.apps import AppConfig


class BlogConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "blog"
    verbose_name = "博客"

    def ready(self):
        # 注册数据信号：删除文章时清理关联图片文件
        from blog import signals  # noqa: F401
