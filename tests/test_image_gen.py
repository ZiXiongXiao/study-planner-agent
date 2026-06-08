import os
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from common.agent.tools import image_gen


class _FakeResponse:
    def __init__(self, payload=None, content=b"", status_code=200):
        self._payload = payload or {}
        self.content = content
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeClient:
    calls = []

    def __init__(self, *args, **kwargs):
        self.kwargs = kwargs

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, url, headers=None, json=None):
        self.calls.append({
            "url": url,
            "headers": headers,
            "json": json,
            "trust_env": self.kwargs.get("trust_env"),
        })
        return _FakeResponse({
            "base_resp": {"status_code": 0},
            "data": {"image_urls": ["https://example.test/image.png"]},
        })


class ImageGenToolTests(unittest.TestCase):
    def test_minimax_image_uses_selected_m3_model_and_returns_first_url(self):
        _FakeClient.calls = []

        with patch("common.agent.tools.image_gen.httpx.Client", _FakeClient):
            url = image_gen.minimax_image("paint a learner", key="secret", aspect_ratio="1:1", model="m3")

        self.assertEqual(url, "https://example.test/image.png")
        call = _FakeClient.calls[0]
        self.assertEqual(call["url"], "https://api.minimax.chat/v1/image_generation")
        self.assertIs(call["trust_env"], False)
        self.assertEqual(call["headers"]["Authorization"], "Bearer secret")
        self.assertEqual(call["json"]["model"], "MiniMax-M3")
        self.assertEqual(call["json"]["aspect_ratio"], "1:1")
        self.assertEqual(call["json"]["response_format"], "url")
        self.assertTrue(call["json"]["prompt_optimizer"])
        self.assertIn("no text", call["json"]["prompt"])
        self.assertIn("no watermark", call["json"]["prompt"])

    def test_minimax_image_can_allow_text_for_diagrams(self):
        _FakeClient.calls = []

        with patch("common.agent.tools.image_gen.httpx.Client", _FakeClient):
            image_gen.minimax_image("draw a roadmap with labels", key="secret", allow_text=True)

        prompt = _FakeClient.calls[0]["json"]["prompt"]
        self.assertIn("readable concise labels", prompt)
        self.assertNotIn("no text", prompt)

    def test_generate_and_save_writes_downloaded_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            with patch("common.agent.tools.image_gen.minimax_image", return_value="https://example.test/image.png"):
                with patch("common.agent.tools.image_gen.download", return_value=b"PNGDATA"):
                    ok = image_gen.generate_and_save(
                        "cover prompt",
                        dest,
                        "cover.png",
                        key="secret",
                        aspect_ratio="16:9",
                        model="m3",
                    )

            self.assertTrue(ok)
            self.assertEqual((dest / "cover.png").read_bytes(), b"PNGDATA")

    def test_generate_and_save_without_key_degrades_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            ok = image_gen.generate_and_save(
                "cover prompt",
                dest,
                "cover.png",
                key=None,
                aspect_ratio="16:9",
            )

            self.assertFalse(ok)
            self.assertFalse((dest / "cover.png").exists())

    def test_setup_image_key_uses_existing_env_without_prompting(self):
        with patch.dict(os.environ, {"MINIMAX_API_KEY": "  sk-existing  "}, clear=True):
            with patch("builtins.input", side_effect=AssertionError("should not prompt")):
                with redirect_stdout(StringIO()):
                    key = image_gen.setup_image_key()

        self.assertEqual(key, "sk-existing")

    def test_setup_image_key_prompts_and_stores_entered_key(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch("builtins.input", return_value="sk-entered"):
                with redirect_stdout(StringIO()):
                    key = image_gen.setup_image_key()
                stored = os.environ.get("MINIMAX_API_KEY")

        self.assertEqual(key, "sk-entered")
        self.assertEqual(stored, "sk-entered")

    def test_setup_image_key_allows_empty_skip(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch("builtins.input", return_value=""):
                with redirect_stdout(StringIO()):
                    key = image_gen.setup_image_key()
                stored = os.environ.get("MINIMAX_API_KEY")

        self.assertIsNone(key)
        self.assertIsNone(stored)


if __name__ == "__main__":
    unittest.main()
