from django.contrib import admin

from blog.models import Category, Comment, Image, Post


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "created_at", "post_count"]
    search_fields = ["name"]

    @admin.display(description="文章数")
    def post_count(self, obj):
        return obj.posts.count()


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ["id", "title", "category", "published_at", "views", "likes"]
    list_filter = ["category"]
    search_fields = ["title", "content_md"]
    date_hierarchy = "published_at"
    show_full_result_count = False


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    """评论管理：不想要的评论在这里删除。"""
    list_display = ["id", "post", "nickname", "short_content", "created_at"]
    list_filter = ["post__category"]
    search_fields = ["nickname", "content", "post__title"]
    show_full_result_count = False

    @admin.display(description="内容")
    def short_content(self, obj):
        content = obj.content or ""
        return content[:30] + ("…" if len(content) > 30 else "")


@admin.register(Image)
class ImageAdmin(admin.ModelAdmin):
    """图片归属跟踪（只读列表，便于排查孤儿图片）。"""
    list_display = ["id", "file", "post", "uploaded_at"]
    list_filter = ["post", "uploaded_at"]
    search_fields = ["file"]
    show_full_result_count = False

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
