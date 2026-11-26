"""通用 Webhook 机器人适配器。"""

import hashlib
import hmac
import json
import time
from dataclasses import dataclass


@dataclass
class VerifiedRequest:
    """已通过验签的 Webhook 请求。"""

    event_id: str


@dataclass
class NormalizedEvent:
    """平台无关的机器人消息。"""

    event_id: str
    sender_id: str
    chat_id: str
    chat_type: str
    text: str


class WebhookAdapter:
    """使用 HMAC-SHA256 保护同步 Webhook 问答。"""

    platform = "webhook"

    def verify(self, raw_body: bytes, headers, secret: str) -> VerifiedRequest:
        """校验时间戳、事件 ID 和请求签名。"""
        timestamp = headers.get("x-webhook-timestamp", "")
        event_id = headers.get("x-webhook-event-id", "")
        signature = headers.get("x-webhook-signature", "")
        try:
            timestamp_value = int(timestamp)
        except (TypeError, ValueError):
            raise ValueError("缺少或非法的 Webhook 时间戳") from None
        if abs(int(time.time()) - timestamp_value) > 300:
            raise ValueError("Webhook 时间戳已过期")
        if not event_id or len(event_id) > 128:
            raise ValueError("缺少或非法的 Webhook 事件 ID")
        expected = hmac.new(
            secret.encode("utf-8"),
            f"{timestamp}.".encode("utf-8") + raw_body,
            hashlib.sha256,
        ).hexdigest()
        if not signature or not hmac.compare_digest(expected, signature.lower()):
            raise ValueError("Webhook 签名不正确")
        return VerifiedRequest(event_id=event_id)

    def parse(self, raw_body: bytes) -> NormalizedEvent:
        """解析统一消息字段。"""
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ValueError("Webhook 请求体不是合法 JSON") from None
        if not isinstance(payload, dict):
            raise ValueError("Webhook 请求体必须是对象")
        event_id = str(payload.get("event_id") or "").strip()
        sender_id = str(payload.get("sender_id") or "").strip()
        chat_id = str(payload.get("chat_id") or "").strip()
        chat_type = str(payload.get("chat_type") or "private").strip().lower()
        text = str(payload.get("text") or "").strip()
        if chat_type not in ("private", "group"):
            raise ValueError("chat_type 只支持 private / group")
        if not event_id or len(event_id) > 128:
            raise ValueError("event_id 不能为空且不能超过 128 字符")
        if not sender_id or len(sender_id) > 128:
            raise ValueError("sender_id 不能为空且不能超过 128 字符")
        if not chat_id or len(chat_id) > 128:
            raise ValueError("chat_id 不能为空且不能超过 128 字符")
        if not text or len(text) > 4000:
            raise ValueError("text 不能为空且不能超过 4000 字符")
        return NormalizedEvent(
            event_id=event_id,
            sender_id=sender_id,
            chat_id=chat_id,
            chat_type=chat_type,
            text=text,
        )

    def render(self, reply: str, conversation_id: str) -> dict:
        """生成同步 Webhook 响应。"""
        return {"reply": reply, "conversation_id": conversation_id}
