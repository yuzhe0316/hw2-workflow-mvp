"""命令行入口：``python -m docflow <run|demo|agents|validate>``。"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
from typing import Any, Dict, Optional

from . import __version__
from .agent import describe_agents
from .pipeline import REGISTRY, build_workflow
from .state import SharedState
from .trace import Trace

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _configure_stdout() -> None:
    """Windows 控制台默认不是 UTF-8，中文日志会乱码，这里尽量纠正。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001 - 非标准流忽略即可
            pass


def _load_config(path: Optional[str]) -> Optional[Dict[str, Any]]:
    if not path:
        return None
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _run(args: argparse.Namespace) -> int:
    source = os.path.abspath(args.source)
    if not os.path.isfile(source):
        print(f"找不到源文件：{source}", file=sys.stderr)
        return 2

    workflow = build_workflow(_load_config(args.config))
    if args.max_steps:
        workflow.max_steps = args.max_steps

    module = os.path.splitext(os.path.basename(source))[0]
    output = os.path.abspath(args.output or os.path.join("output", f"{module}_API.md"))
    run_dir = os.path.abspath(args.trace_dir or os.path.join(
        "runs", _dt.datetime.now().strftime("%Y%m%d-%H%M%S")))
    os.makedirs(run_dir, exist_ok=True)

    trace = Trace(path=os.path.join(run_dir, "trace.jsonl"), color=not args.no_color,
                  quiet=args.quiet)
    state = SharedState({"source_path": source, "output_path": output})
    try:
        result = workflow.run({"source": source}, state=state, trace=trace)
    finally:
        trace.close()

    with open(os.path.join(run_dir, "state.json"), "w", encoding="utf-8") as handle:
        json.dump(state.snapshot(), handle, ensure_ascii=False, indent=2)
    with open(os.path.join(run_dir, "messages.json"), "w", encoding="utf-8") as handle:
        json.dump(state.get("messages", []), handle, ensure_ascii=False, indent=2)

    review = state.get("review") or {}
    if not args.quiet:
        print()
        print(f"Workflow : {workflow.name}")
        print(f"结果     : {result.summary()}")
        print(f"文档     : {state.get('doc_path', output)}")
        print(f"审校     : {review.get('score', '-')} 分 · "
              f"{'通过' if review.get('approved') else '未通过'} · "
              f"第 {review.get('round', 0)} 轮")
        print(f"运行记录 : {run_dir}")

    if args.json:
        payload = state.snapshot()
        payload["run"] = state.get("run_summary")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if result.ok else 1


def _demo(args: argparse.Namespace) -> int:
    source = os.path.join(PROJECT_ROOT, "examples", "billing.py")
    args.source = source
    args.output = args.output or os.path.join(PROJECT_ROOT, "output", "billing_API.md")
    return _run(args)


def _agents(args: argparse.Namespace) -> int:
    instances = {name: cls() for name, cls in REGISTRY.items()}
    print("已注册的 Agent：")
    print(describe_agents(instances))
    print("\n内置流程：代码 → 分析 → 文档 → 审校（未通过则回写，最多 2 轮重试）")
    return 0


def _validate(args: argparse.Namespace) -> int:
    workflow = build_workflow(_load_config(args.config))
    print(workflow.describe())
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="docflow",
        description="docflow：3 个 Agent 协作的代码文档生成 Workflow",
    )
    parser.add_argument("--version", action="version", version=f"docflow {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="对指定 Python 文件生成 API 文档")
    run.add_argument("source", help="源 .py 文件路径")
    run.add_argument("-o", "--output", help="输出 Markdown 路径")
    run.add_argument("--config", help="自定义 workflow JSON 配置")
    run.add_argument("--trace-dir", help="运行记录目录（默认 runs/<时间戳>）")
    run.add_argument("--max-steps", type=int, help="最大执行步数")
    run.add_argument("--json", action="store_true", help="额外输出状态 JSON")
    run.add_argument("--quiet", action="store_true", help="不打印过程日志")
    run.add_argument("--no-color", action="store_true", help="关闭彩色输出")
    run.set_defaults(func=_run)

    demo = sub.add_parser("demo", help="用内置示例跑一遍完整流程")
    demo.add_argument("-o", "--output", help="输出 Markdown 路径")
    demo.add_argument("--config", help="自定义 workflow JSON 配置")
    demo.add_argument("--trace-dir", help="运行记录目录")
    demo.add_argument("--max-steps", type=int)
    demo.add_argument("--json", action="store_true")
    demo.add_argument("--quiet", action="store_true")
    demo.add_argument("--no-color", action="store_true")
    demo.set_defaults(func=_demo)

    agents = sub.add_parser("agents", help="列出已注册的 Agent")
    agents.set_defaults(func=_agents)

    validate = sub.add_parser("validate", help="校验并打印流程图配置")
    validate.add_argument("--config", help="自定义 workflow JSON 配置")
    validate.set_defaults(func=_validate)
    return parser


def main(argv: Optional[list] = None) -> int:
    _configure_stdout()
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
