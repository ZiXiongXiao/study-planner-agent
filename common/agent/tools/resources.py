from __future__ import annotations

import httpx
from common.agent.tools.registry import ToolResult


def understand_goals(goals_text: str) -> ToolResult:
    result = {
        "goals": [],
        "keywords": [],
        "time_available": None,
        "difficulty_preference": None,
    }
    
    keywords = []
    if "python" in goals_text.lower():
        keywords.append("Python")
    if "machine learning" in goals_text.lower() or "ml" in goals_text.lower():
        keywords.append("Machine Learning")
    if "deep learning" in goals_text.lower() or "dl" in goals_text.lower():
        keywords.append("Deep Learning")
    if "web" in goals_text.lower():
        keywords.append("Web Development")
    if "data" in goals_text.lower():
        keywords.append("Data Science")
    
    result["keywords"] = keywords
    result["goals"] = [g.strip() for g in goals_text.split("\n") if g.strip()]
    
    return ToolResult(
        name="understand_goals",
        success=True,
        summary=f"Understood {len(result['goals'])} goals with keywords: {', '.join(keywords)}",
        data=result,
    )


def assess_level(level_info: str) -> ToolResult:
    level = "intermediate"
    level_text = level_info.lower()
    
    if any(word in level_text for word in ["beginner", "新手", "零基础", "初学"]):
        level = "beginner"
    elif any(word in level_text for word in ["advanced", "高级", "专家", "精通"]):
        level = "advanced"
    elif any(word in level_text for word in ["intermediate", "中级", "有一些", "基础"]):
        level = "intermediate"
    
    assessment = {
        "level": level,
        "strengths": [],
        "areas_for_improvement": [],
    }
    
    if level == "beginner":
        assessment["recommendations"] = [
            "Start with fundamentals",
            "Focus on core concepts",
            "Practice with simple exercises",
        ]
    elif level == "intermediate":
        assessment["recommendations"] = [
            "Build on existing knowledge",
            "Tackle more complex projects",
            "Explore advanced topics gradually",
        ]
    else:
        assessment["recommendations"] = [
            "Focus on specialized topics",
            "Contribute to real-world projects",
            "Mentor others",
        ]
    
    return ToolResult(
        name="assess_level",
        success=True,
        summary=f"Assessed skill level as: {level}",
        data=assessment,
    )


def search_resources(keywords: str, level: str = "intermediate") -> ToolResult:
    resources = []
    
    keyword_list = [k.strip() for k in keywords.split(",")]
    
    resource_templates = {
        "python": [
            {
                "title": "Python Official Tutorial",
                "type": "documentation",
                "url": "https://docs.python.org/3/tutorial/",
                "level": "beginner",
            },
            {
                "title": "Python Crash Course",
                "type": "book",
                "url": "https://ehmatthes.github.io/pcc_2e/",
                "level": "beginner",
            },
            {
                "title": "Real Python",
                "type": "website",
                "url": "https://realpython.com/",
                "level": "intermediate",
            },
        ],
        "machine learning": [
            {
                "title": "Hands-On Machine Learning",
                "type": "book",
                "url": "https://github.com/ageron/handson-ml3",
                "level": "intermediate",
            },
            {
                "title": "Andrew Ng's ML Course",
                "type": "course",
                "url": "https://www.coursera.org/learn/machine-learning",
                "level": "beginner",
            },
            {
                "title": "scikit-learn Documentation",
                "type": "documentation",
                "url": "https://scikit-learn.org/stable/",
                "level": "intermediate",
            },
        ],
        "deep learning": [
            {
                "title": "Deep Learning Specialization",
                "type": "course",
                "url": "https://www.coursera.org/specializations/deep-learning",
                "level": "intermediate",
            },
            {
                "title": "PyTorch Tutorials",
                "type": "documentation",
                "url": "https://pytorch.org/tutorials/",
                "level": "intermediate",
            },
            {
                "title": "Fast.ai Course",
                "type": "course",
                "url": "https://course.fast.ai/",
                "level": "beginner",
            },
        ],
        "web": [
            {
                "title": "MDN Web Docs",
                "type": "documentation",
                "url": "https://developer.mozilla.org/",
                "level": "beginner",
            },
            {
                "title": "freeCodeCamp",
                "type": "platform",
                "url": "https://www.freecodecamp.org/",
                "level": "beginner",
            },
        ],
    }
    
    for kw in keyword_list:
        kw_lower = kw.lower()
        for topic, items in resource_templates.items():
            if topic in kw_lower or kw_lower in topic:
                for item in items:
                    if item["level"] == level or item["level"] == "beginner":
                        resources.append(item)
    
    if not resources:
        resources = [
            {
                "title": "General Learning Platform",
                "type": "platform",
                "url": "https://www.edx.org/",
                "level": "all",
            },
            {
                "title": "Coursera",
                "type": "platform",
                "url": "https://www.coursera.org/",
                "level": "all",
            },
        ]
    
    return ToolResult(
        name="search_resources",
        success=True,
        summary=f"Found {len(resources)} learning resources",
        data=resources,
    )
