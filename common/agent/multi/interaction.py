"""
更友好的终端交互组件。

提供：带进度 / 可自定义答案（"其他"）的单选与多选、文本输入、确认。
让需求澄清、反馈调整等人机交互环节更顺手。
"""

from __future__ import annotations

import sys

_RULE = "─" * 60
_CUSTOM_LABEL = "✏️  其他（自己输入）"


def _read(prompt: str) -> str:
    try:
        return input(prompt)
    except (EOFError, KeyboardInterrupt):
        print()
        return ""


def ask_choice(
    question: str,
    options: list[str],
    *,
    default: int = 0,
    allow_custom: bool = True,
    multi: bool = False,
    progress: str = "",
) -> str | list[str]:
    """
    单选 / 多选，支持"其他（自己输入）"。

    - multi=False 返回所选项字符串
    - multi=True  返回所选项字符串列表
    """
    display_options = list(options)
    if allow_custom:
        display_options.append(_CUSTOM_LABEL)

    tag = f"[{progress}] " if progress else ""
    print(f"\n{_RULE}")
    print(f"❓ {tag}{question}")
    print(_RULE)
    for i, opt in enumerate(display_options):
        marker = ">" if (not multi and i == default) else " "
        print(f"  {marker} {i + 1}. {opt}")

    custom_idx = len(options) if allow_custom else -1

    if multi:
        print("（多选：用逗号分隔，如 1,3；直接回车选默认）")
        raw = _read("> 你的选择: ").strip()
        if not raw:
            return [options[default]]
        picks: list[str] = []
        for tok in raw.split(","):
            tok = tok.strip()
            if not tok.isdigit():
                continue
            idx = int(tok) - 1
            if idx == custom_idx:
                custom = ask_text("请补充你的答案", required=False)
                if custom:
                    picks.append(custom)
            elif 0 <= idx < len(options):
                picks.append(options[idx])
        return picks or [options[default]]

    # 单选
    print(f"（单选：输入序号，直接回车默认第 {default + 1} 项）")
    while True:
        raw = _read("> 你的选择: ").strip()
        if not raw:
            return options[default]
        if not raw.isdigit():
            print("  ⚠ 请输入选项序号。")
            continue
        idx = int(raw) - 1
        if idx == custom_idx:
            custom = ask_text("请输入你的答案", required=True)
            return custom
        if 0 <= idx < len(options):
            return options[idx]
        print(f"  ⚠ 请输入 1~{len(display_options)} 之间的序号。")


def ask_text(
    prompt: str,
    *,
    example: str = "",
    multiline: bool = False,
    required: bool = True,
    default: str = "",
) -> str:
    """文本输入。multiline=True 时空行结束。"""
    hint = f"（示例：{example}）" if example else ""
    if multiline:
        print(f"\n{prompt} {hint}")
        print("（可多行，输入完成后按一次空行结束）")
        lines: list[str] = []
        while True:
            line = _read("")
            if not line.strip():
                if lines or not required:
                    break
                continue
            lines.append(line)
        text = "\n".join(lines).strip()
    else:
        suffix = f" {hint}" if hint else ""
        while True:
            text = _read(f"{prompt}{suffix}: ").strip()
            if text or not required:
                break
            print("  ⚠ 此项必填。")
    return text or default


def confirm(prompt: str, *, default: bool = True) -> bool:
    suffix = " [Y/n] " if default else " [y/N] "
    raw = _read(prompt + suffix).strip().lower()
    if not raw:
        return default
    return raw in ("y", "yes", "是", "对", "好")


def section(title: str) -> None:
    print(f"\n{_RULE}")
    print(title)
    print(_RULE)
