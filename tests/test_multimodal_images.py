import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from common.agent.multi.agents import MultimodalDisplayAgent
from common.agent.multi.state import SessionState
from common.agent.tools.registry import ToolResult


class _FakeProvider:
    """视觉编排调用返回给定 visual_plan；其它调用（导语）返回普通文本。"""

    def __init__(self, visual_plan):
        self.vp = visual_plan

    def chat(self, messages, model_id, tools=None):
        if "视觉编排" in messages[0]["content"]:
            return json.dumps(self.vp, ensure_ascii=False)
        return "这份计划保持小步推进，每周都有明确产出。"


class _FakeRegistry:
    def __init__(self):
        self.calls = []

    def call(self, name, **kwargs):
        self.calls.append(kwargs)
        dest = Path(kwargs["dest_dir"])
        dest.mkdir(parents=True, exist_ok=True)
        (dest / kwargs["filename"]).write_bytes(b"PNG")
        return ToolResult(name=name, success=True, summary=f"saved {kwargs['filename']}", data={})


def _plan(stages=3, weeks=2):
    return {
        "long_term_goal": "目标",
        "stage_goals": [f"阶段{i}" for i in range(1, stages + 1)],
        "weekly_schedule": [{"week": i, "topic": f"主题{i}", "output": f"产出{i}"} for i in range(1, weeks + 1)],
        "milestones": [{"name": f"M{i}", "description": "x", "week": i} for i in range(1, 3)],
        "daily_suggestion": "每天 2 小时",
    }


def _run(visual_plan, plan, goal="两周入门 Python", key="sk-SECRET"):
    tmp = tempfile.mkdtemp()
    state = SessionState(raw_goal=goal)
    state.profile = {"domain": "x"}
    state.plan_structured = plan
    state.knowledge_outline = "概要"
    registry = _FakeRegistry()
    with patch("common.agent.multi.agents.image_gen.get_image_key", return_value=key):
        with patch("common.agent.multi.agents.image_gen.build_image_registry", return_value=registry):
            with redirect_stdout(StringIO()) as buf:
                agent = MultimodalDisplayAgent(_FakeProvider(visual_plan), "m", Path(tmp))
                agent.step_index, agent.step_total = 8, 9
                agent.run(state)
    return state, buf.getvalue(), registry


class MultimodalVisualTests(unittest.TestCase):
    def test_technical_topic_generates_png_diagrams_no_stage_images_no_leak(self):
        vp = {"section_visuals": [
            {"anchor": "knowledge_map", "type": "knowledge_map", "learning_purpose": "理解模块", "alt": "知识地图",
             "render_mode": "structured", "data": {"root": "Py", "modules": [
                 {"name": "基础", "topics": ["变量"]}, {"name": "Pandas", "topics": ["DF"]}, {"name": "图", "topics": ["plt"]}]}},
            {"anchor": "workflow", "type": "workflow", "learning_purpose": "理解流程", "alt": "流程",
             "render_mode": "structured", "data": {"steps": ["URL", "解析", "报告"]}},
            {"anchor": "x", "type": "skill_map", "learning_purpose": "", "render_mode": "structured",
             "data": {"steps": ["a", "b"]}},   # 无 learning_purpose -> 丢
        ], "atmosphere_images": [{"type": "cover", "learning_purpose": "氛围", "alt": "封面", "prompt": "cover"}]}
        state, out, reg = _run(vp, _plan())
        anchors = {im["anchor"]: im["kind"] for im in state.images}
        self.assertEqual(anchors.get("knowledge_map"), "png")
        self.assertEqual(anchors.get("workflow"), "png")
        self.assertEqual(anchors.get("learning_path"), "png")    # 代码驱动，优先 AI 图
        self.assertEqual(anchors.get("deliverables"), "png")     # AI 图生成，失败时才回退 SVG
        self.assertEqual(anchors.get("cover"), "png")
        self.assertNotIn("skill_map", anchors)                   # 被丢（无 purpose）
        self.assertFalse(any(str(a).startswith("stage:") for a in anchors))  # 无阶段插图
        md = state.display_markdown
        self.assertIn("![知识地图](assets/knowledge-map.png)", md)
        self.assertIn("assets/deliverables.png", md)
        self.assertIn("## 🔄 执行流程", md)
        self.assertNotIn("sk-SECRET", out + md)                  # key 不泄露
        diagram_call = next(c for c in reg.calls if c["filename"] == "knowledge-map.png")
        self.assertTrue(diagram_call["allow_text"])
        self.assertIn("Chinese knowledge map infographic", diagram_call["prompt"])

    def test_exam_topic_practice_loop(self):
        vp = {"section_visuals": [
            {"anchor": "practice_loop", "type": "practice_loop", "learning_purpose": "备考循环", "alt": "备考循环",
             "render_mode": "structured", "data": {"title": "备考循环", "steps": ["学知识", "做题", "复盘", "模考"]}}],
            "atmosphere_images": [{"type": "cover", "learning_purpose": "氛围", "alt": "封面", "prompt": "c"}]}
        state, out, reg = _run(vp, _plan(), goal="考研英语一 80 分")
        self.assertIn("## 🔁 练习循环", state.display_markdown)
        self.assertIn("assets/practice-loop.png", state.display_markdown)

    def test_simple_goal_downgrades_knowledge_and_skill(self):
        vp = {"section_visuals": [
            {"anchor": "knowledge_map", "type": "knowledge_map", "learning_purpose": "p", "alt": "k",
             "render_mode": "structured", "data": {"root": "Excel", "modules": [
                 {"name": "A", "topics": ["x"]}, {"name": "B", "topics": ["y"]}, {"name": "C", "topics": ["z"]}]}},
            {"anchor": "skill_map", "type": "skill_map", "learning_purpose": "p", "alt": "s",
             "render_mode": "structured", "data": {"steps": ["A", "B"]}}],
            "atmosphere_images": [{"type": "cover", "learning_purpose": "氛围", "alt": "封面", "prompt": "c"}]}
        state, out, reg = _run(vp, _plan(stages=1, weeks=1), goal="3 天学会 Excel")
        anchors = [im["anchor"] for im in state.images]
        self.assertNotIn("knowledge_map", anchors)
        self.assertNotIn("skill_map", anchors)

    def test_no_key_skips_png_but_keeps_svg(self):
        vp = {"section_visuals": [
            {"anchor": "workflow", "type": "workflow", "learning_purpose": "p", "alt": "流程",
             "render_mode": "structured", "data": {"steps": ["a", "b", "c"]}}],
            "atmosphere_images": [{"type": "cover", "learning_purpose": "氛围", "alt": "封面", "prompt": "c"}]}
        state, out, reg = _run(vp, _plan(), key=None)
        kinds = {im["anchor"]: im["kind"] for im in state.images}
        self.assertEqual(kinds.get("workflow"), "svg")
        self.assertNotIn("cover", kinds)                     # 无 key 不生成 PNG
        self.assertFalse(any(k == "png" for k in kinds.values()))
        self.assertEqual(reg.calls, [])
        self.assertIn("跳过 AI 图片", out)
        self.assertEqual(kinds.get("deliverables"), "svg")

    def test_deliverables_use_image_generation_prompt_when_key_available(self):
        state, out, reg = _run({"section_visuals": [], "atmosphere_images": []}, _plan(weeks=2))
        anchors = {im["anchor"]: im for im in state.images}
        self.assertEqual(anchors["deliverables"]["kind"], "png")
        self.assertEqual(anchors["deliverables"]["path"], "assets/deliverables.png")
        call = next(c for c in reg.calls if c["filename"] == "deliverables.png")
        self.assertTrue(call["allow_text"])
        self.assertIn("Chinese educational infographic", call["prompt"])
        self.assertIn("产出1", call["prompt"])

    def test_png_cap_only_counts_images(self):
        # 很多氛围 PNG 请求，但只生成 MAX_IMAGES 张氛围图；结构型学习辅助图不占用上限
        vp = {"section_visuals": [
            {"anchor": "workflow", "type": "workflow", "learning_purpose": "p", "alt": "流程",
             "render_mode": "structured", "data": {"steps": ["a", "b"]}}],
            "atmosphere_images": [
                {"type": "cover", "learning_purpose": "p", "alt": "封面", "prompt": "c"},
                {"type": "outcome", "learning_purpose": "p", "alt": "成果", "prompt": "o"},
                {"type": "representational", "learning_purpose": "p", "alt": "插图1", "prompt": "i1"},
                {"type": "representational", "learning_purpose": "p", "alt": "插图2", "prompt": "i2"},
                {"type": "representational", "learning_purpose": "p", "alt": "插图3", "prompt": "i3"}]}
        state, out, reg = _run(vp, _plan())
        atmosphere = [
            im for im in state.images
            if im["anchor"] in ("cover", "outcome", "concept_summary")
            or str(im["anchor"]).startswith("illustration:")
        ]
        self.assertLessEqual(len(atmosphere), MultimodalDisplayAgent.MAX_IMAGES)
        kinds = {im["anchor"]: im["kind"] for im in state.images}
        self.assertEqual(kinds.get("workflow"), "png")

    def test_image_visual_without_prompt_dropped_and_reuse(self):
        vp = {"section_visuals": [
            {"anchor": "concept_summary", "type": "concept_summary", "learning_purpose": "p", "alt": "概念",
             "render_mode": "image"},   # 缺 prompt -> 丢
            {"anchor": "workflow", "type": "workflow", "learning_purpose": "p", "alt": "流程",
             "render_mode": "structured", "data": {"steps": ["a", "b"]}}],
            "atmosphere_images": [{"type": "cover", "learning_purpose": "p", "alt": "封面", "prompt": "c"}]}
        state, out, reg = _run(vp, _plan())
        anchors = [im["anchor"] for im in state.images]
        self.assertNotIn("concept_summary", anchors)
        # 二次渲染复用，不再调用生成
        before = list(state.images)
        with patch("common.agent.multi.agents.image_gen.get_image_key", return_value="sk-SECRET"):
            with patch("common.agent.multi.agents.image_gen.build_image_registry", return_value=_FakeRegistry()):
                with redirect_stdout(StringIO()):
                    agent = MultimodalDisplayAgent(_FakeProvider(vp), "m", Path(tempfile.mkdtemp()))
                    agent.run(state)
        self.assertEqual(state.images, before)


if __name__ == "__main__":
    unittest.main()
