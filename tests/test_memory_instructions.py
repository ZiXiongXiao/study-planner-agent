import json
import tempfile
import unittest
from pathlib import Path

from common.agent.multi.agents import ProfileMemoryAgent
from common.agent.multi.memory_store import load_memory_instructions, load_profile
from common.agent.multi.state import SessionState


class _Provider:
    def __init__(self):
        self.messages = None

    def chat(self, messages, model_id, tools=None):
        self.messages = messages
        return json.dumps({
            "level": "beginner",
            "weekly_hours": 6,
            "background": "普通上班族",
            "preferences": ["偏项目实战"],
            "resource_preferences": ["中文免费资源"],
            "constraints": ["晚上学习"],
            "output_format": "项目作品",
            "temporary_context": [],
            "uncertain_notes": [],
            "summary": "入门学习者，偏中文实战资源",
        }, ensure_ascii=False)


class MemoryInstructionTests(unittest.TestCase):
    def test_load_memory_instructions_reads_new_soul_files(self):
        root = Path(__file__).resolve().parents[1]
        text = load_memory_instructions(root)

        self.assertIn("memory-policy.md", text)
        self.assertIn("profile-schema.md", text)
        self.assertIn("memory-merge-rules.md", text)
        self.assertIn("不应该记住", text)

    def test_profile_memory_agent_injects_rules_and_saves_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            soul = root / "soul-instr"
            soul.mkdir()
            (soul / "memory-policy.md").write_text("不要保存 API Key。", encoding="utf-8")
            (soul / "profile-schema.md").write_text("必须输出 summary。", encoding="utf-8")
            (soul / "memory-merge-rules.md").write_text("本轮回答优先。", encoding="utf-8")

            provider = _Provider()
            st = SessionState(raw_goal="学 Python")
            st.clarifications = {"基础": "零基础", "时间": "每周 6 小时"}
            ProfileMemoryAgent(provider, "m", root).run(st)

            system_prompt = provider.messages[0]["content"]
            saved = load_profile(root, "学 Python")

        self.assertIn("不要保存 API Key", system_prompt)
        self.assertEqual(saved["summary"], "入门学习者，偏中文实战资源")
        self.assertEqual(st.profile["resource_preferences"], ["中文免费资源"])


if __name__ == "__main__":
    unittest.main()
