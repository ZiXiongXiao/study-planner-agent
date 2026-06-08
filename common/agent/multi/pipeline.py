"""
多智能体协作主流程（核心调用链）。

用户输入 → 任务编排 → 需求澄清 → 画像记忆 → 资源搜索 → 资源评估
        → 知识整理 → 计划生成 → 多模态展示 → 反馈调整 → 存档
"""

from __future__ import annotations

import sys
from pathlib import Path

from common.agent.multi.state import SessionState
from common.agent.multi import interaction
from common.agent.multi.agents import (
    RouterAgent,
    ClarificationAgent,
    ProfileMemoryAgent,
    ResourceSearchAgent,
    ResourceEvaluationAgent,
    KnowledgeOrganizationAgent,
    PlanGenerationAgent,
    MultimodalDisplayAgent,
    FeedbackAdjustmentAgent,
)
from common.providers.base import ensure_study_agents_path
from common.storage import resolve_plan_dir, output_path
from common.agent.tools import image_gen, web_search
from common.agent.multi.package import export_learning_package


def read_goal() -> str:
    return interaction.ask_text(
        "🎯 请描述你的学习目标",
        example="想两周内入门 Python 数据分析，能做基础爬虫",
        multiline=True,
        required=True,
    )


def run_multi_agent(provider) -> None:
    # Windows 终端可能是 GBK，强制 UTF-8 输出，避免 emoji/中文崩溃
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

    root = ensure_study_agents_path()

    provider.initialize()
    provider.get_api_key()
    model_id = provider.choose_model()

    # （可选）配置联网搜索 key —— 三家 provider 通用，留空则跳过、回退纯模型生成
    web_search.setup_search_key()
    # （可选）配置 AI 配图 key —— 默认使用 MiniMax-M3，留空则回退本地 SVG
    image_gen.setup_image_key()

    print("\n" + "#" * 60)
    print("#  📚 学习规划 · 多智能体协作系统")
    print("#  记忆 · 规划 · 工具   |   9 个 Agent 协同完成")
    print("#" * 60)
    print("\n协作流程：①任务编排 → ②需求澄清 → ③画像记忆 → ④资源搜索")
    print("        → ⑤资源评估 → ⑥知识整理 → ⑦计划生成 → ⑧多模态展示 → ⑨反馈调整")

    goal = read_goal()
    if not goal:
        print("未输入学习目标，已退出。")
        return

    state = SessionState(raw_goal=goal)
    provider.reset_conversation()

    display_agent = MultimodalDisplayAgent(provider, model_id, root)

    # 核心调用链：按顺序调度 9 个 Agent
    chain = [
        RouterAgent(provider, model_id),
        ClarificationAgent(provider, model_id),
        ProfileMemoryAgent(provider, model_id, root),
        ResourceSearchAgent(provider, model_id),
        ResourceEvaluationAgent(provider, model_id),
        KnowledgeOrganizationAgent(provider, model_id),
        PlanGenerationAgent(provider, model_id),
        display_agent,
        FeedbackAdjustmentAgent(provider, model_id, display_agent),
    ]

    total = len(chain)
    for i, agent in enumerate(chain, 1):
        agent.step_index = i
        agent.step_total = total
        try:
            agent.run(state)
        except KeyboardInterrupt:
            if interaction.confirm("\n确定要中断整个流程吗？", default=False):
                print("已中断。")
                break
            continue
        except Exception as err:  # 单个 Agent 失败不应让全流程崩溃
            print(f"\n⚠ Agent [{agent.label}] 执行出错：{err}")
            state.log(agent.label, f"ERROR: {err}")

    save_path = _save(root, state, model_id, provider.reply_label)   # canonical 报告，永远保留
    interaction.section("✅ 全流程结束")
    print(f"📄 学习计划已保存：\n   {save_path}")

    # 附加导出学习执行包；失败不影响已保存的报告
    try:
        package_dir = export_learning_package(provider, model_id, root, state)
    except Exception as err:
        package_dir = None
        print(f"⚠ 学习执行包导出失败（不影响已保存的报告）：{err}")
    if package_dir:
        print(f"📦 学习执行包已导出：\n   {package_dir}")

    print(f"🤝 本次共 {len(state.agent_log)} 步 Agent 协作，"
          f"{len(state.clarifications)} 项澄清，{len(state.feedback_rounds)} 轮反馈调整。")
    if state.is_returning_user:
        print("🗂️  本次命中了你的历史画像（长期记忆）。")


def _save(root: Path, state: SessionState, model_id: str, provider_label: str) -> Path:
    ref_dir = resolve_plan_dir(root, state.raw_goal)
    save_path = output_path(ref_dir, f"{model_id}-multiagent")
    report_markdown = _embed_images_for_save(
        state.display_markdown or state.plan_markdown,
        state.images,
    )

    lines = [
        f"# 学习规划（多智能体）：{state.raw_goal}",
        "",
        f"- Provider: {provider_label}",
        f"- Model: `{model_id}`",
        f"- 生成时间: {state.created_at}",
        f"- 老用户(命中长期记忆): {'是' if state.is_returning_user else '否'}",
        "",
        "---",
        "",
        report_markdown,
        "",
        "---",
        "",
        "## 🤝 多智能体协作日志",
        "",
    ]
    lines.extend(f"{i}. {line}" for i, line in enumerate(state.agent_log, 1))

    if state.clarifications:
        lines += ["", "## 🗣️ 需求澄清记录", ""]
        lines.extend(f"- **{q}** → {a}" for q, a in state.clarifications.items())

    if state.feedback_rounds:
        lines += ["", "## 🔄 反馈调整记录", ""]
        lines.extend(f"- {r.get('feedback', '')}" for r in state.feedback_rounds)

    save_path.write_text("\n".join(lines), encoding="utf-8")
    return save_path


def _embed_images_for_save(markdown: str, images: list[dict]) -> str:
    """Ensure generated local images are referenced in the saved Markdown."""
    if not markdown or not images:
        return markdown

    cover_lines: list[str] = []
    illustration_lines: list[str] = []
    for image in images:
        path = str(image.get("path", "")).replace("\\", "/").strip()
        if not path or path in markdown:
            continue
        alt = str(image.get("alt") or "学习规划配图").replace("]", ")")
        line = f"![{alt}]({path})"
        if image.get("role") == "cover":
            cover_lines.append(line)
        else:
            illustration_lines.append(line)
            if alt:
                illustration_lines.append(f"*{alt}*")
                illustration_lines.append("")

    result = markdown
    if cover_lines:
        result = _insert_after_first_heading(result, "\n".join(cover_lines) + "\n")
    if illustration_lines:
        block = "## 🖼️ 主题图示\n\n" + "\n".join(illustration_lines).rstrip() + "\n"
        result = _insert_before_section(result, block, "## 🗓️")
    return result


def _insert_after_first_heading(markdown: str, block: str) -> str:
    lines = markdown.splitlines()
    for idx, line in enumerate(lines):
        if line.startswith("# "):
            lines.insert(idx + 1, "")
            lines.insert(idx + 2, block.rstrip())
            return "\n".join(lines)
    return block.rstrip() + "\n\n" + markdown


def _insert_before_section(markdown: str, block: str, section_prefix: str) -> str:
    marker = f"\n{section_prefix}"
    pos = markdown.find(marker)
    if pos == -1:
        return markdown.rstrip() + "\n\n" + block.rstrip()
    return markdown[:pos].rstrip() + "\n\n" + block.rstrip() + markdown[pos:]
