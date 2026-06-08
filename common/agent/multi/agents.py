"""
9 个智能体的实现（每个都是一个独立的 LLM 角色）。

对照架构图：
  调度与记忆层： RouterAgent / ClarificationAgent / ProfileMemoryAgent
  搜索与分析层： ResourceSearchAgent / ResourceEvaluationAgent / KnowledgeOrganizationAgent
  规划与优化层： PlanGenerationAgent / MultimodalDisplayAgent / FeedbackAdjustmentAgent
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from common.agent.multi.base_agent import BaseAgent
from common.agent.multi.state import SessionState
from common.agent.multi import display
from common.agent.multi import interaction
from common.agent.multi.memory_store import load_memory_instructions, load_profile, save_profile
from common.agent.tools import diagram_render, image_gen, sources, web_search
from common.storage import resolve_plan_dir


# --------------------------------------------------------------------------- #
# 调度与记忆层
# --------------------------------------------------------------------------- #
class RouterAgent(BaseAgent):
    name = "router"
    label = "任务编排 / 路由"
    system_prompt = (
        "你是学习规划多智能体系统的『任务编排/路由 Agent』。"
        "给定用户的学习目标，你要：判断学习领域、提炼关键词、"
        "并简要说明接下来会调度哪些子智能体来完成规划。"
        '只返回 JSON：{"domain": "领域", "keywords": ["..."], "route_note": "一句话调度说明"}。'
    )

    def run(self, state: SessionState) -> None:
        self.banner()
        data = self.think_json(f"用户学习目标：\n{state.raw_goal}") or {}
        domain = data.get("domain", "通用")
        keywords = data.get("keywords", [])
        note = data.get("route_note", "已规划：澄清→画像→搜索→评估→整理→计划→展示→反馈")
        state.profile.setdefault("domain", domain)
        state.profile.setdefault("keywords", keywords)
        state.log(self.label, f"领域={domain}，关键词={keywords}。{note}")
        print(f"📌 领域识别：{domain}")
        print(f"📌 关键词：{', '.join(keywords) if keywords else '—'}")
        print(f"📌 调度说明：{note}")


class ClarificationAgent(BaseAgent):
    name = "clarification"
    label = "需求澄清"
    system_prompt = (
        "你是『需求澄清 Agent』。为了摸清用户的真实水平和偏好，"
        "请基于其学习目标生成 3~4 个单项选择题，覆盖：当前基础水平、相关背景、"
        "每周可投入时间、内容偏好（理论/实战）、期望产出形式等。"
        "每题给 3~4 个互斥选项，选项要具体。"
        '只返回 JSON 数组：[{"question":"...","options":["A选项","B选项","C选项"]}]。'
    )

    _fallback = [
        {
            "question": "你在该方向的当前基础是？",
            "options": ["零基础 / 新手", "有一些相关基础", "已较熟练，想进阶"],
        },
        {
            "question": "每周大概能投入多少学习时间？",
            "options": ["5 小时以内", "5~10 小时", "10~20 小时", "20 小时以上"],
        },
        {
            "question": "你更偏好哪种学习方式？",
            "options": ["重理论与原理", "重动手实战", "理论与实战并重"],
        },
    ]

    def run(self, state: SessionState) -> None:
        self.banner()
        print("我先问你几个问题，把你的真实情况摸清楚（每题可选「其他」自己输入）。\n")
        questions = self.think_json(f"用户学习目标：\n{state.raw_goal}")
        if not isinstance(questions, list) or not questions:
            questions = self._fallback
            print("（网络/解析异常，改用默认澄清问题）\n")

        valid = [
            q for q in questions
            if isinstance(q, dict) and q.get("question") and isinstance(q.get("options"), list) and q["options"]
        ]
        total = len(valid)
        for i, q in enumerate(valid, 1):
            answer = interaction.ask_choice(
                q["question"],
                [str(o) for o in q["options"]],
                default=0,
                allow_custom=True,
                progress=f"问题 {i}/{total}",
            )
            state.clarifications[q["question"]] = answer
            print(f"   ✓ 已记录：{answer}")

        # 给用户一个自由补充的机会
        extra = interaction.ask_text(
            "\n还有什么想补充的信息？（如时间限制、特殊偏好，可直接回车跳过）",
            required=False,
        )
        if extra:
            state.clarifications["补充说明"] = extra

        # 汇总确认
        interaction.section("📝 已收集到你的情况")
        for k, v in state.clarifications.items():
            print(f"  · {k} → {v}")

        state.log(self.label, f"完成 {len(state.clarifications)} 项澄清。")


class ProfileMemoryAgent(BaseAgent):
    name = "profile_memory"
    label = "用户画像与记忆"
    system_prompt = (
        "你是『用户画像与记忆 Agent』。综合用户的学习目标和澄清问答，"
        "生成结构化用户画像。遵守项目记忆规则：只沉淀对后续学习规划有用的稳定信息，"
        "不要保存 API Key、密码、验证码等敏感信息，不要把一次性反馈误写成长期偏好。"
        '只返回 JSON：{"level":"beginner|intermediate|advanced",'
        '"weekly_hours": 数字, "background":"一句话背景",'
        '"preferences":["..."], "resource_preferences":["..."], "constraints":["..."],'
        '"output_format":"偏好的产出形式", "temporary_context":["..."],'
        '"uncertain_notes":["..."], "summary":"一句话画像总结"}。'
    )

    def __init__(self, provider, model_id, root: Path) -> None:
        super().__init__(provider, model_id)
        self.root = root
        self.memory_instructions = load_memory_instructions(root)

    def run(self, state: SessionState) -> None:
        self.banner()

        # 长期记忆：尝试加载历史画像
        history = load_profile(self.root, state.raw_goal)
        if history:
            state.is_returning_user = True
            print("🗂️  检测到历史画像，已加载长期记忆。")
            state.log(self.label, "加载到历史画像（长期记忆命中）。")

        qa_text = "\n".join(f"- {q} → {a}" for q, a in state.clarifications.items())
        user_content = f"学习目标：\n{state.raw_goal}\n\n澄清问答：\n{qa_text or '（无）'}"
        if history:
            user_content += f"\n\n历史画像：\n{json.dumps(history, ensure_ascii=False)}"

        system = self.system_prompt
        if self.memory_instructions:
            system += f"\n\n以下是项目记忆规则库，请严格遵守：\n\n{self.memory_instructions}"

        profile = self.think_json(user_content, system=system) or {}
        # 合并：领域/关键词来自 router，画像来自本 Agent
        profile = {**state.profile, **(history or {}), **profile}
        state.profile = profile

        save_profile(self.root, state.raw_goal, profile)
        print(f"👤 画像：水平={profile.get('level', '?')}，"
              f"每周={profile.get('weekly_hours', '?')}h，"
              f"偏好={profile.get('output_format', '—')}")
        state.log(self.label, f"画像已生成并持久化：{profile.get('summary', '')}")


# --------------------------------------------------------------------------- #
# 搜索与分析层
# --------------------------------------------------------------------------- #
class ResourceSearchAgent(BaseAgent):
    name = "resource_search"
    label = "资源搜索"
    # 有真实搜索结果时：让 LLM 从真实结果里"整理/精选"，只能用给定的真实 URL。
    system_prompt = (
        "你是『资源搜索 Agent』。下面会给你一批【真实搜索结果】（含真实可用的 URL）。"
        "请从中挑选并整理出 6~8 个高质量、类型多样的学习资源，"
        "覆盖在线课程、论文、GitHub 项目、技术博客/帖子、视频、文档等不同类型。"
        "严格要求：url 只能使用所给搜索结果里的真实链接，禁止编造或改写 URL；"
        "若某类型在搜索结果中缺失，可补充 1~2 个你确信存在的权威资源。"
        '只返回 JSON 数组：[{"title":"...","type":"course|paper|github|blog|video|book|documentation",'
        '"url":"真实链接","why":"一句话推荐理由"}]。'
    )
    # 无搜索结果（未配置 key / 检索失败）时的回退 prompt：退化为纯模型生成，保持原有行为。
    _fallback_prompt = (
        "你是『资源搜索 Agent』。根据学习目标和用户水平，推荐 6~8 个高质量学习资源，"
        "覆盖：在线课程、论文、GitHub 项目、技术博客/帖子、视频等不同类型。"
        '只返回 JSON 数组：[{"title":"...","type":"course|paper|github|blog|video|book",'
        '"url":"真实可用的链接","why":"一句话推荐理由"}]。链接请尽量真实。'
    )

    def run(self, state: SessionState) -> None:
        self.banner()

        # 统一通过工具注册表调用：复用 [Tool] 日志与 ToolResult 契约，
        # 并把每次工具调用写入多智能体协作日志（state.agent_log → 存档可见）。
        registry = web_search.build_search_registry()

        # 反馈重搜时的资源偏好约束（如「优先中文/项目类/更简单」）；平时为空。
        pref = str(state.profile.get("resource_pref", "")).strip()
        search_goal = f"{state.raw_goal} {pref}".strip() if pref else state.raw_goal

        # 1. 真实检索（多样性来源：按类型分多路查询）。
        key = web_search.get_search_key()
        minimax_search_key = web_search.get_minimax_search_key()
        search_enabled = bool(key or minimax_search_key)
        raw_hits: list[dict] = []
        if search_enabled:
            queries = web_search.build_typed_queries(
                search_goal,
                state.profile.get("domain", ""),
                state.profile.get("keywords", []),
            )
            print(f"🌐 联网搜索 {len(queries)} 类资源…")
            # key 不作为参数传入（handler 内部读环境变量），避免泄露进日志。
            # topic 供 retrieve 用 GitHub/arXiv 公开 API 补充高星仓库与真实论文。
            topic = web_search.topic_of(
                state.raw_goal,
                state.profile.get("domain", ""),
                state.profile.get("keywords", []),
            )
            res = registry.call("web_search", queries=queries, topic=topic)
            raw_hits = res.data or []
            state.log(self.label, f"🛠 {res.name} → {res.summary}")
        else:
            print("ℹ 未配置 TAVILY_API_KEY / MINIMAX_API_KEY，回退为纯模型生成。")

        pref_line = f"\n用户偏好约束（请优先满足）：{pref}" if pref else ""

        # 2. LLM 整理/精选（agent 自带推理）；无真实结果则退化为纯生成。
        if raw_hits:
            user_content = (
                f"学习目标：{state.raw_goal}\n"
                f"用户水平：{state.level()}\n"
                f"领域：{state.profile.get('domain', '')}{pref_line}\n\n"
                f"真实搜索结果（JSON）：\n{json.dumps(raw_hits, ensure_ascii=False)}"
            )
            curated = self.think_json(user_content)
        else:
            user_content = (
                f"学习目标：{state.raw_goal}\n"
                f"用户水平：{state.level()}\n"
                f"领域：{state.profile.get('domain', '')}{pref_line}"
            )
            curated = self.think_json(user_content, system=self._fallback_prompt)

        if not isinstance(curated, list):
            curated = []
        candidates = [r for r in curated if isinstance(r, dict) and r.get("url")]
        # 解析失败但有真实命中时，用真实命中兜底，避免空结果。
        if not candidates and raw_hits:
            candidates = raw_hits

        # 3. URL 存活校验（精确度核心）：仅丢弃确认不存在(404/410)的死链，
        #    网络异常/反爬等不确定情况一律保留，避免误杀正常资源。
        res = registry.call("url_validate", resources=candidates)
        state.resources = res.data if (res.success and res.data is not None) else candidates
        state.log(self.label, f"🛠 {res.name} → {res.summary}")

        print(f"🔎 搜索到 {len(state.resources)} 个候选资源。")
        state.log(self.label, f"搜索到 {len(state.resources)} 个资源（联网={'是' if search_enabled else '否'}）。")


class ResourceEvaluationAgent(BaseAgent):
    name = "resource_eval"
    label = "资源评估"
    system_prompt = (
        "你是『资源评估 Agent』。对候选资源逐个评估质量、难度、时效性、与用户水平/目标的适合度，"
        "给出 1~10 综合适合度分值，按分值从高到低排序，保留最值得学的若干个。"
        "若某资源带 excerpt（正文摘录），请据其真实内容判断，而非只看标题/摘要。"
        "并为每个资源给出便于使用的信息：语言、是否免费、与目标相关度，以及"
        "『先看哪部分 / 看到什么程度可停 / 可跳过什么』的用法建议（use_hint）。"
        '只返回 JSON 数组：[{"title":"...","type":"...","url":"...",'
        '"difficulty":"beginner|intermediate|advanced","fit_score":数字,'
        '"language":"中文|英文|中英","cost":"免费|付费|部分免费","relevance":数字,'
        '"use_hint":"先看…/看到…即可停","why":"评估说明"}]。'
    )

    def run(self, state: SessionState) -> None:
        self.banner()
        if not state.resources:
            print("⚠ 无候选资源，跳过评估。")
            state.evaluated_resources = []
            return

        # 抽样抓取前若干个候选的正文，让评分基于真实内容而非仅标题/摘要。
        excerpts = self._fetch_excerpts(state.resources, limit=4)
        enriched = []
        for r in state.resources:
            item = dict(r)
            ex = excerpts.get(r.get("url", ""))
            if ex:
                item["excerpt"] = ex
            enriched.append(item)

        user_content = (
            f"学习目标：{state.raw_goal}\n"
            f"用户水平：{state.level()}\n"
            f"候选资源（部分含正文摘录 excerpt）：\n{json.dumps(enriched, ensure_ascii=False)}"
        )
        evaluated = self.think_json(user_content)
        if not isinstance(evaluated, list) or not evaluated:
            evaluated = state.resources  # 评估失败则退回原列表
        state.evaluated_resources = [r for r in evaluated if isinstance(r, dict)]
        n_fetched = sum(1 for v in excerpts.values() if v)
        print(f"⭐ 完成评估（核验 {n_fetched} 篇正文），保留 {len(state.evaluated_resources)} 个优质资源。")
        state.log(self.label, f"评估并排序，保留 {len(state.evaluated_resources)} 个（核验正文 {n_fetched} 篇）。")

    @staticmethod
    def _fetch_excerpts(resources: list[dict], *, limit: int = 4) -> dict[str, str]:
        """并发抓取前 limit 个候选的正文摘录（守卫式，失败留空）。返回 url -> excerpt。"""
        urls = [r.get("url", "") for r in resources[:limit] if r.get("url")]
        if not urls:
            return {}

        def fetch(u: str) -> tuple[str, str]:
            try:
                res = sources.fetch_url(u, max_chars=300)
                return u, (res.data if res.success else "")
            except Exception:
                return u, ""

        out: dict[str, str] = {}
        with ThreadPoolExecutor(max_workers=min(4, len(urls))) as pool:
            for u, ex in pool.map(fetch, urls):
                out[u] = ex
        return out


class KnowledgeOrganizationAgent(BaseAgent):
    name = "knowledge_org"
    label = "知识整理"
    system_prompt = (
        "你是『知识整理 Agent』。针对该学习主题，提炼出结构化的知识体系大纲："
        "核心概念、前置知识、主要模块、各模块要点。"
        "用简洁的 Markdown 列表/小标题输出，便于后续制定计划。不要寒暄。"
    )

    def run(self, state: SessionState) -> None:
        self.banner()
        user_content = (
            f"学习目标：{state.raw_goal}\n用户水平：{state.level()}\n"
            "请输出该主题的知识体系大纲。"
        )
        outline = self.think(user_content)
        state.knowledge_outline = outline.strip()
        print("📚 知识体系大纲已整理。")
        state.log(self.label, "输出结构化知识大纲。")


# --------------------------------------------------------------------------- #
# 规划与优化层
# --------------------------------------------------------------------------- #
class PlanGenerationAgent(BaseAgent):
    name = "plan_generation"
    label = "计划生成"
    system_prompt = (
        "你是『计划生成 Agent』。综合用户画像、知识大纲与优质资源，制定可执行的学习计划。"
        "必须包含：长期目标、阶段目标、逐周计划、每日学习建议、里程碑。"
        "请只返回 JSON：{"
        '"long_term_goal":"...",'
        '"stage_goals":["..."],'
        '"weekly_schedule":[{"week":1,"topic":"...","output":"阶段产出","hours":"本周时长"}],'
        '"daily_suggestion":"每日学习建议",'
        '"milestones":[{"week":2,"name":"里程碑名","description":"..."}]'
        "}。周数要和用户每周可投入时间相匹配。"
    )

    def run(self, state: SessionState) -> None:
        self.banner()
        user_content = (
            f"用户画像：{json.dumps(state.profile, ensure_ascii=False)}\n\n"
            f"知识大纲：\n{state.knowledge_outline}\n\n"
            f"优质资源：{json.dumps(state.evaluated_resources, ensure_ascii=False)}"
        )
        plan = self.think_json(user_content)
        if not isinstance(plan, dict):
            plan = {}
        state.plan_structured = plan
        # 同时保留一份可读 markdown（用于存档/兜底）
        state.plan_markdown = _plan_to_markdown(plan)
        weeks = len(plan.get("weekly_schedule", []))
        print(f"🗓️  学习计划已生成（共 {weeks} 周）。")
        state.log(self.label, f"生成 {weeks} 周计划，含里程碑 {len(plan.get('milestones', []))} 个。")


class MultimodalDisplayAgent(BaseAgent):
    """视觉编排 Agent：优先用图片模型生成学习辅助图，失败时回退本地 SVG。"""

    name = "multimodal_display"
    label = "多模态展示"
    system_prompt = (
        "你是『多模态展示 Agent』。用一段简洁、激励性的中文导语（2~3 句）"
        "概括这份学习计划的整体思路。只输出导语本身。"
    )
    MAX_IMAGES = 4  # 氛围/具象 PNG 上限；结构型学习辅助图不占用该预算

    visual_plan_prompt = (
        "你是『视觉编排 Agent』。为一份学习计划决定用哪些**学习辅助图**与**氛围图**并给出内容。\n"
        "核心原则：知识结构/先后关系/流程/依赖要给出结构化 data，"
        "系统会把 data 转成精确提示词交给图片模型生成学习辅助图；若失败会回退本地 SVG。\n"
        "section_visuals（学习辅助图，render_mode=structured，必须给 data）：\n"
        "- knowledge_map：领域有 ≥3 个模块时给 data={root, modules:[{name, topics:[...]}]}。\n"
        "- skill_map：有明显前置依赖时给有序 data={steps:[...]}（数学基础→机器学习→深度学习→GNN）。\n"
        "- workflow：项目/复现/开发/分析类，线性 data={title, steps:[...]}（爬虫:URL→请求→解析→DataFrame→清洗→可视化→报告）。\n"
        "- practice_loop：考试/备考/语言/技能训练类，循环 data={title, steps:[...]}（备考:学知识→做题→订正→复盘→模考→调整；语言:输入→模仿→输出→纠错→复用）。workflow 与 practice_loop 二选一。\n"
        "- 简单短目标（≤1 周或 <3 模块）不要给 knowledge_map/skill_map。\n"
        "render_mode=image 的 concept_summary 可选：某章节的概念图（prompt 英文）。\n"
        "atmosphere_images（MiniMax 生成，prompt 英文、无可读文字）：cover（必给 1）；"
        "outcome（仅项目/作品制且产出具体，考试/语言不给）；representational（仅视觉具象主题如绘画/摄影/建筑/生物/医学/地理/运动/乐器，≤2）。\n"
        "每个视觉必须有 learning_purpose（中文，说明帮助理解什么），否则会被丢弃。结构图节点文字短(≤12字)、无引号括号。\n"
        '只返回 JSON：{"section_visuals":[{"anchor":"knowledge_map","section":"知识体系大纲",'
        '"type":"knowledge_map|skill_map|workflow|practice_loop|deliverables|concept_summary",'
        '"learning_purpose":"...","alt":"中文图注","render_mode":"structured|image","prompt":"仅 image 用","data":{}}],'
        '"atmosphere_images":[{"anchor":"cover","type":"cover|outcome|representational",'
        '"learning_purpose":"...","alt":"中文图注","prompt":"英文，无可读文字"}]}。'
    )

    _CHAIN_TYPES = {"skill_map", "workflow", "practice_loop", "learning_path"}

    def __init__(self, provider, model_id, root: Path) -> None:
        super().__init__(provider, model_id)
        self.root = root

    # ----------------------------- 渲染主流程 ----------------------------- #
    def run(self, state: SessionState) -> None:
        self.banner()
        plan = state.plan_structured or {}

        intro = ""
        try:
            intro = self.think(
                f"长期目标：{plan.get('long_term_goal', state.raw_goal)}\n"
                f"阶段目标：{plan.get('stage_goals', [])}"
            ).strip()
        except Exception:
            intro = ""

        self._ensure_visuals(state)

        p: list[str] = []
        p.append(f"# 📋 学习规划：{state.raw_goal}\n")
        cover = self._image_for_anchor(state, "cover")
        if cover:
            p.append(self._image_markdown(cover) + "\n")
        if intro:
            p.append(f"> {intro}\n")

        if plan.get("long_term_goal"):
            p.append(f"**🎯 长期目标：** {plan['long_term_goal']}\n")
        if plan.get("stage_goals"):
            p.append("**阶段目标：**")
            p.extend(f"- {g}" for g in plan["stage_goals"])
            p.append("")

        # 顺序：技能依赖 → 概念概括 → 知识地图 → 路线图 → 流程/循环 → 周表
        #      → 产出物清单 → 每日 → 里程碑(+成果) → 知识大纲 → 具象插图 → 资源
        self._section(p, state, "skill_map", "## 🪜 技能依赖图")
        self._section(p, state, "concept_summary", "## 🧩 概念概括")
        self._section(p, state, "knowledge_map", "## 🧠 知识地图")
        if not self._section(p, state, "learning_path", "## 🗺️ 学习路线图"):
            rm = display.roadmap_mermaid(plan.get("milestones", []))
            if rm:
                p.append("## 🗺️ 学习路线图\n")
                p.append(rm + "\n")
        if not self._section(p, state, "workflow", "## 🔄 执行流程"):
            self._section(p, state, "practice_loop", "## 🔁 练习循环")

        if plan.get("weekly_schedule"):
            p.append("## 🗓️ 逐周计划（执行型：表格 + 时间线）\n")
            p.append(display.schedule_table(plan["weekly_schedule"]) + "\n")

        self._section(p, state, "deliverables", "## ✅ 产出物清单")

        if plan.get("daily_suggestion"):
            p.append(f"## ☀️ 每日学习建议\n\n{plan['daily_suggestion']}\n")

        milestones = plan.get("milestones", [])
        if milestones:
            p.append("## 📊 里程碑与进度（复盘型：总结 + 进度图）\n")
            outcome = self._image_for_anchor(state, "outcome")
            if outcome:
                p.append(self._image_markdown(outcome))
                if outcome.get("alt"):
                    p.append(f"*{outcome['alt']}*")
                p.append("")
            p.append(display.milestones_progress(milestones) + "\n")

        if state.knowledge_outline:
            p.append("## 📚 知识体系大纲（解释型）\n")
            p.append(state.knowledge_outline + "\n")

        illustrations = [im for im in state.images
                         if str(im.get("anchor", "")).startswith("illustration")]
        if illustrations:
            p.append("## 🖼️ 主题插图\n")
            for im in illustrations:
                p.append(self._image_markdown(im))
                if im.get("alt"):
                    p.append(f"*{im['alt']}*")
                p.append("")

        if state.evaluated_resources:
            p.append("## 🔗 推荐资源（资源型：链接卡片 + 视频）\n")
            p.append(display.resource_cards(state.evaluated_resources) + "\n")

        state.display_markdown = "\n".join(p)
        n_svg = sum(1 for im in state.images if im.get("kind") == "svg")
        n_png = sum(1 for im in state.images if im.get("kind") == "png")
        print(f"🎨 视觉编排完成：SVG 兜底图 {n_svg} 张 / AI 生成图 {n_png} 张(PNG)。")
        state.log(self.label, f"视觉编排完成：SVG×{n_svg}、PNG×{n_png}。")
        print("\n" + "-" * 60)
        print(state.display_markdown)
        print("-" * 60)

    def _section(self, parts: list[str], state: SessionState, anchor: str, heading: str) -> bool:
        """在 heading 下放该 anchor 的视觉：优先嵌入已生成图片，否则用文字兜底；都无则跳过。"""
        img = self._image_for_anchor(state, anchor)
        if img:
            parts.append(heading + "\n")
            parts.append(self._image_markdown(img))
            if img.get("alt"):
                parts.append(f"*{img['alt']}*")
            parts.append("")
            return True
        fb = self._md_fallback(state, anchor)
        if fb:
            parts.append(heading + "\n")
            parts.append(fb + "\n")
            return True
        return False

    # ----------------------------- 视觉生成 ----------------------------- #
    def _ensure_visuals(self, state: SessionState) -> None:
        if state.images or state.images_attempted:
            return
        state.images_attempted = True

        plan = state.plan_structured or {}
        vp = self._normalize_visual_plan(self._visual_plan(state), state)
        state.visual_plan = vp
        assets = resolve_plan_dir(self.root, state.raw_goal) / "assets"

        key = image_gen.get_image_key()
        registry = image_gen.build_image_registry() if key else None

        # 1) LLM 规划的学习辅助图：优先图片模型 PNG，失败回退 SVG
        for sv in vp.get("section_visuals", []):
            if sv.get("render_mode") != "structured":
                continue
            ok = False
            if registry:
                ok = self._gen_structured_png(state, sv, registry, assets)
            if not ok:
                rel = self._render_structured(sv.get("type", ""), sv.get("data") or {},
                                              assets, self._asset_name(sv.get("anchor") or sv.get("type")))
                if rel:
                    self._add_asset(state, sv.get("anchor", ""), sv.get("section", ""), rel, sv.get("alt", ""), "svg")
                    state.log(self.label, f"🛠 diagram → {rel}")

        # 2) 代码驱动学习辅助图（保证出现）：学习路线图（里程碑链）、产出物清单（周产出）
        #    优先图片模型 PNG，失败/无 key 回退 SVG。
        self._code_driven_visuals(state, plan, assets, registry)

        # 3) PNG 氛围图（需 key，≤MAX_IMAGES）
        if not key:
            print("ℹ 未配置 MINIMAX_API_KEY，跳过 AI 图片；学习辅助图已回退为本地 SVG。")
            return
        self._gen_pngs(state, vp, registry, assets)

    def _code_driven_visuals(self, state: SessionState, plan: dict, assets, registry=None) -> None:
        if not self._has_anchor(state, "learning_path"):
            names = [m.get("name", "") for m in (plan.get("milestones") or []) if m.get("name")]
            ok = False
            if registry and names:
                ok = self._gen_chain_png(
                    state,
                    anchor="learning_path",
                    section="学习路线图",
                    filename="learning-path.png",
                    alt="学习路线图",
                    title="学习路线",
                    steps=names,
                    registry=registry,
                    assets=assets,
                )
            if not ok:
                rel = diagram_render.render_chain(names, assets, "learning-path", title="学习路线")
                if rel:
                    self._add_asset(state, "learning_path", "学习路线图", rel, "学习路线图", "svg")
        if not self._has_anchor(state, "deliverables"):
            outs = [w.get("output") or w.get("deliverable") for w in (plan.get("weekly_schedule") or [])]
            outs = [o for o in outs if o]
            ok = self._gen_deliverables_png(state, plan, registry, assets) if registry else False
            if not ok:
                rel = diagram_render.render_deliverables(outs, assets, "deliverables")
                if rel:
                    self._add_asset(state, "deliverables", "产出物清单", rel, "产出物清单", "svg")

    def refresh_for_plan_change(self, state: SessionState) -> None:
        """计划文本被反馈改动后，只重生成依赖 plan_structured 的代码驱动结构图
        （learning_path / deliverables），其余缓存（封面/知识地图等）保持不变。"""
        state.images = [im for im in state.images
                        if im.get("anchor") not in ("learning_path", "deliverables")]
        assets = resolve_plan_dir(self.root, state.raw_goal) / "assets"
        key = image_gen.get_image_key()
        registry = image_gen.build_image_registry() if key else None
        self._code_driven_visuals(state, state.plan_structured or {}, assets, registry)

    def _gen_deliverables_png(self, state: SessionState, plan: dict, registry, assets) -> bool:
        if self._has_anchor(state, "deliverables"):
            return True
        if not registry:
            return False
        outputs = [
            str(w.get("output") or w.get("deliverable") or "").strip()
            for w in (plan.get("weekly_schedule") or [])
        ]
        outputs = [o for o in outputs if o]
        if not outputs:
            return False
        prompt = self._deliverables_image_prompt(state.raw_goal, outputs)
        res = registry.call(
            "generate_image",
            prompt=prompt,
            dest_dir=str(assets),
            filename="deliverables.png",
            aspect_ratio="16:9",
            allow_text=True,
        )
        state.log(self.label, f"🛠 {res.name} → {res.summary}")
        if res.success:
            self._add_asset(state, "deliverables", "产出物清单", "assets/deliverables.png", "产出物清单", "png")
            return True
        return False

    @staticmethod
    def _deliverables_image_prompt(goal: str, outputs: list[str]) -> str:
        listed = "\n".join(f"- {x}" for x in outputs[:8])[:700]
        return (
            "Create a polished Chinese educational infographic for a study plan deliverables checklist. "
            "Use a clean board layout with task cards, checkboxes, progress markers, and weekly output grouping. "
            "Use concise readable Chinese labels based on the provided deliverables when possible. "
            f"Learning goal: {goal}\nDeliverables:\n{listed}"
        )

    def _gen_pngs(self, state: SessionState, vp: dict, registry, assets) -> None:
        reqs = list(vp.get("atmosphere_images") or [])
        reqs += [sv for sv in vp.get("section_visuals", []) if sv.get("render_mode") == "image"]
        prio = {"cover": 0, "outcome": 1, "representational": 2, "illustration": 2, "concept_summary": 3}
        reqs.sort(key=lambda d: prio.get(str(d.get("type", "")), 5))

        budget = self.MAX_IMAGES
        illus_n = 0
        for d in reqs:
            if budget <= 0:
                break
            prompt = str(d.get("prompt", "")).strip()
            if not prompt:
                continue
            typ = str(d.get("type", ""))
            if typ in ("representational", "illustration"):
                illus_n += 1
                if illus_n > 2:
                    continue
                anchor, fname = f"illustration:{illus_n}", f"illustration-{illus_n}.png"
            elif typ == "cover":
                anchor, fname = "cover", "cover.png"
            elif typ == "outcome":
                anchor, fname = "outcome", "outcome.png"
            else:  # concept_summary 等
                anchor = "concept_summary"
                fname = "concept-summary.png"
            if self._has_anchor(state, anchor):
                continue
            res = registry.call("generate_image", prompt=prompt, dest_dir=str(assets),
                                filename=fname, aspect_ratio="16:9", allow_text=False)
            state.log(self.label, f"🛠 {res.name} → {res.summary}")
            if res.success:
                self._add_asset(state, anchor, str(d.get("section", "")), f"assets/{fname}", str(d.get("alt", "")), "png")
                budget -= 1

    def _gen_structured_png(self, state: SessionState, sv: dict, registry, assets) -> bool:
        anchor = str(sv.get("anchor") or sv.get("type") or "diagram")
        if self._has_anchor(state, anchor):
            return True
        asset = self._asset_name(anchor)
        typ = str(sv.get("type", ""))
        data = sv.get("data") or {}
        prompt = self._structured_image_prompt(state.raw_goal, typ, data, str(sv.get("alt", "") or anchor))
        res = registry.call(
            "generate_image",
            prompt=prompt,
            dest_dir=str(assets),
            filename=f"{asset}.png",
            aspect_ratio="16:9",
            allow_text=True,
        )
        state.log(self.label, f"🛠 {res.name} → {res.summary}")
        if res.success:
            self._add_asset(state, anchor, str(sv.get("section", "")), f"assets/{asset}.png",
                            str(sv.get("alt", "") or anchor), "png")
            return True
        return False

    def _gen_chain_png(
        self,
        state: SessionState,
        *,
        anchor: str,
        section: str,
        filename: str,
        alt: str,
        title: str,
        steps: list[str],
        registry,
        assets,
        cyclic: bool = False,
    ) -> bool:
        prompt = self._chain_image_prompt(state.raw_goal, title, steps, cyclic=cyclic)
        res = registry.call(
            "generate_image",
            prompt=prompt,
            dest_dir=str(assets),
            filename=filename,
            aspect_ratio="16:9",
            allow_text=True,
        )
        state.log(self.label, f"🛠 {res.name} → {res.summary}")
        if res.success:
            self._add_asset(state, anchor, section, f"assets/{filename}", alt, "png")
            return True
        return False

    @staticmethod
    def _structured_image_prompt(goal: str, typ: str, data: dict, alt: str) -> str:
        if typ == "knowledge_map":
            modules = []
            for m in data.get("modules", []):
                topics = "、".join(m.get("topics", [])[:5])
                modules.append(f"{m.get('name', '')}: {topics}")
            body = "\n".join(modules)
            return (
                "Create a Chinese knowledge map infographic for a learning plan. "
                "Show a central topic and surrounding module cards with concise labels. "
                f"Title: {alt}. Learning goal: {goal}. Root: {data.get('root', goal)}.\nModules:\n{body}"
            )
        if typ == "deliverables":
            items = "\n".join(f"- {x}" for x in data.get("items", [])[:8])
            return (
                "Create a Chinese deliverables checklist infographic for a learning plan. "
                "Use task cards, check marks, and a clear weekly output board. "
                f"Learning goal: {goal}\nItems:\n{items}"
            )
        return MultimodalDisplayAgent._chain_image_prompt(
            goal,
            data.get("title") or alt or typ,
            data.get("steps", []),
            cyclic=(typ == "practice_loop"),
        )

    @staticmethod
    def _chain_image_prompt(goal: str, title: str, steps: list[str], *, cyclic: bool = False) -> str:
        relation = "a circular loop with arrows returning to the first step" if cyclic else "a left-to-right process with clear arrows"
        listed = " -> ".join(str(s) for s in steps[:8])
        return (
            "Create a clean Chinese educational infographic diagram. "
            f"Layout: {relation}. Use concise readable labels exactly matching these steps when possible. "
            "Use a professional study-planning style with clear visual grouping. "
            f"Learning goal: {goal}. Diagram title: {title}. Steps: {listed}"
        )

    def _render_structured(self, typ: str, data: dict, assets, name: str):
        try:
            if typ == "knowledge_map":
                return diagram_render.render_knowledge_map(data.get("root", ""), data.get("modules") or [], assets, name)
            if typ == "deliverables":
                return diagram_render.render_deliverables(data.get("items") or [], assets, name)
            if typ in self._CHAIN_TYPES:
                return diagram_render.render_chain(data.get("steps") or [], assets, name,
                                                   cyclic=(typ == "practice_loop"), title=data.get("title", ""))
        except Exception:
            return None
        return None

    # ----------------------------- visual_plan ----------------------------- #
    def _visual_plan(self, state: SessionState) -> dict:
        plan = state.plan_structured or {}
        weeks = plan.get("weekly_schedule") or []
        user_content = (
            f"学习目标：{state.raw_goal}\n"
            f"用户画像：{json.dumps(state.profile, ensure_ascii=False)}\n"
            f"阶段目标：{json.dumps(plan.get('stage_goals') or [], ensure_ascii=False)}\n"
            f"周主题：{json.dumps([w.get('topic', '') for w in weeks], ensure_ascii=False)}\n"
            f"里程碑：{json.dumps([m.get('name', '') for m in (plan.get('milestones') or [])], ensure_ascii=False)}\n"
            f"知识大纲（节选）：\n{(state.knowledge_outline or '（无）')[:800]}\n\n"
            "请产出 section_visuals 与 atmosphere_images。"
        )
        try:
            vp = self.think_json(user_content, system=self.visual_plan_prompt)
        except Exception:
            vp = None
        return vp if isinstance(vp, dict) else {}

    def _normalize_visual_plan(self, vp: dict, state: SessionState) -> dict:
        """schema 清洗：丢无 learning_purpose / 无 data(structured) / 无 prompt(image)；
        简单目标降级；上限截断；封面槽位兜底。"""
        plan = state.plan_structured or {}
        simple = len(plan.get("weekly_schedule") or []) <= 1 or len(plan.get("stage_goals") or []) < 3

        out_sv: list[dict] = []
        seen_type: set[str] = set()
        for sv in (vp.get("section_visuals") if isinstance(vp, dict) else None) or []:
            if not isinstance(sv, dict):
                continue
            typ = str(sv.get("type", "")).strip()
            if not typ or not str(sv.get("learning_purpose", "")).strip():
                continue
            if simple and typ in ("knowledge_map", "skill_map"):
                continue
            if typ in seen_type and typ != "concept_summary":
                continue
            mode = "image" if sv.get("render_mode") == "image" else "structured"
            if mode == "structured":
                data = self._clean_data(typ, sv.get("data"))
                if not data:
                    continue
                anchor = "learning_path" if typ == "learning_path" else (sv.get("anchor") or typ)
                out_sv.append({"type": typ, "anchor": str(anchor), "section": str(sv.get("section", "")),
                               "alt": str(sv.get("alt", "")).strip() or typ, "render_mode": "structured", "data": data})
            else:
                if not str(sv.get("prompt", "")).strip():
                    continue
                out_sv.append({"type": typ, "anchor": "concept_summary", "section": str(sv.get("section", "")),
                               "alt": str(sv.get("alt", "")).strip() or "概念概括", "render_mode": "image",
                               "prompt": str(sv.get("prompt", "")).strip()})
            seen_type.add(typ)

        out_ai: list[dict] = []
        have_cover = False
        illus = 0
        for ai in (vp.get("atmosphere_images") if isinstance(vp, dict) else None) or []:
            if not isinstance(ai, dict):
                continue
            typ = str(ai.get("type", "")).strip()
            if not str(ai.get("learning_purpose", "")).strip() or not str(ai.get("prompt", "")).strip():
                continue
            if typ == "cover":
                if have_cover:
                    continue
                have_cover = True
            elif typ in ("representational", "illustration"):
                illus += 1
                if illus > 2:
                    continue
            out_ai.append({"type": typ, "alt": str(ai.get("alt", "")).strip() or "配图",
                           "section": str(ai.get("section", "")), "prompt": str(ai.get("prompt", "")).strip()})
        if not have_cover:  # 封面槽位兜底（实际是否生成取决于 key）
            out_ai.insert(0, {"type": "cover", "alt": f"{state.raw_goal} 学习规划封面", "section": "",
                              "prompt": ("a warm, encouraging conceptual cover representing the journey "
                                         f"of learning {state.raw_goal}, no text")})
        return {"section_visuals": out_sv, "atmosphere_images": out_ai}

    @staticmethod
    def _clean_data(typ: str, data) -> dict | None:
        if isinstance(data, list):
            data = {"items": data} if typ == "deliverables" else {"steps": data}
        if not isinstance(data, dict):
            return None
        if typ == "knowledge_map":
            mods = []
            for m in (data.get("modules") or [])[:6]:
                if not isinstance(m, dict):
                    continue
                name = str(m.get("name", "")).strip()
                if not name:
                    continue
                topics = [str(t).strip() for t in (m.get("topics") or []) if str(t).strip()][:5]
                mods.append({"name": name, "topics": topics})
            return {"root": str(data.get("root", "")).strip(), "modules": mods} if mods else None
        if typ == "deliverables":
            items = [str(x).strip() for x in (data.get("items") or []) if str(x).strip()][:8]
            return {"items": items} if items else None
        steps = [str(s).strip() for s in (data.get("steps") or []) if str(s).strip()][:8]
        return {"steps": steps, "title": str(data.get("title", "")).strip()} if len(steps) >= 2 else None

    def _md_fallback(self, state: SessionState, anchor: str) -> str:
        """SVG 缺失时的文字兜底（绝不空），从 visual_plan 数据生成。"""
        for sv in (state.visual_plan.get("section_visuals") or []):
            if sv.get("anchor") != anchor or sv.get("render_mode") != "structured":
                continue
            typ, data = sv.get("type"), sv.get("data") or {}
            if typ == "knowledge_map":
                return "\n".join(f"- **{m.get('name', '')}**：" + "、".join(m.get("topics", []))
                                 for m in data.get("modules", []))
            if typ == "deliverables":
                return "\n".join(f"- [ ] {x}" for x in data.get("items", []))
            steps = data.get("steps", [])
            if steps:
                return ("**循环：** " if typ == "practice_loop" else "**流程：** ") + " → ".join(steps)
        return ""

    # ----------------------------- 小工具 ----------------------------- #
    @staticmethod
    def _add_asset(state: SessionState, anchor: str, section: str, path: str, alt: str, kind: str) -> None:
        state.images.append({"anchor": anchor, "section": section, "path": path, "alt": alt, "kind": kind})

    @staticmethod
    def _has_anchor(state: SessionState, anchor: str) -> bool:
        return any(im.get("anchor") == anchor for im in state.images)

    @staticmethod
    def _asset_name(anchor) -> str:
        s = "".join(c if c.isalnum() else "-" for c in str(anchor or "diagram")).strip("-").lower()
        return s or "diagram"

    @staticmethod
    def _image_for_anchor(state: SessionState, anchor: str) -> dict | None:
        for img in state.images:
            if img.get("anchor") == anchor:
                return img
        return None

    @staticmethod
    def _image_markdown(image: dict) -> str:
        alt = str(image.get("alt", "学习规划配图")).replace("]", ")")
        path = str(image.get("path", "")).replace("\\", "/")
        return f"![{alt}]({path})"


class FeedbackAdjustmentAgent(BaseAgent):
    name = "feedback_adjust"
    label = "反馈调整"
    system_prompt = (
        "你是『反馈调整 Agent』。根据用户反馈，对现有学习计划做针对性调整，"
        "保持原有结构，只改动需要变化的部分。"
        "请只返回与计划生成相同结构的 JSON（long_term_goal / stage_goals / "
        "weekly_schedule / daily_suggestion / milestones）。"
    )

    _MENU = [
        "满意，结束并保存",
        "时间太紧，帮我压缩周期",
        "难度不合适，帮我调整",
        "想要不同的学习资源（中文/项目/更简单等）",
        "增加 / 删减某部分内容",
    ]
    _FEEDBACK_MAP = {
        "满意，结束并保存": None,
        "时间太紧，帮我压缩周期": "学习周期太长，请在保证效果的前提下压缩总周数、提高每周强度。",
        "难度不合适，帮我调整": "当前难度不合适，请重新调整难度梯度，使其更匹配我的水平。",
        "想要不同的学习资源（中文/项目/更简单等）": "请按我的偏好重新推荐学习资源。",
        "增加 / 删减某部分内容": "请根据我的补充意见增删内容。",
    }
    # 命中以下任一关键词，视为资源类反馈 → 触发定向重搜
    _RES_KEYWORDS = ("中文", "英文", "免费", "付费", "项目", "实战", "视频", "书",
                     "教程", "课程", "太难", "太简单", "更简单", "换资源", "资源", "论文", "GitHub")

    def __init__(self, provider, model_id, display_agent: MultimodalDisplayAgent) -> None:
        super().__init__(provider, model_id)
        self.display_agent = display_agent

    def _is_resource_feedback(self, choice: str, feedback: str) -> bool:
        if choice == self._MENU[3]:
            return True
        return any(k in feedback for k in self._RES_KEYWORDS)

    def _research_resources(self, state: SessionState, feedback: str) -> None:
        """按反馈偏好重跑现有 搜索→校验→fetch 核验→评分 链，刷新资源（稳定、复用）。"""
        print("   🔎 正在按你的偏好重新搜索资源…")
        state.profile["resource_pref"] = feedback
        try:
            ResourceSearchAgent(self.provider, self.model_id).run(state)
            ResourceEvaluationAgent(self.provider, self.model_id).run(state)
        except Exception as err:
            print(f"   ⚠ 资源重搜失败，沿用原资源：{err}")
        finally:
            state.profile.pop("resource_pref", None)

    def run(self, state: SessionState) -> None:
        self.banner()
        max_rounds = 5
        for rnd in range(1, max_rounds + 1):
            choice = interaction.ask_choice(
                "对这份计划是否满意？需要怎么调整？",
                self._MENU,
                default=0,
                allow_custom=True,  # 允许用户自己输入任意调整诉求
                progress=f"第 {rnd} 轮",
            )

            if choice == self._MENU[0]:
                print("👍 已确认计划，准备保存。")
                state.log(self.label, "用户确认满意，结束调整。")
                return

            # 预设诉求 or 用户自定义诉求
            feedback = self._FEEDBACK_MAP.get(choice, choice)
            if choice in ("增加 / 删减某部分内容", self._MENU[3]):
                prompt = ("请具体说明你想要的资源（如：中文、免费、偏项目实战、更简单…）"
                          if choice == self._MENU[3] else "请具体说明要增加或删减什么")
                extra = interaction.ask_text(prompt, required=True)
                feedback = f"{feedback} {extra}".strip()

            print(f"\n🔄 收到反馈：{feedback}")

            # P3：资源类反馈 → 先定向重搜，刷新 state.evaluated_resources
            is_res = self._is_resource_feedback(choice, feedback)
            if is_res:
                self._research_resources(state, feedback)

            print("   反馈调整 Agent 正在重新规划...")
            user_content = (
                f"用户反馈：{feedback}\n\n"
                f"现有计划：{json.dumps(state.plan_structured, ensure_ascii=False)}"
            )
            new_plan = self.think_json(user_content)
            plan_changed = isinstance(new_plan, dict) and bool(new_plan)
            if plan_changed:
                state.plan_structured = new_plan
                state.plan_markdown = _plan_to_markdown(new_plan)

            if not plan_changed and not is_res:
                print("   ⚠ 调整失败，保留原计划。")
                continue

            state.feedback_rounds.append({"feedback": feedback})
            state.log(self.label, f"按反馈调整：{feedback[:30]}（重搜={'是' if is_res else '否'}）")
            if plan_changed:
                # 计划结构变了 → 刷新依赖它的代码驱动结构图（路线图/产出物清单）
                self.display_agent.refresh_for_plan_change(state)
            print("   ✅ 已根据反馈更新，下面是新版本：")
            self.display_agent.run(state)  # 重新渲染

        print("已达到最大调整轮数，自动结束。")


# --------------------------------------------------------------------------- #
# 工具函数
# --------------------------------------------------------------------------- #
def _plan_to_markdown(plan: dict) -> str:
    if not plan:
        return "_（计划生成失败）_"
    lines: list[str] = []
    if plan.get("long_term_goal"):
        lines.append(f"## 长期目标\n\n{plan['long_term_goal']}\n")
    if plan.get("stage_goals"):
        lines.append("## 阶段目标\n")
        lines.extend(f"- {g}" for g in plan["stage_goals"])
        lines.append("")
    if plan.get("weekly_schedule"):
        lines.append("## 逐周计划\n")
        for w in plan["weekly_schedule"]:
            lines.append(
                f"- 第 {w.get('week', '')} 周：{w.get('topic', '')} "
                f"（产出：{w.get('output', '')}，{w.get('hours', '')}）"
            )
        lines.append("")
    if plan.get("daily_suggestion"):
        lines.append(f"## 每日建议\n\n{plan['daily_suggestion']}\n")
    if plan.get("milestones"):
        lines.append("## 里程碑\n")
        for m in plan["milestones"]:
            lines.append(f"- 第 {m.get('week', '')} 周：{m.get('name', '')} - {m.get('description', '')}")
    return "\n".join(lines)
