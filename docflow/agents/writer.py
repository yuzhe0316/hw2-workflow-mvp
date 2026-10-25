"""写作 Agent：把分析结果写成 Markdown。

共享状态里的 revision 是 0 时只写签名和一句说明，算草稿；
被打回后 revision 变成 1，再补参数表、返回值、复杂度和示例。
"""

from __future__ import annotations

import datetime as _dt
import os
from typing import Any, Dict, List, Optional

from ..agent import Agent, AgentError
from ..message import Message
from ..state import SharedState

# 参数名 → 中文说明的启发式词表，覆盖示例模块里的常见命名
_PARAM_HINTS = {
    "customer": "客户名称或客户编号",
    "items": "明细列表，每项包含商品、数量与单价",
    "tax_rate": "税率，按小数传入（0.06 表示 6%）",
    "amount": "金额（单位：元）",
    "name": "名称",
    "path": "文件路径",
    "callback": "回调函数，接收处理结果",
    "config": "配置字典",
    "timeout": "超时时间（秒）",
    "data": "输入数据",
    "text": "待处理文本",
}

_TYPE_HINTS = {
    "str": "字符串",
    "int": "整数",
    "float": "浮点数",
    "bool": "布尔值",
    "list": "列表",
    "dict": "字典",
    "tuple": "元组",
    "set": "集合",
    "none": "无",
}


def _describe_param(param: Dict[str, Any]) -> str:
    name = str(param["name"]).lstrip("*")
    for key, hint in _PARAM_HINTS.items():
        if key in name:
            return hint
    type_name = str(param.get("type", "")).lower()
    for key, label in _TYPE_HINTS.items():
        if key in type_name:
            return f"{label}类型的输入"
    return "输入参数"


def _sample_value(param: Dict[str, Any]) -> str:
    type_name = str(param.get("type", "")).lower()
    if "str" in type_name:
        return '"示例"'
    if "bool" in type_name:
        return "True"
    if "int" in type_name:
        return "1"
    if "float" in type_name:
        return "1.0"
    if "list" in type_name:
        return "[]"
    if "dict" in type_name:
        return "{}"
    if "tuple" in type_name:
        return "()"
    return "None"


def _one_line(docstring: str, fallback: str) -> str:
    text = " ".join(docstring.strip().split())
    if not text:
        return fallback
    first = text.split("。")[0].split(". ")[0].strip()
    return first if first else text


def _example_code(analysis: Dict[str, Any]) -> str:
    functions = [f for f in analysis["functions"] if f["public"]]
    module = analysis["module"]
    if functions:
        target = sorted(functions, key=lambda f: len(f["params"]))[0]
        args = []
        for param in target["params"]:
            prefix = "*" if param["kind"] == "var_positional" else ""
            args.append(f"{prefix}{param['name']}={_sample_value(param)}")
        call = f"{target['name']}({', '.join(args)})"
        return (
            f"```python\n"
            f"from {module} import {target['name']}\n\n"
            f"result = {call}\n"
            f"print(result)\n"
            f"```"
        )
    classes = [c for c in analysis["classes"] if c["public"]]
    if classes:
        cls = classes[0]
        return (
            f"```python\n"
            f"from {module} import {cls['name']}\n\n"
            f"obj = {cls['name']}()\n"
            f"print(obj)\n"
            f"```"
        )
    return "```python\n# 该模块没有公开符号，可直接按需导入\n```"


class WriterAgent(Agent):
    """根据分析结果生成 Markdown API 文档。"""

    name = "writer"
    description = "把 AST 分析结果渲染为 Markdown API 文档（草稿 / 扩写两档）"

    def handle(self, message: Message, state: SharedState) -> Optional[Message]:
        analysis = state.get("analysis")
        if not analysis:
            raise AgentError("writer 未收到 analysis，请检查上游 analyzer 节点")

        revision = int(state.get("revision", 0) or 0)
        issues: List[str] = list(state.get("review_issues") or [])
        self._emit(state, f"生成{'扩写版' if revision else '初稿'}（revision={revision}）")

        markdown = self._render(analysis, revision=revision, issues=issues)
        output_path = state.get("output_path") or message.payload.get("output_path")
        if not output_path:
            output_path = os.path.join("output", f"{analysis['module']}_API.md")
        output_path = os.path.abspath(str(output_path))
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as handle:
            handle.write(markdown)

        state.set("markdown", markdown)
        state.set("doc_path", output_path)
        state.put_artifact("draft.md" if revision == 0 else "final.md", markdown)
        words = len(markdown)
        self._emit(state, f"已写入 {output_path}（{words} 字符，{markdown.count(chr(10)) + 1} 行）",
                   path=output_path, chars=words)

        topic = "doc.drafted" if revision == 0 else "doc.revised"
        return message.reply(topic, {
            "path": output_path,
            "chars": words,
            "revision": revision,
            "addressed": issues,
        }, recipient="reviewer")

    # ---------- 渲染 ----------
    def _render(self, analysis: Dict[str, Any], revision: int,
                issues: List[str]) -> str:
        functions = [f for f in analysis["functions"] if f["public"]]
        classes = [c for c in analysis["classes"] if c["public"]]
        coverage = analysis["coverage"]
        now = _dt.datetime.now().strftime("%Y-%m-%d %H:%M")

        lines: List[str] = [
            f"# API 文档：{analysis['module']}",
            "",
            f"> docflow 生成 · {now} · revision {revision}",
            "",
            "## 模块概览",
            "",
            "| 指标 | 数值 |",
            "|------|------|",
            f"| 源文件 | `{analysis['filename']}` |",
            f"| 代码行数 | {analysis['lines']} |",
            f"| 公共函数 | {len(functions)} |",
            f"| 公共类 | {len(classes)} |",
            f"| 文档覆盖率 | {coverage['documented']}/{coverage['total']}"
            f"（{coverage['ratio']:.0%}） |",
            "",
            "## 模块说明",
            "",
        ]

        docstring = analysis["docstring"].strip()
        if docstring:
            lines.extend(docstring.splitlines())
        else:
            lines.append("源文件未提供模块级 docstring，以下说明由代码结构与类型注解推断。")
        if analysis["imports"]:
            lines.extend(["", f"依赖：{', '.join(f'`{name}`' for name in analysis['imports'])}"])
        lines.append("")

        lines.extend(["## 公共 API", ""])
        if not functions and not classes:
            lines.extend(["> 未发现公开符号。", ""])
        for function in functions:
            lines.extend(self._render_function(function, revision))
        for cls in classes:
            lines.extend(self._render_class(cls, revision))

        if revision:
            lines.extend(self._render_example(analysis))
            lines.extend(self._render_coverage(analysis))
            if issues:
                lines.extend([
                    "## 审校意见处理",
                    "",
                    "本版针对上一轮审校提出的问题做了补充：",
                    "",
                ])
                lines.extend(f"- {issue}" for issue in issues)
                lines.append("")

        return "\n".join(lines).rstrip() + "\n"

    def _render_function(self, function: Dict[str, Any], revision: int) -> List[str]:
        title = function["name"]
        summary = _one_line(function["docstring"], "（未提供 docstring，说明待补充）")
        lines = [
            f"### `{title}`",
            "",
            f"`{function['signature']}`",
            "",
            summary,
            "",
        ]
        if not revision:
            return lines

        params = function["params"]
        if params:
            lines.extend([
                "**参数**",
                "",
                "| 参数 | 类型 | 默认值 | 说明 |",
                "|------|------|--------|------|",
            ])
            for param in params:
                name = param["name"]
                default = f"`{param['default']}`" if param["default"] else "-"
                lines.append(f"| `{name}` | `{param['type']}` | {default} | {_describe_param(param)} |")
            lines.append("")
        else:
            lines.extend(["**参数**：无。", ""])

        returns = function.get("returns") or "无显式返回值"
        lines.extend([f"**返回值**：`{returns}`", ""])
        complexity = function["complexity"]
        level = "简单" if complexity <= 3 else "中等" if complexity <= 8 else "偏高"
        lines.extend([f"**圈复杂度**：{complexity}（{level}）", ""])
        if function["docstring"].strip().splitlines():
            body = "\n".join(function["docstring"].strip().splitlines()[1:]).strip()
            if body:
                lines.extend(["**补充说明**", "", body, ""])
        return lines

    def _render_class(self, cls: Dict[str, Any], revision: int) -> List[str]:
        summary = _one_line(cls["docstring"], "（未提供 docstring，说明待补充）")
        lines = [f"### `{cls['name']}`", "", summary, ""]
        if cls["bases"]:
            lines.extend([f"继承自：{', '.join(f'`{b}`' for b in cls['bases'])}", ""])
        methods = [m for m in cls["methods"] if m["public"]]
        if methods:
            lines.extend(["**公开方法**", ""])
            if revision:
                lines.extend(["| 方法 | 签名 | 说明 |", "|------|------|------|"])
                for method in methods:
                    lines.append(f"| `{method['name']}` | `{method['signature']}` | "
                                 f"{_one_line(method['docstring'], '待补充')} |")
            else:
                for method in methods:
                    lines.append(f"- `{method['name']}`："
                                 f"{_one_line(method['docstring'], '待补充说明')}")
            lines.append("")
        return lines

    def _render_example(self, analysis: Dict[str, Any]) -> List[str]:
        return ["## 使用示例", "", _example_code(analysis), ""]

    def _render_coverage(self, analysis: Dict[str, Any]) -> List[str]:
        missing = analysis["missing_docstrings"]
        lines = ["## 文档覆盖情况", ""]
        if missing:
            lines.extend([
                f"以下 {len(missing)} 个符号缺少 docstring，正文中的说明由签名与类型推断，"
                "建议补充源码注释后重新生成：",
                "",
            ])
            lines.extend(f"- `{name}`" for name in missing)
        else:
            lines.append("所有公共符号均已有 docstring。")
        lines.append("")
        return lines
