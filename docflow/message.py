"""消息和消息总线。

Agent 之间不直接调用，只传 Message。MessageBus 记录所有消息，方便回放。
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

# 常用 topic 常量，避免各处拼写不一致
START = "workflow.start"
DONE = "workflow.done"
HANDOFF = "workflow.handoff"


@dataclass
class Message:
    """Agent 之间传递的一条消息。

    Attributes:
        topic: 消息主题，路由和日志都依赖它。
        sender: 发送方 Agent 名称，``workflow`` 表示引擎本身。
        recipient: 接收方 Agent 名称。
        payload: 结构化数据，约定为 JSON 可序列化的字典。
        id: 短消息 id，用于把回复和请求关联起来。
        reply_to: 若本条是回复，记录原消息 id。
    """

    topic: str
    sender: str
    recipient: str
    payload: Dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    reply_to: Optional[str] = None
    created_at: float = field(default_factory=time.time)

    def reply(self, topic: str, payload: Optional[Dict[str, Any]] = None,
              recipient: Optional[str] = None) -> "Message":
        """生成一条回信，默认回给本条消息的发送方。"""
        return Message(
            topic=topic,
            sender=self.recipient,
            recipient=recipient or self.sender,
            payload=dict(payload or {}),
            reply_to=self.id,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "topic": self.topic,
            "sender": self.sender,
            "recipient": self.recipient,
            "reply_to": self.reply_to,
            "created_at": self.created_at,
            "payload": self.payload,
        }


class MessageBus:
    """极简发布/订阅总线：记录历史 + 可选的主题订阅者。"""

    def __init__(self) -> None:
        self._history: List[Message] = []
        self._subscribers: Dict[str, List[Callable[[Message], None]]] = {}

    def subscribe(self, topic: str, handler: Callable[[Message], None]) -> None:
        self._subscribers.setdefault(topic, []).append(handler)

    def publish(self, message: Message) -> Message:
        """投递消息：先落历史，再通知订阅者（订阅者异常不影响主流程）。"""
        self._history.append(message)
        for handler in self._subscribers.get(message.topic, []):
            try:
                handler(message)
            except Exception:  # noqa: BLE001 - 订阅者属于旁路观测，不应中断流程
                continue
        for handler in self._subscribers.get("*", []):
            try:
                handler(message)
            except Exception:  # noqa: BLE001
                continue
        return message

    @property
    def history(self) -> List[Message]:
        return list(self._history)

    def to_dicts(self) -> List[Dict[str, Any]]:
        return [m.to_dict() for m in self._history]
