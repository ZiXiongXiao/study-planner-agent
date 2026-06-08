"""
多模态展示辅助：把结构化数据渲染成 Markdown 富文本。

对照架构图的"动态展示策略"：
  - 解释型内容 → 文字 + 图示(Mermaid)
  - 执行型内容 → 表格 + 时间线
  - 资源型内容 → 链接卡片 + 视频
  - 复盘型内容 → 总结 + 进度图
"""

from __future__ import annotations

import re


def resource_cards(resources: list[dict]) -> str:
    """资源型内容 → 链接卡片 + 视频清单。"""
    if not resources:
        return "_（暂无资源）_"

    type_icon = {
        "course": "🎓",
        "课程": "🎓",
        "paper": "📄",
        "论文": "📄",
        "github": "💻",
        "repo": "💻",
        "video": "▶️",
        "视频": "▶️",
        "book": "📚",
        "documentation": "📖",
        "文档": "📖",
        "blog": "✍️",
        "技术帖": "✍️",
    }

    lines: list[str] = []
    videos: list[dict] = []
    for r in resources:
        rtype = str(r.get("type", "")).lower()
        icon = type_icon.get(rtype, "🔗")
        title = r.get("title", "Unknown")
        url = r.get("url", "")
        why = r.get("why") or r.get("reason") or ""
        score = r.get("fit_score") or r.get("score")

        head = f"{icon} **{title}**"
        if score is not None:
            head += f"  ·  适合度 {score}"
        lines.append(f"- {head}")
        if url:
            lines.append(f"  - 链接：<{url}>")

        # 适配信息徽章：语言 / 是否免费 / 适合阶段（缺字段则省略，向后兼容）
        badges = []
        if r.get("language"):
            badges.append(f"🌐 {r['language']}")
        if r.get("cost"):
            badges.append(f"💰 {r['cost']}")
        if r.get("difficulty"):
            badges.append(f"🎯 适合 {r['difficulty']}")
        if badges:
            lines.append(f"  - {' · '.join(badges)}")
        if why:
            lines.append(f"  - 推荐理由：{why}")
        if r.get("use_hint"):
            lines.append(f"  - 📌 用法：{r['use_hint']}")

        if any(k in rtype for k in ("video", "视频")):
            videos.append(r)

    if videos:
        lines.append("")
        lines.append("**▶️ 视频播放清单**")
        for i, v in enumerate(videos, 1):
            lines.append(f"  {i}. [{v.get('title', 'video')}]({v.get('url', '')})")

    return "\n".join(lines)


def parse_resources_from_report(markdown: str) -> list[dict]:
    """从已保存报告的「推荐资源」章节还原资源卡片数据，供 Web 资源页展示。"""

    if not markdown:
        return []

    match = re.search(
        r"^## 🔗 推荐资源[^\n]*\n(.*?)(?=^## |\Z)",
        markdown,
        re.MULTILINE | re.DOTALL,
    )
    if not match:
        return []

    resources: list[dict] = []
    current: dict | None = None

    for line in match.group(1).splitlines():
        if line.startswith("- ") and "**" in line:
            if current and current.get("title"):
                resources.append(current)
            current = {}
            head = line[2:]
            title_match = re.search(r"\*\*(.+?)\*\*", head)
            if title_match:
                current["title"] = title_match.group(1).strip()
            score_match = re.search(r"适合度\s*([\d.]+)", head)
            if score_match:
                current["fit_score"] = score_match.group(1)
            continue

        if not line.startswith("  - ") or current is None:
            continue

        detail = line[4:].strip()
        link_match = re.match(r"链接：<(.*?)>", detail)
        if link_match:
            url = link_match.group(1).strip()
            if url and not url.startswith(("http://", "https://")):
                url = f"https://{url.lstrip('/')}"
            current["url"] = url
            continue

        if detail.startswith("🌐"):
            lang_match = re.search(r"🌐\s*([^·]+)", detail)
            cost_match = re.search(r"💰\s*([^·]+)", detail)
            diff_match = re.search(r"🎯\s*适合\s*(.+)", detail)
            if lang_match:
                current["language"] = lang_match.group(1).strip()
            if cost_match:
                current["cost"] = cost_match.group(1).strip()
            if diff_match:
                current["difficulty"] = diff_match.group(1).strip()
            continue

        if detail.startswith("推荐理由："):
            current["why"] = detail.removeprefix("推荐理由：").strip()
            continue

        if detail.startswith("📌 用法："):
            current["use_hint"] = detail.removeprefix("📌 用法：").strip()

    if current and current.get("title"):
        resources.append(current)

    return resources


def roadmap_mermaid(milestones: list[dict]) -> str:
    """学习路线图 → Mermaid 流程图（解释型内容的图示）。"""
    if not milestones:
        return ""
    nodes = []
    edges = []
    for i, m in enumerate(milestones):
        node_id = f"M{i}"
        week = m.get("week", i + 1)
        name = str(m.get("name", f"阶段{i + 1}")).replace('"', "'")
        nodes.append(f'    {node_id}["第{week}周\\n{name}"]')
        if i > 0:
            edges.append(f"    M{i - 1} --> {node_id}")
    body = "\n".join(nodes + edges)
    return "```mermaid\nflowchart LR\n" + body + "\n```"


def schedule_table(schedule: list[dict]) -> str:
    """执行型内容 → 表格 + 时间线。"""
    if not schedule:
        return "_（暂无周计划）_"
    lines = [
        "| 周次 | 学习主题 | 目标产出 | 预计时长 |",
        "| --- | --- | --- | --- |",
    ]
    for row in schedule:
        week = row.get("week", "")
        topic = row.get("topic") or row.get("task", "")
        output = row.get("output") or row.get("deliverable", "")
        hours = row.get("hours") or row.get("duration", "")
        lines.append(f"| {week} | {topic} | {output} | {hours} |")
    return "\n".join(lines)


def progress_bar(percent: int, width: int = 20) -> str:
    """复盘型内容 → 文字版进度图。"""
    percent = max(0, min(100, int(percent)))
    filled = round(width * percent / 100)
    return f"`[{'█' * filled}{'░' * (width - filled)}]` {percent}%"


def milestones_progress(milestones: list[dict]) -> str:
    if not milestones:
        return ""
    lines = ["**🎯 阶段里程碑与进度**", ""]
    for m in milestones:
        week = m.get("week", "")
        name = m.get("name", "")
        desc = m.get("description", "")
        done = int(m.get("progress", 0))
        lines.append(f"- 第 {week} 周 · **{name}** {progress_bar(done)}")
        if desc:
            lines.append(f"  - {desc}")
    return "\n".join(lines)
