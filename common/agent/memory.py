from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AgentMemory:
    soul: str
    mode_supplement: str
    task_instruction: str = ""
    plan_log: str = ""
    tool_log: list[str] = field(default_factory=list)

    def build_system_prompt(self) -> str:
        sections = [
            self.soul.strip(),
            self.mode_supplement.strip(),
        ]
        if self.task_instruction.strip():
            sections.append(
                "## Task-specific instruction\n\n" + self.task_instruction.strip()
            )
        return "\n\n---\n\n".join(section for section in sections if section)

    def append_tool_log(self, line: str) -> None:
        self.tool_log.append(line)

    def format_tool_log(self) -> str:
        if not self.tool_log:
            return ""
        return "## Tool execution log\n\n" + "\n".join(f"- {line}" for line in self.tool_log)


def load_text(path: Path, *, fallback: str = "") -> str:
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    return fallback


def load_soul(root: Path) -> str:
    return load_text(
        root / "soul-instr" / "prompt.md",
        fallback="You are a helpful study planning assistant.",
    )


def load_mode_supplement(root: Path, mode: int) -> str:
    if mode == 1:
        path = root / "soul-instr" / "mode1-goal.md"
    else:
        path = root / "soul-instr" / "mode2-plan.md"
    return load_text(path)


def read_multiline_prompt(header: str, *, required: bool = True) -> str:
    print(header)
    print("Finish with an empty line:\n")
    lines: list[str] = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if not line.strip():
            if lines:
                break
            if not required:
                break
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def read_optional_instruction() -> str:
    print(
        "\nOptional task-specific instruction (empty = use mode defaults only)."
    )
    print("Finish with an empty line:\n")
    return read_multiline_prompt("", required=False)


def parse_messages_from_md(text: str) -> tuple[str, list[dict]]:
    instruction_match = re.search(
        r"## Instruction\s*\n+(.*?)(?=\n## Turn |\n## Plan |\Z)",
        text,
        flags=re.DOTALL,
    )
    instruction = instruction_match.group(1).strip() if instruction_match else ""

    messages: list[dict] = []
    turn_pattern = re.compile(
        r"## Turn (\d+)\s*\n+### User\s*\n+(.*?)\n+### Assistant\s*\n+(.*?)(?=\n## Turn |\Z)",
        flags=re.DOTALL,
    )
    for match in turn_pattern.finditer(text):
        user_content = match.group(2).strip()
        assistant_content = match.group(3).strip()
        messages.append({"role": "user", "content": user_content})
        messages.append({"role": "assistant", "content": assistant_content})

    return instruction, messages


def try_resume_messages(save_path: Path) -> list[dict] | None:
    if not save_path.is_file():
        return None
    text = save_path.read_text(encoding="utf-8", errors="replace")
    _, messages = parse_messages_from_md(text)
    return messages or None
