"""项目根 URL：/admin/ 后台 + 三个模块 + 开发期媒体文件直出。"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    path("", RedirectView.as_view(url="/blog/", permanent=False)),
    path("admin/", admin.site.urls),
    path("blog/", include("blog.urls")),
    path("chat/", include("chat.urls")),
    path("ledger/", include("ledger.urls")),
]

# 开发环境 / 生产由 nginx 直接服务媒体文件，无需 Django 参与
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# 页面标题
admin.site.site_header = "个人网站后台"
admin.site.site_title = "个人网站后台"
admin.site.index_title = "内容管理"
