from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class ToolResult:
    name: str
    success: bool
    summary: str
    data: Any = None
    error: str | None = None


@dataclass
class ToolSpec:
    name: str
    description: str
    handler: Callable[..., ToolResult]


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        self._tools[spec.name] = spec

    def list_tools(self) -> list[ToolSpec]:
        return list(self._tools.values())

    def call(self, name: str, **kwargs: Any) -> ToolResult:
        if name not in self._tools:
            return ToolResult(
                name=name,
                success=False,
                summary=f"Unknown tool: {name}",
                error=f"Tool '{name}' is not registered.",
            )
        spec = self._tools[name]
        args_preview = ", ".join(
            f"{key}={repr(value)[:60]}" for key, value in kwargs.items()
        )
        print(f"[Tool] {name}({args_preview})", flush=True)
        try:
            result = spec.handler(**kwargs)
            status = "OK" if result.success else "FAIL"
            print(f"[Tool] {name} → {status}: {result.summary}", flush=True)
            return result
        except Exception as err:
            message = f"{type(err).__name__}: {err}"
            print(f"[Tool] {name} → ERROR: {message}", flush=True)
            return ToolResult(
                name=name,
                success=False,
                summary=message,
                error=message,
            )


def build_default_registry() -> ToolRegistry:
    from common.agent.tools.resources import search_resources
    from common.agent.tools.scheduler import schedule_tasks
    from common.agent.tools.progress import (
        breakdown_goals,
        set_milestones,
        understand_goals,
        assess_level,
        track_progress,
    )

    registry = ToolRegistry()
    
    registry.register(
        ToolSpec(
            name="understand_goals",
            description="Understand user's learning goals and preferences.",
            handler=understand_goals,
        )
    )
    
    registry.register(
        ToolSpec(
            name="assess_level",
            description="Assess user's current skill level.",
            handler=assess_level,
        )
    )
    
    registry.register(
        ToolSpec(
            name="search_resources",
            description="Search for high-quality learning resources.",
            handler=search_resources,
        )
    )
    
    registry.register(
        ToolSpec(
            name="breakdown_goals",
            description="Break down large goals into manageable tasks.",
            handler=breakdown_goals,
        )
    )
    
    registry.register(
        ToolSpec(
            name="schedule_tasks",
            description="Schedule tasks based on available time.",
            handler=schedule_tasks,
        )
    )
    
    registry.register(
        ToolSpec(
            name="set_milestones",
            description="Set learning milestones and checkpoints.",
            handler=set_milestones,
        )
    )
    
    registry.register(
        ToolSpec(
            name="track_progress",
            description="Track learning progress.",
            handler=track_progress,
        )
    )
    
    return registry
