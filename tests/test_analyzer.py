"""分析 Agent 的单元测试。"""

from __future__ import annotations

import os
import tempfile
import unittest

from docflow.agent import AgentError
from docflow.agents.analyzer import analyze_source

SAMPLE = '''
"""示例模块。"""

import os


def greet(name: str, times: int = 1) -> str:
    """重复问候。"""
    return ("hi " + name + " ") * times


def _private() -> None:
    pass


class Greeter:
    """问候器。"""

    def hello(self, who: str) -> str:
        """向某人问好。"""
        if who:
            return "hello " + who
        return ""


class _Hidden:
    pass
'''


class AnalyzerTest(unittest.TestCase):
    def setUp(self) -> None:
        handle = tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8")
        handle.write(SAMPLE)
        handle.close()
        self.path = handle.name

    def tearDown(self) -> None:
        if os.path.exists(self.path):
            os.unlink(self.path)

    def test_parses_module_facts(self) -> None:
        result = analyze_source(self.path)
        self.assertEqual(result["module"], os.path.splitext(os.path.basename(self.path))[0])
        self.assertEqual(result["docstring"], "示例模块。")
        self.assertIn("os", result["imports"])
        names = [f["name"] for f in result["functions"]]
        self.assertEqual(names, ["greet", "_private"])
        self.assertEqual([c["name"] for c in result["classes"]], ["Greeter", "_Hidden"])

    def test_signature_and_params(self) -> None:
        result = analyze_source(self.path)
        greet = result["functions"][0]
        self.assertEqual(greet["signature"], "def greet(name: str, times: int = 1) -> str")
        self.assertEqual([p["name"] for p in greet["params"]], ["name", "times"])
        self.assertFalse(greet["params"][1]["required"])

    def test_coverage_ignores_private(self) -> None:
        result = analyze_source(self.path)
        # 公共符号：greet、Greeter；Greeter.hello 也算一个
        self.assertEqual(result["coverage"]["total"], 3)
        self.assertEqual(result["coverage"]["documented"], 3)
        self.assertEqual(result["missing_docstrings"], [])

    def test_syntax_error_wrapped(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as bad:
            bad.write("def broken(:\n")
            path = bad.name
        try:
            with self.assertRaises(AgentError):
                analyze_source(path)
        finally:
            os.unlink(path)

    def test_missing_file(self) -> None:
        with self.assertRaises(AgentError):
            analyze_source("no_such_file.py")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
