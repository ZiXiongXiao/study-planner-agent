from __future__ import annotations

from dataclasses import dataclass
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
