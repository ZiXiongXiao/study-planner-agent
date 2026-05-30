#!/usr/bin/env python3
"""
Study Planner Agent - Kimi Provider Entry Point
智能学习规划助手 - Kimi 平台入口
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from providers.kimi import KimiProvider
from common.agent.orchestrator import run_study_agent


def main():
    provider = KimiProvider()
    run_study_agent(provider)


if __name__ == "__main__":
    main()
