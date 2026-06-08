#!/usr/bin/env python3
"""
MiniMax Provider Implementation for Study Planner Agent
基于 MiniMax 开放平台的模型适配器（chatcompletion_v2，OpenAI 兼容格式）
"""

from __future__ import annotations

import httpx
import os
import time


class MiniMaxProvider:
    reply_label = "MiniMax"
    # 国内站；国际站为 https://api.minimaxi.com/v1
    BASE_URL = "https://api.minimax.chat/v1"

    MODELS = {
        "m3": "MiniMax-M3",
        "m2.7": "MiniMax-M2.7",
    }

    def __init__(self) -> None:
        self.api_key: str | None = None
        self.conversation_history: list[dict] = []

    def initialize(self) -> None:
        print(f"Using {self.reply_label} provider")

    def get_api_key(self) -> None:
        env_key = os.environ.get("MINIMAX_API_KEY")
        if env_key:
            self.api_key = env_key
            print("Loaded API key from environment")
            return

        print("\n" + "=" * 50)
        print("MiniMax API Key Setup")
        print("=" * 50)
        print("\nEnter your MiniMax API Key:")
        print("(Get your key from https://platform.minimaxi.com)")
        key = input().strip()

        if not key:
            raise ValueError("API key is required")

        self.api_key = key

    def choose_model(self) -> str:
        print("\n" + "=" * 50)
        print("Available Models:")
        print("=" * 50)
        for display_name, _ in self.MODELS.items():
            print(f"  • {display_name}")

        print("\nEnter model name [m3]:", end=" ")
        choice = input().strip()

        if not choice:
            choice = "m3"

        if choice not in self.MODELS:
            print(f"⚠ Unknown model '{choice}', using m3")
            choice = "m3"

        print(f"✓ Selected: {choice}")
        return choice

    def chat(self, messages: list[dict], model_id: str, tools: list | None = None) -> "str | dict":
        if not self.api_key:
            raise RuntimeError("API key not set")

        model_name = self.MODELS.get(model_id, "MiniMax-M3")

        url = f"{self.BASE_URL}/text/chatcompletion_v2"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        payload = {
            "model": model_name,
            "messages": messages,
            "temperature": 0.7,
        }
        # 仅在显式传入工具时开启 function-calling；否则保持原有纯文本行为。
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        print("\n" + "-" * 50)
        print("🤖 MiniMax is thinking...")
        print("-" * 50)

        max_retries = 3
        for attempt in range(max_retries + 1):
            try:
                # trust_env=False：忽略系统代理(HTTP_PROXY 等)，国内 API 直连，
                # 避免残留代理导致 WinError 10061 连接被拒。
                # read=300s：大模型生成长内容（如计划生成）较慢，避免读取超时
                timeout = httpx.Timeout(300.0, connect=15.0)
                with httpx.Client(timeout=timeout, trust_env=False) as client:
                    response = client.post(url, headers=headers, json=payload)
                    response.raise_for_status()
                    data = response.json()

                # MiniMax 的业务错误放在 base_resp 里（HTTP 仍是 200）
                base = data.get("base_resp", {})
                if base and base.get("status_code", 0) != 0:
                    raise RuntimeError(
                        f"MiniMax error {base.get('status_code')}: {base.get('status_msg', '')}"
                    )
                if "choices" not in data:
                    raise RuntimeError(f"Unexpected response: {data}")
                message = data["choices"][0]["message"]
                # 传了 tools 则返回完整 message（可能含 tool_calls）；否则只取文本。
                return message if tools else message.get("content", "")

            except httpx.HTTPStatusError as e:
                code = e.response.status_code
                if code == 401:
                    raise RuntimeError("Invalid API key. Please check your MiniMax API key.")
                if code == 429:
                    if attempt < max_retries:
                        wait = 5 * (attempt + 1)
                        print(f"   ⏳ 触发限流(429)，{wait}s 后重试（第 {attempt + 1}/{max_retries} 次）...")
                        time.sleep(wait)
                        continue
                    raise RuntimeError(
                        "多次重试仍被限流(429)。通常是账户额度用尽或余额不足，"
                        "请到 platform.minimaxi.com 查看额度。"
                    )
                raise RuntimeError(f"HTTP error: {code}")
            except httpx.ConnectError as e:
                raise RuntimeError(
                    "无法连接 api.minimax.chat。请检查网络是否正常、是否能直接访问该域名。"
                    f"（已默认直连不走代理）原始错误：{e}"
                )
            except httpx.TimeoutException as e:
                if attempt < max_retries:
                    print(f"   ⏳ 请求超时，重试（第 {attempt + 1}/{max_retries} 次）...")
                    continue
                raise RuntimeError(
                    "请求多次超时。M3 生成长内容较慢，可重试，或在选择模型时改用更快的型号。"
                    f"原始错误：{e}"
                )
            except Exception as e:
                raise RuntimeError(f"Request failed: {str(e)}")

    def reset_conversation(self) -> None:
        self.conversation_history = []
