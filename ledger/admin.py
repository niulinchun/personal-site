from django.contrib import admin

from ledger.models import LedgerCategory, Record


@admin.register(LedgerCategory)
class LedgerCategoryAdmin(admin.ModelAdmin):
    """分类管理在这里增删改。"""
    list_display = ["id", "name", "type", "record_count"]
    list_filter = ["type"]
    search_fields = ["name"]

    @admin.display(description="笔数")
    def record_count(self, obj):
        return obj.records.count()


@admin.register(Record)
class RecordAdmin(admin.ModelAdmin):
    list_display = ["id", "type", "category", "amount", "note", "record_date"]
    list_filter = ["type", "category", "record_date"]
    search_fields = ["note"]
    date_hierarchy = "record_date"
    show_full_result_count = False
