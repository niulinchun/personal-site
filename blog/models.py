"""
blog 数据模型：文章 / 分类 / 评论 / 上传图片。

图片文件名使用 UUID + 上传年月路径，移动文章时不受影响，
每篇文章删除时仅删除自己引用的图片，互不误伤。
"""
import os
import uuid

from django.db import models
from django.utils import timezone


def image_upload_to(instance, filename: str) -> str:
    """ImageField 上传路径：uploads/YYYY/MM/<uuid>.<ext>（按日期分目录，UUID 命名）。"""
    ext = os.path.splitext(filename)[1][:10].lower()
    now = timezone.localdate()
    return os.path.join(
        "uploads",
        f"{now:%Y}",
        f"{now:%m}",
        f"{uuid.uuid4().hex}{ext}",
    ).replace("\\", "/")


class Category(models.Model):
    name = models.CharField("名称", max_length=64, unique=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        verbose_name = "文章分类"
        verbose_name_plural = "文章分类"
        ordering = ["created_at", "id"]

    def __str__(self):
        return self.name


class Post(models.Model):
    title = models.CharField("标题", max_length=200)
    category = models.ForeignKey(
        Category,
        verbose_name="分类",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="posts",
    )
    content_md = models.TextField("正文（Markdown）", blank=True, default="")
    published_at = models.DateTimeField("发布时间", default=timezone.now)
    views = models.PositiveIntegerField("浏览量", default=0)
    likes = models.PositiveIntegerField("点赞数", default=0)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        verbose_name = "文章"
        verbose_name_plural = "文章"
        ordering = ["-published_at", "-id"]

    def __str__(self):
        return self.title


class Comment(models.Model):
    post = models.ForeignKey(Post, verbose_name="文章", on_delete=models.CASCADE, related_name="comments")
    nickname = models.CharField("昵称", max_length=32)
    content = models.TextField("内容")
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        verbose_name = "评论"
        verbose_name_plural = "评论"
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"{self.nickname}：{self.content[:20]}"


class Image(models.Model):
    file = models.ImageField("图片", upload_to=image_upload_to)
    uploaded_at = models.DateTimeField("上传时间", auto_now_add=True)
    post = models.ForeignKey(
        Post,
        verbose_name="所属文章",
        # Post 删除时级联删除 Image 记录；Image.post_delete 信号删除物理文件
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        verbose_name = "上传图片"
        verbose_name_plural = "上传图片"

    def __str__(self):
        return self.file.name
