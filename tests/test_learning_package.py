import json
import tempfile
import unittest
from pathlib import Path

from common.agent.multi.package import export_learning_package
from common.agent.multi.state import SessionState


class _Provider:
    def chat(self, messages, model_id, tools=None):
        return json.dumps([{"stage": "阶段一 基础",
                            "items": [{"q": "什么是变量？", "a": "存储数据的名字"},
                                      {"q": "list 与 tuple 区别？", "a": "可变 vs 不可变"}]}],
                          ensure_ascii=False)


class _BadProvider:
    def chat(self, *a, **k):
        raise RuntimeError("LLM down")


class _WrappedProvider:
    def chat(self, messages, model_id, tools=None):
        return json.dumps({"quiz": [{"stage": "阶段一",
                                     "items": [{"q": "什么是 ETF？", "a": "交易型开放式指数基金"}]}]},
                          ensure_ascii=False)


class _RetryProvider:
    def __init__(self):
        self.calls = 0

    def chat(self, messages, model_id, tools=None):
        self.calls += 1
        if self.calls == 1:
            return "这次没有返回 JSON"
        return json.dumps([{"stage": "阶段二",
                            "items": [{"q": "为什么要控制仓位？", "a": "降低单一决策风险"}]}],
                          ensure_ascii=False)


class _UnparseableProvider:
    def chat(self, messages, model_id, tools=None):
        return "not json at all"


class _MalformedJsonProvider:
    def chat(self, messages, model_id, tools=None):
        return """```json
[
  {
    "stage": "第 1 阶段",
    "items": [
      {
        "q": "什么是 ETF？",
        "a": "ETF 是可以在交易所买卖的一篮子基金。
      },
      {
        "q": "为什么长期定投适合上班族？",
        "a": "它降低择时压力，并用纪律对抗情绪。"
      }
    ]
  }
]
```"""


def _state():
    st = SessionState(raw_goal="两周入门 Python 数据分析")
    st.display_markdown = "# 计划\n\n![封面](assets/cover.png)\n\n正文"
    st.knowledge_outline = "Python / Pandas"
    st.plan_structured = {
        "stage_goals": ["基础", "项目"],
        "weekly_schedule": [{"week": 1, "topic": "基础语法", "output": "练习脚本", "hours": "10h"},
                            {"week": 2, "topic": "项目", "output": "完整项目", "hours": "10h"}],
        "milestones": [{"week": 1, "name": "M1 首个脚本", "description": "跑通"},
                       {"week": 2, "name": "M2 项目", "description": "交付"}],
    }
    return st


class LearningPackageTests(unittest.TestCase):
    def test_exports_four_files_with_rewrites(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = export_learning_package(_Provider(), "m3", Path(tmp), _state())
            files = {p.name: p.read_text(encoding="utf-8") for p in pkg.iterdir()}
        self.assertEqual(set(files), {"plan.md", "daily-checklist.md", "review-log.md", "quiz.md"})
        self.assertIn("](../assets/cover.png)", files["plan.md"])           # 路径回退一级
        self.assertIn("- [ ] 完成产出：练习脚本", files["daily-checklist.md"])
        self.assertIn("- [ ] 第 1 周 · M1 首个脚本", files["daily-checklist.md"])
        self.assertIn("今天学了什么", files["review-log.md"])
        self.assertIn("什么是变量？", files["quiz.md"])
        self.assertIn("<details>", files["quiz.md"])

    def test_quiz_failure_is_graceful(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = export_learning_package(_BadProvider(), "m3", Path(tmp), _state())
            quiz = (pkg / "quiz.md").read_text(encoding="utf-8")
            self.assertIn("生成失败", quiz)
            self.assertTrue((pkg / "daily-checklist.md").exists())   # 其它文件不受影响

    def test_quiz_accepts_wrapped_array_response(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = export_learning_package(_WrappedProvider(), "m3", Path(tmp), _state())
            quiz = (pkg / "quiz.md").read_text(encoding="utf-8")
        self.assertIn("什么是 ETF？", quiz)
        self.assertIn("交易型开放式指数基金", quiz)

    def test_quiz_retries_after_unparseable_response(self):
        provider = _RetryProvider()
        with tempfile.TemporaryDirectory() as tmp:
            pkg = export_learning_package(provider, "m3", Path(tmp), _state())
            quiz = (pkg / "quiz.md").read_text(encoding="utf-8")
        self.assertEqual(provider.calls, 2)
        self.assertIn("为什么要控制仓位？", quiz)

    def test_quiz_failure_writes_raw_diagnostic(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = export_learning_package(_UnparseableProvider(), "m3", Path(tmp), _state())
            quiz = (pkg / "quiz.md").read_text(encoding="utf-8")
            raw = (pkg / "quiz.raw.txt").read_text(encoding="utf-8")
        self.assertIn("生成失败", quiz)
        self.assertIn("not json at all", raw)

    def test_quiz_recovers_from_malformed_json_string(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = export_learning_package(_MalformedJsonProvider(), "m3", Path(tmp), _state())
            quiz = (pkg / "quiz.md").read_text(encoding="utf-8")
        self.assertIn("什么是 ETF？", quiz)
        self.assertIn("为什么长期定投适合上班族？", quiz)
        self.assertNotIn("生成失败", quiz)

    def test_empty_plan_does_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            st = SessionState(raw_goal="空计划")
            pkg = export_learning_package(_Provider(), "m3", Path(tmp), st)
            self.assertTrue((pkg / "daily-checklist.md").exists())


if __name__ == "__main__":
    unittest.main()
