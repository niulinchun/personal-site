"""
chat 模块测试：登录边界、会话 CRUD、SSE 流式、标题自动生成、历史落库。
"""
from django.conf import settings
from django.contrib.auth.models import User
from django.test import TestCase
from unittest.mock import patch

from chat.models import Conversation, Message


def _sse_payload(response):
    chunks = b""
    if response.streaming:
        for chunk in response.streaming_content:
            chunks += chunk
    return chunks.decode("utf-8")


class ChatLoginBoundaryTests(TestCase):
    def test_page_requires_login(self):
        resp = self.client.get("/chat/")
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp["Location"].startswith("/admin/login/"))

    def test_apis_require_login(self):
        self.assertEqual(self.client.post("/chat/api/conversations/create/").status_code, 302)
        self.assertEqual(self.client.get("/chat/api/conversations/").status_code, 302)
        self.assertEqual(self.client.delete("/chat/api/conversations/1/delete/").status_code, 302)
        self.assertEqual(self.client.get("/chat/api/conversations/1/messages/").status_code, 302)
        self.assertEqual(
            self.client.post("/chat/api/conversations/1/messages/stream/", data="{}",
                             content_type="application/json").status_code, 302)


class ChatApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("me", "me@example.com", "pass123456")
        self.client.force_login(self.user)

    def test_index_lists_conversations(self):
        Conversation.objects.create(title="测试会话")
        resp = self.client.get("/chat/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "测试会话")

    def test_conversation_create_and_list(self):
        resp = self.client.post("/chat/api/conversations/create/")
        self.assertEqual(resp.status_code, 201, resp.content)
        conv_id = resp.json()["conversation"]["id"]
        conversation = Conversation.objects.get(pk=conv_id)
        self.assertEqual(conversation.title, "新的对话")

        resp = self.client.get("/chat/api/conversations/")
        self.assertEqual(resp.json()["items"][0]["id"], conv_id)

    def test_conversation_delete_cascade_messages(self):
        conversation = Conversation.objects.create()
        Message.objects.create(conversation=conversation, role=Message.ROLE_USER, content="hi")
        resp = self.client.delete(f"/chat/api/conversations/{conversation.pk}/delete/")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Conversation.objects.exists())
        self.assertFalse(Message.objects.exists())

    def test_message_list(self):
        conversation = Conversation.objects.create(title="会话")
        Message.objects.create(conversation=conversation, role=Message.ROLE_USER, content="你好")
        Message.objects.create(conversation=conversation, role=Message.ROLE_ASSISTANT, content="你好！")
        resp = self.client.get(f"/chat/api/conversations/{conversation.pk}/messages/")
        data = resp.json()
        self.assertEqual(len(data["items"]), 2)
        self.assertEqual(data["items"][0]["role"], "user")

    def test_stream_rejects_empty_and_long(self):
        conversation = Conversation.objects.create()
        resp = self.client.post(
            f"/chat/api/conversations/{conversation.pk}/messages/stream/",
            data='{"content": "  "}', content_type="application/json")
        self.assertEqual(resp.status_code, 400)
        resp = self.client.post(
            f"/chat/api/conversations/{conversation.pk}/messages/stream/",
            data='{"content": "%s"}' % ("长" * 8001), content_type="application/json")
        self.assertEqual(resp.status_code, 400)

    def test_stream_requires_login(self):
        self.client.logout()
        conversation = Conversation.objects.create()
        resp = self.client.post(
            f"/chat/api/conversations/{conversation.pk}/messages/stream/",
            data='{"content": "hi"}', content_type="application/json")
        self.assertEqual(resp.status_code, 302)


class ChatStreamingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("me", "me@example.com", "pass123456")
        self.client.force_login(self.user)

    @patch("chat.views.stream_chat")
    def test_stream_success_saves_assistant_reply(self, mock_stream):
        mock_stream.return_value = iter(
            [("content", "你好"), ("content", "，"), ("content", "世界")]
        )
        conversation = Conversation.objects.create(title="新的对话")

        resp = self.client.post(
            f"/chat/api/conversations/{conversation.pk}/messages/stream/",
            data='{"content": "打个招呼"}', content_type="application/json")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"].split(";")[0], "text/event-stream")
        self.assertEqual(resp["Cache-Control"], "no-cache")

        payload = _sse_payload(resp)
        self.assertIn('"delta": "你好"', payload)
        self.assertIn('"delta": "，"', payload)
        self.assertIn('"delta": "世界"', payload)
        self.assertIn('"done": true', payload)

        # 消息落库：user + assistant 各一条
        messages = list(conversation.messages.order_by("id"))
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0].role, "user")
        self.assertEqual(messages[1].role, "assistant")
        self.assertEqual(messages[1].content, "你好，世界")

        # 首条提问自动生成标题
        conversation.refresh_from_db()
        self.assertEqual(conversation.title, "打个招呼")

    @patch("chat.views.stream_chat")
    def test_stream_llm_error_yields_error_event(self, mock_stream):
        from chat.llm_client import LLMError

        def raise_error(*args, **kwargs):
            raise LLMError("上游炸了")

        mock_stream.side_effect = raise_error
        conversation = Conversation.objects.create(title="新的对话")
        resp = self.client.post(
            f"/chat/api/conversations/{conversation.pk}/messages/stream/",
            data='{"content": "hi"}', content_type="application/json")
        self.assertEqual(resp.status_code, 200)
        payload = _sse_payload(resp)
        self.assertIn("上游炸了", payload)
        self.assertIn('"done": true', payload)
        self.assertEqual(conversation.messages.count(), 1)  # 只有 user 的那条

    def test_stream_not_configured_returns_error_event(self):
        conversation = Conversation.objects.create(title="新的对话")
        with patch.object(settings, "LLM_API_KEY", ""):
            resp = self.client.post(
                f"/chat/api/conversations/{conversation.pk}/messages/stream/",
                data='{"content": "hi"}', content_type="application/json")
        payload = _sse_payload(resp)
        self.assertIn("LLM_API_KEY", payload)
        self.assertIn('"done": true', payload)

    @patch("chat.views.stream_chat")
    def test_history_sent_to_upstream(self, mock_stream):
        mock_stream.return_value = iter([("content", "好")])
        conversation = Conversation.objects.create(title="旧会话")
        Message.objects.create(conversation=conversation, role=Message.ROLE_USER, content="第一问")
        Message.objects.create(conversation=conversation, role=Message.ROLE_ASSISTANT, content="第一答")

        resp = self.client.post(
            f"/chat/api/conversations/{conversation.pk}/messages/stream/",
            data='{"content": "第二问"}', content_type="application/json")

        payload = _sse_payload(resp)
        self.assertEqual(resp.status_code, 200, payload)

        args, kwargs = mock_stream.call_args
        history = args[0]
        self.assertEqual(history[0], {"role": "user", "content": "第一问"})
        self.assertEqual(history[1], {"role": "assistant", "content": "第一答"})
        self.assertEqual(history[-1], {"role": "user", "content": "第二问"})


class ChatModelThinkingTests(TestCase):
    """模型选择 + 思考深度档位。"""

    def setUp(self):
        self.user = User.objects.create_superuser("me", "me@example.com", "pass123456")
        self.client.force_login(self.user)
        self.conversation = Conversation.objects.create(title="会话")

    def _post(self, body):
        return self.client.post(
            f"/chat/api/conversations/{self.conversation.pk}/messages/stream/",
            data=body, content_type="application/json")

    def test_index_renders_model_options(self):
        resp = self.client.get("/chat/")
        self.assertEqual(resp.status_code, 200)
        for model in settings.LLM_MODELS:
            self.assertContains(resp, model)

    def test_rejects_model_outside_whitelist(self):
        resp = self._post('{"content": "hi", "model": "glm-9.9-evil"}')
        self.assertEqual(resp.status_code, 400)
        self.assertIn("不支持的模型", resp.json()["error"])

    def test_rejects_bad_thinking_level(self):
        resp = self._post('{"content": "hi", "thinking": "turbo"}')
        self.assertEqual(resp.status_code, 400)
        self.assertIn("low / high / max", resp.json()["error"])

    @patch("chat.views.stream_chat")
    def test_model_and_effort_forwarded_to_upstream(self, mock_stream):
        mock_stream.return_value = iter([("content", "好")])
        resp = self._post(
            '{"content": "hi", "model": "glm-5.3-flashx", "thinking": "max"}')
        self.assertEqual(resp.status_code, 200, _sse_payload(resp))
        kwargs = mock_stream.call_args.kwargs
        self.assertEqual(kwargs["model"], "glm-5.3-flashx")
        self.assertEqual(kwargs["reasoning_effort"], "max")

    @patch("chat.views.stream_chat")
    def test_defaults_when_model_and_thinking_omitted(self, mock_stream):
        mock_stream.return_value = iter([("content", "好")])
        resp = self._post('{"content": "hi"}')
        self.assertEqual(resp.status_code, 200, _sse_payload(resp))
        kwargs = mock_stream.call_args.kwargs
        self.assertIsNone(kwargs["model"])  # 视图不传 → llm_client 用 settings.LLM_MODEL
        self.assertIsNone(kwargs["reasoning_effort"])

    @patch("chat.views.stream_chat")
    def test_thinking_events_forwarded_but_not_saved(self, mock_stream):
        mock_stream.return_value = iter(
            [("reasoning", "先想一下"), ("reasoning", "…"), ("content", "答案是 4")]
        )
        resp = self._post('{"content": "2+2=?", "thinking": "max"}')
        self.assertEqual(resp.status_code, 200)
        payload = _sse_payload(resp)
        self.assertIn('"thinking"', payload)
        self.assertIn("先想一下", payload)
        self.assertIn('"delta"', payload)
        self.assertIn("答案是 4", payload)
        # 落库只存正文（思考链不进数据库）
        contents = [m.content for m in self.conversation.messages.order_by("id")]
        self.assertEqual(contents, ["2+2=?", "答案是 4"])
