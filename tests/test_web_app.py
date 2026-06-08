import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from common.agent.multi.state import SessionState
from common.agent.web_app import (
    WebConfigStore,
    WebPlannerService,
    WebSession,
    _safe_child,
    apply_runtime_config,
    delete_saved_plan,
    list_saved_plans,
    open_saved_plan_folder,
    save_final_artifacts,
)


class _Provider:
    reply_label = "Fake"

    def chat(self, messages, model_id, tools=None):
        return json.dumps([{"stage": "S1", "items": [{"q": "Q?", "a": "A"}]}])


class _Agent:
    def __init__(self, provider=None, model_id=None, root=None):
        self.provider = provider
        self.model_id = model_id
        self.root = root

    def run(self, state):
        print(f"{self.__class__.__name__} done")
        state.agent_log.append(f"[{self.__class__.__name__}] done")
        state.display_markdown = "# Draft"
        state.evaluated_resources = [{"title": "R"}]


class _FailingAgent(_Agent):
    def run(self, state):
        raise RuntimeError("agent exploded")


def _state():
    st = SessionState(raw_goal="测试 Web 学习计划")
    st.display_markdown = "# Web 计划\n\n正文"
    st.plan_structured = {
        "stage_goals": ["阶段一"],
        "weekly_schedule": [{"week": 1, "topic": "入门", "output": "笔记"}],
        "milestones": [{"week": 1, "name": "M1"}],
    }
    return st


class WebAppSupportTests(unittest.TestCase):
    def test_config_store_persists_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = WebConfigStore(Path(tmp))
            saved = store.save({
                "provider": "kimi",
                "model_id": "kimi-k2.6",
                "main_api_key": "sk-main",
                "image_model": "m3",
                "minimax_image_key": "sk-image",
                "tavily_key": "tvly-test",
                "global_memory": "偏好中文资源",
            })
            loaded = store.load()
        self.assertEqual(saved["provider"], "kimi")
        self.assertEqual(loaded["global_memory"], "偏好中文资源")
        self.assertEqual(loaded["main_api_key"], "sk-main")

    def test_apply_runtime_config_sets_environment_keys(self):
        with patch.dict("os.environ", {}, clear=True):
            apply_runtime_config({
                "provider": "deepseek",
                "main_api_key": "sk-deep",
                "image_model": "m3",
                "minimax_image_key": "sk-img",
                "tavily_key": "tvly",
            })
            import os

            self.assertEqual(os.environ["DEEPSEEK_API_KEY"], "sk-deep")
            self.assertEqual(os.environ["MINIMAX_IMAGE_MODEL"], "m3")
            self.assertEqual(os.environ["MINIMAX_API_KEY"], "sk-img")
            self.assertEqual(os.environ["TAVILY_API_KEY"], "tvly")

    def test_list_saved_plans_reads_canonical_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_dir = root / "plans" / "目标A"
            pkg = plan_dir / "m3-package"
            pkg.mkdir(parents=True)
            report = plan_dir / "m3-multiagent.md"
            report.write_text("# 学习规划（多智能体）：目标A\n\n正文", encoding="utf-8")
            (pkg / "daily-checklist.md").write_text("- [ ] task", encoding="utf-8")

            plans = list_saved_plans(root)

        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0]["title"], "目标A")
        self.assertTrue(plans[0]["has_package"])
        self.assertIn("m3-multiagent.md", plans[0]["report_path"])

    def test_save_final_artifacts_writes_report_and_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = save_final_artifacts(root, _state(), "m3", _Provider())

            self.assertTrue(Path(result["report_path"]).exists())
            self.assertTrue(Path(result["package_dir"]).exists())
            self.assertTrue((Path(result["package_dir"]) / "quiz.md").exists())
            self.assertTrue(Path(result["folder_path"]).exists())
            self.assertTrue(result["plan_id"])
            self.assertEqual(Path(result["folder_path"]), Path(result["report_path"]).parent)
            self.assertIn("daily-checklist.md", result["package_files"])

    def test_open_saved_plan_folder_opens_report_parent(self):
        opened = []
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_dir = root / "plans" / "Goal"
            plan_dir.mkdir(parents=True)
            report = plan_dir / "m3-multiagent.md"
            report.write_text("# Plan", encoding="utf-8")
            path_id = list_saved_plans(root)[0]["id"]

            result = open_saved_plan_folder(root, path_id, opener=opened.append)

        self.assertEqual(opened, [Path(result["folder_path"])])
        self.assertEqual(Path(result["folder_path"]).name, "Goal")

    def test_delete_saved_plan_removes_plan_folder_and_refreshes_list_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_dir = root / "plans" / "Goal"
            pkg = plan_dir / "m3-package"
            pkg.mkdir(parents=True)
            report = plan_dir / "m3-multiagent.md"
            report.write_text("# Plan", encoding="utf-8")
            (pkg / "plan.md").write_text("# Copy", encoding="utf-8")
            path_id = list_saved_plans(root)[0]["id"]

            result = delete_saved_plan(root, path_id)

            self.assertEqual(Path(result["folder_path"]).name, "Goal")
            self.assertFalse(plan_dir.exists())
            self.assertEqual(list_saved_plans(root), [])

    def test_frontend_layout_uses_sidebar_settings_and_folder_workspace(self):
        root = Path(__file__).resolve().parents[1]
        index = (root / "web" / "index.html").read_text(encoding="utf-8")
        app = (root / "web" / "app.js").read_text(encoding="utf-8")

        self.assertIn('id="settingsButton"', index)
        self.assertIn('id="settingsModal"', index)
        self.assertIn('id="imageModel"', index)
        self.assertIn('value="m3"', index)
        self.assertIn('id="openFolderBtn"', index)
        self.assertIn('rel="icon"', index)
        self.assertIn('autocomplete="off"', index)
        self.assertIn("selectedImageModel", app)
        self.assertNotIn('id="tab-settings"', index)
        self.assertIn("/api/open-folder", app)

    def test_frontend_supports_resizable_chat_workspace_split(self):
        root = Path(__file__).resolve().parents[1]
        index = (root / "web" / "index.html").read_text(encoding="utf-8")
        app = (root / "web" / "app.js").read_text(encoding="utf-8")
        styles = (root / "web" / "styles.css").read_text(encoding="utf-8")

        self.assertIn('id="splitResizer"', index)
        self.assertIn('role="separator"', index)
        self.assertIn("initResizableSplit", app)
        self.assertIn("pointerdown", app)
        self.assertIn("studyPlannerSplit", app)
        self.assertIn("clampSplitRatio", app)
        self.assertIn("--chat-width", styles)
        self.assertNotIn("--chat-fr", styles)
        self.assertNotIn("--workspace-fr", styles)
        self.assertIn(".split-resizer", styles)

    def test_frontend_keeps_chat_pane_fixed_with_internal_scroll(self):
        root = Path(__file__).resolve().parents[1]
        styles = (root / "web" / "styles.css").read_text(encoding="utf-8")

        self.assertIn("height: calc(100vh - 36px)", styles)
        self.assertIn("min-height: 0", styles)
        self.assertIn("overflow: auto", styles)
        self.assertIn("flex: 1 1 auto", styles)

    def test_frontend_gives_agent_output_room_and_uses_quiet_theme(self):
        root = Path(__file__).resolve().parents[1]
        styles = (root / "web" / "styles.css").read_text(encoding="utf-8")

        self.assertIn("min-height: clamp(300px, 44vh, 520px)", styles)
        self.assertIn("#goalInput", styles)
        self.assertIn("max-height: 150px", styles)
        self.assertIn("--accent: #2f6f5e", styles)
        self.assertNotIn("--accent: #3d63ff", styles)
        self.assertNotIn("linear-gradient(135deg, var(--accent), #6f86ff)", styles)

    def test_frontend_supports_light_dark_theme_controls(self):
        root = Path(__file__).resolve().parents[1]
        index = (root / "web" / "index.html").read_text(encoding="utf-8")
        app = (root / "web" / "app.js").read_text(encoding="utf-8")
        styles = (root / "web" / "styles.css").read_text(encoding="utf-8")

        self.assertIn('id="themeQuickSwitch"', index)
        self.assertIn('id="appearanceCard"', index)
        self.assertIn('data-theme-choice="light"', index)
        self.assertIn('data-theme-choice="dark"', index)
        self.assertIn('data-theme-choice="system"', index)
        self.assertIn("studyPlannerTheme", app)
        self.assertIn("initTheme", app)
        self.assertIn("applyTheme", app)
        self.assertIn('document.documentElement.dataset.theme', app)
        self.assertIn(':root[data-theme="dark"]', styles)
        self.assertIn(".theme-card", styles)
        self.assertIn(".theme-quick", styles)

    def test_frontend_supports_canvas_background_styles(self):
        root = Path(__file__).resolve().parents[1]
        index = (root / "web" / "index.html").read_text(encoding="utf-8")
        app = (root / "web" / "app.js").read_text(encoding="utf-8")
        styles = (root / "web" / "styles.css").read_text(encoding="utf-8")

        self.assertIn('id="canvasStyleGroup"', index)
        self.assertIn('data-canvas-style="plain"', index)
        self.assertIn('data-canvas-style="grid"', index)
        self.assertIn('data-canvas-style="paper"', index)
        self.assertIn('data-canvas-style="texture"', index)
        self.assertIn("studyPlannerCanvasStyle", app)
        self.assertIn("initCanvasStyle", app)
        self.assertIn("applyCanvasStyle", app)
        self.assertIn("document.documentElement.dataset.canvasStyle", app)
        self.assertIn(':root[data-canvas-style="grid"] .main::before', styles)
        self.assertIn(':root[data-canvas-style="paper"] .main::before', styles)
        self.assertIn(':root[data-canvas-style="texture"] .main::before', styles)
        self.assertIn("repeating-linear-gradient", styles)
        self.assertIn(".canvas-style-grid", styles)
        self.assertIn(".canvas-card", styles)

    def test_frontend_can_delete_saved_plans_and_sync_list(self):
        root = Path(__file__).resolve().parents[1]
        app = (root / "web" / "app.js").read_text(encoding="utf-8")
        styles = (root / "web" / "styles.css").read_text(encoding="utf-8")

        self.assertIn("/api/plan/delete", app)
        self.assertIn("deletePlan", app)
        self.assertIn("renderPlanList", app)
        self.assertIn("plan-menu", app)
        self.assertIn(".plan-row", styles)
        self.assertIn(".plan-menu", styles)

    def test_frontend_uses_clarify_deck_and_sse_status_stream(self):
        root = Path(__file__).resolve().parents[1]
        index = (root / "web" / "index.html").read_text(encoding="utf-8")
        app = (root / "web" / "app.js").read_text(encoding="utf-8")
        styles = (root / "web" / "styles.css").read_text(encoding="utf-8")

        self.assertIn('id="clarifyDeck"', index)
        self.assertIn('id="agentTimeline"', index)
        self.assertNotIn('id="agentLogStream"', index)
        self.assertIn("clarifyState", app)
        self.assertIn("renderClarifyCard", app)
        self.assertIn("EventSource", app)
        self.assertIn("/api/session/events", app)
        self.assertIn("connectStatusStream", app)
        self.assertIn("addAgentLogBubble", app)
        self.assertIn("showError", app)
        self.assertIn(".clarify-deck", styles)
        self.assertIn(".agent-timeline", styles)
        self.assertNotIn(".agent-log-stream", styles)

    def test_frontend_clarify_and_agent_status_do_not_overflow(self):
        root = Path(__file__).resolve().parents[1]
        styles = (root / "web" / "styles.css").read_text(encoding="utf-8")

        self.assertIn(".clarify-card", styles)
        self.assertIn("max-height: min(460px, 46vh)", styles)
        self.assertIn("flex-direction: column", styles)
        self.assertIn(".clarify-options", styles)
        self.assertIn("overflow-y: auto", styles)
        self.assertIn("scrollbar-gutter: stable", styles)
        self.assertIn("overscroll-behavior: contain", styles)
        self.assertIn("grid-template-columns: repeat(auto-fit, minmax(142px, 1fr))", styles)
        self.assertIn("overflow-x: hidden", styles)
        self.assertIn("min-width: 0", styles)
        self.assertIn("white-space: normal", styles)
        self.assertNotIn("overflow-x: auto", styles)

    def test_frontend_keeps_feedback_and_save_actions_reachable_after_draft(self):
        root = Path(__file__).resolve().parents[1]
        app = (root / "web" / "app.js").read_text(encoding="utf-8")
        styles = (root / "web" / "styles.css").read_text(encoding="utf-8")

        self.assertIn(".chat-pane", styles)
        self.assertIn("overflow-y: auto", styles)
        self.assertIn("scrollbar-gutter: stable", styles)
        self.assertIn("overscroll-behavior: contain", styles)
        self.assertIn(".toolbar", styles)
        self.assertIn("position: sticky", styles)
        self.assertIn("scrollChatPaneToActions", app)
        self.assertIn("requestAnimationFrame", app)
        self.assertIn("scrollHeight", app)

    def test_frontend_uses_single_composer_for_plan_feedback(self):
        root = Path(__file__).resolve().parents[1]
        index = (root / "web" / "index.html").read_text(encoding="utf-8")
        app = (root / "web" / "app.js").read_text(encoding="utf-8")

        self.assertNotIn('id="feedbackPanel"', index)
        self.assertNotIn('id="feedbackInput"', index)
        self.assertIn('id="draftActionBar"', index)
        self.assertIn('id="saveBtn"', index)
        self.assertIn("submitFeedbackFromComposer", app)
        self.assertIn("isDraftReady", app)

    def test_frontend_resets_to_new_plan_after_successful_save(self):
        root = Path(__file__).resolve().parents[1]
        app = (root / "web" / "app.js").read_text(encoding="utf-8")

        self.assertIn("resetToNewPlanAfterSave", app)
        self.assertIn("resetToNewPlan(", app)
        self.assertIn("currentSession = null", app)
        self.assertIn("latestSaved = null", app)
        self.assertIn('renderMarkdown("")', app)
        self.assertIn("renderFolderWorkspace(null)", app)
        self.assertIn("await loadPlans()", app)

    def test_safe_child_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "plan"
            base.mkdir()
            self.assertEqual(_safe_child(base, "assets/a.png"), (base / "assets" / "a.png").resolve())
            with self.assertRaises(ValueError):
                _safe_child(base, "../secret.txt")

    def test_answer_returns_running_and_emits_sse_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = WebPlannerService(Path(tmp))
            session = WebSession("s1", _Provider(), "m3", _state(), Path(tmp))
            service.sessions[session.id] = session
            patches = [
                patch("common.agent.web_app.ProfileMemoryAgent", _Agent),
                patch("common.agent.web_app.ResourceSearchAgent", _Agent),
                patch("common.agent.web_app.ResourceEvaluationAgent", _Agent),
                patch("common.agent.web_app.KnowledgeOrganizationAgent", _Agent),
                patch("common.agent.web_app.PlanGenerationAgent", _Agent),
                patch("common.agent.web_app.MultimodalDisplayAgent", _Agent),
            ]
            for p in patches:
                p.start()
            try:
                payload = service.answer("s1", {"水平": "刚入门"}, "")
                self.assertEqual(payload["status"], "running")
                self.assertTrue(payload["is_running"])

                deadline = time.time() + 3
                events = []
                while time.time() < deadline:
                    events = service.events_since("s1", 0, timeout=0.05)
                    if any(event["type"] == "result" for event in events):
                        break
                types = [event["type"] for event in events]
                self.assertIn("phase", types)
                self.assertIn("log", types)
                self.assertIn("result", types)
                self.assertEqual(service._get("s1").status, "draft")
            finally:
                for p in reversed(patches):
                    p.stop()

    def test_background_agent_error_emits_error_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = WebPlannerService(Path(tmp))
            session = WebSession("s2", _Provider(), "m3", _state(), Path(tmp))
            service.sessions[session.id] = session
            with patch("common.agent.web_app.ProfileMemoryAgent", _FailingAgent):
                payload = service.answer("s2", {"水平": "刚入门"}, "")
                self.assertEqual(payload["status"], "running")

                deadline = time.time() + 3
                events = []
                while time.time() < deadline:
                    events = service.events_since("s2", 0, timeout=0.05)
                    if any(event["type"] == "error" for event in events):
                        break
                error_events = [event for event in events if event["type"] == "error"]
                self.assertTrue(error_events)
                self.assertIn("agent exploded", error_events[-1]["data"]["message"])
                self.assertFalse(service._get("s2").is_running)


if __name__ == "__main__":
    unittest.main()
