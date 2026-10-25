"""默认流水线与 Agent 注册表。

新增一个流程节点只需要三步：
1. 写一个 :class:`~docflow.agent.Agent` 子类；
2. 在 ``REGISTRY`` 里登记类型名；
3. 在配置的 ``agents`` / ``edges`` 里加节点和连线。
引擎代码不需要任何改动。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from .agents.analyzer import AnalyzerAgent
from .agents.reviewer import ReviewerAgent
from .agents.writer import WriterAgent
from .message import DONE
from .state import SharedState
from .workflow import END, Workflow

REGISTRY = {
    "analyzer": AnalyzerAgent,
    "writer": WriterAgent,
    "reviewer": ReviewerAgent,
}


def needs_revision(state: SharedState, reply: Any) -> bool:
    """审校未通过 → 回到 writer。"""
    return bool(reply is not None and reply.topic == "review.request_changes")


def approved(state: SharedState, reply: Any) -> bool:
    """审校通过（reviewer 发出 workflow.done）→ 结束。"""
    return bool(reply is not None and reply.topic == DONE)


CONDITIONS = {
    "needs_revision": needs_revision,
    "approved": approved,
}

DEFAULT_PIPELINE: Dict[str, Any] = {
    "name": "code-to-doc",
    "description": "代码 → 分析 → 文档 → 审校（未通过则回写一轮）",
    "start": "analyzer",
    "max_steps": 12,
    "agents": [
        {"name": "analyzer", "type": "analyzer"},
        {"name": "writer", "type": "writer"},
        {"name": "reviewer", "type": "reviewer"},
    ],
    "edges": [
        {"from": "analyzer", "to": "writer"},
        {"from": "writer", "to": "reviewer"},
        {"from": "reviewer", "to": "writer", "when": "needs_revision"},
        {"from": "reviewer", "to": END, "when": "approved"},
    ],
}


def build_workflow(config: Optional[Dict[str, Any]] = None) -> Workflow:
    """用默认配置或外部 JSON 配置构建 Workflow。"""
    return Workflow.from_config(config or DEFAULT_PIPELINE, REGISTRY, CONDITIONS)
