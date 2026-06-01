from __future__ import annotations

import sys


def choose_option(
    header: str,
    options: list[tuple[str, int]],
    default_index: int = 0,
    footer: str = "",
) -> int:
    print(header)
    print()

    for i, (label, _) in enumerate(options):
        marker = "  " if i != default_index else "> "
        print(f"{marker}{i + 1}. {label}")

    if footer:
        print()
        print(footer)

    print()
    prompt = "Enter number or select with ↑/↓ + Enter [1]: "
    raw = input(prompt).strip()

    if not raw:
        return options[default_index][1]

    if raw in ("q", "quit", "exit"):
        print("Exiting.")
        sys.exit(0)

    try:
        num = int(raw)
        if 1 <= num <= len(options):
            return options[num - 1][1]
    except ValueError:
        pass

    print(f"Invalid input, using default: {options[default_index][0]}")
    return options[default_index][1]
