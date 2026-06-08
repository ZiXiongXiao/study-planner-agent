#!/usr/bin/env python3
"""
Kimi Provider Implementation for Study Planner Agent
基于 Moonshot API 的 Kimi 模型适配器
"""

from __future__ import annotations

import httpx
import os
import time


class KimiProvider:
    reply_label = "Kimi"
    BASE_URL = "https://api.moonshot.cn/v1"

    MODELS = {
        "kimi-k2.6": "moonshot-v1-256k",
        "kimi-k2": "moonshot-v1-32k",
        "kimi-lite": "moonshot-v1-8k",
    }

    def __init__(self) -> None:
        self.api_key: str | None = None
        self.conversation_history: list[dict] = []

    def initialize(self) -> None:
        print(f"Using {self.reply_label} provider")

    def get_api_key(self) -> None:
        env_key = os.environ.get("MOONSHOT_API_KEY")
        if env_key:
            self.api_key = env_key
            print("Loaded API key from environment")
            return

        print("\n" + "=" * 50)
        print("Moonshot API Key Setup")
        print("=" * 50)
        print("\nEnter your Moonshot API Key (sk-...):")
        print("(Get your key from https://platform.moonshot.cn)")
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

        print("\nEnter model name [kimi-k2.6]:", end=" ")
        choice = input().strip()

        if not choice:
            choice = "kimi-k2.6"

        if choice not in self.MODELS:
            print(f"⚠ Unknown model '{choice}', using kimi-k2.6")
            choice = "kimi-k2.6"

        print(f"✓ Selected: {choice}")
        return choice

    def chat(self, messages: list[dict], model_id: str, tools: list | None = None) -> "str | dict":
        if not self.api_key:
            raise RuntimeError("API key not set")

        model_name = self.MODELS.get(model_id, "moonshot-v1-256k")

        url = f"{self.BASE_URL}/chat/completions"
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
        print("🤖 Kimi is thinking...")
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
                message = data["choices"][0]["message"]
                # 传了 tools 则返回完整 message（可能含 tool_calls）；否则只取文本。
                return message if tools else message.get("content", "")

            except httpx.HTTPStatusError as e:
                code = e.response.status_code
                if code == 401:
                    raise RuntimeError("Invalid API key. Please check your Moonshot API key.")
                if code == 429:
                    if attempt < max_retries:
                        wait = 5 * (attempt + 1)
                        print(f"   ⏳ 触发限流(429)，{wait}s 后重试（第 {attempt + 1}/{max_retries} 次）...")
                        time.sleep(wait)
                        continue
                    raise RuntimeError(
                        "多次重试仍被限流(429)。通常是账户免费额度用尽或余额不足，"
                        "请到 platform.moonshot.cn 查看额度，或改用 DeepSeek。"
                    )
                raise RuntimeError(f"HTTP error: {code}")
            except httpx.ConnectError as e:
                raise RuntimeError(
                    "无法连接 api.moonshot.cn。请检查网络是否正常、是否能直接访问该域名。"
                    f"（已默认直连不走代理）原始错误：{e}"
                )
            except httpx.TimeoutException as e:
                if attempt < max_retries:
                    print(f"   ⏳ 请求超时，重试（第 {attempt + 1}/{max_retries} 次）...")
                    continue
                raise RuntimeError(f"请求多次超时，可稍后重试。原始错误：{e}")
            except Exception as e:
                raise RuntimeError(f"Request failed: {str(e)}")

    def reset_conversation(self) -> None:
        self.conversation_history = []
