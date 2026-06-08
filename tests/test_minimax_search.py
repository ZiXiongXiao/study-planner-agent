import os
import unittest
from unittest.mock import patch

from common.agent.tools import web_search


class MiniMaxSearchMergeTests(unittest.TestCase):
    def test_retrieve_merges_tavily_and_minimax_search_results(self):
        queries = [{"type": "video", "query": "AI Agent 应用开发 bilibili 教程"}]
        tavily_hits = [{"title": "Tavily Course", "url": "https://example.com/course", "content": "course"}]
        minimax_hits = [{"title": "Bilibili AI Agent 教程", "url": "https://www.bilibili.com/video/BV1xx", "content": "中文视频"}]

        with patch.dict(os.environ, {"MINIMAX_API_KEY": "sk-mini"}, clear=True), \
             patch.object(web_search, "tavily_search", return_value=tavily_hits), \
             patch.object(web_search, "minimax_mcp_search", return_value=minimax_hits) as mm:
            hits = web_search.retrieve(queries, key="tvly-test", topic="", per_query=2)

        urls = [h["url"] for h in hits]
        self.assertIn("https://example.com/course", urls)
        self.assertIn("https://www.bilibili.com/video/BV1xx", urls)
        self.assertEqual(hits[-1]["source"], "minimax")
        mm.assert_called_once_with("AI Agent 应用开发 bilibili 教程", max_results=2)

    def test_retrieve_can_use_minimax_when_tavily_key_is_missing(self):
        queries = [{"type": "video", "query": "Python 入门 B站"}]
        minimax_hits = [{"title": "Python B站课", "url": "https://www.bilibili.com/video/BV2xx"}]

        with patch.dict(os.environ, {"MINIMAX_API_KEY": "sk-mini"}, clear=True), \
             patch.object(web_search, "tavily_search") as tavily, \
             patch.object(web_search, "minimax_mcp_search", return_value=minimax_hits):
            hits = web_search.retrieve(queries, key=None, topic="", per_query=2)

        self.assertEqual([h["url"] for h in hits], ["https://www.bilibili.com/video/BV2xx"])
        tavily.assert_not_called()


if __name__ == "__main__":
    unittest.main()
