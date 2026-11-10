"""
GLM（智谱）OpenAI 兼容接口的 httpx 流式客户端。

一切配置来自 Django settings（读取 .env）：
- LLM_BASE_URL  默认 https://open.bigmodel.cn/api/paas/v4/
- LLM_API_KEY
- LLM_MODEL     默认 glm-5.3
以后换模型 / 换供应商只改 .env，不动代码。
"""
import json
import logging

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)

STREAM_TIMEOUT = httpx.Timeout(
    None,  # 关闭总超时
    connect=15.0,
    read=300.0,  # 与 nginx /chat 的 proxy_read_timeout 对齐
    write=30.0,
)


class LLMError(Exception):
    """上游接口错误（含 HTTP 层错误与流中断）。"""


class LLMNotConfigured(LLMError):
    """没配 LLM_API_KEY。"""


def _endpoints():
    base_url = (settings.LLM_BASE_URL or "").rstrip("/")
    if not base_url:
        raise LLMNotConfigured("LLM_BASE_URL 未配置")
    if base_url.endswith("/chat/completions"):
        url = base_url
    else:
        url = base_url + "/chat/completions"
    return url


def stream_chat(messages):
    """
    调用 OpenAI 兼容 /chat/completions（stream=True），
    逐条 yield 内容增量（str）。

    messages：[{"role": "user"|"assistant", "content": str}, ...]
    出错抛 LLMError；调用方负责在流式响应里把错误转给前端。
    """
    api_key = (settings.LLM_API_KEY or "").strip()
    if not api_key:
        raise LLMNotConfigured("未配置 LLM_API_KEY，请在 .env 中设置后重启")

    payload = {
        "model": settings.LLM_MODEL or "glm-5.3",
        "messages": list(messages),
        "stream": True,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }

    url = _endpoints()
    try:
        with httpx.Client(timeout=STREAM_TIMEOUT) as client:
            with client.stream("POST", url, json=payload, headers=headers) as resp:
                if resp.status_code != 200:
                    body = resp.read()
                    snippet = body.decode("utf-8", errors="replace")[:300]
                    logger.warning("LLM 上游返回 %s：%s", resp.status_code, snippet)
                    raise LLMError(f"上游接口返回 {resp.status_code}：{snippet}")

                for line in resp.iter_lines():
                    if not line:
                        continue
                    line = line.strip()
                    if not line.startswith("data:"):
                        continue
                    data = line[len("data:") :].strip()
                    if not data or data == "[DONE]":
                        continue
                    try:
                        chunk = json.loads(data)
                    except ValueError:
                        continue
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    content = delta.get("content")
                    if content:
                        yield content
    except LLMError:
        raise
    except httpx.HTTPError as exc:
        raise LLMError(f"连接上游失败：{exc}") from exc
