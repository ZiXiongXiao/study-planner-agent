"""
BaseAgent: 每个智能体都是一个独立的 LLM 角色。

每个 Agent 持有自己的 system prompt 和职责，通过 provider.chat() 独立调用大模型，
再由 pipeline 把它们串成协作链。
"""

from __future__ import annotations

import json
import re
from typing import Any

from common.agent.multi.state import SessionState


class BaseAgent:
    # 子类覆盖
    name: str = "agent"           # 英文标识
    label: str = "智能体"          # 中文显示名
    system_prompt: str = ""

    def __init__(self, provider: Any, model_id: str) -> None:
        self.provider = provider
        self.model_id = model_id
        self.step_index: int | None = None   # 由 pipeline 设置，用于显示 [i/N]
        self.step_total: int | None = None

    # ---- 与大模型交互 ----
    def think(self, user_content: str, *, system: str | None = None) -> str:
        messages = [
            {"role": "system", "content": system or self.system_prompt},
            {"role": "user", "content": user_content},
        ]
        return self.provider.chat(messages, self.model_id)

    def think_json(self, user_content: str, *, system: str | None = None) -> Any:
        """要求模型返回 JSON，并稳健地解析出来。"""
        raw = self.think(user_content, system=system)
        return extract_json(raw)

    # ---- 子类实现 ----
    def run(self, state: SessionState) -> None:
        raise NotImplementedError

    # ---- 展示 ----
    def banner(self) -> None:
        if self.step_index and self.step_total:
            tag = f"[{self.step_index}/{self.step_total}] "
            dots = "●" * self.step_index + "○" * (self.step_total - self.step_index)
        else:
            tag, dots = "", ""
        print("\n" + "=" * 60)
        print(f"🧠 {tag}Agent · {self.label}  ({self.name})")
        if dots:
            print(f"   进度 {dots}")
        print("=" * 60)


def extract_json(text: str) -> Any:
    """
    从模型回复里提取 JSON。容忍 ```json 代码块、前后多余文字等情况。
    解析失败返回 None。
    """
    if not text:
        return None

    # 去掉 ```json ... ``` 围栏
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL)
    candidate = fenced.group(1).strip() if fenced else text.strip()

    # 先直接尝试
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass

    # 退而求其次：截取第一个 { 或 [ 到最后一个 } 或 ]
    start = min(
        [i for i in (candidate.find("{"), candidate.find("[")) if i != -1],
        default=-1,
    )
    if start == -1:
        return None
    end = max(candidate.rfind("}"), candidate.rfind("]"))
    if end <= start:
        return None
    snippet = candidate[start : end + 1]
    try:
        return json.loads(snippet)
    except json.JSONDecodeError:
        return None
