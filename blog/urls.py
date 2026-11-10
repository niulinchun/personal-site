from django.urls import path

from blog import views

app_name = "blog"

urlpatterns = [
    path("", views.blog_home, name="index"),
    # JSON API
    path("api/posts/", views.api_post_list, name="api_post_list"),
    path("api/posts/<int:pk>/", views.api_post_detail, name="api_post_detail"),
    path("api/posts/<int:pk>/like/", views.api_post_like, name="api_post_like"),
    path("api/posts/<int:pk>/comments/", views.api_post_comments, name="api_post_comments"),
    path("api/upload/", views.api_upload, name="api_upload"),
    # 文章管理（需登录）
    path("manage/", views.manage_post_list, name="manage"),
    path("manage/new/", views.manage_post_create, name="manage_create"),
    path("manage/<int:pk>/edit/", views.manage_post_edit, name="manage_edit"),
    path("manage/<int:pk>/delete/", views.manage_post_delete, name="manage_delete"),
    # 文章详情页（与首页同布局）。放在最后，避免与上面路径混淆
    path("<int:pk>/", views.blog_post_page, name="post_page"),
]
