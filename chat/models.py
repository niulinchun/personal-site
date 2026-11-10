from django.db import models
from django.utils import timezone


class Conversation(models.Model):
    title = models.CharField("会话标题", max_length=200, default="新的对话")
    created_at = models.DateTimeField("创建时间", default=timezone.now, editable=False)
    updated_at = models.DateTimeField("最近活跃时间", default=timezone.now)

    class Meta:
        verbose_name = "会话"
        verbose_name_plural = "会话"
        ordering = ["-updated_at", "-id"]

    def __str__(self):
        return self.title


class Message(models.Model):
    ROLE_USER = "user"
    ROLE_ASSISTANT = "assistant"

    ROLE_CHOICES = [
        (ROLE_USER, "用户"),
        (ROLE_ASSISTANT, "助手"),
    ]

    conversation = models.ForeignKey(
        Conversation,
        verbose_name="会话",
        on_delete=models.CASCADE,
        related_name="messages",
    )
    role = models.CharField("角色", max_length=16, choices=ROLE_CHOICES)
    content = models.TextField("内容")
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        verbose_name = "消息"
        verbose_name_plural = "消息"
        ordering = ["id"]

    def __str__(self):
        return f"[{self.role}] {self.content[:30]}"
