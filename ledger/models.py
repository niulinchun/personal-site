from django.core.validators import MinValueValidator
from django.db import models
from django.db import models
from django.utils import timezone


class LedgerCategory(models.Model):
    """收支分类：分类管理在 Django admin 操作。"""

    class Type(models.TextChoices):
        INCOME = "income", "收入"
        EXPENSE = "expense", "支出"

    name = models.CharField("名称", max_length=64)
    type = models.CharField("类型", max_length=8, choices=Type.choices, default=Type.EXPENSE)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        verbose_name = "收支分类"
        verbose_name_plural = "收支分类"
        ordering = ["type", "name"]
        constraints = [
            models.UniqueConstraint(fields=["name", "type"], name="unique_category_name_type"),
        ]

    def __str__(self):
        return f"{self.name}（{self.get_type_display()}）"


class Record(models.Model):
    """一笔流水：收入或支出。"""

    type = models.CharField(
        "类型", max_length=8, choices=LedgerCategory.Type.choices, default=LedgerCategory.Type.EXPENSE
    )
    category = models.ForeignKey(
        LedgerCategory,
        verbose_name="分类",
        on_delete=models.PROTECT,
        related_name="records",
    )
    amount = models.DecimalField("金额", max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    note = models.CharField("备注", max_length=200, blank=True, default="")
    record_date = models.DateField("记账日期", default=timezone.localdate)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        verbose_name = "记账流水"
        verbose_name_plural = "记账流水"
        ordering = ["-record_date", "-id"]

    def __str__(self):
        return f"{self.get_type_display()} {self.amount} {self.category.name if self.category else '-'}"

    def save(self, *args, **kwargs):
        # 类型跟随所选分类，避免两者不一致
        if self.category:
            self.type = self.category.type
        super().save(*args, **kwargs)
