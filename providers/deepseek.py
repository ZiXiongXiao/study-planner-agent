#!/usr/bin/env python3
"""
Study Planner Agent - DeepSeek Provider Entry Point
智能学习规划助手 - DeepSeek 平台入口
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from providers.deepseek_impl import DeepSeekProvider
from common.agent.orchestrator import run_study_agent


def main():
    provider = DeepSeekProvider()
    run_study_agent(provider)


if __name__ == "__main__":
    main()
