"""Workflow 引擎。

节点是 Agent，连线是 Edge，可以带条件。流程能在代码里搭，也能用 JSON 描述。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Type

from .agent import Agent
from .message import DONE, HANDOFF, Message
from .state import SharedState
from .trace import Trace

END = "__end__"
Condition = Callable[[SharedState, Optional[Message]], bool]


@dataclass
class Edge:
    """一条有向连线；``when`` 为空表示无条件跳转。"""

    source: str
    target: str
    when: Optional[str] = None
    label: str = ""

    def describe(self) -> str:
        if self.target == END:
            target = "结束"
        else:
            target = self.target
        return f"{self.source} → {target}" + (f" [{self.when}]" if self.when else "")


@dataclass
class Step:
    """一次节点执行的记录。"""

    index: int
    agent: str
    topic: str
    reply_topic: Optional[str]
    duration_ms: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "agent": self.agent,
            "request": self.topic,
            "reply": self.reply_topic,
            "duration_ms": round(self.duration_ms, 2),
        }


@dataclass
class RunResult:
    """一次 Workflow 运行的完整结果。"""

    ok: bool
    steps: List[Step] = field(default_factory=list)
    state: Optional[SharedState] = None
    messages: List[Message] = field(default_factory=list)
    error: Optional[str] = None
    duration_ms: float = 0.0

    def summary(self) -> str:
        status = "成功" if self.ok else f"失败（{self.error}）"
        return f"{status}｜{len(self.steps)} 步｜{self.duration_ms:.0f} ms"


class Workflow:
    """顺序执行 + 条件路由的极简 Workflow 引擎。"""

    def __init__(self, name: str, agents: Dict[str, Agent], start: str,
                 edges: Optional[List[Edge]] = None, max_steps: int = 16,
                 conditions: Optional[Dict[str, Condition]] = None,
                 description: str = "") -> None:
        self.name = name
        self.description = description
        self.agents = dict(agents)
        self.start = start
        self.edges: List[Edge] = list(edges or [])
        self.max_steps = max_steps
        self.conditions: Dict[str, Condition] = dict(conditions or {})
        self.validate()

    # ---------- 组装 ----------
    def add_agent(self, agent: Agent) -> "Workflow":
        self.agents[agent.name] = agent
        return self

    def connect(self, source: str, target: str, when: Optional[str] = None,
                label: str = "") -> "Workflow":
        self.edges.append(Edge(source, target, when, label))
        return self

    def validate(self) -> None:
        if self.start not in self.agents:
            raise ValueError(f"起始节点不存在：{self.start}")
        known = set(self.agents) | {END}
        for edge in self.edges:
            if edge.source not in known:
                raise ValueError(f"连线起点未知：{edge.source}")
            if edge.target not in known:
                raise ValueError(f"连线终点未知：{edge.target}")
            if edge.when and edge.when not in self.conditions:
                raise ValueError(f"条件未注册：{edge.when}")

    # ---------- 路由 ----------
    def route(self, source: str, reply: Optional[Message],
              state: SharedState) -> Optional[str]:
        """按连线顺序寻找第一条满足条件的边；没有则返回 ``None`` 结束。"""
        for edge in self.edges:
            if edge.source != source:
                continue
            if edge.when is None:
                return edge.target
            condition = self.conditions.get(edge.when)
            if condition is not None and condition(state, reply):
                return edge.target
        return None

    # ---------- 执行 ----------
    def run(self, payload: Optional[Dict[str, Any]] = None,
            state: Optional[SharedState] = None,
            trace: Optional[Trace] = None) -> RunResult:
        state = state or SharedState()
        trace = trace or Trace(quiet=True)
        started = time.time()
        result = RunResult(ok=True, state=state)
        steps: List[Step] = []

        trace.event("workflow", f"启动 workflow「{self.name}」 起始节点={self.start} 节点数={len(self.agents)}")
        message = Message(topic="workflow.start", sender="workflow", recipient=self.start,
                          payload=dict(payload or {}))
        self._publish(message, state, trace)

        current: Optional[str] = self.start
        index = 0
        while current and current != END and index < self.max_steps:
            agent = self.agents[current]
            trace.event("agent", f"▶ {agent.name} 处理 {message.topic}")
            index += 1
            t0 = time.time()
            try:
                reply = agent.handle(message, state)
            except Exception as exc:  # noqa: BLE001 - 引擎统一兜底并给出失败步骤
                duration = (time.time() - t0) * 1000
                steps.append(Step(index, current, message.topic, None, duration))
                result.ok = False
                result.error = f"{type(exc).__name__}: {exc}"
                trace.event("error", f"✗ {current} 执行失败：{result.error}")
                break
            duration = (time.time() - t0) * 1000
            steps.append(Step(index, current, message.topic,
                              reply.topic if reply else None, duration))

            if reply is None:
                trace.event("done", f"· {current} 未返回消息，流程结束")
                break
            self._publish(reply, state, trace)
            if reply.topic == DONE:
                trace.event("done", f"✓ {current} 宣布流程完成")
                break

            nxt = self.route(current, reply, state)
            if nxt is None or nxt == END:
                trace.event("workflow", f"· 无后续连线，流程在 {current} 结束")
                break
            trace.event("workflow", f"→ 跳转 {current} → {nxt}")
            message = Message(topic=HANDOFF, sender="workflow", recipient=nxt,
                              payload=dict(reply.payload or {}))
            self._publish(message, state, trace)
            current = nxt
        else:
            if index >= self.max_steps and current not in (None, END):
                result.ok = False
                result.error = f"超过最大步数 {self.max_steps}，疑似死循环"
                trace.event("error", f"✗ {result.error}")

        result.steps = steps
        result.messages = [m for m in state.get("messages", [])]
        result.duration_ms = (time.time() - started) * 1000
        trace.event("done", f"结束：{result.summary()}")
        state.set("run_summary", {
            "ok": result.ok,
            "steps": [s.to_dict() for s in steps],
            "duration_ms": round(result.duration_ms, 2),
            "error": result.error,
        })
        return result

    def _publish(self, message: Message, state: SharedState, trace: Trace) -> None:
        state.append("messages", message.to_dict())
        state.record({"kind": "message", "topic": message.topic,
                      "sender": message.sender, "recipient": message.recipient})
        trace.message(message)

    # ---------- 配置化 ----------
    @classmethod
    def from_config(cls, config: Dict[str, Any], registry: Dict[str, Type[Agent]],
                    conditions: Optional[Dict[str, Condition]] = None) -> "Workflow":
        """根据 JSON 配置构建流程。

        配置格式::

            {
              "name": "code-to-doc",
              "start": "analyzer",
              "max_steps": 12,
              "agents": [{"name": "analyzer", "type": "analyzer"},
                         {"name": "writer", "type": "writer", "options": {...}}],
              "edges": [{"from": "analyzer", "to": "writer"},
                        {"from": "reviewer", "to": "writer", "when": "needs_revision"},
                        {"from": "reviewer", "to": "__end__", "when": "approved"}]
            }
        """
        agents: Dict[str, Agent] = {}
        for item in config.get("agents", []):
            type_name = item["type"]
            if type_name not in registry:
                raise ValueError(f"未注册的 Agent 类型：{type_name}")
            agent_cls = registry[type_name]
            options = dict(item.get("options", {}))
            agents[item["name"]] = agent_cls(name=item["name"], **options)
        edges = [Edge(e["from"], e["to"], e.get("when"), e.get("label", ""))
                 for e in config.get("edges", [])]
        return cls(
            name=config.get("name", "workflow"),
            description=config.get("description", ""),
            agents=agents,
            start=config["start"],
            edges=edges,
            max_steps=int(config.get("max_steps", 16)),
            conditions=conditions,
        )

    def describe(self) -> str:
        lines = [f"Workflow: {self.name}"]
        if self.description:
            lines.append(f"  {self.description}")
        lines.append(f"  起始节点: {self.start}")
        for edge in self.edges:
            lines.append(f"  - {edge.describe()}")
        return "\n".join(lines)
