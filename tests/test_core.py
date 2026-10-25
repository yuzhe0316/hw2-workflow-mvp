"""消息与共享状态的单元测试。"""

from __future__ import annotations

import unittest

from docflow.message import DONE, Message, MessageBus
from docflow.state import SharedState


class MessageTest(unittest.TestCase):
    def test_reply_links_to_original(self) -> None:
        request = Message(topic="task", sender="a", recipient="b", payload={"x": 1})
        reply = request.reply("result", {"y": 2})
        self.assertEqual(reply.sender, "b")
        self.assertEqual(reply.recipient, "a")
        self.assertEqual(reply.reply_to, request.id)
        self.assertEqual(reply.payload, {"y": 2})

    def test_bus_records_history_and_notifies(self) -> None:
        bus = MessageBus()
        seen = []
        bus.subscribe(DONE, seen.append)
        bus.publish(Message(topic=DONE, sender="a", recipient="workflow"))
        self.assertEqual(len(bus.history), 1)
        self.assertEqual(len(seen), 1)
        self.assertEqual(bus.to_dicts()[0]["topic"], DONE)

    def test_subscriber_error_does_not_break_publish(self) -> None:
        bus = MessageBus()
        bus.subscribe("*", lambda _msg: 1 / 0)
        bus.publish(Message(topic="t", sender="a", recipient="b"))
        self.assertEqual(len(bus.history), 1)


class StateTest(unittest.TestCase):
    def test_get_set_increment(self) -> None:
        state = SharedState({"a": 1})
        state.set("b", 2)
        self.assertEqual(state.increment("b"), 3)
        self.assertEqual(state.get("missing", "x"), "x")
        self.assertEqual(state.keys(), ["a", "b"])

    def test_snapshot_is_deep_copy(self) -> None:
        state = SharedState({"items": [1]})
        snap = state.snapshot()
        snap["data"]["items"].append(2)
        self.assertEqual(state.get("items"), [1])

    def test_artifacts_do_not_leak(self) -> None:
        state = SharedState()
        state.put_artifact("a.md", "hello")
        state.artifacts["a.md"] = "changed"
        self.assertEqual(state.get_artifact("a.md"), "hello")
        self.assertEqual(state.snapshot()["artifact_names"], ["a.md"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
