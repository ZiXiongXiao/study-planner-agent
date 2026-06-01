from __future__ import annotations

from typing import Any
from common.agent.tools.registry import ToolResult


def understand_goals(goals_text: str) -> ToolResult:
    goals = [g.strip() for g in goals_text.split("\n") if g.strip()]
    
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
    
    result = {
        "goals": goals,
        "keywords": keywords,
        "detected_topics": list(set(keywords)) if keywords else ["General"],
    }
    
    return ToolResult(
        name="understand_goals",
        success=True,
        summary=f"Understood {len(goals)} goals, detected topics: {', '.join(result['detected_topics'])}",
        data=result,
    )


def assess_level(level_info: str) -> ToolResult:
    level = "intermediate"
    level_text = level_info.lower()
    
    beginner_indicators = ["beginner", "新手", "零基础", "初学", "刚开始", "没有经验"]
    advanced_indicators = ["advanced", "高级", "专家", "精通", "多年", "资深"]
    
    if any(word in level_text for word in beginner_indicators):
        level = "beginner"
    elif any(word in level_text for word in advanced_indicators):
        level = "advanced"
    
    recommendations = {
        "beginner": [
            "建议从基础概念开始",
            "多做一些简单练习",
            "不要急于求成，打好基础",
        ],
        "intermediate": [
            "巩固已有知识",
            "尝试更复杂的项目",
            "深入理解核心原理",
        ],
        "advanced": [
            "专注于高级主题",
            "参与开源项目",
            "尝试教授他人",
        ],
    }
    
    result = {
        "level": level,
        "recommendations": recommendations[level],
        "message": f"您的当前水平评估为：{level}",
    }
    
    return ToolResult(
        name="assess_level",
        success=True,
        summary=f"Assessed level as {level}",
        data=result,
    )


def breakdown_goals(main_goal: str, level: str = "intermediate") -> ToolResult:
    default_tasks = [
        {"task": "基础知识学习", "duration": "2周", "priority": "high"},
        {"task": "核心概念掌握", "duration": "3周", "priority": "high"},
        {"task": "进阶技能提升", "duration": "3周", "priority": "medium"},
        {"task": "项目实战练习", "duration": "4周", "priority": "high"},
    ]
    
    if "python" in main_goal.lower():
        default_tasks = [
            {"task": "Python 基础语法", "duration": "2周", "priority": "high"},
            {"task": "数据结构与算法", "duration": "3周", "priority": "high"},
            {"task": "面向对象编程", "duration": "2周", "priority": "high"},
            {"task": "项目实战与代码规范", "duration": "3周", "priority": "high"},
        ]
    elif "machine learning" in main_goal.lower():
        default_tasks = [
            {"task": "数学基础复习", "duration": "2周", "priority": "high"},
            {"task": "机器学习算法理论", "duration": "4周", "priority": "high"},
            {"task": "Scikit-learn 实战", "duration": "2周", "priority": "medium"},
            {"task": "项目实战", "duration": "4周", "priority": "high"},
        ]
    
    total_weeks = sum([int(t["duration"].replace("周", "")) for t in default_tasks])
    
    return ToolResult(
        name="breakdown_goals",
        success=True,
        summary=f"分解为 {len(default_tasks)} 个任务，总计约 {total_weeks} 周",
        data={
            "main_goal": main_goal,
            "tasks": default_tasks,
            "total_weeks": total_weeks,
        },
    )


def set_milestones(tasks: list[dict], total_weeks: int) -> ToolResult:
    milestones = []
    
    checkpoints = [
        ("起点", "开始学习旅程", 0),
        ("25%", "基础知识入门", 25),
        ("50%", "核心技能掌握", 50),
        ("75%", "进阶提升阶段", 75),
        ("100%", "学习目标完成", 100),
    ]
    
    for name, description, percentage in checkpoints:
        week = max(1, min(total_weeks, int(total_weeks * percentage / 100)))
        milestones.append({
            "week": week,
            "name": name,
            "description": description,
            "percentage": percentage,
        })
    
    return ToolResult(
        name="set_milestones",
        success=True,
        summary=f"设置了 {len(milestones)} 个里程碑",
        data={
            "milestones": milestones,
            "total_weeks": total_weeks,
        },
    )


def track_progress(current_week: int, total_weeks: int, completed_tasks: list[str]) -> ToolResult:
    progress_percentage = (current_week / total_weeks * 100) if total_weeks > 0 else 0
    
    status = "进行中"
    if progress_percentage >= 100:
        status = "已完成"
    elif progress_percentage >= 75:
        status = "冲刺阶段"
    elif progress_percentage >= 50:
        status = "过半了"
    elif progress_percentage >= 25:
        status = "稳步推进"
    else:
        status = "刚刚开始"
    
    remaining_tasks = total_weeks - current_week
    
    return ToolResult(
        name="track_progress",
        success=True,
        summary=f"当前进度 {progress_percentage:.1f}% - {status}",
        data={
            "current_week": current_week,
            "total_weeks": total_weeks,
            "progress_percentage": progress_percentage,
            "status": status,
            "completed_tasks": completed_tasks,
            "remaining_weeks": remaining_tasks,
        },
    )
