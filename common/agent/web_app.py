"""Local web workspace for the Study Planner Agent.

The web layer keeps the existing multi-agent business logic intact, but replaces
terminal prompts with HTTP endpoints:

1. start a planning chat and generate clarification questions
2. submit clarification answers and generate a draft plan
3. send optional feedback to adjust the draft
4. confirm/save, which writes the canonical report and learning package

It intentionally uses only the Python standard library plus the project's
existing dependencies, so the web UI can run without npm or extra Python
packages.
"""

from __future__ import annotations

import base64
import contextlib
import io
import json
import mimetypes
import os
import shutil
import subprocess
import sys
import threading
import uuid
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from common.agent.multi.agents import (
    ClarificationAgent,
    FeedbackAdjustmentAgent,
    KnowledgeOrganizationAgent,
    MultimodalDisplayAgent,
    PlanGenerationAgent,
    ProfileMemoryAgent,
    ResourceEvaluationAgent,
    ResourceSearchAgent,
    RouterAgent,
)
from common.agent.multi.display import parse_resources_from_report
from common.agent.multi.pipeline import _save
from common.agent.multi.package import export_learning_package
from common.agent.multi.state import SessionState
from common.providers.base import ensure_study_agents_path


WEB_DIR = Path(__file__).resolve().parents[2] / "web"


DEFAULT_SETTINGS = {
    "provider": "minimax",
    "model_id": "m3",
    "main_api_key": "",
    "image_model": "m3",
    "minimax_image_key": "",
    "tavily_key": "",
    "global_memory": "",
    "deep_thinking": "on",   # 深度思考开关（UI 偏好，持久化为 "on"/"off"）
}

PACKAGE_FILE_NAMES = ("plan.md", "daily-checklist.md", "review-log.md", "quiz.md")

PROVIDER_MODEL_DEFAULTS = {
    "kimi": "kimi-k2.6",
    "minimax": "m3",
    "deepseek": "deepseek-v4-flash",
}

PROVIDER_ENV = {
    "kimi": "MOONSHOT_API_KEY",
    "minimax": "MINIMAX_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
}


class WebConfigStore:
    """Small JSON settings store for local API keys and global memory."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.path = self.root / "web_data" / "settings.json"

    def load(self) -> dict:
        data = dict(DEFAULT_SETTINGS)
        try:
            if self.path.exists():
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    data.update({k: str(v) for k, v in loaded.items() if k in data})
        except Exception:
            pass
        return data

    def save(self, settings: dict) -> dict:
        current = self.load()
        for key in DEFAULT_SETTINGS:
            if key in settings:
                current[key] = str(settings.get(key) or "").strip()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
        apply_runtime_config(current)
        return current


def apply_runtime_config(settings: dict) -> None:
    """Expose keys to existing tools/providers without changing their APIs."""

    provider = str(settings.get("provider") or "minimax").strip().lower()
    main_key = str(settings.get("main_api_key") or "").strip()
    env_name = PROVIDER_ENV.get(provider)
    if env_name and main_key:
        os.environ[env_name] = main_key

    image_key = str(settings.get("minimax_image_key") or "").strip()
    image_model = str(settings.get("image_model") or "m3").strip()
    if image_model:
        os.environ["MINIMAX_IMAGE_MODEL"] = image_model
    if image_key:
        os.environ["MINIMAX_API_KEY"] = image_key
    elif provider == "minimax" and main_key:
        os.environ["MINIMAX_API_KEY"] = main_key

    tavily_key = str(settings.get("tavily_key") or "").strip()
    if tavily_key:
        os.environ["TAVILY_API_KEY"] = tavily_key


def create_provider(provider_name: str, api_key: str):
    name = (provider_name or "minimax").lower()
    if name == "kimi":
        from providers.kimi_impl import KimiProvider

        provider = KimiProvider()
    elif name == "deepseek":
        from providers.deepseek_impl import DeepSeekProvider

        provider = DeepSeekProvider()
    else:
        from providers.minimax_impl import MiniMaxProvider

        provider = MiniMaxProvider()

    provider.api_key = api_key.strip()
    if not provider.api_key:
        env_name = PROVIDER_ENV.get(name, "")
        provider.api_key = os.environ.get(env_name, "").strip()
    return provider


def _rel_id(root: Path, path: Path) -> str:
    rel = path.resolve().relative_to(root.resolve()).as_posix()
    return base64.urlsafe_b64encode(rel.encode("utf-8")).decode("ascii")


def _path_from_id(root: Path, path_id: str) -> Path:
    rel = base64.urlsafe_b64decode(path_id.encode("ascii")).decode("utf-8")
    path = (root / rel).resolve()
    if root.resolve() not in path.parents and path != root.resolve():
        raise ValueError("path outside workspace")
    return path


def _safe_child(base: Path, rel: str) -> Path:
    rel = unquote(rel or "").replace("\\", "/").lstrip("/")
    path = (base / rel).resolve()
    if base.resolve() not in path.parents and path != base.resolve():
        raise ValueError("path outside plan directory")
    return path


def list_saved_plans(root: Path) -> list[dict]:
    plans_dir = Path(root) / "plans"
    if not plans_dir.exists():
        return []
    items: list[dict] = []
    for report in sorted(plans_dir.glob("*/*-multiagent.md"), key=lambda p: p.stat().st_mtime, reverse=True):
        plan_dir = report.parent
        title = plan_dir.name
        try:
            first = report.read_text(encoding="utf-8").splitlines()[0]
            if "：" in first:
                title = first.split("：", 1)[1].strip()
        except Exception:
            pass
        package_dirs = list(plan_dir.glob("*-package"))
        package_files = _package_file_names(package_dirs[0]) if package_dirs else []
        items.append({
            "id": _rel_id(root, report),
            "title": title,
            "model": report.name.replace("-multiagent.md", ""),
            "report_path": str(report),
            "folder_path": str(plan_dir),
            "updated_at": report.stat().st_mtime,
            "has_package": any(p.is_dir() for p in package_dirs),
            "package_dir": str(package_dirs[0]) if package_dirs else "",
            "package_files": package_files,
        })
    return items


def _package_file_names(package_dir: Path) -> list[str]:
    return [name for name in PACKAGE_FILE_NAMES if (package_dir / name).exists()]


def save_final_artifacts(root: Path, state: SessionState, model_id: str, provider) -> dict:
    report_path = _save(Path(root), state, model_id, provider.reply_label)
    package_dir = export_learning_package(provider, model_id, Path(root), state)
    package_path = Path(package_dir) if package_dir else None
    return {
        "plan_id": _rel_id(Path(root), report_path),
        "report_path": str(report_path),
        "folder_path": str(report_path.parent),
        "package_dir": str(package_dir) if package_dir else "",
        "package_files": _package_file_names(package_path) if package_path else [],
    }


def open_saved_plan_folder(root: Path, path_id: str, opener=None) -> dict:
    report = _path_from_id(Path(root), path_id)
    if not report.exists() or not report.name.endswith("-multiagent.md"):
        raise ValueError("saved plan report not found")
    folder = report.parent.resolve()
    (opener or _open_folder)(folder)
    return {"folder_path": str(folder)}


def delete_saved_plan(root: Path, path_id: str) -> dict:
    workspace = Path(root).resolve()
    plans_dir = (workspace / "plans").resolve()
    report = _path_from_id(workspace, path_id)
    if not report.exists() or not report.name.endswith("-multiagent.md"):
        raise ValueError("saved plan report not found")

    folder = report.parent.resolve()
    if folder.parent != plans_dir or not folder.is_dir():
        raise ValueError("invalid saved plan folder")

    shutil.rmtree(folder)
    return {"folder_path": str(folder), "deleted": True}


def _open_folder(path: Path) -> None:
    if not path.exists() or not path.is_dir():
        raise ValueError("folder not found")
    if os.name == "nt":
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


@dataclass
class WebSession:
    id: str
    provider: Any
    model_id: str
    state: SessionState
    root: Path
    global_memory: str = ""
    messages: list[dict] = field(default_factory=list)
    questions: list[dict] = field(default_factory=list)
    status: str = "created"
    saved: dict | None = None
    events: list[dict] = field(default_factory=list)
    event_seq: int = 0
    event_condition: threading.Condition = field(default_factory=threading.Condition, repr=False)
    is_running: bool = False
    last_error: str = ""


class WebPlannerService:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.sessions: dict[str, WebSession] = {}
        self.lock = threading.Lock()

    def start(self, payload: dict) -> dict:
        settings = WebConfigStore(self.root).load()
        merged = {**settings, **{k: v for k, v in payload.items() if v not in (None, "")}}
        apply_runtime_config(merged)

        goal = str(payload.get("goal") or "").strip()
        if not goal:
            raise ValueError("请输入学习目标")
        provider_name = str(merged.get("provider") or "minimax").lower()
        model_id = str(merged.get("model_id") or PROVIDER_MODEL_DEFAULTS.get(provider_name, "m3"))
        provider = create_provider(provider_name, str(merged.get("main_api_key") or ""))
        if not provider.api_key:
            raise ValueError("请先在设置里填写主模型 API Key")

        state = SessionState(raw_goal=goal)
        global_memory = str(merged.get("global_memory") or "").strip()
        if global_memory:
            state.clarifications["全局记忆"] = global_memory
            state.profile["global_memory"] = global_memory

        sid = uuid.uuid4().hex[:12]
        session = WebSession(sid, provider, model_id, state, self.root, global_memory)
        with self.lock:
            self.sessions[sid] = session

        output = _capture(lambda: RouterAgent(provider, model_id).run(state))
        session.messages.append({"role": "assistant", "content": output})

        questions = self._clarification_questions(session)
        session.questions = questions
        session.status = "clarifying"
        return self._session_payload(session)

    def _clarification_questions(self, session: WebSession) -> list[dict]:
        agent = ClarificationAgent(session.provider, session.model_id)
        try:
            questions = agent.think_json(f"用户学习目标：\n{session.state.raw_goal}")
        except Exception:
            questions = None
        if not isinstance(questions, list) or not questions:
            questions = ClarificationAgent._fallback
        valid = []
        for q in questions:
            if isinstance(q, dict) and q.get("question") and isinstance(q.get("options"), list):
                valid.append({"question": str(q["question"]), "options": [str(o) for o in q["options"]]})
        return valid or ClarificationAgent._fallback

    def answer(self, session_id: str, answers: dict, extra: str = "") -> dict:
        session = self._get(session_id)
        for q, a in (answers or {}).items():
            if str(a).strip():
                session.state.clarifications[str(q)] = str(a).strip()
        if extra.strip():
            session.state.clarifications["补充说明"] = extra.strip()

        if not session.is_running:
            session.status = "running"
            session.is_running = True
            session.last_error = ""
            self._emit_event(session, "phase", {"phase": "准备运行", "status": "running"})
            payload = self._session_payload(session)
            thread = threading.Thread(target=self._run_remaining_agents, args=(session,), daemon=True)
            thread.start()
            return payload
        return self._session_payload(session)

    def events_since(self, session_id: str, last_id: int = 0, timeout: float = 20.0) -> list[dict]:
        session = self._get(session_id)
        with session.event_condition:
            if not any(event["id"] > last_id for event in session.events):
                session.event_condition.wait(timeout=timeout)
            events = [event for event in session.events if event["id"] > last_id]
        if not events:
            return [self._format_event(0, "heartbeat", {"status": session.status})]
        return events

    def _run_remaining_agents(self, session: WebSession) -> None:
        logs: list[str] = []
        try:
            chain = [
                ("画像与记忆", lambda: ProfileMemoryAgent(session.provider, session.model_id, session.root)),
                ("资源搜索", lambda: ResourceSearchAgent(session.provider, session.model_id)),
                ("资源评估", lambda: ResourceEvaluationAgent(session.provider, session.model_id)),
                ("知识整理", lambda: KnowledgeOrganizationAgent(session.provider, session.model_id)),
                ("计划生成", lambda: PlanGenerationAgent(session.provider, session.model_id)),
                ("多模态展示", lambda: MultimodalDisplayAgent(session.provider, session.model_id, session.root)),
            ]
            for phase, make_agent in chain:
                self._emit_event(session, "phase", {"phase": phase, "status": "running"})
                output = _capture(lambda: make_agent().run(session.state))
                if output.strip():
                    logs.append(output)
                    self._emit_event(session, "log", {"phase": phase, "text": output})
                self._emit_event(session, "phase", {"phase": phase, "status": "done"})
            session.messages.append({"role": "assistant", "content": "\n".join(logs)})
            session.status = "draft"
            session.is_running = False
            self._emit_event(session, "result", self._session_payload(session))
        except Exception as err:
            session.status = "error"
            session.is_running = False
            session.last_error = str(err)
            self._emit_event(session, "error", {"message": str(err)})

    def _emit_event(self, session: WebSession, event_type: str, data: dict) -> dict:
        with session.event_condition:
            session.event_seq += 1
            event = self._format_event(session.event_seq, event_type, data)
            session.events.append(event)
            if len(session.events) > 300:
                session.events = session.events[-300:]
            session.event_condition.notify_all()
            return event

    @staticmethod
    def _format_event(event_id: int, event_type: str, data: dict) -> dict:
        return {"id": event_id, "type": event_type, "data": data}

    def feedback(self, session_id: str, feedback_text: str) -> dict:
        session = self._get(session_id)
        feedback = str(feedback_text or "").strip()
        if not feedback:
            raise ValueError("请输入反馈内容")

        display_agent = MultimodalDisplayAgent(session.provider, session.model_id, session.root)
        agent = FeedbackAdjustmentAgent(session.provider, session.model_id, display_agent)

        def apply_feedback() -> None:
            is_resource = agent._is_resource_feedback("", feedback)
            if is_resource:
                agent._research_resources(session.state, feedback)
            user_content = (
                f"用户反馈：{feedback}\n\n"
                f"现有计划：{json.dumps(session.state.plan_structured, ensure_ascii=False)}"
            )
            new_plan = agent.think_json(user_content)
            if isinstance(new_plan, dict) and new_plan:
                session.state.plan_structured = new_plan
                session.state.plan_markdown = ""
                display_agent.refresh_for_plan_change(session.state)
            session.state.feedback_rounds.append({"feedback": feedback})
            session.state.log("反馈调整", f"Web 反馈调整：{feedback[:30]}")
            display_agent.run(session.state)

        output = _capture(apply_feedback)
        session.messages.append({"role": "user", "content": feedback})
        session.messages.append({"role": "assistant", "content": output})
        session.status = "draft"
        return self._session_payload(session)

    def save(self, session_id: str) -> dict:
        session = self._get(session_id)
        result = save_final_artifacts(session.root, session.state, session.model_id, session.provider)
        session.saved = result
        session.status = "saved"
        return self._session_payload(session)

    def _get(self, session_id: str) -> WebSession:
        with self.lock:
            session = self.sessions.get(session_id)
        if not session:
            raise ValueError("会话不存在或已过期")
        return session

    def _session_payload(self, session: WebSession) -> dict:
        return {
            "session_id": session.id,
            "status": session.status,
            "is_running": session.is_running,
            "last_error": session.last_error,
            "questions": session.questions,
            "messages": session.messages[-8:],
            "markdown": session.state.display_markdown or session.state.plan_markdown,
            "resources": session.state.evaluated_resources,
            "agent_log": session.state.agent_log,
            "saved": session.saved,
        }


def _capture(fn) -> str:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn()
    return buf.getvalue()


class StudyPlannerWebHandler(BaseHTTPRequestHandler):
    service: WebPlannerService
    config_store: WebConfigStore
    root: Path

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/":
                self._serve_file(WEB_DIR / "index.html")
            elif parsed.path in ("/app.js", "/styles.css"):
                self._serve_file(WEB_DIR / parsed.path.lstrip("/"))
            elif parsed.path == "/api/settings":
                self._json(self.config_store.load())
            elif parsed.path == "/api/plans":
                self._json({"plans": list_saved_plans(self.root)})
            elif parsed.path == "/api/plan":
                self._handle_plan_read(parsed.query)
            elif parsed.path == "/api/asset":
                self._handle_asset_read(parsed.query)
            elif parsed.path == "/api/session/asset":
                self._handle_session_asset_read(parsed.query)
            elif parsed.path == "/api/session/events":
                self._handle_session_events(parsed.query)
            else:
                self.send_error(404)
        except Exception as err:
            self._json({"error": str(err)}, status=500)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        try:
            payload = self._read_json()
            if parsed.path == "/api/settings":
                self._json(self.config_store.save(payload))
            elif parsed.path == "/api/session/start":
                self._json(self.service.start(payload))
            elif parsed.path == "/api/session/answer":
                self._json(self.service.answer(
                    str(payload.get("session_id") or ""),
                    payload.get("answers") or {},
                    str(payload.get("extra") or ""),
                ))
            elif parsed.path == "/api/session/feedback":
                self._json(self.service.feedback(
                    str(payload.get("session_id") or ""),
                    str(payload.get("feedback") or ""),
                ))
            elif parsed.path == "/api/session/save":
                self._json(self.service.save(str(payload.get("session_id") or "")))
            elif parsed.path == "/api/open-folder":
                self._json(open_saved_plan_folder(self.root, str(payload.get("id") or "")))
            elif parsed.path == "/api/plan/delete":
                self._json(delete_saved_plan(self.root, str(payload.get("id") or "")))
            else:
                self.send_error(404)
        except Exception as err:
            self._json({"error": str(err)}, status=400)

    def _handle_plan_read(self, query: str) -> None:
        params = parse_qs(query)
        path_id = params.get("id", [""])[0]
        artifact = params.get("artifact", ["report"])[0]
        report = _path_from_id(self.root, path_id)
        if artifact == "package":
            package_dirs = list(report.parent.glob("*-package"))
            files = {}
            for pkg in package_dirs[:1]:
                for name in PACKAGE_FILE_NAMES:
                    path = pkg / name
                    if path.exists():
                        files[name] = path.read_text(encoding="utf-8")
            self._json({"files": files})
            return
        content = report.read_text(encoding="utf-8")
        self._json({
            "content": content,
            "resources": parse_resources_from_report(content),
        })

    def _handle_asset_read(self, query: str) -> None:
        params = parse_qs(query)
        path_id = params.get("id", [""])[0]
        rel = params.get("path", [""])[0]
        report = _path_from_id(self.root, path_id)
        asset = _safe_child(report.parent, rel)
        self._serve_file(asset)

    def _handle_session_asset_read(self, query: str) -> None:
        params = parse_qs(query)
        session_id = params.get("session_id", [""])[0]
        rel = params.get("path", [""])[0]
        session = self.service._get(session_id)
        from common.storage import resolve_plan_dir

        plan_dir = resolve_plan_dir(session.root, session.state.raw_goal)
        asset = _safe_child(plan_dir, rel)
        self._serve_file(asset)

    def _handle_session_events(self, query: str) -> None:
        params = parse_qs(query)
        session_id = params.get("session_id", [""])[0]
        last_id_raw = params.get("last_id", [self.headers.get("Last-Event-ID", "0")])[0]
        try:
            last_id = int(last_id_raw or "0")
        except ValueError:
            last_id = 0

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        while True:
            events = self.service.events_since(session_id, last_id, timeout=15.0)
            should_close = False
            for event in events:
                event_id = int(event.get("id") or 0)
                if event_id > 0:
                    self.wfile.write(f"id: {event_id}\n".encode("utf-8"))
                    last_id = event_id
                self.wfile.write(f"event: {event.get('type', 'message')}\n".encode("utf-8"))
                data = json.dumps(event.get("data") or {}, ensure_ascii=False)
                self.wfile.write(f"data: {data}\n\n".encode("utf-8"))
                self.wfile.flush()
                if event.get("type") in {"result", "error"}:
                    should_close = True
            if should_close:
                break

    def _serve_file(self, path: Path) -> None:
        if not path.exists():
            self.send_error(404)
            return
        data = path.read_bytes()
        mime = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", f"{mime}; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw) if raw else {}

    def _json(self, payload: dict, *, status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt: str, *args: Any) -> None:
        return


def run_server(host: str = "127.0.0.1", port: int = 8765) -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
    root = ensure_study_agents_path()
    config_store = WebConfigStore(root)
    apply_runtime_config(config_store.load())
    service = WebPlannerService(root)

    class Handler(StudyPlannerWebHandler):
        pass

    Handler.service = service
    Handler.config_store = config_store
    Handler.root = root

    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"Study Planner Web is running at http://{host}:{port}")
    httpd.serve_forever()


if __name__ == "__main__":
    run_server()
