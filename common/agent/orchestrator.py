from __future__ import annotations

import sys
from pathlib import Path

from common.agent.executor import ExecutionContext, run_mode1_plan, run_mode2_plan
from common.agent.memory import (
    AgentMemory,
    load_mode_supplement,
    load_soul,
    read_multiline_prompt,
    read_optional_instruction,
    try_resume_messages,
)
from common.agent.planner import Plan, get_plan, print_plan
from common.agent.tools.registry import ToolRegistry, build_default_registry
from common.cli_menu import choose_option
from common.providers.base import StudyProvider
from common.storage import output_path, resolve_plan_dir, save_session


def choose_mode() -> int:
    mode = choose_option(
        "Select agent mode:",
        [
            ("Goal Setting — define learning goals and assess level (multi-turn)", 1),
            (
                "Plan Making — create detailed learning plan with schedule (multi-turn)",
                2,
            ),
        ],
        default_index=0,
        footer=(
            "Mode 2 follow-up: use /adjust <aspect> or phrases like 调整计划/修改"
        ),
    )
    return int(mode)


def ask_resume(save_path: Path) -> list[dict] | None:
    if not save_path.is_file():
        return None
    answer = input(
        f"\nFound existing session: {save_path.name}\n"
        "Resume previous conversation? [y/N]: "
    ).strip().lower()
    if answer not in ("y", "yes"):
        return None
    messages = try_resume_messages(save_path)
    if messages:
        print(f"Loaded {len(messages) // 2} previous turn(s).")
        return messages
    print("Could not parse previous session; starting fresh.")
    return None


def run_conversation_loop(
    provider: StudyProvider,
    *,
    memory: AgentMemory,
    model_id: str,
    save_path: Path,
    session_title: str,
    mode: int,
    initial_messages: list[dict],
    plan: Plan,
    registry: ToolRegistry | None = None,
    exec_ctx: ExecutionContext | None = None,
) -> None:
    system_prompt = memory.build_system_prompt()
    messages: list[dict] = [{"role": "system", "content": system_prompt}]

    resumed = ask_resume(save_path)
    if resumed:
        messages.extend(resumed)
    else:
        messages.extend(initial_messages)

    print("Multi-turn chat enabled. Type exit or quit to finish.\n")

    while True:
        if messages[-1]["role"] == "assistant":
            try:
                follow_up = input("\nYou: ").strip()
            except (KeyboardInterrupt, EOFError):
                print()
                break
            if follow_up.lower() in ("exit", "quit"):
                break
            if not follow_up:
                continue
            messages.append({"role": "user", "content": follow_up})

        try:
            reply = provider.chat(messages, model_id)
        except RuntimeError as err:
            print(f"\nError: {err}", file=sys.stderr)
            if messages[-1]["role"] == "user":
                messages.pop()
            break
        except Exception as err:
            print(f"\nUnexpected error: {err}", file=sys.stderr)
            if messages[-1]["role"] == "user":
                messages.pop()
            break

        if not reply.strip():
            print("No response received.", file=sys.stderr)
            if messages[-1]["role"] == "user":
                messages.pop()
            break

        messages.append({"role": "assistant", "content": reply})
        saved = save_session(
            save_path,
            session_title=session_title,
            mode=mode,
            model_id=model_id,
            provider_label=provider.reply_label,
            instruction=memory.build_system_prompt(),
            messages=messages,
            plan_text=plan.render(),
            tool_log=memory.format_tool_log(),
        )
        print(f"\nSaved to {saved}")


def run_mode1(
    provider: StudyProvider,
    *,
    root: Path,
    model_id: str,
    memory: AgentMemory,
    plan: Plan,
    registry: ToolRegistry,
) -> None:
    goals_text = read_multiline_prompt(
        "Enter your learning goals (one per line).\nFinish with an empty line:"
    )
    if not goals_text:
        print("Error: learning goals are required.", file=sys.stderr)
        sys.exit(1)

    plan_slug = goals_text[:50].replace("\n", "-").replace(" ", "-")
    ref_dir = resolve_plan_dir(root, plan_slug)
    save_path = output_path(ref_dir, model_id)
    print(f"\nModel: {model_id}")
    print(f"Output: {save_path}\n")

    provider.reset_conversation()
    paper_content, exec_ctx = run_mode1_plan(
        plan,
        registry,
        memory,
        goals_text=goals_text,
    )

    run_conversation_loop(
        provider,
        memory=memory,
        model_id=model_id,
        save_path=save_path,
        session_title=goals_text[:120],
        mode=1,
        initial_messages=[{"role": "user", "content": paper_content}],
        plan=plan,
    )


def run_mode2(
    provider: StudyProvider,
    *,
    root: Path,
    model_id: str,
    memory: AgentMemory,
    plan: Plan,
    registry: ToolRegistry,
) -> None:
    main_goal = read_multiline_prompt(
        "Enter your main learning goal.\nFinish with an empty line:"
    )
    if not main_goal:
        print("Error: main learning goal is required.", file=sys.stderr)
        sys.exit(1)

    user_level = input("Enter your current level [beginner/intermediate/advanced]: ").strip().lower()
    if user_level not in ["beginner", "intermediate", "advanced"]:
        user_level = "intermediate"

    plan_slug = main_goal[:50].replace(" ", "-")
    ref_dir = resolve_plan_dir(root, plan_slug)
    save_path = output_path(ref_dir, model_id)
    print(f"\nModel: {model_id}")
    print(f"Output: {save_path}\n")

    provider.reset_conversation()
    context, exec_ctx = run_mode2_plan(
        plan,
        registry,
        memory,
        main_goal=main_goal,
        user_level=user_level,
    )

    run_conversation_loop(
        provider,
        memory=memory,
        model_id=model_id,
        save_path=save_path,
        session_title=main_goal[:120],
        mode=2,
        initial_messages=[{"role": "user", "content": context}],
        plan=plan,
    )


def run_study_agent(provider: StudyProvider) -> None:
    from common.providers.base import ensure_study_agents_path

    root = ensure_study_agents_path()
    provider.initialize()
    provider.get_api_key()
    model_id = provider.choose_model()

    mode = choose_mode()
    plan = get_plan(mode)
    print_plan(plan)

    soul = load_soul(root)
    mode_supplement = load_mode_supplement(root, mode)
    task_instruction = read_optional_instruction()

    memory = AgentMemory(
        soul=soul,
        mode_supplement=mode_supplement,
        task_instruction=task_instruction,
        plan_log=plan.render(),
    )

    registry = build_default_registry()
    print("\nRegistered tools:")
    for tool in registry.list_tools():
        print(f"  - {tool.name}: {tool.description}")
    print()

    if mode == 1:
        run_mode1(
            provider,
            root=root,
            model_id=model_id,
            memory=memory,
            plan=plan,
            registry=registry,
        )
    else:
        run_mode2(
            provider,
            root=root,
            model_id=model_id,
            memory=memory,
            plan=plan,
            registry=registry,
        )

    print("\nDone.")
