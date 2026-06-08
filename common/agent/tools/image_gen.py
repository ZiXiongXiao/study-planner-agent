"""
AI image generation tools for the multimodal display stage.

MiniMax image URLs can expire, so the public helper generates the image, downloads
it immediately, and stores it next to the Markdown report.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx

from common.agent.tools.registry import ToolRegistry, ToolResult, ToolSpec


MINIMAX_IMAGE_URL = "https://api.minimax.chat/v1/image_generation"
DEFAULT_IMAGE_MODEL = "m3"
IMAGE_MODEL_ALIASES = {
    "m3": "MiniMax-M3",
    "minimax-m3": "MiniMax-M3",
    "MiniMax-M3": "MiniMax-M3",
    "image-01": "image-01",
}
NO_TEXT_STYLE_SUFFIX = (
    "clean modern flat vector illustration, educational, soft colors, "
    "no text, no watermark"
)
DIAGRAM_STYLE_SUFFIX = (
    "clean educational infographic diagram, clear visual hierarchy, "
    "precise layout, readable concise labels if labels are requested, "
    "no watermark, no logo"
)


def get_image_key() -> str | None:
    """Read the shared MiniMax API key without exposing it in tool arguments."""
    key = os.environ.get("MINIMAX_API_KEY", "").strip()
    return key or None


def get_image_model() -> str:
    """Read the selected image model id. Defaults to M3 per Web settings."""
    model = os.environ.get("MINIMAX_IMAGE_MODEL", "").strip()
    return model or DEFAULT_IMAGE_MODEL


def _api_model_name(model: str | None = None) -> str:
    selected = (model or get_image_model()).strip() or DEFAULT_IMAGE_MODEL
    return IMAGE_MODEL_ALIASES.get(selected, selected)


def _image_endpoint() -> str:
    return os.environ.get("MINIMAX_IMAGE_URL", "").strip() or MINIMAX_IMAGE_URL


def setup_image_key() -> str | None:
    """Configure MiniMax image key at startup.

    Prefer MINIMAX_API_KEY from the environment. If it is missing, ask once in
    the CLI. Leaving the prompt empty skips image generation without affecting
    the text-only learning plan.
    """
    key = get_image_key()
    if key:
        print("🎨 已检测到 MINIMAX_API_KEY，多模态展示将启用 AI 配图。")
        return key

    print("\n" + "-" * 50)
    print("🎨 （可选）AI 配图配置")
    print("-" * 50)
    print("配置 MiniMax key 可让『多模态展示』生成本地封面图；视觉具象主题会额外")
    print("生成最多 2 张表征性插图。直接回车可跳过（不影响文字版学习计划）。")
    print("获取地址：https://platform.minimaxi.com")
    try:
        entered = input("请输入 MiniMax API Key（sk-...，留空跳过）：").strip()
    except (EOFError, KeyboardInterrupt):
        entered = ""

    if entered:
        os.environ["MINIMAX_API_KEY"] = entered
        print("✓ 已启用 AI 配图。")
        return entered

    print("→ 已跳过，后续将不生成 AI 配图。")
    return None


def _with_style(prompt: str, *, allow_text: bool = False) -> str:
    prompt = (prompt or "").strip()
    if not prompt:
        prompt = "an encouraging learner starting a study journey"
    suffix = DIAGRAM_STYLE_SUFFIX if allow_text else NO_TEXT_STYLE_SUFFIX
    return f"{prompt}. {suffix}"


def _first_url(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None

    def pick(value: Any) -> str | None:
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            for key in ("url", "image_url", "imageUrl"):
                url = value.get(key)
                if isinstance(url, str) and url.strip():
                    return url.strip()
        return None

    data = payload.get("data")
    if isinstance(data, dict):
        for key in ("image_urls", "imageUrls", "images"):
            values = data.get(key)
            if isinstance(values, list):
                for item in values:
                    url = pick(item)
                    if url:
                        return url
        url = pick(data)
        if url:
            return url

    if isinstance(data, list):
        for item in data:
            url = pick(item)
            if url:
                return url

    for key in ("image_urls", "imageUrls", "images"):
        values = payload.get(key)
        if isinstance(values, list):
            for item in values:
                url = pick(item)
                if url:
                    return url
    return None


def minimax_image(
    prompt: str,
    *,
    key: str,
    aspect_ratio: str = "16:9",
    model: str | None = None,
    allow_text: bool = False,
) -> str | None:
    """Generate one image with the selected MiniMax image model and return the temporary URL."""
    if not key:
        return None

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": _api_model_name(model),
        "prompt": _with_style(prompt, allow_text=allow_text),
        "aspect_ratio": aspect_ratio,
        "response_format": "url",
        "n": 1,
        "prompt_optimizer": True,
    }

    try:
        timeout = httpx.Timeout(180.0, connect=15.0)
        with httpx.Client(timeout=timeout, trust_env=False) as client:
            response = client.post(_image_endpoint(), headers=headers, json=body)
            response.raise_for_status()
            payload = response.json()
    except Exception:
        return None

    base_resp = payload.get("base_resp") if isinstance(payload, dict) else None
    if isinstance(base_resp, dict):
        status = base_resp.get("status_code")
        if status not in (None, 0, "0"):
            return None

    return _first_url(payload)


def download(url: str) -> bytes | None:
    """Download image bytes from a temporary MiniMax URL."""
    if not url:
        return None
    try:
        timeout = httpx.Timeout(120.0, connect=15.0)
        with httpx.Client(timeout=timeout, trust_env=False) as client:
            response = client.get(url)
            response.raise_for_status()
            return response.content or None
    except Exception:
        return None


def generate_and_save(
    prompt: str,
    dest_dir: str | Path,
    filename: str,
    *,
    key: str | None,
    aspect_ratio: str = "16:9",
    model: str | None = None,
    allow_text: bool = False,
) -> bool:
    """Generate an image, download it, and write it to ``dest_dir/filename``."""
    if not key:
        return False

    url = minimax_image(prompt, key=key, aspect_ratio=aspect_ratio, model=model, allow_text=allow_text)
    if not url:
        return False

    content = download(url)
    if not content:
        return False

    try:
        dest = Path(dest_dir)
        dest.mkdir(parents=True, exist_ok=True)
        path = dest / Path(filename).name
        path.write_bytes(content)
        return True
    except Exception:
        return False


def _gen_image_tool(
    prompt: str,
    dest_dir: str | Path,
    filename: str,
    aspect_ratio: str = "16:9",
    allow_text: bool = False,
    model: str | None = None,
) -> ToolResult:
    key = get_image_key()
    ok = generate_and_save(
        prompt,
        dest_dir,
        filename,
        key=key,
        aspect_ratio=aspect_ratio,
        model=model,
        allow_text=allow_text,
    )
    safe_name = Path(filename).name
    if not ok:
        return ToolResult(
            name="generate_image",
            success=False,
            summary=f"图片生成失败或已跳过：{safe_name}",
        )

    return ToolResult(
        name="generate_image",
        success=True,
        summary=f"图片已保存：{safe_name}",
        data={"path": str(Path(dest_dir) / safe_name)},
    )


def build_image_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="generate_image",
            description="Generate and save an educational image with the selected MiniMax image model.",
            handler=_gen_image_tool,
        )
    )
    return registry
