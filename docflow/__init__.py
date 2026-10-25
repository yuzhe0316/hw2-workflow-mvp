"""docflow：一个 3 Agent 协作的"代码 → 文档"Workflow MVP。"""

from __future__ import annotations

__version__ = "0.1.0"

from .agent import Agent, AgentError  # noqa: E402
from .message import Message, MessageBus  # noqa: E402
from .pipeline import DEFAULT_PIPELINE, REGISTRY, build_workflow  # noqa: E402
from .state import SharedState  # noqa: E402
from .workflow import END, Edge, Workflow  # noqa: E402

__all__ = [
    "Agent",
    "AgentError",
    "Message",
    "MessageBus",
    "SharedState",
    "Edge",
    "Workflow",
    "END",
    "build_workflow",
    "DEFAULT_PIPELINE",
    "REGISTRY",
    "__version__",
]
