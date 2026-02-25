"""
内务Agent - 主工作流

整合所有Agent节点，构建完整的LangGraph工作流

流程：
  START → router (LLM意图识别) → 条件路由 → 各Agent节点 → formatter → END
"""
import os
from typing import TypedDict, Annotated, Sequence
from langgraph.graph import StateGraph, START, END

from .intent_router import (
    InternalAffairsState,
    intent_router_node,
    route_by_intent,
    unknown_handler_node
)
from .expense_agent import expense_write_node
from .loan_agent import loan_write_node
from .bookkeeping_agent import bookkeeping_write_node
from .query_agent import query_node


def result_formatter_node(state: InternalAffairsState) -> InternalAffairsState:
    """
    结果格式化节点
    
    将各Agent的结果整理成最终回复
    """
    result = state.get("result", "")
    current_step = state.get("current_step", "")
    intent = state.get("intent")
    
    # 如果已经有结果，直接返回
    if result:
        return {
            **state,
            "current_step": "formatter",
            "messages": [("assistant", result)]
        }
    
    # 默认回复
    response = "处理完成"
    
    return {
        **state,
        "current_step": "formatter",
        "result": response,
        "messages": [("assistant", response)]
    }


def create_internal_affairs_graph():
    """
    创建内务Agent工作流图
    
    节点：
    - router: LLM意图识别
    - expense_agent: 报销处理
    - loan_agent: 借款处理
    - bookkeeping_agent: 记账处理
    - query_agent: 查询处理
    - unknown_handler: 无法识别处理
    - formatter: 结果格式化
    """
    graph = StateGraph(InternalAffairsState)
    
    # 添加节点
    graph.add_node("router", intent_router_node)
    graph.add_node("expense_agent", expense_write_node)
    graph.add_node("loan_agent", loan_write_node)
    graph.add_node("bookkeeping_agent", bookkeeping_write_node)
    graph.add_node("query_agent", query_node)
    graph.add_node("unknown_handler", unknown_handler_node)
    graph.add_node("formatter", result_formatter_node)
    
    # 添加边
    graph.add_edge(START, "router")
    
    # 条件路由：根据意图路由到对应Agent
    graph.add_conditional_edges(
        "router",
        route_by_intent,
        {
            "expense_agent": "expense_agent",
            "loan_agent": "loan_agent",
            "bookkeeping_agent": "bookkeeping_agent",
            "query_agent": "query_agent",
            "unknown_handler": "unknown_handler"
        }
    )
    
    # 所有Agent节点 → 格式化 → 结束
    for node in ["expense_agent", "loan_agent", "bookkeeping_agent", "query_agent", "unknown_handler"]:
        graph.add_edge(node, "formatter")
    
    graph.add_edge("formatter", END)
    
    return graph


def create_internal_affairs_agent(checkpointer=None):
    """
    创建可运行的Agent
    
    Args:
        checkpointer: LangGraph checkpointer用于保持会话状态
    
    Returns:
        compiled graph
    """
    graph = create_internal_affairs_graph()
    return graph.compile(checkpointer=checkpointer)


def run_internal_affairs(
    user_input: str,
    user_id: str,
    thread_id: str = None
) -> dict:
    """
    运行内务Agent
    
    Args:
        user_input: 用户输入
        user_id: 用户ID
        thread_id: 会话ID（可选）
    
    Returns:
        Agent执行结果
    """
    from .intent_router import get_original_message
    
    # 获取或创建thread_id
    if thread_id is None:
        import uuid
        thread_id = f"ia_{user_id}_{uuid.uuid4().hex[:8]}"
    
    # 获取checkpointer
    try:
        from langgraph_mvp.config.checkpointer import get_checkpointer
        checkpointer = get_checkpointer()
    except ImportError:
        checkpointer = None
    
    # 创建Agent
    agent = create_internal_affairs_agent(checkpointer=checkpointer)
    
    # 构建初始状态
    initial_state: InternalAffairsState = {
        "messages": [("user", user_input)],
        "task_type": "internal_affairs",
        "current_step": "init",
        "result": None,
        "metadata": {"user_id": user_id},
        "intent": None,
        "entities": None,
        "confidence": None,
        "intent_reasoning": None
    }
    
    # 执行
    config = {"configurable": {"thread_id": thread_id}}
    result = agent.invoke(initial_state, config=config)
    
    return result


# 测试
if __name__ == "__main__":
    print("=" * 60)
    print("内务Agent工作流演示")
    print("=" * 60)
    
    test_cases = [
        ("报销客户招待费用500元", "test_user"),
        ("借款2000元买办公用品", "test_user"),
        ("今天午餐花了25元", "test_user"),
        ("我本月收入多少钱", "test_user"),
        ("这个那个什么的", "test_user"),  # 未知意图
    ]
    
    for user_input, user_id in test_cases:
        print(f"\n>>> 用户输入: {user_input}")
        
        try:
            result = run_internal_affairs(user_input, user_id)
            messages = result.get("messages", [])
            if messages:
                response = messages[-1]
                if isinstance(response, tuple):
                    print(f"<<< 回复: {response[1]}")
                else:
                    print(f"<<< 回复: {response}")
        except Exception as e:
            print(f"<<< 错误: {e}")
        
        print("-" * 40)
