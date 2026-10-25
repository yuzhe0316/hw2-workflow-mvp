"""审校 Agent：检查文档并打分。

六项检查都能直接用字符串判断，总分 100，85 分通过。没通过就退回 writer 重写。
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from ..agent import Agent, AgentError
from ..message import DONE, Message
from ..state import SharedState

# (检查项, 分值, 说明)
CHECKS: List[Tuple[str, int, str]] = [
    ("title", 10, "文档标题"),
    ("overview", 10, "模块概览"),
    ("symbols", 25, "公共符号覆盖"),
    ("params", 25, "参数说明"),
    ("example", 15, "使用示例"),
    ("placeholder", 15, "无占位符"),
]

PASS_SCORE = 85
MAX_REVISIONS = 2


def _section(markdown: str, fragment: str) -> str:
    """截取包含 ``fragment`` 的三级标题小节（到下一个三级标题为止）。"""
    lines = markdown.splitlines()
    collected: List[str] = []
    inside = False
    for line in lines:
        if line.startswith("### "):
            if inside:
                break
            inside = fragment in line
        if inside:
            collected.append(line)
    return "\n".join(collected)


class ReviewerAgent(Agent):
    """对文档草稿做结构化审校。"""

    name = "reviewer"
    description = "按固定评分项审校文档，未达标时打回 writer 重写（最多 2 轮）"

    def handle(self, message: Message, state: SharedState) -> Optional[Message]:
        markdown = state.get("markdown")
        analysis = state.get("analysis")
        if not markdown or not analysis:
            raise AgentError("reviewer 缺少文档或分析结果，无法审校")

        round_no = int(state.get("revision", 0) or 0) + 1
        self._emit(state, f"开始第 {round_no} 轮审校（{len(markdown)} 字符）")
        checks, issues = self._check(markdown, analysis)
        score = sum(weight for name, weight, _ in CHECKS if checks.get(name))
        approved = score >= PASS_SCORE

        for name, weight, label in CHECKS:
            mark = "✓" if checks.get(name) else "✗"
            self._emit(state, f"  {mark} {label}（{weight} 分）")

        review = {
            "score": score,
            "approved": approved,
            "round": round_no,
            "issues": issues,
            "checks": checks,
        }
        state.set("review", review)
        state.put_artifact("review.json", json.dumps(review, ensure_ascii=False, indent=2))
        self._emit(state, f"评分 {score}/{PASS_SCORE} 分，"
                          f"{'通过' if approved else '未通过'}，问题 {len(issues)} 条")

        if not approved and round_no <= MAX_REVISIONS:
            state.increment("revision")
            state.set("review_issues", issues)
            return message.reply("review.request_changes", {
                "score": score,
                "issues": issues,
                "round": round_no,
            }, recipient="writer")

        if not approved:
            self._emit(state, f"已达最大重试轮次（{MAX_REVISIONS}），带问题放行")
            review["forced"] = True
            state.set("review", review)
        state.set("review_issues", [])
        return message.reply(DONE, {
            "score": score,
            "round": round_no,
            "issues": issues,
            "forced": review.get("forced", False),
        }, recipient="workflow")

    # ---------- 检查 ----------
    def _check(self, markdown: str, analysis: Dict[str, Any]) -> Tuple[Dict[str, bool], List[str]]:
        checks: Dict[str, bool] = {}
        issues: List[str] = []

        checks["title"] = bool(re.search(r"^# API 文档：\S+", markdown, flags=re.M))
        if not checks["title"]:
            issues.append("缺少一级标题「# API 文档：<模块名>」")

        checks["overview"] = "## 模块概览" in markdown
        if not checks["overview"]:
            issues.append("缺少「## 模块概览」小节")

        symbols = [f for f in analysis["functions"] if f["public"]]
        symbols += [c for c in analysis["classes"] if c["public"]]
        missing_symbols = [item["name"] for item in symbols
                           if not re.search(rf"^###\s+`?{re.escape(item['name'])}`?\s*$",
                                            markdown, flags=re.M)]
        checks["symbols"] = not missing_symbols
        if missing_symbols:
            issues.append("以下公共符号未写入文档：" + "、".join(f"`{n}`" for n in missing_symbols))

        param_issues: List[str] = []
        for function in analysis["functions"]:
            if not function["public"] or not function["params"]:
                continue
            section = _section(markdown, f"`{function['name']}`")
            if "| 参数 |" not in section:
                param_issues.append(f"`{function['name']}` 缺少参数表")
                continue
            missing = [p["name"] for p in function["params"]
                       if f"| `{p['name']}` |" not in section]
            if missing:
                param_issues.append(f"`{function['name']}` 参数表缺少："
                                    + "、".join(f"`{n}`" for n in missing))
        checks["params"] = not param_issues
        issues.extend(param_issues)

        checks["example"] = "## 使用示例" in markdown and "```python" in markdown
        if not checks["example"]:
            issues.append("缺少可运行的「## 使用示例」代码块")

        checks["placeholder"] = not re.search(r"\b(TODO|FIXME)\b", markdown)
        if not checks["placeholder"]:
            issues.append("文档中仍存在 TODO/FIXME 占位符")

        return checks, issues
