import tempfile
import unittest
import xml.dom.minidom as minidom
from pathlib import Path

from common.agent.tools import diagram_render as dr


def _read(base, rel):
    return (Path(base) / "assets" / rel.split("/")[-1]).read_text(encoding="utf-8")


class DiagramRenderTests(unittest.TestCase):
    def setUp(self):
        self.base = tempfile.mkdtemp()
        self.assets = str(Path(self.base) / "assets")   # 渲染器把 dest_dir 当作 assets 目录

    def _valid(self, rel):
        self.assertTrue(rel and rel.startswith("assets/") and rel.endswith(".svg"))
        txt = _read(self.base, rel)
        minidom.parseString(txt)                        # 必须是合法 XML/SVG
        self.assertTrue(txt.startswith("<svg") and txt.endswith("</svg>"))
        return txt

    def test_knowledge_map(self):
        rel = dr.render_knowledge_map(
            "Python 数据分析",
            [{"name": "基础语法", "topics": ["变量", "控制流"]},
             {"name": "Pandas", "topics": ["Series", "DataFrame", "清洗"]}],
            self.assets, "knowledge-map")
        txt = self._valid(rel)
        self.assertIn("基础语法", txt)
        self.assertIn("DataFrame", txt)

    def test_chain_and_cyclic(self):
        wf = dr.render_chain(["URL", "请求", "解析", "报告"], self.assets, "workflow", title="爬虫数据流")
        self.assertIn("爬虫数据流", self._valid(wf))
        loop = dr.render_chain(["学知识", "做题", "复盘", "模考"], self.assets, "practice-loop", cyclic=True)
        txt = self._valid(loop)
        self.assertIn("循环", txt)
        self.assertIn("stroke-dasharray", txt)          # 回流虚线箭头

    def test_deliverables(self):
        rel = dr.render_deliverables(["爬虫.py", "分析.ipynb", "README"], self.assets, "deliverables")
        self.assertIn("README", self._valid(rel))

    def test_guards_return_none_without_throw(self):
        self.assertIsNone(dr.render_chain(["仅一个"], self.assets, "x"))   # <2 步
        self.assertIsNone(dr.render_chain([], self.assets, "x"))
        self.assertIsNone(dr.render_knowledge_map("r", [], self.assets, "x"))
        self.assertIsNone(dr.render_knowledge_map("r", None, self.assets, "x"))
        self.assertIsNone(dr.render_deliverables([], self.assets, "x"))

    def test_sanitize_and_truncate(self):
        txt = self._valid(dr.render_chain(['<bad> & "q"', "a[b]c", "长" * 40], self.assets, "san"))
        self.assertIn("&lt;bad&gt;", txt)               # 尖括号被转义
        self.assertIn("&amp;", txt)
        self.assertNotIn("<bad>", txt)
        self.assertIn("…", txt)                          # 超长截断
        self.assertNotIn("[b]", txt)                     # 方括号被替换


if __name__ == "__main__":
    unittest.main()
