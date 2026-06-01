from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path


def resolve_plan_dir(root: Path, goal_slug: str) -> Path:
    safe_slug = re.sub(r"[^\w\-]", "-", goal_slug)
    safe_slug = re.sub(r"-+", "-", safe_slug)
    safe_slug = safe_slug.strip("-")[:80]

    plans_dir = root / "plans"
    plan_dir = plans_dir / safe_slug
    plan_dir.mkdir(parents=True, exist_ok=True)

    return plan_dir


def output_path(ref_dir: Path, model_id: str) -> Path:
    return ref_dir / f"{model_id}.md"


def save_session(
    save_path: Path,
    *,
    session_title: str,
    mode: int,
    model_id: str,
    provider_label: str,
    instruction: str,
    messages: list[dict],
    plan_text: str,
    tool_log: str,
) -> Path:
    lines = [
        f"# {session_title}",
        "",
        f"- Mode: {mode} ({'Goal Setting' if mode == 1 else 'Plan Making'})",
        f"- Model: `{model_id}`",
        f"- Provider: {provider_label}",
        f"- Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
    ]

    lines.append("## Plan\n")
    lines.append(plan_text)

    if tool_log:
        lines.append("")
        lines.append(tool_log)

    lines.append("")
    lines.append("## Instruction\n")
    lines.append(instruction)

    turn = 0
    for msg in messages:
        if msg["role"] == "system":
            continue

        if msg["role"] == "user":
            turn += 1
            lines.append("")
            lines.append(f"## Turn {turn}")
            lines.append("")
            lines.append("### User")
            lines.append("")
            lines.append(msg["content"])
        elif msg["role"] == "assistant":
            lines.append("")
            lines.append("### Assistant")
            lines.append("")
            lines.append(msg["content"])

    content = "\n".join(lines)
    save_path.write_text(content, encoding="utf-8")

    return save_path
