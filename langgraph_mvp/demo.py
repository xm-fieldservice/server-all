"""
多岗位 Agent 协作演示

展示：
1. 不同岗位 Agent 的隔离（namespace 隔离）
2. Checkpoint 持久化（断点恢复）
3. 多轮对话
"""
from langgraph_mvp.agents.recruiting import run_recruiting_task, create_recruiting_agent
from langgraph_mvp.agents.finance import run_finance_task, create_finance_agent
from langgraph_mvp.config.checkpointer import build_thread_id, get_checkpointer


def get_message_content(msg) -> str:
    """获取消息内容，支持字典和消息对象"""
    if hasattr(msg, "content"):
        return msg.content
    if isinstance(msg, dict):
        return msg.get("content", "")
    return str(msg)


def demo_isolated_agents():
    """演示：不同 Agent 隔离运行"""
    print("\n" + "=" * 60)
    print("演示 1: Agent 隔离")
    print("=" * 60)
    
    # 招聘 Agent
    recruiting_thread = build_thread_id(
        user_id="user_001",
        namespace="agent/recruiting",
        source_identifier="recruiter_001"
    )
    
    # 财务 Agent
    finance_thread = build_thread_id(
        user_id="user_001",
        namespace="agent/finance",
        source_identifier="finance_001"
    )
    
    # 运行招聘任务
    print("\n[招聘 Agent] 处理招聘请求...")
    recruiting_result = run_recruiting_task(
        "招聘一名高级 Python 工程师",
        thread_id=recruiting_thread
    )
    print(f"✓ 招聘结果: {recruiting_result.get('result')}")
    
    # 运行财务任务
    print("\n[财务 Agent] 处理预算申请...")
    finance_result = run_finance_task(
        "申请 50000 元市场活动预算",
        thread_id=finance_thread
    )
    print(f"✓ 财务结果: {finance_result.get('result')}")
    
    print("\n✓ 两个 Agent 完全隔离，互不影响")


def demo_checkpoint_recovery():
    """演示：Checkpoint 断点恢复"""
    print("\n" + "=" * 60)
    print("演示 2: Checkpoint 断点恢复")
    print("=" * 60)
    
    thread_id = build_thread_id(
        user_id="user_001",
        namespace="agent/recruiting",
        source_identifier="recruiter_001"
    )
    
    config = {"configurable": {"thread_id": thread_id}}
    agent = create_recruiting_agent()
    
    # 第一次调用：会保存 Checkpoint
    print("\n[第一次调用] 启动招聘流程...")
    state1 = {
        "messages": [("user", "我们需要招聘一名前端工程师")],
        "task_type": "recruiting",
        "current_step": "init",
        "result": None,
        "metadata": {},
    }
    result1 = agent.invoke(state1, config=config)
    print(f"✓ 完成步骤: {result1.get('current_step')}")
    
    # 第二次调用：从 Checkpoint 恢复，继续执行
    print("\n[第二次调用] 从 Checkpoint 恢复，继续流程...")
    state2 = {
        "messages": [("user", "继续处理")],
        "task_type": "recruiting",
        "current_step": result1.get("current_step"),
        "result": result1.get("result"),
        "metadata": {},
    }
    result2 = agent.invoke(state2, config=config)
    print(f"✓ 当前步骤: {result2.get('current_step')}")
    print(f"✓ 完整消息历史: {len(result2.get('messages', []))} 条")
    
    # 查看 Checkpoint 历史
    print("\n[查看 Checkpoint 历史]")
    checkpointer = get_checkpointer()
    checkpoints = list(checkpointer.list(config))
    print(f"✓ 共 {len(checkpoints)} 个 Checkpoint")
    
    print("\n✓ Checkpoint 持久化成功！")


def demo_multi_turn_conversation():
    """演示：多轮对话"""
    print("\n" + "=" * 60)
    print("演示 3: 多轮对话")
    print("=" * 60)
    
    thread_id = build_thread_id(
        user_id="user_001",
        namespace="agent/recruiting",
        source_identifier="recruiter_001"
    )
    
    config = {"configurable": {"thread_id": thread_id}}
    agent = create_recruiting_agent()
    
    # 第一轮
    print("\n[第 1 轮] 用户: 我们需要招聘一名数据科学家")
    state = {
        "messages": [("user", "我们需要招聘一名数据科学家")],
        "task_type": "recruiting",
        "current_step": "init",
        "result": None,
        "metadata": {},
    }
    result = agent.invoke(state, config=config)
    print(f"Agent: {get_message_content(result['messages'][-1])[:80]}...")
    
    # 第二轮（带历史）
    print("\n[第 2 轮] 用户: 薪资范围是多少？")
    state = {
        "messages": result["messages"] + [("user", "薪资范围是多少？")],
        "task_type": "recruiting",
        "current_step": result.get("current_step"),
        "result": result.get("result"),
        "metadata": {},
    }
    result = agent.invoke(state, config=config)
    print(f"Agent: {get_message_content(result['messages'][-1])[:80]}...")
    
    # 第三轮
    print("\n[第 3 轮] 用户: 那工作地点呢？")
    state = {
        "messages": result["messages"] + [("user", "那工作地点呢？")],
        "task_type": "recruiting",
        "current_step": result.get("current_step"),
        "result": result.get("result"),
        "metadata": {},
    }
    result = agent.invoke(state, config=config)
    print(f"Agent: {get_message_content(result['messages'][-1])[:80]}...")
    
    print(f"\n✓ 完整对话历史: {len(result.get('messages', []))} 条")


def main():
    """运行所有演示"""
    print("\n" + "=" * 60)
    print("LangGraph 多岗位 Agent 系统演示")
    print("=" * 60)
    
    # 演示 1: Agent 隔离
    demo_isolated_agents()
    
    # 演示 2: Checkpoint 恢复
    demo_checkpoint_recovery()
    
    # 演示 3: 多轮对话
    demo_multi_turn_conversation()
    
    print("\n" + "=" * 60)
    print("所有演示完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()
