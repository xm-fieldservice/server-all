"""
Store 长期记忆演示

展示：
1. 存储候选人偏好
2. 跨会话读取偏好
3. Checkpoint vs Store 的区别
"""
from langgraph_mvp.agents.recruiting import (
    save_candidate_preference,
    get_candidate_preference,
    save_recruiting_summary,
    get_recruiting_summary,
)


def demo_store_save_and_retrieve():
    """演示：存储和读取长期记忆"""
    print("\n" + "=" * 60)
    print("演示 1: Store 存储和读取")
    print("=" * 60)
    
    candidate_id = "candidate_001"
    
    # 存储偏好
    preference = {
        "name": "张三",
        "expected_salary": 35000,
        "preferred_location": "北京",
        "skills": ["Python", "PostgreSQL", "AI/ML"],
    }
    save_candidate_preference(candidate_id, preference)
    print(f"\n✓ 已保存候选人偏好: {preference['name']}")
    
    # 读取偏好（模拟另一个会话）
    retrieved = get_candidate_preference(candidate_id)
    print(f"✓ 读取到偏好: {retrieved}")
    
    print(f"\n期望薪资: {retrieved['expected_salary']} 元/月")
    print(f"偏好城市: {retrieved['preferred_location']}")
    print(f"技能: {retrieved['skills']}")


def demo_store_cross_session():
    """演示：跨会话记忆"""
    print("\n" + "=" * 60)
    print("演示 2: 跨会话长期记忆")
    print("=" * 60)
    
    job_id = "job_python_001"
    
    # 第一次交互：保存职位总结
    summary1 = {
        "position": "高级Python工程师",
        "candidates_interviewed": 3,
        "final_candidate": "张三",
    }
    save_recruiting_summary(job_id, summary1)
    print(f"\n✓ 会话1: 保存招聘总结 - 面试了 {summary1['candidates_interviewed']} 人")
    
    # 第二次交互（新的对话会话）：读取历史
    summary2 = get_recruiting_summary(job_id)
    print(f"✓ 会话2: 读取历史 - 最终录用 {summary2['final_candidate']}")
    
    print("\n✓ Store 实现了跨会话的长期记忆！")


def demo_checkpoint_vs_store():
    """演示：Checkpoint vs Store 区别"""
    print("\n" + "=" * 60)
    print("演示 3: Checkpoint vs Store 对比")
    print("=" * 60)
    
    print("""
┌─────────────────────────────────────────────────────────────┐
│  Checkpoint (短期记忆)          │  Store (长期记忆)           │
├─────────────────────────────────────────────────────────────┤
│  • 对话状态                     │  • 实体知识                │
│  • 中间步骤结果                 │  • 用户偏好                │
│  • 只在当前会话有效             │  • 跨会话持久化            │
│  • 存在 checkpoinst 表          │  • 存在 langgraph_store   │
│  • LangGraph 自动管理           │  • 需要手动调用 put/get   │
└─────────────────────────────────────────────────────────────┘
    """)
    
    print("实际例子:")
    print("  Checkpoint: 用户刚才说了什么（对话上下文）")
    print("  Store: 用户张三的薪资偏好是 35K（持久知识）")


def main():
    print("\n" + "=" * 60)
    print("LangGraph Store 长期记忆演示")
    print("=" * 60)
    
    demo_store_save_and_retrieve()
    demo_store_cross_session()
    demo_checkpoint_vs_store()
    
    print("\n" + "=" * 60)
    print("演示完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()
