#!/usr/bin/env python3
"""
Kimi Provider Implementation for Study Planner Agent
基于 Moonshot API 的 Kimi 模型适配器
"""

from __future__ import annotations

import httpx
import os


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

    def chat(self, messages: list[dict], model_id: str) -> str:
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

        print("\n" + "-" * 50)
        print("🤖 Kimi is thinking...")
        print("-" * 50)

        try:
            with httpx.Client(timeout=120.0) as client:
                response = client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()

            return data["choices"][0]["message"]["content"]

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise RuntimeError("Invalid API key. Please check your Moonshot API key.")
            elif e.response.status_code == 429:
                raise RuntimeError("Rate limit exceeded. Please try again later.")
            else:
                raise RuntimeError(f"HTTP error: {e.response.status_code}")
        except Exception as e:
            raise RuntimeError(f"Request failed: {str(e)}")

    def reset_conversation(self) -> None:
        self.conversation_history = []
