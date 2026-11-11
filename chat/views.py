"""
chat 视图。整个模块（页面 + API）都需要 admin 登录（LOGIN_URL=admin 登录页）。

SSE 流式实现：
- POST /chat/api/conversations/<id>/messages/  发送用户消息，返回
  StreamingHttpResponse(content_type="text/event-stream")
- 后端用 httpx 流式读上游，逐行解析后以 `data: {...}\n\n` 转发
- 前端 EventSource 不支持 POST，故用 fetch + reader 手动解析 SSE
"""
import json
import logging

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from chat.llm_client import LLMError, stream_chat
from chat.models import Conversation, Message

logger = logging.getLogger(__name__)

# 发送给上游的历史消息条数上限（控制 token 消耗）
HISTORY_LIMIT = 30

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",  # nginx 配置之外的兜底
}


def _msg_payload(message: Message):
    return {
        "id": message.id,
        "role": message.role,
        "content": message.content,
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
    conversation.delete()  # Message 级联删除
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
    解析发消息请求体：content + model + thinking（思考深度）。
    返回 (content, model, thinking)；JSON 解析失败返回 None。
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
    return content, model, thinking


@login_required
@require_http_methods(["POST"])
def api_message_stream(request, pk):
    """
    发送一条用户消息并流式返回助手回答。

    请求体（JSON）：{"content": str, "model": 可选, "thinking": 可选 low|high|max}

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
    content, model, thinking = payload
    if not content:
        return JsonResponse({"error": "消息不能为空"}, status=400)
    if len(content) > 8000:
        return JsonResponse({"error": "单条消息最多 8000 字"}, status=400)
    if model and model not in settings.LLM_MODELS:
        return JsonResponse({"error": "不支持的模型：" + model}, status=400)
    if thinking and thinking not in THINKING_LEVELS:
        return JsonResponse({"error": "思考深度只支持 low / high / max"}, status=400)

    Message.objects.create(conversation=conversation, role=Message.ROLE_USER, content=content)

    # 自动取标题：首条用户消息前 24 字
    if conversation.title == "新的对话":
        conversation.title = content[:24]
        conversation.save(update_fields=["title", "updated_at"])
        conversation.refresh_from_db(fields=["title"])

    # 历史消息只保留最近 HISTORY_LIMIT 条，控制 token
    recent = list(conversation.messages.order_by("-id").values("role", "content")[:HISTORY_LIMIT])
    recent.reverse()
    history = [{"role": m["role"], "content": m["content"]} for m in recent]

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
