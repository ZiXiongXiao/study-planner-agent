from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from common.agent.memory import AgentMemory
from common.agent.planner import Plan, PlanStep, StepKind
from common.agent.tools.registry import ToolRegistry, ToolResult


@dataclass
class ExecutionContext:
    mode: int
    goals: list[str] = field(default_factory=list)
    resources: list[dict] = field(default_factory=list)
    tasks: list[dict] = field(default_factory=list)
    milestones: list[dict] = field(default_factory=list)
    schedule: list[dict] = field(default_factory=list)
    assessment: dict | None = None

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "goals": self.goals,
            "resources": self.resources,
            "tasks": self.tasks,
            "milestones": self.milestones,
            "schedule": self.schedule,
            "assessment": self.assessment,
        }


def execute_tool_step(
    step: PlanStep,
    registry: ToolRegistry,
    memory: AgentMemory,
    context: ExecutionContext,
) -> ToolResult:
    if step.tool_name is None:
        return ToolResult(name="", success=False, summary="No tool specified")

    tool_args = step.tool_args.copy()

    result = registry.call(step.tool_name, **tool_args)

    memory.append_tool_log(f"{step.tool_name} → {result.summary}")

    if result.success and result.data:
        _update_context(context, step.tool_name, result.data)

    return result


def _update_context(ctx: ExecutionContext, tool_name: str, data: any) -> None:
    if tool_name == "understand_goals" and isinstance(data, dict):
        if "goals" in data:
            ctx.goals = data["goals"]
        if "detected_topics" in data:
            ctx.goals = data.get("detected_topics", [])

    elif tool_name == "assess_level" and isinstance(data, dict):
        ctx.assessment = data

    elif tool_name == "search_resources" and isinstance(data, list):
        ctx.resources.extend(data)

    elif tool_name == "breakdown_goals" and isinstance(data, dict):
        if "tasks" in data:
            ctx.tasks = data["tasks"]

    elif tool_name == "set_milestones" and isinstance(data, dict):
        if "milestones" in data:
            ctx.milestones = data["milestones"]

    elif tool_name == "schedule_tasks" and isinstance(data, dict):
        if "schedule" in data:
            ctx.schedule = data["schedule"]


def run_mode1_plan(
    plan: Plan,
    registry: ToolRegistry,
    memory: AgentMemory,
    goals_text: str,
) -> tuple[str, ExecutionContext]:
    context = ExecutionContext(mode=1)
    context.goals = [g.strip() for g in goals_text.split("\n") if g.strip()]

    print("\n" + "=" * 50)
    print("执行计划中...")
    print("=" * 50 + "\n")

    for i, step in enumerate(plan.steps, start=1):
        if step.kind == StepKind.TOOL:
            print(f"[Plan] Step {i}: {step.description}")
            if step.tool_name == "understand_goals":
                step.tool_args = {"goals_text": goals_text}
            elif step.tool_name == "search_resources":
                keywords = ", ".join(context.goals)
                step.tool_args = {"keywords": keywords, "level": context.assessment.get("level", "intermediate") if context.assessment else "intermediate"}

            result = execute_tool_step(step, registry, memory, context)

            if not result.success:
                print(f"Tool execution failed: {result.error}")
        else:
            print(f"[Plan] Step {i}: {step.description} [LLM]")

    user_message = _build_mode1_user_message(context, goals_text)
    return user_message, context


def run_mode2_plan(
    plan: Plan,
    registry: ToolRegistry,
    memory: AgentMemory,
    main_goal: str,
    user_level: str = "intermediate",
) -> tuple[str, ExecutionContext]:
    context = ExecutionContext(mode=2)
    context.goals = [main_goal]

    print("\n" + "=" * 50)
    print("执行计划中...")
    print("=" * 50 + "\n")

    for i, step in enumerate(plan.steps, start=1):
        if step.kind == StepKind.TOOL:
            print(f"[Plan] Step {i}: {step.description}")
            
            if step.tool_name == "breakdown_goals":
                step.tool_args = {"main_goal": main_goal, "level": user_level}
            elif step.tool_name == "search_resources":
                step.tool_args = {"keywords": main_goal, "level": user_level}
            elif step.tool_name == "set_milestones":
                total_weeks = sum([int(t["duration"].replace("周", "")) for t in context.tasks]) if context.tasks else 12
                step.tool_args = {"tasks": context.tasks, "total_weeks": total_weeks}
            elif step.tool_name == "schedule_tasks":
                step.tool_args = {"tasks": context.tasks, "available_hours_per_week": 10}

            result = execute_tool_step(step, registry, memory, context)

            if not result.success:
                print(f"Tool execution failed: {result.error}")
        else:
            print(f"[Plan] Step {i}: {step.description} [LLM]")

    user_message = _build_mode2_user_message(context, main_goal)
    return user_message, context


def _build_mode1_user_message(ctx: ExecutionContext, goals_text: str) -> str:
    message_parts = [
        "## 学习目标\n\n" + goals_text,
    ]

    if ctx.assessment:
        message_parts.append(f"\n## 当前水平评估\n\n{ctx.assessment.get('message', '')}")
        if ctx.assessment.get("recommendations"):
            message_parts.append("建议：\n" + "\n".join(f"- {r}" for r in ctx.assessment["recommendations"]))

    if ctx.resources:
        message_parts.append("\n## 相关学习资源\n\n")
        for r in ctx.resources[:5]:
            message_parts.append(f"- **{r.get('title', 'Unknown')}** ({r.get('type', 'Unknown')})\n  {r.get('url', '')}")

    return "\n".join(message_parts)


def _build_mode2_user_message(ctx: ExecutionContext, main_goal: str) -> str:
    message_parts = [
        "## 学习目标\n\n" + main_goal,
    ]

    if ctx.tasks:
        message_parts.append("\n## 任务分解\n\n")
        for i, task in enumerate(ctx.tasks, start=1):
            message_parts.append(f"{i}. **{task['task']}** (预计 {task['duration']})")

    if ctx.milestones:
        message_parts.append("\n## 学习里程碑\n\n")
        for m in ctx.milestones:
            message_parts.append(f"- 第 {m['week']} 周: {m['name']} - {m['description']}")

    if ctx.resources:
        message_parts.append("\n## 推荐学习资源\n\n")
        for r in ctx.resources[:5]:
            message_parts.append(f"- **{r.get('title', 'Unknown')}** ({r.get('type', 'Unknown')})\n  {r.get('url', '')}")

    message_parts.append("\n\n请根据以上信息，生成一份详细的学习计划，包括：\n1. 具体的周计划\n2. 每日学习内容建议\n3. 阶段性目标\n4. 注意事项和建议")

    return "\n".join(message_parts)
