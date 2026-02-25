"""
LangGraph 状态定义

每个岗位 Agent 共享相同的基础状态结构，支持对话历史和任务状态跟踪。
"""
from typing import TypedDict, Annotated, Sequence
from langgraph.graph import add_messages


class AgentState(TypedDict):
    """
    基础 Agent 状态
    
    字段:
    - messages: 对话消息历史（LangGraph 自动管理）
    - task_type: 任务类型（如 "recruiting", "finance"）
    - current_step: 当前执行步骤
    - result: 最终结果
    - metadata: 附加元数据
    """
    # messages 会自动合并（add_messages reducer）
    messages: Annotated[Sequence[dict], add_messages]
    
    # 任务类型
    task_type: str
    
    # 当前步骤
    current_step: str
    
    # 最终结果
    result: str | None
    
    # 附加元数据
    metadata: dict


def create_initial_state(task_type: str) -> AgentState:
    """创建初始状态"""
    return {
        "messages": [],
        "task_type": task_type,
        "current_step": "init",
        "result": None,
        "metadata": {},
    }
