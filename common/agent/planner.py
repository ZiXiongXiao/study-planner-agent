from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class StepKind(str, Enum):
    TOOL = "tool"
    LLM = "llm"


@dataclass
class PlanStep:
    step_id: int
    kind: StepKind
    description: str
    tool_name: str | None = None
    tool_args: dict = field(default_factory=dict)


@dataclass
class Plan:
    mode: int
    title: str
    steps: list[PlanStep] = field(default_factory=list)

    def render(self) -> str:
        lines = [f"Plan ({self.title}):", ""]
        for step in self.steps:
            prefix = step.kind.value.upper()
            tool = f" → {step.tool_name}" if step.tool_name else ""
            lines.append(f"  {step.step_id}. [{prefix}{tool}] {step.description}")
        return "\n".join(lines)


def plan_mode1_goal_setting() -> Plan:
    return Plan(
        mode=1,
        title="Goal Setting",
        steps=[
            PlanStep(
                1,
                StepKind.TOOL,
                "Understand user's learning goals and preferences",
                "understand_goals",
            ),
            PlanStep(
                2,
                StepKind.TOOL,
                "Assess user's current skill level",
                "assess_level",
            ),
            PlanStep(
                3,
                StepKind.TOOL,
                "Search for relevant learning resources",
                "search_resources",
            ),
            PlanStep(
                4,
                StepKind.LLM,
                "Generate structured learning goals with milestones",
            ),
            PlanStep(
                5,
                StepKind.LLM,
                "Multi-turn refinement and adjustment",
            ),
        ],
    )


def plan_mode2_plan_making() -> Plan:
    return Plan(
        mode=2,
        title="Plan Making",
        steps=[
            PlanStep(
                1,
                StepKind.TOOL,
                "Break down large goals into manageable tasks",
                "breakdown_goals",
            ),
            PlanStep(
                2,
                StepKind.TOOL,
                "Schedule tasks based on available time",
                "schedule_tasks",
            ),
            PlanStep(
                3,
                StepKind.TOOL,
                "Set learning milestones and checkpoints",
                "set_milestones",
            ),
            PlanStep(
                4,
                StepKind.TOOL,
                "Search for additional learning resources",
                "search_resources",
            ),
            PlanStep(
                5,
                StepKind.LLM,
                "Generate detailed learning plan with timeline",
            ),
            PlanStep(
                6,
                StepKind.LLM,
                "Multi-turn optimization and adjustment",
            ),
        ],
    )


def get_plan(mode: int) -> Plan:
    if mode == 1:
        return plan_mode1_goal_setting()
    return plan_mode2_plan_making()


def print_plan(plan: Plan) -> None:
    print("\n=== Agent Plan ===")
    print(plan.render())
    print("==================\n")
