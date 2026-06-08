#!/usr/bin/env python3
"""
Study Planner Agent - MiniMax 入口
智能学习规划助手 · 多智能体协作（单一模式）

按 5 层架构、9 个 Agent 的核心调用链完成学习规划。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from providers.minimax_impl import MiniMaxProvider
from common.agent.multi import run_multi_agent


def main():
    provider = MiniMaxProvider()
    run_multi_agent(provider)


if __name__ == "__main__":
    main()
