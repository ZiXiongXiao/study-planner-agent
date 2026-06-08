"""
扩展检索源（供 Python 侧直接调用）。

  - github_search：GitHub 仓库搜索，按 stars 排序（star 数=质量信号），免 key
                   （未认证 60 次/小时）。给"找项目/实战代码"提供真实、可排序的结果。
  - arxiv_search ：arXiv 论文搜索（公开 Atom API），免 key。给"找论文/综述"提供真实结果。
  - fetch_url    ：抓取网页正文纯文本（截断），用于让模型/评估基于真实内容判断。

设计原则：全部对异常宽容——失败返回 success=False 的 ToolResult，绝不抛异常打断流程。
这些来源给精确度提供"模型编不出来的事实"（真实仓库、星标、论文）。
"""

from __future__ import annotations

import re
from xml.etree import ElementTree as ET

import httpx

from common.agent.tools.registry import ToolResult

_TIMEOUT = httpx.Timeout(15.0, connect=8.0)
_UA = {"User-Agent": "Mozilla/5.0 (StudyPlannerBot)"}


def github_search(query: str, limit: int = 5) -> ToolResult:
    """搜索 GitHub 高星仓库。返回 [{title,type,url,stars,why}]。"""
    url = "https://api.github.com/search/repositories"
    params = {"q": query, "sort": "stars", "order": "desc",
              "per_page": max(1, min(int(limit), 10))}
    try:
        headers = {**_UA, "Accept": "application/vnd.github+json"}
        with httpx.Client(timeout=_TIMEOUT, headers=headers) as c:
            r = c.get(url, params=params)
            r.raise_for_status()
            items = r.json().get("items", []) or []
    except Exception as e:
        return ToolResult(name="github_search", success=False,
                          summary=f"GitHub 搜索失败：{e}", data=[], error=str(e))
    repos = [{
        "title": it.get("full_name", ""),
        "type": "github",
        "url": it.get("html_url", ""),
        "stars": it.get("stargazers_count", 0),
        "why": (it.get("description") or "").strip()[:80],
    } for it in items if it.get("html_url")]
    return ToolResult(name="github_search", success=True,
                      summary=f"GitHub 命中 {len(repos)} 个高星仓库", data=repos)


_ARXIV_NS = {"a": "http://www.w3.org/2005/Atom"}


def arxiv_search(query: str, limit: int = 5) -> ToolResult:
    """搜索 arXiv 论文。返回 [{title,type,url,why}]。"""
    url = "http://export.arxiv.org/api/query"
    params = {"search_query": f"all:{query}", "start": 0,
              "max_results": max(1, min(int(limit), 10))}
    try:
        with httpx.Client(timeout=_TIMEOUT, headers=_UA) as c:
            r = c.get(url, params=params)
            r.raise_for_status()
            root = ET.fromstring(r.text)
    except Exception as e:
        return ToolResult(name="arxiv_search", success=False,
                          summary=f"arXiv 搜索失败：{e}", data=[], error=str(e))
    papers = []
    for entry in root.findall("a:entry", _ARXIV_NS):
        title = (entry.findtext("a:title", default="", namespaces=_ARXIV_NS) or "").strip()
        link = (entry.findtext("a:id", default="", namespaces=_ARXIV_NS) or "").strip()
        summary = (entry.findtext("a:summary", default="", namespaces=_ARXIV_NS) or "").strip()
        if link:
            papers.append({"title": re.sub(r"\s+", " ", title),
                           "type": "paper", "url": link, "why": summary[:80]})
    return ToolResult(name="arxiv_search", success=True,
                      summary=f"arXiv 命中 {len(papers)} 篇论文", data=papers)


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def fetch_url(url: str, max_chars: int = 2000) -> ToolResult:
    """抓取网页正文纯文本（去标签、截断）。返回 data 为字符串。"""
    try:
        with httpx.Client(timeout=_TIMEOUT, headers=_UA, follow_redirects=True) as c:
            r = c.get(url)
            r.raise_for_status()
            html = r.text
    except Exception as e:
        return ToolResult(name="fetch_url", success=False,
                          summary=f"抓取失败：{e}", data="", error=str(e))
    html = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    text = _WS_RE.sub(" ", _TAG_RE.sub(" ", html)).strip()[:max_chars]
    return ToolResult(name="fetch_url", success=True,
                      summary=f"抓取 {len(text)} 字正文", data=text)
