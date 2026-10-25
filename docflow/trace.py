"""执行日志与轨迹记录。

两种消费方式：
- 终端：带时间戳的彩色流水，演示时可直接看；
- 文件：``trace.jsonl``，每行一个事件，便于事后排查。
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Any, Dict, Optional, TextIO

_COLORS = {
    "workflow": "\033[36m",   # cyan
    "message": "\033[35m",    # magenta
    "agent": "\033[32m",      # green
    "error": "\033[31m",      # red
    "done": "\033[33m",       # yellow
    "dim": "\033[2m",
    "reset": "\033[0m",
}


class Trace:
    """把 Workflow 的执行过程同时写到终端和 JSONL 文件。"""

    def __init__(self, path: Optional[str] = None, stream: Optional[TextIO] = None,
                 color: Optional[bool] = None, quiet: bool = False) -> None:
        self.path = path
        self.stream = stream or sys.stdout
        self.quiet = quiet
        self.color = self._supports_color(self.stream) if color is None else color
        self.started = time.time()
        self._file: Optional[TextIO] = None
        if path:
            parent = os.path.dirname(os.path.abspath(path))
            os.makedirs(parent, exist_ok=True)
            self._file = open(path, "w", encoding="utf-8")

    @staticmethod
    def _supports_color(stream: TextIO) -> bool:
        return bool(getattr(stream, "isatty", lambda: False)()) and os.environ.get("NO_COLOR") is None

    def _paint(self, kind: str, text: str) -> str:
        if not self.color:
            return text
        return f"{_COLORS.get(kind, '')}{text}{_COLORS['reset']}"

    def event(self, kind: str, text: str, **data: Any) -> None:
        elapsed = time.time() - self.started
        record: Dict[str, Any] = {
            "t": round(elapsed, 4),
            "kind": kind,
            "text": text,
        }
        if data:
            record["data"] = data
        if self._file:
            self._file.write(json.dumps(record, ensure_ascii=False) + "\n")
            self._file.flush()
        if self.quiet:
            return
        stamp = f"{elapsed:6.3f}s"
        prefix = self._paint(kind, f"[{stamp}]")
        print(f"{prefix} {text}", file=self.stream, flush=True)

    def message(self, message: Any, direction: str = "") -> None:
        arrow = f"{message.sender} → {message.recipient}"
        topic = message.topic
        detail = _compact(message.payload)
        suffix = f" {detail}" if detail else ""
        label = f"{direction} " if direction else ""
        self.event("message", f"{label}{self._paint('message', arrow)}  ·  {topic}{suffix}")

    def close(self) -> None:
        if self._file:
            self._file.close()
            self._file = None


def _compact(payload: Dict[str, Any], limit: int = 90) -> str:
    if not payload:
        return ""
    parts = []
    for key, value in payload.items():
        text = str(value).replace("\n", " ")
        if len(text) > 40:
            text = text[:37] + "..."
        parts.append(f"{key}={text}")
    joined = ", ".join(parts)
    return joined if len(joined) <= limit else joined[: limit - 3] + "..."
