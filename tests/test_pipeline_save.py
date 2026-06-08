import tempfile
import unittest
from pathlib import Path

from common.agent.multi.pipeline import _save
from common.agent.multi.state import SessionState


class PipelineSaveTests(unittest.TestCase):
    def test_save_embeds_state_images_when_display_markdown_missing_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = SessionState(raw_goal="零基础学水彩画")
            state.display_markdown = "# 学习规划：零基础学水彩画\n\n## 周计划\n\n开始练习。"
            state.images = [
                {"role": "cover", "path": "assets/cover.png", "alt": "水彩学习封面"},
                {"role": "illustration", "path": "assets/illustration-1.png", "alt": "水彩工具"},
            ]

            save_path = _save(root, state, "m3", "MiniMax")

            content = save_path.read_text(encoding="utf-8")

        self.assertIn("![水彩学习封面](assets/cover.png)", content)
        self.assertIn("## 🖼️ 主题图示", content)
        self.assertIn("![水彩工具](assets/illustration-1.png)", content)

    def test_save_does_not_duplicate_existing_image_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = SessionState(raw_goal="零基础学水彩画")
            state.display_markdown = (
                "# 学习规划：零基础学水彩画\n\n"
                "![水彩学习封面](assets/cover.png)\n\n"
                "## 周计划\n\n开始练习。"
            )
            state.images = [
                {"role": "cover", "path": "assets/cover.png", "alt": "水彩学习封面"},
            ]

            save_path = _save(root, state, "m3", "MiniMax")

            content = save_path.read_text(encoding="utf-8")

        self.assertEqual(content.count("assets/cover.png"), 1)


if __name__ == "__main__":
    unittest.main()
