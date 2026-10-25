"""共享状态，相当于一块黑板。

分析结果、文档草稿、审校结论都放这里，节点按 key 读写。
"""

from __future__ import annotations

import copy
import threading
import time
from typing import Any, Dict, List, Optional


class SharedState:
    """线程安全的键值黑板，附带产物区与事件流。"""

    def __init__(self, initial: Optional[Dict[str, Any]] = None) -> None:
        self._data: Dict[str, Any] = dict(initial or {})
        self._artifacts: Dict[str, Any] = {}
        self._events: List[Dict[str, Any]] = []
        self._lock = threading.RLock()
        self.created_at = time.time()

    # ---------- 普通数据 ----------
    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._data[key] = value

    def update(self, values: Dict[str, Any]) -> None:
        with self._lock:
            self._data.update(values)

    def append(self, key: str, item: Any) -> None:
        with self._lock:
            self._data.setdefault(key, []).append(item)

    def increment(self, key: str, step: int = 1) -> int:
        with self._lock:
            value = int(self._data.get(key, 0)) + step
            self._data[key] = value
            return value

    def keys(self) -> List[str]:
        with self._lock:
            return sorted(self._data)

    # ---------- 产物区 ----------
    def put_artifact(self, name: str, content: Any) -> None:
        with self._lock:
            self._artifacts[name] = content

    def get_artifact(self, name: str) -> Any:
        with self._lock:
            return self._artifacts.get(name)

    @property
    def artifacts(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._artifacts)

    # ---------- 事件流 ----------
    def record(self, event: Dict[str, Any]) -> None:
        with self._lock:
            item = dict(event)
            item.setdefault("at", round(time.time() - self.created_at, 4))
            self._events.append(item)

    @property
    def events(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._events)

    # ---------- 导出 ----------
    def snapshot(self) -> Dict[str, Any]:
        """返回可 JSON 序列化的快照（深拷贝，避免外部改动污染状态）。"""
        with self._lock:
            return {
                "data": copy.deepcopy(self._data),
                "artifact_names": sorted(self._artifacts),
                "artifact_sizes": {
                    k: len(v) if isinstance(v, (str, bytes, list, dict)) else 1
                    for k, v in self._artifacts.items()
                },
                "event_count": len(self._events),
            }
