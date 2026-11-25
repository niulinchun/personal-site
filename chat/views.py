"""
chat 视图。整个模块（页面 + API）都需要 admin 登录（LOGIN_URL=admin 登录页）。

SSE 流式实现：
- POST /chat/api/conversations/<id>/messages/  发送用户消息，返回
  StreamingHttpResponse(content_type="text/event-stream")
- 后端用 httpx 流式读上游，逐行解析后以 `data: {...}\n\n` 转发
- 前端 EventSource 不支持 POST，故用 fetch + reader 手动解析 SSE

截图问答：
- POST /chat/api/image/upload/   上传截图（multipart，字段 file）
- DELETE /chat/api/image/delete/  取消预览时删除刚上传的图
- 发消息请求体可带 {"image": "/media/uploads/chat/..."}，历史组装时把
  最近带图的用户消息转为 OpenAI 多模态 content 数组发给上游。
"""
import json
import logging
import mimetypes
import os
import re
from base64 import b64encode
from uuid import uuid4

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.files.storage import default_storage
from django.http import JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from chat.llm_client import LLMError, stream_chat
from chat.models import Conversation, Message

logger = logging.getLogger(__name__)

# 发送给上游的历史消息条数上限（控制 token 消耗）
HISTORY_LIMIT = 30

# 历史里最多携带几张图片（base64 图片很占 token，老图只保留文字占位）
HISTORY_IMAGE_LIMIT = 4

# 上传图片限制（截图经过前端 canvas 压缩，一般几百 KB）
MAX_IMAGE_BYTES = 10 * 1024 * 1024
ALLOWED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}

# 只允许引用本应用自己生成的聊天图片（防路径穿越 / 防外链任意文件）
CHAT_IMAGE_RE = re.compile(r"^/media/uploads/chat/\d{4}/\d{2}/[0-9a-f]{32}\.[a-z]+$")

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",  # nginx 配置之外的兜底
}

IMG_PLACEHOLDER = "[图片]"  # 超出 HISTORY_IMAGE_LIMIT 的老图，发给上游的文字占位


def _msg_payload(message: Message):
    return {
        "id": message.id,
        "role": message.role,
        "content": message.content,
        "image": message.image.url if message.image else "",
        "created_at": message.created_at.strftime("%Y/%m/%d %H:%M"),
    }


def _conv_payload(conversation: Conversation):
    return {
        "id": conversation.id,
        "title": conversation.title,
        "updated_at": conversation.updated_at.strftime("%Y/%m/%d %H:%M"),
    }


# ---------------------------------------------------------------------------
# 页面
# ---------------------------------------------------------------------------


@login_required
def chat_index(request):
    conversations = Conversation.objects.all()[:200]
    return render(
        request,
        "chat/index.html",
        {
            "conversations": conversations,
            "llm_models": settings.LLM_MODELS,
            "llm_default": settings.LLM_MODEL,
        },
    )


# ---------------------------------------------------------------------------
# 会话管理 API
# ---------------------------------------------------------------------------


@login_required
@require_http_methods(["GET", "POST"])
def api_conversations_dispatch(request):
    """/chat/api/conversations/ 入口：GET=会话列表，POST=新建。"""
    if request.method == "GET":
        items = [_conv_payload(c) for c in Conversation.objects.all()[:200]]
        return JsonResponse({"items": items})
    conversation = Conversation.objects.create(title="新的对话")
    return JsonResponse({"conversation": _conv_payload(conversation)}, status=201)


@login_required
@require_http_methods(["POST"])
def api_conversation_create(request):
    conversation = Conversation.objects.create(title="新的对话")
    return JsonResponse({"conversation": _conv_payload(conversation)}, status=201)


@login_required
@require_http_methods(["DELETE"])
def api_conversation_delete(request, pk):
    conversation = get_object_or_404(Conversation, pk=pk)
    # 级联删除消息前，先删掉消息附图的真实文件
    for m in conversation.messages.exclude(image="").only("image"):
        if m.image:
            m.image.delete(save=False)
    conversation.delete()  # Message 级联删除
    return JsonResponse({"ok": True})


# ---------------------------------------------------------------------------
# 截图上传 / 取消
# ---------------------------------------------------------------------------


@login_required
@require_http_methods(["POST"])
def api_image_upload(request):
    """
    上传聊天截图（multipart，字段 file）。
    校验同 blog 上传：content-type 必须为图片、扩展名白名单、≤10MB。
    文件名统一重命名为 uuid.hex（不可预测），存 uploads/chat/YYYY/MM/。
    返回 {"url": "/media/uploads/chat/YYYY/MM/<uuid>.<ext>"}。
    """
    upload = request.FILES.get("file")
    if upload is None:
        return JsonResponse({"error": "未收到文件（字段名 file）"}, status=400)

    ctype = (upload.content_type or "").lower()
    name = upload.name or ""
    ext = os.path.splitext(name)[1].lower()

    if not ctype.startswith("image/"):
        return JsonResponse({"error": "仅支持上传图片文件"}, status=400)
    if ext and ext not in ALLOWED_IMAGE_EXTS:
        return JsonResponse({"error": "不支持的扩展名：" + ext}, status=400)
    if upload.size > MAX_IMAGE_BYTES:
        return JsonResponse({"error": "图片不能超过 10MB"}, status=400)

    # 用 content-type 修正扩展名（前端 canvas 压缩后统一为 jpeg/png）
    if not ext:
        ext = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}.get(ctype, ".png")

    from django.utils import timezone
    path = default_storage.save(
        f"uploads/chat/{timezone.now():%Y/%m}/{uuid4().hex}{ext}", upload
    )
    return JsonResponse({"url": default_storage.url(path)})


@login_required
@require_http_methods(["DELETE"])
def api_image_delete(request):
    """
    取消预览时删除刚上传的图。请求体 JSON：{"url": "/media/uploads/chat/..."}。
    只接受本应用生成的聊天图片路径（CHAT_IMAGE_RE），否则 400。
    """
    try:
        data = json.loads(request.body.decode("utf-8") or "{}")
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"error": "请求体不是合法 JSON"}, status=400)
    url = (data.get("url") or "").strip()
    if not CHAT_IMAGE_RE.match(url):
        return JsonResponse({"error": "非法图片路径"}, status=400)
    name = url[len("/media/"):]  # media 相对路径
    if default_storage.exists(name):
        default_storage.delete(name)
    return JsonResponse({"ok": True})


@login_required
@require_http_methods(["GET"])
def api_message_list(request, pk):
    conversation = get_object_or_404(Conversation, pk=pk)
    return JsonResponse(
        {
            "conversation": _conv_payload(conversation),
            "items": [_msg_payload(m) for m in conversation.messages.all()[:500]],
        }
    )


# ---------------------------------------------------------------------------
# SSE 流式问答
# ---------------------------------------------------------------------------


# 思考深度档位（GLM 深度思考：low=快速 / high=标准 / max=深度）
THINKING_LEVELS = ("low", "high", "max")


def _read_payload(request):
    """
    解析发消息请求体：content + model + thinking（思考深度）+ image（附图 URL）。
    返回 (content, model, thinking, image)；JSON 解析失败返回 None。
    """
    if request.content_type and "json" in request.content_type:
        try:
            data = json.loads(request.body.decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError):
            return None
    else:
        data = request.POST
    content = (data.get("content") or "").strip()
    model = (data.get("model") or "").strip()
    thinking = (data.get("thinking") or "").strip()
    image = (data.get("image") or "").strip()
    return content, model, thinking, image


def _image_data_url(path):
    """读 media 里的图片文件转 base64 data URL（发给上游用，不暴露公网地址）。"""
    try:
        with default_storage.open(path, "rb") as fh:
            raw = fh.read()
    except (OSError, ValueError):
        return None
    mime = mimetypes.guess_type(path)[0] or "image/png"
    if not mime.startswith("image/"):
        mime = "image/png"
    return f"data:{mime};base64,{b64encode(raw).decode()}"


def _build_upstream_history(conversation):
    """
    组装发给上游的历史：最近 HISTORY_LIMIT 条；带图的用户消息转为
    OpenAI 多模态 content 数组，但最多带 HISTORY_IMAGE_LIMIT 张图，
    更老的图降级为文字占位（控制 token）。
    """
    recent = list(
        conversation.messages.order_by("-id").values("id", "role", "content", "image")[:HISTORY_LIMIT]
    )
    recent.reverse()

    # 从最新往旧数，第 HISTORY_IMAGE_LIMIT 张之后的图不携带
    image_budget = HISTORY_IMAGE_LIMIT
    image_paths = {}
    for m in recent:
        if m["image"] and m["role"] == Message.ROLE_USER and image_budget > 0:
            image_budget -= 1
            image_paths[m["id"]] = m["image"]

    history = []
    for m in recent:
        path = image_paths.get(m["id"])
        if path:
            data_url = _image_data_url(path)
            if data_url:
                history.append({
                    "role": m["role"],
                    "content": [
                        {"type": "text", "text": m["content"] or IMG_PLACEHOLDER},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                })
                continue
        text = m["content"]
        if m["image"] and m["role"] == Message.ROLE_USER:
            # 超出图片预算的老图：文字前打 [图片] 占位标记，避免上游误解
            text = f"{IMG_PLACEHOLDER} {text}".strip() if text else IMG_PLACEHOLDER
        history.append({"role": m["role"], "content": text})
    return history


@login_required
@require_http_methods(["POST"])
def api_message_stream(request, pk):
    """
    发送一条用户消息并流式返回助手回答。

    请求体（JSON）：{"content": str, "model": 可选, "thinking": 可选 low|high|max,
                    "image": 可选, "/media/uploads/chat/..." 先经 upload 接口}
    content 和 image 至少有一个；纯图消息 content 可为空。

    SSE 事件格式（每条以 data: 开头、空行结尾）：
      {"delta": "正文增量"}          # 多条
      {"thinking": "思考链增量"}     # 深度思考时的推理过程（max 档常见）
      {"error": "错误信息"}          # 失败时
      {"done": true}                 # 结束标记
    """
    conversation = get_object_or_404(Conversation, pk=pk)
    payload = _read_payload(request)
    if payload is None:
        return JsonResponse({"error": "请求体不是合法 JSON"}, status=400)
    content, model, thinking, image = payload
    if not content and not image:
        return JsonResponse({"error": "消息不能为空"}, status=400)
    if len(content) > 8000:
        return JsonResponse({"error": "单条消息最多 8000 字"}, status=400)
    if model and model not in settings.LLM_MODELS:
        return JsonResponse({"error": "不支持的模型：" + model}, status=400)
    if thinking and thinking not in THINKING_LEVELS:
        return JsonResponse({"error": "思考深度只支持 low / high / max"}, status=400)

    # 附图校验：必须是本应用上传接口生成的聊天图片，且真实存在
    image_name = ""
    if image:
        if not CHAT_IMAGE_RE.match(image):
            return JsonResponse({"error": "非法图片路径"}, status=400)
        image_name = image[len("/media/"):]
        if not default_storage.exists(image_name):
            return JsonResponse({"error": "图片不存在，请重新上传"}, status=400)

    Message.objects.create(
        conversation=conversation,
        role=Message.ROLE_USER,
        content=content,
        image=image_name,
    )

    # 自动取标题：首条消息前 24 字（纯图消息用占位符）
    if conversation.title == "新的对话":
        conversation.title = (content or IMG_PLACEHOLDER)[:24]
        conversation.save(update_fields=["title", "updated_at"])
        conversation.refresh_from_db(fields=["title"])

    # 历史消息只保留最近 HISTORY_LIMIT 条（带图消息转多模态），控制 token
    history = _build_upstream_history(conversation)

    def sse_stream():
        chunks = []
        try:
            yield "retry: 3000\n\n"
            for kind, text in stream_chat(
                history,
                model=model or None,
                reasoning_effort=thinking or None,
            ):
                if kind == "content":
                    chunks.append(text)
                    yield "data: " + json.dumps({"delta": text}, ensure_ascii=False) + "\n\n"
                elif kind == "reasoning":
                    yield "data: " + json.dumps({"thinking": text}, ensure_ascii=False) + "\n\n"
        except LLMError as exc:
            logger.warning("LLM 流式失败：%s", exc)
            yield "data: " + json.dumps({"error": str(exc)}, ensure_ascii=False) + "\n\n"
            yield "data: {\"done\": true}\n\n"
            return
        except Exception:
            logger.exception("SSE 流式未捕获异常")
            yield "data: " + json.dumps({"error": "服务器内部错误"}, ensure_ascii=False) + "\n\n"
            yield "data: {\"done\": true}\n\n"
            return

        full_text = "".join(chunks)
        if full_text:
            Message.objects.create(
                conversation=conversation, role=Message.ROLE_ASSISTANT, content=full_text
            )
        # 更新会话活跃时间，左侧列表排到最上
        conversation.save(update_fields=["updated_at"])
        yield "data: {\"done\": true}\n\n"

    response = StreamingHttpResponse(sse_stream(), content_type="text/event-stream")
    for key, value in SSE_HEADERS.items():
        response[key] = value
    return response
