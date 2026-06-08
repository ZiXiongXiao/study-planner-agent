from __future__ import annotations

import os
import sys
from abc import ABC, abstractmethod
from pathlib import Path


class StudyProvider(ABC):
    reply_label: str = "Unknown"

    def __init__(self) -> None:
        self.api_key: str | None = None

    def initialize(self) -> None:
        pass

    @abstractmethod
    def get_api_key(self) -> None:
        pass

    @abstractmethod
    def choose_model(self) -> str:
        pass

    @abstractmethod
    def chat(self, messages: list[dict], model_id: str, tools: list | None = None) -> "str | dict":
        """常规对话返回文本字符串。

        当传入 ``tools``（OpenAI function-calling schema 列表）时，应改为返回
        完整的 assistant message（dict，可能含 ``tool_calls``）。不传 tools 时行为
        与原先完全一致。
        """
        pass

    def reset_conversation(self) -> None:
        pass


def ensure_study_agents_path() -> Path:
    if "__file__" in globals():
        script_path = Path(__file__).resolve()
        study_agents_root = script_path.parent.parent.parent
    else:
        study_agents_root = Path.cwd()

    expected_marker = study_agents_root / "web_app.py"
    if not expected_marker.exists():
        study_agents_root = Path(__file__).parent.parent.parent
        expected_marker = study_agents_root / "web_app.py"
        if not expected_marker.exists():
            print(
                f"Warning: Could not find project marker at {expected_marker}",
                file=sys.stderr,
            )

    return study_agents_root
