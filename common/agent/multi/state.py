"""
Shared session state passed between agents.
在各个 Agent 之间传递的共享上下文。
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime


@dataclass
class SessionState:
    # 用户输入层
    raw_goal: str = ""

    # 需求澄清 Agent 的产出（问题 -> 用户所选答案）
    clarifications: dict[str, str] = field(default_factory=dict)

    # 用户画像与记忆 Agent 的产出
    profile: dict = field(default_factory=dict)
    is_returning_user: bool = False

    # 搜索与分析层
    resources: list[dict] = field(default_factory=list)
    evaluated_resources: list[dict] = field(default_factory=list)
    knowledge_outline: str = ""

    # 规划与优化层
    plan_structured: dict = field(default_factory=dict)
    plan_markdown: str = ""
    display_markdown: str = ""
    # 视觉编排：LLM 一次性产出的章节级视觉计划（结构图 + 氛围图），缓存以便反馈重渲染复用。
    visual_plan: dict = field(default_factory=dict)
    # 生成的视觉资产：每项 {anchor, section, path, alt, kind: svg|png}
    # 结构图(svg) 由本地渲染、氛围图(png) 由 MiniMax 生成；anchor 用于就近插到对应章节旁。
    images: list[dict] = field(default_factory=list)
    images_attempted: bool = False

    # 反馈调整记录
    feedback_rounds: list[dict] = field(default_factory=list)

    # 多智能体协作日志（用于答辩演示 / 存档）
    agent_log: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    def log(self, agent_label: str, message: str) -> None:
        line = f"[{agent_label}] {message}"
        self.agent_log.append(line)

    def level(self) -> str:
        return self.profile.get("level", "intermediate")

    def to_dict(self) -> dict:
        return asdict(self)
