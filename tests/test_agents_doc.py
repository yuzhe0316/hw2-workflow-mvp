"""写作与审校 Agent 的单元测试。"""

from __future__ import annotations

import os
import tempfile
import unittest

from docflow.agents.analyzer import analyze_source
from docflow.agents.reviewer import ReviewerAgent
from docflow.agents.writer import WriterAgent
from docflow.message import DONE, Message
from docflow.state import SharedState

EXAMPLE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "examples", "billing.py")


class WriterReviewerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = SharedState({
            "analysis": analyze_source(EXAMPLE),
            "output_path": os.path.join(self.tmp.name, "API.md"),
        })
        self.request = Message(topic="handoff", sender="workflow", recipient="writer")

    def _draft(self) -> Message:
        reply = WriterAgent().handle(self.request, self.state)
        self.assertIsNotNone(reply)
        return reply

    def test_draft_is_compact(self) -> None:
        reply = self._draft()
        markdown = self.state.get("markdown")
        self.assertEqual(reply.topic, "doc.drafted")
        self.assertIn("# API 文档：billing", markdown)
        self.assertNotIn("## 使用示例", markdown)
        self.assertNotIn("| 参数 |", markdown)
        self.assertTrue(os.path.isfile(self.state.get("doc_path")))

    def test_expanded_adds_tables_and_example(self) -> None:
        self._draft()
        self.state.set("revision", 1)
        self.state.set("review_issues", ["缺少参数表"])
        reply = WriterAgent().handle(self.request, self.state)
        markdown = self.state.get("markdown")
        self.assertEqual(reply.topic, "doc.revised")
        self.assertIn("| 参数 |", markdown)
        self.assertIn("## 使用示例", markdown)
        self.assertIn("## 审校意见处理", markdown)
        self.assertGreater(len(markdown), 1200)

    def test_reviewer_requests_changes_for_draft(self) -> None:
        self._draft()
        reply = ReviewerAgent().handle(
            Message(topic="handoff", sender="workflow", recipient="reviewer"), self.state)
        self.assertEqual(reply.topic, "review.request_changes")
        self.assertLess(self.state.get("review")["score"], 85)
        self.assertGreater(len(reply.payload["issues"]), 0)
        self.assertEqual(self.state.get("revision"), 1)

    def test_reviewer_approves_expanded_doc(self) -> None:
        self._draft()
        reviewer = ReviewerAgent()
        reviewer.handle(Message(topic="h", sender="workflow", recipient="reviewer"), self.state)
        WriterAgent().handle(Message(topic="h", sender="workflow", recipient="writer"), self.state)
        reply = reviewer.handle(Message(topic="h", sender="workflow", recipient="reviewer"),
                                self.state)
        self.assertEqual(reply.topic, DONE)
        self.assertTrue(self.state.get("review")["approved"])
        self.assertGreaterEqual(self.state.get("review")["score"], 85)

    def test_reviewer_forces_pass_after_max_rounds(self) -> None:
        self._draft()
        self.state.set("revision", 2)
        reply = ReviewerAgent().handle(
            Message(topic="h", sender="workflow", recipient="reviewer"), self.state)
        self.assertEqual(reply.topic, DONE)
        self.assertTrue(reply.payload["forced"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
