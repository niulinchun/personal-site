"""ASGI 入口。生产用 uvicorn 部署，SSE 流式聊天走本文件。"""
import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_asgi_application()
