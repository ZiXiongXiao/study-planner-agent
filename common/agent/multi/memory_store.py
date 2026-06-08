"""
长期记忆存储：把用户画像按主题持久化到磁盘，实现跨会话记忆。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

MEMORY_INSTRUCTION_FILES = (
    "memory-policy.md",
    "profile-schema.md",
    "memory-merge-rules.md",
)


def _slug(text: str) -> str:
    s = re.sub(r"[^\w一-鿿\-]", "-", text.lower())
    s = re.sub(r"-+", "-", s).strip("-")
    return s[:60] or "default"


def memory_path(root: Path, goal: str) -> Path:
    store = root / "memory_store"
    store.mkdir(parents=True, exist_ok=True)
    return store / f"{_slug(goal)}.json"


def load_profile(root: Path, goal: str) -> dict | None:
    path = memory_path(root, goal)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def save_profile(root: Path, goal: str, profile: dict) -> Path:
    path = memory_path(root, goal)
    path.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_memory_instructions(root: Path) -> str:
    """Load project memory rules from soul-instr/*.md.

    The files are optional so tests and packaged runs can still work if the
    folder is missing. Missing files simply reduce the prompt to the built-in
    schema in ProfileMemoryAgent.
    """
    base = Path(root) / "soul-instr"
    parts: list[str] = []
    for name in MEMORY_INSTRUCTION_FILES:
        path = base / name
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if text:
            parts.append(f"## {name}\n\n{text}")
    return "\n\n".join(parts)
