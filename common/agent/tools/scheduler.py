from __future__ import annotations

from typing import Any
from common.agent.tools.registry import ToolResult


def breakdown_goals(main_goal: str, level: str = "intermediate") -> ToolResult:
    tasks = []
    
    if "python" in main_goal.lower():
        tasks = [
            {"task": "Python 基础语法", "duration": "2周", "priority": "high"},
            {"task": "数据结构与算法", "duration": "3周", "priority": "high"},
            {"task": "文件操作与异常处理", "duration": "1周", "priority": "medium"},
            {"task": "面向对象编程", "duration": "2周", "priority": "high"},
            {"task": "标准库与常用模块", "duration": "2周", "priority": "medium"},
            {"task": "项目实战", "duration": "2周", "priority": "high"},
        ]
    elif "machine learning" in main_goal.lower() or "ml" in main_goal.lower():
        tasks = [
            {"task": "数学基础（线性代数、概率论）", "duration": "2周", "priority": "high"},
            {"task": "Python 数据科学库", "duration": "2周", "priority": "high"},
            {"task": "监督学习算法", "duration": "3周", "priority": "high"},
            {"task": "无监督学习算法", "duration": "2周", "priority": "medium"},
            {"task": "模型评估与优化", "duration": "2周", "priority": "medium"},
            {"task": "实战项目", "duration": "3周", "priority": "high"},
        ]
    elif "deep learning" in main_goal.lower() or "dl" in main_goal.lower():
        tasks = [
            {"task": "神经网络基础", "duration": "2周", "priority": "high"},
            {"task": "深度学习框架（PyTorch/TensorFlow）", "duration": "2周", "priority": "high"},
            {"task": "卷积神经网络 CNN", "duration": "2周", "priority": "high"},
            {"task": "循环神经网络 RNN", "duration": "2周", "priority": "medium"},
            {"task": "Transformer 与注意力机制", "duration": "3周", "priority": "high"},
            {"task": "实战项目", "duration": "3周", "priority": "high"},
        ]
    elif "web" in main_goal.lower():
        tasks = [
            {"task": "HTML/CSS 基础", "duration": "2周", "priority": "high"},
            {"task": "JavaScript 基础", "duration": "3周", "priority": "high"},
            {"task": "前端框架（React/Vue）", "duration": "3周", "priority": "high"},
            {"task": "后端基础（Node.js/Django）", "duration": "3周", "priority": "medium"},
            {"task": "数据库", "duration": "2周", "priority": "medium"},
            {"task": "全栈项目实战", "duration": "3周", "priority": "high"},
        ]
    else:
        tasks = [
            {"task": "基础知识入门", "duration": "2周", "priority": "high"},
            {"task": "核心概念学习", "duration": "3周", "priority": "high"},
            {"task": "进阶技能提升", "duration": "3周", "priority": "medium"},
            {"task": "实践项目", "duration": "4周", "priority": "high"},
        ]
    
    result = {
        "main_goal": main_goal,
        "tasks": tasks,
        "total_duration": "约" + str(sum([int(t["duration"].replace("周", "")) for t in tasks])) + "周",
    }
    
    return ToolResult(
        name="breakdown_goals",
        success=True,
        summary=f"Broken down into {len(tasks)} tasks, total duration: {result['total_duration']}",
        data=result,
    )


def schedule_tasks(tasks: list[dict], available_hours_per_week: int = 10) -> ToolResult:
    schedule = []
    week = 1
    
    for task in tasks:
        task_name = task.get("task", "Unknown Task")
        duration_weeks = int(task.get("duration", "1周").replace("周", ""))
        
        for w in range(duration_weeks):
            schedule.append({
                "week": week + w,
                "task": task_name,
                "hours_needed": min(available_hours_per_week, 10),
            })
        
        week += duration_weeks
    
    return ToolResult(
        name="schedule_tasks",
        success=True,
        summary=f"Scheduled {len(tasks)} tasks across {week - 1} weeks",
        data={
            "schedule": schedule,
            "total_weeks": week - 1,
            "hours_per_week": available_hours_per_week,
        },
    )


def set_milestones(tasks: list[dict], total_weeks: int) -> ToolResult:
    milestones = []
    
    milestone_points = [
        (0.0, "起点", "开始学习之旅"),
        (0.25, "基础完成", "完成基础知识学习"),
        (0.5, "中期评估", "完成核心技术学习"),
        (0.75, "进阶阶段", "完成进阶内容"),
        (1.0, "终点", "完成全部学习目标"),
    ]
    
    for percentage, name, description in milestone_points:
        week = max(1, int(total_weeks * percentage))
        milestones.append({
            "week": week,
            "name": name,
            "description": description,
            "percentage": int(percentage * 100),
        })
    
    return ToolResult(
        name="set_milestones",
        success=True,
        summary=f"Set {len(milestones)} milestones",
        data={
            "milestones": milestones,
            "total_weeks": total_weeks,
        },
    )
