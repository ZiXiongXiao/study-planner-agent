import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from common.agent.multi import agents as A
from common.agent.multi import display
from common.agent.multi.agents import (
    FeedbackAdjustmentAgent, MultimodalDisplayAgent, ResourceEvaluationAgent)
from common.agent.multi.state import SessionState
from common.agent.tools.registry import ToolResult


class _Dummy:
    def chat(self, *a, **k):
        return "{}"


# ----------------------------- P2: 资源评估 ----------------------------- #
class ResourceEvalGroundingTests(unittest.TestCase):
    def test_fetch_excerpt_injected_and_new_fields(self):
        captured = {}

        class P:
            def chat(self, messages, model_id, tools=None):
                captured["user"] = messages[1]["content"]
                return json.dumps([{"title": "X", "type": "course", "url": "u1",
                                    "difficulty": "beginner", "fit_score": 9, "language": "中文",
                                    "cost": "免费", "relevance": 9, "use_hint": "先看前3章", "why": "好"}],
                                  ensure_ascii=False)

        st = SessionState(raw_goal="目标")
        st.profile = {"level": "beginner"}
        st.resources = [{"title": "X", "type": "course", "url": "u1"}, {"title": "Y", "url": "u2"}]
        with patch.object(A.sources, "fetch_url",
                          side_effect=lambda u, max_chars=300: ToolResult("fetch_url", True, "ok", data=f"正文-{u}")):
            ResourceEvaluationAgent(P(), "m").run(st)
        self.assertIn("excerpt", captured["user"])
        self.assertIn("正文-u1", captured["user"])
        self.assertEqual(st.evaluated_resources[0]["language"], "中文")
        self.assertEqual(st.evaluated_resources[0]["use_hint"], "先看前3章")

    def test_fetch_failure_degrades_without_crash(self):
        class P:
            def chat(self, messages, model_id, tools=None):
                return json.dumps([{"title": "X", "url": "u1", "fit_score": 7}], ensure_ascii=False)

        st = SessionState(raw_goal="目标")
        st.resources = [{"title": "X", "url": "u1"}]
        with patch.object(A.sources, "fetch_url", side_effect=RuntimeError("net down")):
            ResourceEvaluationAgent(P(), "m").run(st)   # 不抛
        self.assertEqual(len(st.evaluated_resources), 1)


class ResourceCardsTests(unittest.TestCase):
    def test_renders_new_fields_and_missing_compat(self):
        md = display.resource_cards([{"title": "A", "type": "course", "url": "u", "language": "中文",
                                      "cost": "免费", "difficulty": "beginner", "use_hint": "看前3章",
                                      "fit_score": 9, "why": "好"}])
        self.assertIn("🌐 中文", md)
        self.assertIn("💰 免费", md)
        self.assertIn("🎯 适合 beginner", md)
        self.assertIn("📌 用法：看前3章", md)
        md2 = display.resource_cards([{"title": "B", "type": "course", "url": "u"}])  # 缺字段
        self.assertIn("B", md2)
        self.assertNotIn("🌐", md2)


# ----------------------------- P3: 反馈重搜 ----------------------------- #
class FeedbackResearchTests(unittest.TestCase):
    def _make(self):
        calls = {"search": 0, "eval": 0, "refresh": 0, "render": 0}

        class Disp:
            def run(self, state):
                calls["render"] += 1

            def refresh_for_plan_change(self, state):
                calls["refresh"] += 1

        class Prov:
            def chat(self, messages, model_id, tools=None):
                return json.dumps({"stage_goals": ["a2"], "weekly_schedule": [], "milestones": []})

        return calls, Disp(), Prov()

    def _drive(self, st, calls, disp, prov, first_choice):
        choices = iter([first_choice, FeedbackAdjustmentAgent._MENU[0]])  # 一轮调整后“满意”
        with patch.object(A.interaction, "ask_choice", side_effect=lambda *a, **k: next(choices)), \
             patch.object(A.interaction, "ask_text", side_effect=lambda *a, **k: "中文"), \
             patch.object(A.ResourceSearchAgent, "run", lambda self, state: calls.__setitem__("search", calls["search"] + 1)), \
             patch.object(A.ResourceEvaluationAgent, "run", lambda self, state: calls.__setitem__("eval", calls["eval"] + 1)):
            FeedbackAdjustmentAgent(prov, "m", disp).run(st)

    def test_resource_choice_triggers_research(self):
        st = SessionState(raw_goal="目标")
        st.plan_structured = {"stage_goals": ["a"]}
        calls, disp, prov = self._make()
        self._drive(st, calls, disp, prov, FeedbackAdjustmentAgent._MENU[3])
        self.assertEqual(calls["search"], 1)
        self.assertEqual(calls["eval"], 1)
        self.assertEqual(calls["refresh"], 1)   # 计划也变了 → 刷新结构图
        self.assertGreaterEqual(calls["render"], 1)

    def test_non_resource_feedback_does_not_research(self):
        st = SessionState(raw_goal="目标")
        st.plan_structured = {"stage_goals": ["a"]}
        calls, disp, prov = self._make()
        self._drive(st, calls, disp, prov, "时间太紧，帮我压缩周期")
        self.assertEqual(calls["search"], 0)
        self.assertEqual(calls["eval"], 0)


class RefreshStructuralTests(unittest.TestCase):
    def test_refresh_regenerates_only_structural(self):
        with tempfile.TemporaryDirectory() as tmp:
            st = SessionState(raw_goal="目标")
            st.plan_structured = {"milestones": [{"name": "M1"}, {"name": "M2"}],
                                  "weekly_schedule": [{"week": 1, "output": "o1"}, {"week": 2, "output": "o2"}]}
            st.images = [{"anchor": "cover", "path": "assets/cover.png", "kind": "png"},
                         {"anchor": "learning_path", "path": "assets/STALE.svg", "kind": "svg"},
                         {"anchor": "deliverables", "path": "assets/STALE2.svg", "kind": "svg"}]
            with patch.object(A.image_gen, "get_image_key", return_value=None):
                MultimodalDisplayAgent(_Dummy(), "m", Path(tmp)).refresh_for_plan_change(st)
        anchors = {im["anchor"]: im["path"] for im in st.images}
        self.assertEqual(anchors["cover"], "assets/cover.png")                  # 不动
        self.assertEqual(anchors["learning_path"], "assets/learning-path.svg")  # 重生成
        self.assertEqual(anchors["deliverables"], "assets/deliverables.svg")


if __name__ == "__main__":
    unittest.main()
