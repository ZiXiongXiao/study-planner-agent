"""
Study Planner Agent - Demo Script
智能学习规划助手 - 演示脚本

This script demonstrates the core functionality of the Study Planner Agent
without requiring API keys or complex setup.
"""

from common.agent.memory import AgentMemory
from common.agent.planner import get_plan, print_plan
from common.agent.tools.registry import build_default_registry


def demo_mode1():
    """演示模式1：学习目标设定"""
    print("\n" + "=" * 60)
    print("演示：模式 1 - 学习目标设定")
    print("=" * 60)

    registry = build_default_registry()
    memory = AgentMemory(
        soul="你是智能学习规划助手",
        mode_supplement="帮助用户明确学习目标、评估水平、推荐资源",
        task_instruction="使用中文回答",
    )

    print("\n【场景】用户想要学习 Python 数据分析\n")

    goals_text = """我想学习 Python 数据分析
目标是能够在工作中使用 Pandas 进行数据处理
每周可以投入 10 小时学习时间"""

    print("用户输入：")
    print(goals_text)
    print()

    print("--- 执行工具链 ---\n")

    understand_result = registry.call("understand_goals", goals_text=goals_text)
    print(f"\n理解目标结果: {understand_result.data}\n")

    assess_result = registry.call("assess_level", level_info="有一些编程基础，但不是 Python")
    print(f"\n水平评估结果: {assess_result.data}\n")

    search_result = registry.call(
        "search_resources",
        keywords="python,data analysis,pandas",
        level="intermediate"
    )
    print(f"\n找到 {len(search_result.data)} 个学习资源\n")

    print("--- 生成学习目标建议 ---\n")
    print("1. 主目标：掌握 Python 数据分析技能")
    print("2. 次目标：能够独立完成数据处理任务")
    print("3. 时间线：预计 8-12 周完成基础学习")
    print("\n推荐资源：")
    for i, r in enumerate(search_result.data[:3], 1):
        print(f"  {i}. {r['title']} - {r['url']}")

    print("\n[V] 演示完成")


def demo_mode2():
    """演示模式 2：学习计划制定"""
    print("\n" + "=" * 60)
    print("演示：模式 2 - 学习计划制定")
    print("=" * 60)

    registry = build_default_registry()
    memory = AgentMemory(
        soul="你是智能学习规划助手",
        mode_supplement="帮助用户制定详细的学习计划",
        task_instruction="使用中文回答",
    )

    print("\n【场景】用户想要制定 Python 学习计划\n")

    main_goal = "系统学习 Python 编程，达到能够开发 Web 应用的水平"
    print(f"用户目标：{main_goal}\n")

    print("--- 执行工具链 ---\n")

    breakdown_result = registry.call("breakdown_goals", main_goal=main_goal, level="beginner")
    print(f"\n任务分解结果：")
    for i, task in enumerate(breakdown_result.data["tasks"], 1):
        print(f"  {i}. {task['task']} - {task['duration']}")
    print(f"\n总预计时间：{breakdown_result.data['total_weeks']} 周\n")

    schedule_result = registry.call(
        "schedule_tasks",
        tasks=breakdown_result.data["tasks"],
        available_hours_per_week=10
    )
    print(f"时间安排：共 {schedule_result.data['total_weeks']} 周，每周 {schedule_result.data['hours_per_week']} 小时\n")

    milestones_result = registry.call(
        "set_milestones",
        tasks=breakdown_result.data["tasks"],
        total_weeks=schedule_result.data["total_weeks"]
    )
    print("里程碑设置：")
    for m in milestones_result.data["milestones"]:
        print(f"  - 第 {m['week']} 周: {m['name']} ({m['description']})")

    print("\n--- 生成学习计划 ---\n")
    print("## Python Web 开发学习计划（12周）")
    print("\n### 第1-2周：Python 基础")
    print("- 语法、数据类型、函数")
    print("- 每天1.5小时 + 30分钟练习")
    print("\n### 第3-4周：面向对象编程")
    print("- 类、继承、模块")
    print("- 完成2个小项目")
    print("\n### 第5-6周：Web 基础")
    print("- HTML/CSS/JavaScript")
    print("- Flask 或 Django 入门")
    print("\n### 第7-10周：Web 开发实战")
    print("- 完成个人博客项目")
    print("- 学习数据库集成")
    print("\n### 第11-12周：项目完善与部署")
    print("- 代码优化与重构")
    print("- 部署到云服务器")

    print("\n[V] 演示完成")


def demo_agent_loop():
    """模拟 Agent 主循环"""
    print("\n" + "=" * 60)
    print("演示：Agent 完整工作流程")
    print("=" * 60)

    print("\n【步骤1】选择模式")
    mode = 2
    print(f"选择模式 {mode}: Plan Making")

    print("\n【步骤2】加载计划")
    plan = get_plan(mode)
    print_plan(plan)

    print("\n【步骤3】初始化工具")
    registry = build_default_registry()
    print(f"已注册 {len(registry.list_tools())} 个工具")

    print("\n【步骤4】执行计划")
    print("[Plan] Step 1: Break down goals...")
    print("[Tool] breakdown_goals → OK")
    print("[Plan] Step 2: Schedule tasks...")
    print("[Tool] schedule_tasks → OK")
    print("[Plan] Step 3: Set milestones...")
    print("[Tool] set_milestones → OK")
    print("[Plan] Step 4: Search resources...")
    print("[Tool] search_resources → OK")
    print("[Plan] Step 5: Generate plan [LLM]")
    print("[Plan] Step 6: Multi-turn optimization [LLM]")

    print("\n【步骤5】多轮对话")
    print("Assistant: 您好！根据您的目标，我为您制定了一个12周的学习计划...")
    print("User: 可以把时间压缩到8周吗？")
    print("Assistant: 当然可以，我来调整计划...")
    print("User: 好的，谢谢！")
    print("Assistant: 不客气，祝您学习顺利！")

    print("\n【步骤6】保存会话")
    print("Saved to plans/example/deepseek-v4-flash.md")

    print("\n[V] 完整工作流程演示完成")


def main():
    """运行所有演示"""
    print("\n" + "=" * 60)
    print("Study Planner Agent 演示脚本")
    print("智能学习规划助手 - 核心功能演示")
    print("=" * 60)

    demo_mode1()
    demo_mode2()
    demo_agent_loop()

    print("\n" + "=" * 60)
    print("演示结束！")
    print("=" * 60)
    print("\n要运行完整的 Agent，请使用：")
    print("  python providers/kimi.py")
    print("  或")
    print("  python providers/deepseek.py")
    print()


if __name__ == "__main__":
    main()
