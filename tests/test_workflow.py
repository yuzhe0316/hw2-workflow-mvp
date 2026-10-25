"""Workflow 引擎的单元测试。"""

from __future__ import annotations

import os
import tempfile
import unittest

from docflow.agent import Agent
from docflow.message import DONE, Message
from docflow.pipeline import DEFAULT_PIPELINE, build_workflow
from docflow.state import SharedState
from docflow.trace import Trace
from docflow.workflow import END, Edge, Workflow

EXAMPLE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "examples", "billing.py")


class EchoAgent(Agent):
    name = "echo"

    def handle(self, message: Message, state: SharedState):
        state.increment("count")
        return message.reply("echo.ok", {"count": state.get("count")}, recipient="echo")


class LoopAgent(Agent):
    name = "loop"

    def handle(self, message: Message, state: SharedState):
        return message.reply("loop", {}, recipient="loop2")


class WorkflowTest(unittest.TestCase):
    def test_full_pipeline_runs_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = os.path.join(tmp, "API.md")
            state = SharedState({"output_path": output})
            workflow = build_workflow()
            result = workflow.run({"source": EXAMPLE}, state=state, trace=Trace(quiet=True))

            self.assertTrue(result.ok, result.error)
            self.assertEqual([s.agent for s in result.steps],
                             ["analyzer", "writer", "reviewer", "writer", "reviewer"])
            self.assertEqual(state.get("review")["score"], 100)
            self.assertTrue(os.path.isfile(output))
            with open(output, encoding="utf-8") as handle:
                self.assertIn("## 使用示例", handle.read())

    def test_conditional_loop_and_max_steps(self) -> None:
        agent = LoopAgent()
        workflow = Workflow(
            name="loop-test",
            agents={"loop": agent, "loop2": agent},
            start="loop",
            edges=[Edge("loop", "loop2"), Edge("loop2", "loop")],
            max_steps=4,
        )
        result = workflow.run(trace=Trace(quiet=True))
        self.assertFalse(result.ok)
        self.assertIn("最大步数", result.error or "")
        self.assertEqual(len(result.steps), 4)

    def test_unconditional_route_to_end(self) -> None:
        workflow = Workflow(
            name="one-step",
            agents={"echo": EchoAgent()},
            start="echo",
            edges=[Edge("echo", END)],
        )
        result = workflow.run(trace=Trace(quiet=True))
        self.assertTrue(result.ok)
        self.assertEqual(len(result.steps), 1)

    def test_done_topic_stops_workflow(self) -> None:
        class DoneAgent(Agent):
            name = "done"

            def handle(self, message, state):
                return message.reply(DONE, {}, recipient="workflow")

        workflow = Workflow(name="done-test", agents={"done": DoneAgent()},
                            start="done", edges=[])
        result = workflow.run(trace=Trace(quiet=True))
        self.assertTrue(result.ok)
        self.assertEqual(result.steps[0].reply_topic, DONE)

    def test_validate_rejects_unknown_edge(self) -> None:
        with self.assertRaises(ValueError):
            Workflow(name="bad", agents={"echo": EchoAgent()}, start="echo",
                     edges=[Edge("echo", "missing")])

    def test_validate_rejects_unknown_condition(self) -> None:
        with self.assertRaises(ValueError):
            Workflow(name="bad", agents={"echo": EchoAgent()}, start="echo",
                     edges=[Edge("echo", END, when="nope")])

    def test_from_config_builds_custom_pipeline(self) -> None:
        config = {
            "name": "custom",
            "start": "analyzer",
            "agents": [{"name": "analyzer", "type": "analyzer"},
                       {"name": "writer", "type": "writer"}],
            "edges": [{"from": "analyzer", "to": "writer"},
                      {"from": "writer", "to": END}],
        }
        workflow = build_workflow(config)
        self.assertEqual(sorted(workflow.agents), ["analyzer", "writer"])
        self.assertIn("custom", workflow.describe())

    def test_default_config_is_valid(self) -> None:
        workflow = build_workflow(DEFAULT_PIPELINE)
        self.assertEqual(workflow.start, "analyzer")
        self.assertEqual(len(workflow.edges), 4)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
