from django.urls import path

from chat import views

app_name = "chat"

urlpatterns = [
    path("", views.chat_index, name="index"),
    path("api/conversations/", views.api_conversations_dispatch, name="api_conversations"),
    path("api/conversations/create/", views.api_conversation_create, name="api_conversation_create"),
    path(
        "api/conversations/<int:pk>/delete/",
        views.api_conversation_delete,
        name="api_conversation_delete",
    ),
    path(
        "api/conversations/<int:pk>/messages/",
        views.api_message_list,
        name="api_message_list",
    ),
    path(
        "api/conversations/<int:pk>/messages/stream/",
        views.api_message_stream,
        name="api_message_stream",
    ),
]
