from django.contrib import admin

from chat.models import Conversation, Message


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    fields = ["role", "content", "created_at"]
    readonly_fields = ["created_at"]
    show_change_link = False


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ["id", "title", "created_at", "updated_at", "message_count"]
    search_fields = ["title"]
    date_hierarchy = "created_at"
    inlines = [MessageInline]
    show_full_result_count = False

    @admin.display(description="消息数")
    def message_count(self, obj):
        return obj.messages.count()


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ["id", "conversation", "role", "short_content", "created_at"]
    list_filter = ["role"]
    search_fields = ["content", "conversation__title"]
    show_full_result_count = False

    @admin.display(description="内容")
    def short_content(self, obj):
        content = obj.content or ""
        return content[:40] + ("…" if len(content) > 40 else "")
