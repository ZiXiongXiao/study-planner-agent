"""
Multi-Agent Study Planner
多智能体学习规划系统

按 5 层架构、9 个 Agent 的核心调用链协作完成学习规划：
用户输入 → 任务编排 → 需求澄清 → 画像记忆 → 资源搜索 → 资源评估
        → 知识整理 → 计划生成 → 多模态展示 → 反馈调整
"""

from common.agent.multi.pipeline import run_multi_agent

__all__ = ["run_multi_agent"]
