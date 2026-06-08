"""
Web 搜索工具：为『资源搜索 Agent』提供真实检索能力。

设计原则（见交付计划）：
  - 仅依赖 httpx，单一环境变量 TAVILY_API_KEY。
  - 多样性：按资源类型分多路查询（build_typed_queries / retrieve）。
  - 精确度：对候选 URL 做存活校验，丢弃死链（validate_urls）。
  - 全程对异常宽容：任何失败都返回空/False，绝不抛异常打断主流程。

LLM 负责"推理/筛选"，本模块只负责"提供真实数据"，与项目既有
"工具在 Python 侧执行、结果喂给 LLM"的架构一致。
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit, urlunsplit

import httpx

from common.agent.tools.registry import ToolRegistry, ToolSpec, ToolResult

TAVILY_URL = "https://api.tavily.com/search"
MINIMAX_MCP_HOST = "https://api.minimax.io"

# 资源类型 -> 查询模板。键名与 display.resource_cards 的图标键保持一致，
# 这样不同类型会被渲染成对应图标，天然形成多样性。
_QUERY_TEMPLATES: list[tuple[str, str]] = [
    ("course", "{goal} 在线课程 教程"),
    ("video", "{goal} 视频教程"),
    ("github", "{goal} GitHub 开源项目"),
    ("blog", "{goal} 入门 实战 博客"),
    ("paper", "{topic} 论文 综述 arXiv"),
    ("documentation", "{goal} 官方文档"),
]


def get_search_key() -> str | None:
    """读取 Tavily API key；未配置返回 None（沿用 providers 的取 key 习惯）。"""
    key = os.environ.get("TAVILY_API_KEY")
    return key.strip() if key else None


def get_minimax_search_key() -> str | None:
    """读取 MiniMax Web Search MCP key。

    优先使用专门的 MINIMAX_SEARCH_API_KEY；未配置时复用 MINIMAX_API_KEY，和图生成/主模型
    的配置习惯保持一致。未安装 MCP 运行时也只会降级跳过，不影响主流程。
    """
    key = os.environ.get("MINIMAX_SEARCH_API_KEY") or os.environ.get("MINIMAX_API_KEY")
    return key.strip() if key else None


def setup_search_key() -> str | None:
    """启动时配置 Tavily 搜索 key（可选，三家 provider 通用）。

    优先用环境变量 TAVILY_API_KEY；未设置则交互式询问，**留空即跳过**（资源搜索
    会自动回退为纯模型生成）。用户输入的 key 写回进程环境，供后续 get_search_key
    读取。返回最终生效的 key 或 None。
    """
    key = get_search_key()
    if key:
        print("🌐 已检测到 TAVILY_API_KEY，资源搜索将启用真实联网检索。")
        return key

    print("\n" + "-" * 50)
    print("🌐 （可选）联网搜索配置")
    print("-" * 50)
    print("配置 Tavily key 可让『资源搜索』真实联网检索并校验链接存活，资源更精确、")
    print("更多样；直接回车可跳过（改用纯模型生成，不影响运行）。")
    print("获取地址：https://tavily.com")
    try:
        entered = input("请输入 Tavily API Key（tvly-…，留空跳过）：").strip()
    except (EOFError, KeyboardInterrupt):
        entered = ""

    if entered:
        os.environ["TAVILY_API_KEY"] = entered
        print("✓ 已启用联网搜索。")
        return entered

    print("→ 已跳过，资源搜索将使用纯模型生成。")
    return None


def topic_of(goal: str, domain: str = "", keywords=None) -> str:
    """归纳一个简洁主题串，用于 GitHub/arXiv 这类需要精炼查询的源。"""
    kw = " ".join(keywords[:3]) if keywords else ""
    return f"{domain} {kw}".strip() or (goal or "").strip()


def build_typed_queries(goal: str, domain: str = "", keywords=None) -> list[dict]:
    """按资源类型构造多路查询，作为搜索多样性的来源。返回 [{type, query}]。"""
    goal = (goal or "").strip()
    topic = topic_of(goal, domain, keywords)
    queries: list[dict] = []
    for rtype, template in _QUERY_TEMPLATES:
        q = template.format(goal=goal, topic=topic).strip()
        if q:
            queries.append({"type": rtype, "query": q})
    return queries


def tavily_search(query: str, *, key: str, max_results: int = 3) -> list[dict]:
    """调用 Tavily 检索单条 query，归一化为 [{title,url,content}]。失败返回 []。"""
    payload = {
        "api_key": key,
        "query": query,
        "max_results": max_results,
        "search_depth": "basic",
    }
    # 注意：Tavily 是境外端点，与境内 LLM API 相反——这里尊重系统代理(默认
    # trust_env=True)，国内用户可能需要本机代理才能访问。
    timeout = httpx.Timeout(20.0, connect=10.0)
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.post(TAVILY_URL, json=payload)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:  # 网络/鉴权/解析任何异常都不打断主流程
        print(f"   ⚠ 搜索失败（{query[:20]}…）：{e}")
        return []

    results: list[dict] = []
    for item in data.get("results", []) or []:
        url = (item.get("url") or "").strip()
        if not url:
            continue
        results.append({
            "title": (item.get("title") or url).strip(),
            "url": url,
            "content": (item.get("content") or "").strip(),
        })
    return results


def _minimax_mcp_command() -> list[str] | None:
    configured = os.environ.get("MINIMAX_SEARCH_CMD", "").strip()
    if configured:
        return shlex.split(configured, posix=(os.name != "nt"))
    if not shutil.which("uvx"):
        return None
    return ["uvx", "minimax-coding-plan-mcp", "-y"]


def _coerce_search_items(value) -> list[dict]:
    if isinstance(value, dict):
        for key in ("results", "data", "items", "search_results"):
            if isinstance(value.get(key), list):
                return _coerce_search_items(value[key])
        url = str(value.get("url") or value.get("link") or "").strip()
        if url:
            return [{
                "title": str(value.get("title") or value.get("name") or url).strip(),
                "url": url,
                "content": str(value.get("content") or value.get("snippet") or value.get("summary") or "").strip(),
            }]
        return []
    if isinstance(value, list):
        out: list[dict] = []
        for item in value:
            out.extend(_coerce_search_items(item))
        return out
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            return _coerce_search_items(json.loads(text))
        except Exception:
            pass
        urls = re.findall(r"https?://[^\s)\]>\"']+", text)
        out = []
        for url in urls:
            out.append({"title": url, "url": url, "content": ""})
        return out
    return []


def _extract_mcp_search_items(payload: dict) -> list[dict]:
    result = payload.get("result") if isinstance(payload, dict) else None
    if not isinstance(result, dict):
        return []
    direct = _coerce_search_items(result)
    if direct:
        return direct
    content = result.get("content")
    if isinstance(content, list):
        out: list[dict] = []
        for block in content:
            if isinstance(block, dict):
                out.extend(_coerce_search_items(block.get("text") or block.get("data") or block))
        return out
    return _coerce_search_items(content)


def minimax_mcp_search(query: str, *, max_results: int = 3) -> list[dict]:
    """Best-effort MiniMax Token Plan MCP web_search.

    这是可选增强：需要本机可执行 uvx/minimax-coding-plan-mcp，且存在 MiniMax key。
    任意失败都返回空列表，避免影响 Tavily 或主规划流程。
    """
    key = get_minimax_search_key()
    cmd = _minimax_mcp_command()
    if not key or not cmd or not query:
        return []

    env = os.environ.copy()
    env["MINIMAX_API_KEY"] = key
    env.setdefault("MINIMAX_API_HOST", MINIMAX_MCP_HOST)
    messages = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "study-planner-agent", "version": "0.1"},
            },
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "web_search", "arguments": {"query": query}},
        },
    ]
    payload = "\n".join(json.dumps(m, ensure_ascii=False) for m in messages) + "\n"
    try:
        proc = subprocess.run(
            cmd,
            input=payload,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=35,
            env=env,
        )
    except Exception as exc:
        print(f"   ⚠ MiniMax 搜索跳过（{query[:20]}…）：{exc}")
        return []

    items: list[dict] = []
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except Exception:
            continue
        if data.get("id") == 2:
            items = _extract_mcp_search_items(data)
            break
    out = []
    for item in items[:max_results]:
        url = str(item.get("url") or "").strip()
        if not url:
            continue
        out.append({
            "title": str(item.get("title") or url).strip(),
            "url": url,
            "content": str(item.get("content") or item.get("why") or "").strip(),
        })
    return out


def _canon(url: str) -> str:
    """URL 归一化，用于去重：小写 scheme/host，去掉末尾斜杠与 fragment。"""
    try:
        parts = urlsplit(url)
        path = parts.path.rstrip("/")
        return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, parts.query, ""))
    except Exception:
        return url


def retrieve(queries: list[dict], *, key: str | None, topic: str = "", per_query: int = 3) -> list[dict]:
    """对每路查询检索并打类型标签，归一化为资源 dict，按 URL 去重。

    若提供 topic，则额外用 GitHub/arXiv 公开 API（免 key、best-effort）补充
    高星仓库与真实论文——给"项目/论文"两类注入模型编不出来的事实，提升精确度。
    """
    seen: set[str] = set()
    resources: list[dict] = []
    for q in queries:
        rtype = q.get("type", "")
        if key:
            for hit in tavily_search(q.get("query", ""), key=key, max_results=per_query):
                canon = _canon(hit["url"])
                if canon in seen:
                    continue
                seen.add(canon)
                why = hit["content"]
                if len(why) > 80:
                    why = why[:80].rstrip() + "…"
                resources.append({
                    "title": hit["title"],
                    "type": rtype,
                    "url": hit["url"],
                    "why": why,
                    "source": "tavily",
                })
        for hit in minimax_mcp_search(q.get("query", ""), max_results=per_query):
            canon = _canon(hit["url"])
            if canon in seen:
                continue
            seen.add(canon)
            why = hit.get("content") or ""
            if len(why) > 80:
                why = why[:80].rstrip() + "…"
            resources.append({
                "title": hit.get("title") or hit["url"],
                "type": rtype,
                "url": hit["url"],
                "why": why,
                "source": "minimax",
            })

    # 补充来源（守卫式：逐个 try，任何失败都跳过，绝不影响已有的 Tavily 结果）。
    if topic:
        from common.agent.tools import sources
        for fn in (sources.github_search, sources.arxiv_search):
            try:
                res = fn(topic, limit=3)
            except Exception:
                continue
            if not res.success:
                continue
            for hit in res.data or []:
                canon = _canon(hit.get("url", ""))
                if not canon or canon in seen:
                    continue
                seen.add(canon)
                resources.append({
                    "title": hit.get("title", ""),
                    "type": hit.get("type", ""),
                    "url": hit.get("url", ""),
                    "why": hit.get("why", ""),
                })
    return resources


def validate_url(url: str, *, client: httpx.Client) -> bool:
    """探活：仅在"页面明确不存在/已删除(404/410)"时判死，其余一律保留。

    设计取舍：国内网络下，很多正常资源(YouTube/Coursera/GitHub)可能因被墙、
    反爬(403)、限流(429)、临时 5xx 或超时而无法访问，但它们并非死链。若一律
    丢弃会误杀大量优质资源。因此只把最可靠的"不存在"信号(404/410)当作死链，
    其它情况(含网络异常)保守保留。
    """
    if not url:
        return False
    try:
        resp = client.head(url)
        status = resp.status_code
        if status in (403, 405, 501):
            # 一些站点禁用 HEAD，改用 GET（只读状态行，不下载整页正文）。
            with client.stream("GET", url) as s:
                status = s.status_code
        return status not in (404, 410)
    except Exception:
        # 网络不可达/超时无法定论，保守保留，避免误杀正常资源。
        return True


def validate_urls(resources: list[dict]) -> list[dict]:
    """并发探活，丢弃确认不存在(404/410)的死链。精确度的核心步骤。

    httpx.Client 线程安全，可在线程池中共享；pool.map 保持原顺序，判活逻辑
    与顺序版完全一致，只是把"逐个等待"改成"并发探活"以缩短耗时。
    """
    if not resources:
        return []
    timeout = httpx.Timeout(8.0, connect=6.0)
    with httpx.Client(
        timeout=timeout,
        follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (StudyPlannerBot)"},
    ) as client:
        with ThreadPoolExecutor(max_workers=min(8, len(resources))) as pool:
            flags = list(pool.map(
                lambda r: validate_url(r.get("url", ""), client=client),
                resources,
            ))
    alive = [r for r, ok in zip(resources, flags) if ok]
    dropped = len(resources) - len(alive)
    if dropped:
        print(f"   🧹 URL 存活校验：丢弃 {dropped} 个死链，保留 {len(alive)} 个。")
    return alive


# --------------------------------------------------------------------------- #
# 工具注册：把上面的能力包成 ToolResult 契约，复用项目既有的 ToolRegistry，
# 这样调用会自动打印统一的 [Tool] 日志，且可写入多智能体协作日志。
# 注意：handler 内部自行从环境变量读取 key，key 绝不作为参数传入，避免被
# registry 的参数预览打印进日志而泄露。
# --------------------------------------------------------------------------- #
def _retrieve_tool(queries: list[dict], topic: str = "") -> ToolResult:
    key = get_search_key()
    mm_key = get_minimax_search_key()
    if not key and not mm_key:
        return ToolResult(name="web_search", success=True,
                          summary="未配置 Tavily/MiniMax 搜索 key，跳过联网检索", data=[])
    hits = retrieve(queries, key=key, topic=topic)
    return ToolResult(name="web_search", success=True,
                      summary=f"联网检索命中 {len(hits)} 条真实结果（Tavily + MiniMax）", data=hits)


def _validate_tool(resources: list[dict]) -> ToolResult:
    alive = validate_urls(resources)
    return ToolResult(name="url_validate", success=True,
                      summary=f"链接存活校验：保留 {len(alive)}/{len(resources)}", data=alive)


def register_search_tools(registry: ToolRegistry) -> ToolRegistry:
    """把联网检索 / 链接校验注册为工具。返回同一个 registry 以便链式调用。"""
    registry.register(ToolSpec(
        name="web_search",
        description="按资源类型多路联网检索学习资源（Tavily），返回真实 URL 候选。",
        handler=_retrieve_tool,
    ))
    registry.register(ToolSpec(
        name="url_validate",
        description="并发校验资源链接存活，丢弃确认不存在(404/410)的死链。",
        handler=_validate_tool,
    ))
    return registry


def build_search_registry() -> ToolRegistry:
    """构造一个只含资源搜索相关工具的注册表（内部批处理工具），供资源搜索 Agent 使用。"""
    return register_search_tools(ToolRegistry())
