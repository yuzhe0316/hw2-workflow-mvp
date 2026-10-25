"""分析 Agent：用标准库 ``ast`` 把源码解析成结构化事实。

它不生成自然语言，只负责"看清代码"：模块信息、导入、类与函数签名、
参数、docstring、圈复杂度、文档覆盖率。后续 Agent 全部消费这份结构化数据。
"""

from __future__ import annotations

import ast
import json
import os
from typing import Any, Dict, List, Optional

from ..agent import Agent, AgentError
from ..message import Message
from ..state import SharedState

_DECISION_NODES = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler,
                   ast.IfExp, ast.Assert)


def _literal(node: Optional[ast.AST]) -> str:
    """把注解 / 默认值节点转成短文本，失败时退回 ``...``。"""
    if node is None:
        return ""
    try:
        text = ast.unparse(node)
    except Exception:  # noqa: BLE001 - 极旧语法或特殊节点时保底
        return "..."
    return text if len(text) <= 60 else text[:57] + "..."


def _complexity(node: ast.AST) -> int:
    """圈复杂度近似：1 + 判定节点数（含布尔运算与推导式条件）。"""
    score = 1
    for child in ast.walk(node):
        if isinstance(child, _DECISION_NODES):
            score += 1
        elif isinstance(child, ast.BoolOp):
            score += len(child.values) - 1
        elif isinstance(child, ast.comprehension):
            score += 1 + len(child.ifs)
    return score


def _render_params(args: ast.arguments) -> List[Dict[str, Any]]:
    """把 ``ast.arguments`` 拆成便于渲染的参数列表。"""
    params: List[Dict[str, Any]] = []
    positional = list(args.posonlyargs) + list(args.args)
    defaults: List[Optional[ast.AST]] = [None] * (len(positional) - len(args.defaults))
    defaults += list(args.defaults)

    for index, (arg, default) in enumerate(zip(positional, defaults)):
        kind = "positional_only" if index < len(args.posonlyargs) else "positional"
        params.append({
            "name": arg.arg,
            "type": _literal(arg.annotation) or "Any",
            "default": _literal(default),
            "kind": kind,
            "required": default is None,
        })
    if args.vararg:
        params.append({"name": args.vararg.arg, "type": _literal(args.vararg.annotation) or "Any",
                       "default": "", "kind": "var_positional", "required": False})
    for arg, default in zip(args.kwonlyargs, args.kw_defaults):
        params.append({"name": arg.arg, "type": _literal(arg.annotation) or "Any",
                       "default": _literal(default), "kind": "keyword_only",
                       "required": default is None})
    if args.kwarg:
        params.append({"name": args.kwarg.arg, "type": _literal(args.kwarg.annotation) or "Any",
                       "default": "", "kind": "var_keyword", "required": False})
    return params


def _render_signature(name: str, args: ast.arguments, returns: Optional[ast.AST],
                      drop_self: bool = False) -> str:
    params = _render_params(args)
    if drop_self and params and params[0]["name"] in ("self", "cls"):
        params = params[1:]
    parts = []
    for param in params:
        text = param["name"]
        if param["type"] != "Any":
            text += f": {param['type']}"
        if param["default"]:
            text += f" = {param['default']}"
        parts.append(text)
    signature = f"def {name}({', '.join(parts)})"
    if returns is not None:
        signature += f" -> {_literal(returns)}"
    return signature


def _function_info(node: ast.AST, drop_self: bool = False) -> Dict[str, Any]:
    name = node.name
    doc = ast.get_docstring(node) or ""
    params = _render_params(node.args)
    if drop_self and params and params[0]["name"] in ("self", "cls"):
        params = params[1:]
    return {
        "name": name,
        "signature": _render_signature(name, node.args, node.returns, drop_self),
        "returns": _literal(node.returns) or "",
        "docstring": doc,
        "params": params,
        "lineno": node.lineno,
        "complexity": _complexity(node),
        "public": not name.startswith("_"),
        "decorators": [_literal(d) for d in node.decorator_list],
    }


def analyze_source(path: str) -> Dict[str, Any]:
    """解析单个 Python 文件，返回结构化分析结果。"""
    if not os.path.isfile(path):
        raise AgentError(f"源文件不存在：{path}")
    if not path.endswith(".py"):
        raise AgentError(f"只支持 .py 文件：{path}")
    try:
        with open(path, "r", encoding="utf-8") as handle:
            source = handle.read()
    except UnicodeDecodeError as exc:
        raise AgentError(f"文件不是 UTF-8 编码：{path}") from exc
    if not source.strip():
        raise AgentError(f"源文件为空：{path}")

    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as exc:
        raise AgentError(f"语法错误（第 {exc.lineno} 行）：{exc.msg}") from exc

    imports: List[str] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or "."
            imports.append(module)

    functions: List[Dict[str, Any]] = []
    classes: List[Dict[str, Any]] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(_function_info(node))
        elif isinstance(node, ast.ClassDef):
            methods = [_function_info(item, drop_self=True)
                       for item in node.body
                       if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))]
            classes.append({
                "name": node.name,
                "docstring": ast.get_docstring(node) or "",
                "bases": [_literal(base) for base in node.bases],
                "lineno": node.lineno,
                "public": not node.name.startswith("_"),
                "methods": methods,
            })

    symbols = [f for f in functions if f["public"]]
    for cls in classes:
        if cls["public"]:
            symbols.append(cls)
    documented = 0
    total = 0
    missing: List[str] = []
    for item in symbols:
        total += 1
        if item["docstring"].strip():
            documented += 1
        else:
            missing.append(item["name"])
        for method in item.get("methods", []):
            if not method["public"] or method["name"].startswith("_"):
                continue
            total += 1
            if method["docstring"].strip():
                documented += 1
            else:
                missing.append(f"{item['name']}.{method['name']}")

    return {
        "path": os.path.abspath(path),
        "filename": os.path.basename(path),
        "module": os.path.splitext(os.path.basename(path))[0],
        "lines": len(source.splitlines()),
        "source_lines": len([line for line in source.splitlines()
                             if line.strip() and not line.strip().startswith("#")]),
        "docstring": ast.get_docstring(tree) or "",
        "imports": sorted(set(imports)),
        "functions": functions,
        "classes": classes,
        "missing_docstrings": missing,
        "coverage": {
            "documented": documented,
            "total": total,
            "ratio": round(documented / total, 3) if total else 0.0,
        },
    }


class AnalyzerAgent(Agent):
    """读取源码并产出结构化分析结果。"""

    name = "analyzer"
    description = "解析 Python 源码（AST），产出模块/符号/复杂度等结构化事实"

    def handle(self, message: Message, state: SharedState) -> Optional[Message]:
        source = message.payload.get("source") or state.get("source_path")
        if not source:
            raise AgentError("缺少输入：请通过 --source 指定 .py 文件")
        self._emit(state, f"开始分析 {source}")
        analysis = analyze_source(str(source))

        state.set("source_path", analysis["path"])
        state.set("analysis", analysis)
        state.put_artifact("analysis.json", json.dumps(analysis, ensure_ascii=False, indent=2))

        public_count = len([f for f in analysis["functions"] if f["public"]]) + \
            len([c for c in analysis["classes"] if c["public"]])
        self._emit(state, f"解析完成：{public_count} 个公共符号，"
                          f"{len(analysis['functions'])} 个顶层函数，"
                          f"{len(analysis['classes'])} 个类，"
                          f"文档覆盖率 {analysis['coverage']['ratio']:.0%}")

        return message.reply("analysis.completed", {
            "path": analysis["path"],
            "module": analysis["module"],
            "symbols": public_count,
            "lines": analysis["lines"],
            "missing_docstrings": len(analysis["missing_docstrings"]),
        }, recipient="writer")
