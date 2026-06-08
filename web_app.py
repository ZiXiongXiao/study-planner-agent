#!/usr/bin/env python3
"""Start the local Study Planner web workspace."""

from __future__ import annotations

import argparse

from common.agent.web_app import run_server


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Study Planner Agent web UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    run_server(args.host, args.port)


if __name__ == "__main__":
    main()
