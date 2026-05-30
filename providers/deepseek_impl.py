#!/usr/bin/env python3
"""
DeepSeek Provider Implementation for Study Planner Agent
基于 DeepSeek API 的模型适配器
"""

from __future__ import annotations

import httpx
import os


class DeepSeekProvider:
    reply_label = "DeepSeek"
    BASE_URL = "https://api.deepseek.com/v1"

    MODELS = {
        "deepseek-v4-flash": "deepseek-chat",
        "deepseek-v4": "deepseek-chat",
        "deepseek-coder": "deepseek-coder",
    }

    def __init__(self) -> None:
        self.api_key: str | None = None
        self.conversation_history: list[dict] = []

    def initialize(self) -> None:
        print(f"Using {self.reply_label} provider")

    def get_api_key(self) -> None:
        env_key = os.environ.get("DEEPSEEK_API_KEY")
        if env_key:
            self.api_key = env_key
            print("Loaded API key from environment")
            return

        print("\n" + "=" * 50)
        print("DeepSeek API Key Setup")
        print("=" * 50)
        print("\nEnter your DeepSeek API Key (sk-...):")
        print("(Get your key from https://platform.deepseek.com)")
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

        print("\nEnter model name [deepseek-v4-flash]:", end=" ")
        choice = input().strip()

        if not choice:
            choice = "deepseek-v4-flash"

        if choice not in self.MODELS:
            print(f"⚠ Unknown model '{choice}', using deepseek-v4-flash")
            choice = "deepseek-v4-flash"

        print(f"✓ Selected: {choice}")
        return choice

    def chat(self, messages: list[dict], model_id: str) -> str:
        if not self.api_key:
            raise RuntimeError("API key not set")

        model_name = self.MODELS.get(model_id, "deepseek-chat")

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
        print("🤖 DeepSeek is thinking...")
        print("-" * 50)

        try:
            with httpx.Client(timeout=120.0) as client:
                response = client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()

            return data["choices"][0]["message"]["content"]

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise RuntimeError("Invalid API key. Please check your DeepSeek API key.")
            elif e.response.status_code == 429:
                raise RuntimeError("Rate limit exceeded. Please try again later.")
            else:
                raise RuntimeError(f"HTTP error: {e.response.status_code}")
        except Exception as e:
            raise RuntimeError(f"Request failed: {str(e)}")

    def reset_conversation(self) -> None:
        self.conversation_history = []
