"""
学习执行包导出：把定稿的学习计划派生成 learner-facing 的多份文件，便于每天执行与复盘。

**附加产物，绝不替代原始报告** `<model>-multiagent.md`（由 pipeline._save 保存）。写到：
  plans/<目标>/<model>-package/
    plan.md            报告副本（图片相对路径回退到 ../assets）
    daily-checklist.md 每周/每日可勾选任务清单（确定性，零 LLM）
    review-log.md      每日三栏复盘模板（确定性，零 LLM）
    quiz.md            按阶段自测题（1 次 LLM；失败写占位、不崩）

每个文件独立 try/except，任一失败不影响其它与主流程。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from common.agent.multi.base_agent import BaseAgent, extract_json
from common.storage import resolve_plan_dir


def export_learning_package(provider, model_id, root, state) -> Path | None:
    """导出学习执行包，返回包目录（失败返回 None，绝不抛）。"""
    plan = state.plan_structured or {}
    try:
        pkg_dir = resolve_plan_dir(root, state.raw_goal) / f"{model_id}-package"
        pkg_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        return None

    _safe_write(pkg_dir / "plan.md", _plan_copy(state))
    _safe_write(pkg_dir / "daily-checklist.md", _daily_checklist(state, plan))
    _safe_write(pkg_dir / "review-log.md", _review_log(plan))
    _safe_write(pkg_dir / "quiz.md", _quiz(provider, model_id, state, plan, pkg_dir))
    return pkg_dir


def _safe_write(path: Path, content: str) -> None:
    try:
        if content:
            path.write_text(content, encoding="utf-8")
    except Exception:
        pass


def _plan_copy(state) -> str:
    """报告副本：执行包在子目录，图片相对路径回退一级 assets → ../assets。"""
    md = state.display_markdown or state.plan_markdown or ""
    return md.replace("](assets/", "](../assets/")


def _daily_checklist(state, plan: dict) -> str:
    weeks = plan.get("weekly_schedule") or []
    milestones = plan.get("milestones") or []
    lines = [f"# ✅ 学习任务清单：{state.raw_goal}", "",
             "> 勾选完成项，保持节奏。每完成一周记得在 review-log.md 里复盘。", ""]
    for w in weeks:
        topic = w.get("topic") or w.get("task", "")
        output = w.get("output") or w.get("deliverable", "")
        hours = w.get("hours") or w.get("duration", "")
        head = f"## 第 {w.get('week', '')} 周：{topic}".rstrip()
        lines.append(head)
        if hours:
            lines.append(f"_预计投入：{hours}_")
        lines.append("")
        if topic:
            lines.append(f"- [ ] 学习本周主题：{topic}")
        if output:
            lines.append(f"- [ ] 完成产出：{output}")
        lines.append("- [ ] 本周复盘并记录卡点")
        lines.append("")
    if milestones:
        lines.append("## 🎯 里程碑")
        lines.append("")
        for m in milestones:
            name = m.get("name", "")
            desc = m.get("description", "")
            line = f"- [ ] 第 {m.get('week', '')} 周 · {name}".rstrip()
            lines.append(line + (f" —— {desc}" if desc else ""))
        lines.append("")
    if not weeks and not milestones:
        lines.append("- [ ] 暂无结构化周计划，请参考 plan.md 自行拆解任务。")
    return "\n".join(lines)


def _review_log(plan: dict) -> str:
    weeks = plan.get("weekly_schedule") or []
    lines = ["# 📓 复盘日志", "",
             "> 每天填三栏：**今天学了什么 / 卡在哪里 / 明天怎么改**。坚持比完美更重要。", ""]
    header = ["| 日期 | 今天学了什么 | 卡在哪里 | 明天怎么改 |", "| --- | --- | --- | --- |"]
    if weeks:
        for w in weeks:
            lines.append(f"## 第 {w.get('week', '')} 周：{w.get('topic', '')}".rstrip())
            lines.append("")
            lines.extend(header)
            lines.extend(["|  |  |  |  |"] * 3)
            lines.append("")
    else:
        lines.extend(header)
        lines.extend(["|  |  |  |  |"] * 7)
    return "\n".join(lines)


_QUIZ_SYS = (
    "你是『学习自测出题 Agent』。针对该学习计划，按阶段出自测题，帮学习者判断是否掌握、"
    "能否进入下一阶段。每个阶段 3~5 题，覆盖概念/应用/易错点，并附简短答案。"
    '只返回 JSON 数组：[{"stage":"阶段名","items":[{"q":"题目","a":"答案"}]}]。'
)


class _QuizAgent(BaseAgent):
    name = "package_quiz"
    label = "执行包自测题"
    system_prompt = _QUIZ_SYS


def _quiz(provider, model_id, state, plan: dict, pkg_dir: Path | None = None) -> str:
    stages = plan.get("stage_goals") or []
    user = (
        f"学习目标：{state.raw_goal}\n"
        f"阶段目标：{json.dumps(stages, ensure_ascii=False)}\n"
        f"知识大纲（节选）：\n{(state.knowledge_outline or '')[:800]}\n\n"
        "请按阶段出自测题。"
    )
    agent = _QuizAgent(provider, model_id)
    last_raw = ""
    last_error = ""
    data = None
    blocks: list[dict] = []
    attempts = 2

    for attempt in range(1, attempts + 1):
        try:
            raw = agent.think(user)
            last_raw = raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False)
            data = extract_json(last_raw)
            raw_blocks = _coerce_quiz_blocks(data) or _recover_quiz_blocks_from_text(last_raw)
            blocks = _normalize_quiz_blocks(raw_blocks)
            if blocks:
                break
            if data is None:
                last_error = f"attempt {attempt}: response was not parseable as quiz JSON"
            else:
                last_error = f"attempt {attempt}: JSON parsed but no quiz array found"
        except Exception as err:
            last_error = f"attempt {attempt}: {type(err).__name__}: {err}"
            last_raw = ""

    if not blocks:
        _write_quiz_diagnostic(pkg_dir, last_raw, last_error, data)
        try:
            state.log("学习执行包", f"quiz 生成失败：{last_error or 'empty/unparseable response'}")
        except Exception:
            pass
        print(f"[WARN] 自测题生成失败，已写入占位。{last_error}")
        return "# 📝 阶段自测\n\n_（本次自测题生成失败，可稍后重试。）_\n"

    lines = [f"# 📝 阶段自测：{state.raw_goal}", "",
             "> 每完成一个阶段，用对应小测自查；答得上来再进入下一阶段。", ""]
    for i, blk in enumerate(blocks, 1):
        if not isinstance(blk, dict):
            continue
        lines.append(f"## {str(blk.get('stage', f'阶段 {i}'))}")
        lines.append("")
        for j, it in enumerate(blk.get("items") or [], 1):
            if not isinstance(it, dict):
                continue
            q = str(it.get("q", "")).strip()
            if not q:
                continue
            lines.append(f"{j}. {q}")
            a = str(it.get("a", "")).strip()
            if a:
                lines.append(f"   <details><summary>答案</summary>{a}</details>")
        lines.append("")
    return "\n".join(lines)


def _coerce_quiz_blocks(data) -> list[dict]:
    """兼容模型把数组包成 {"quiz": [...]} / {"stages": [...]} 的常见返回。"""
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if not isinstance(data, dict):
        return []
    for key in ("quiz", "quizzes", "stages", "stage_quizzes", "items"):
        value = data.get(key)
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)]
    for value in data.values():
        if isinstance(value, list) and any(isinstance(x, dict) for x in value):
            return [x for x in value if isinstance(x, dict)]
    return []


def _normalize_quiz_blocks(blocks: list[dict]) -> list[dict]:
    """Normalize common model variants to [{stage, items:[{q,a}]}]."""
    out: list[dict] = []
    for i, blk in enumerate(blocks, 1):
        if not isinstance(blk, dict):
            continue
        stage = str(blk.get("stage") or blk.get("title") or blk.get("name") or f"阶段 {i}").strip()
        raw_items = (
            blk.get("items") or blk.get("questions") or blk.get("quiz") or blk.get("quizzes") or []
        )
        if isinstance(raw_items, dict):
            raw_items = [raw_items]
        items = []
        for it in raw_items if isinstance(raw_items, list) else []:
            if not isinstance(it, dict):
                continue
            q = str(it.get("q") or it.get("question") or it.get("题目") or "").strip()
            a = str(it.get("a") or it.get("answer") or it.get("答案") or "").strip()
            if q:
                items.append({"q": q, "a": a})
        if items:
            out.append({"stage": stage, "items": items})
    return out


def _recover_quiz_blocks_from_text(raw: str) -> list[dict]:
    """Best-effort recovery for almost-JSON quiz output with one broken string.

    Some models return a fenced JSON array where a single answer misses its closing
    quote. Standard JSON parsing then fails even though the stage/question shape is
    still visible. This fallback extracts stage/q/a fields conservatively.
    """
    text = _strip_fence(raw or "")
    stage_matches = list(re.finditer(r'"stage"\s*:\s*"([^"]+)"', text))
    if not stage_matches:
        return []

    blocks: list[dict] = []
    for idx, sm in enumerate(stage_matches):
        stage = sm.group(1).strip()
        start = sm.end()
        end = stage_matches[idx + 1].start() if idx + 1 < len(stage_matches) else len(text)
        body = text[start:end]
        q_matches = list(re.finditer(r'"q"\s*:\s*"((?:\\.|[^"\\])*)"', body))
        items = []
        for qi, qm in enumerate(q_matches):
            q = _unescape_jsonish(qm.group(1)).strip()
            q_end = q_matches[qi + 1].start() if qi + 1 < len(q_matches) else len(body)
            item_body = body[qm.end():q_end]
            a = _extract_answer_from_item_text(item_body)
            if q:
                items.append({"q": q, "a": a})
        if items:
            blocks.append({"stage": stage, "items": items})
    return blocks


def _strip_fence(text: str) -> str:
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL)
    return fenced.group(1) if fenced else text


def _extract_answer_from_item_text(text: str) -> str:
    marker = re.search(r'"a"\s*:\s*"', text)
    if not marker:
        marker = re.search(r'"answer"\s*:\s*"', text)
    if not marker:
        return ""
    s = text[marker.end():]
    end = _find_json_string_end(s)
    if end is None:
        close = re.search(r"\n\s*\}\s*,?", s)
        end = close.start() if close else len(s)
    return _unescape_jsonish(s[:end]).strip().rstrip(",")


def _find_json_string_end(text: str) -> int | None:
    escaped = False
    for i, ch in enumerate(text):
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if ch == '"':
            return i
    return None


def _unescape_jsonish(text: str) -> str:
    try:
        return json.loads(f'"{text}"')
    except Exception:
        return text.replace('\\"', '"').replace("\\n", "\n")


def _write_quiz_diagnostic(pkg_dir: Path | None, raw: str, error: str, parsed) -> None:
    if not pkg_dir:
        return
    parsed_text = ""
    try:
        parsed_text = json.dumps(parsed, ensure_ascii=False, indent=2)
    except Exception:
        parsed_text = str(parsed)
    body = "\n".join([
        "quiz generation failed",
        f"error: {error or 'unknown'}",
        "",
        "parsed:",
        parsed_text or "(empty)",
        "",
        "raw:",
        raw or "(empty)",
        "",
    ])
    _safe_write(pkg_dir / "quiz.raw.txt", body)
