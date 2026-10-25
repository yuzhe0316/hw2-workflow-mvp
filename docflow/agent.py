"""Agent 基类。

每个节点实现 handle(message, state)，返回一条回复消息，返回 None 表示结束。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from .message import Message
from .state import SharedState


class AgentError(RuntimeError):
    """Agent 处理失败时抛出，引擎会记录失败原因并中止流程。"""


class Agent(ABC):
    """Workflow 节点基类。"""

    name: str = "agent"
    description: str = ""

    def __init__(self, name: Optional[str] = None, description: Optional[str] = None) -> None:
        if name:
            self.name = name
        if description:
            self.description = description

    @abstractmethod
    def handle(self, message: Message, state: SharedState) -> Optional[Message]:
        """处理一条消息并返回回复；返回 ``None`` 表示不再继续。"""

    # ---------- 供子类使用的工具方法 ----------
    def _emit(self, state: SharedState, text: str, **data: Any) -> None:
        """记录一条 Agent 内部事件（会出现在日志和 trace 里）。"""
        state.record({"agent": self.name, "kind": "agent", "text": text, **data})

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return f"<{type(self).__name__} name={self.name!r}>"


def describe_agents(agents: Dict[str, Agent]) -> str:
    """生成 Agent 清单文本，供 CLI ``agents`` 子命令使用。"""
    lines = []
    for name in sorted(agents):
        agent = agents[name]
        lines.append(f"- {name:<12} {agent.description or type(agent).__name__}")
    return "\n".join(lines)
