"""
招聘 Agent (Recruiting Agent)

示例：处理招聘相关任务，包括职位发布、简历筛选、面试安排等。
支持长期记忆（Store）存储候选人偏好。
"""
from langgraph.graph import StateGraph, START, END

from ..config.state import AgentState
from ..config.checkpointer import get_checkpointer, build_thread_id
from ..config.store import build_memory_namespace, save_item, get_item


# ============ Node Functions ============

def get_last_message_content(messages) -> str:
    """从消息列表中提取最后一条消息的内容"""
    if not messages:
        return ""
    last_msg = messages[-1]
    if hasattr(last_msg, "content"):
        return last_msg.content
    return str(last_msg)


# ============ Store (长期记忆) 工具函数 ============

def save_candidate_preference(candidate_id: str, preference: dict):
    """保存候选人偏好到长期记忆"""
    namespace = build_memory_namespace("candidates", candidate_id)
    save_item(namespace, "preferences", preference)


def get_candidate_preference(candidate_id: str) -> dict | None:
    """从长期记忆获取候选人偏好"""
    namespace = build_memory_namespace("candidates", candidate_id)
    return get_item(namespace, "preferences")


def save_recruiting_summary(job_id: str, summary: dict):
    """保存招聘流程总结"""
    namespace = build_memory_namespace("jobs", job_id)
    save_item(namespace, "summary", summary)


def get_recruiting_summary(job_id: str) -> dict | None:
    """获取招聘流程总结"""
    namespace = build_memory_namespace("jobs", job_id)
    return get_item(namespace, "summary")


def analyze_requirements(state: AgentState) -> AgentState:
    """分析招聘需求"""
    last_message = get_last_message_content(state["messages"])
    
    response = f"【招聘需求分析】收到招聘请求: {last_message[:50]}..."
    
    return {
        **state,
        "current_step": "analyze_requirements",
        "messages": [("assistant", response)],
        "result": None,
    }


def search_candidates(state: AgentState) -> AgentState:
    """搜索候选人"""
    response = "【搜索候选人】已从人才库中筛选出 5 位匹配候选人"
    
    return {
        **state,
        "current_step": "search_candidates",
        "messages": [("assistant", response)],
    }


def schedule_interview(state: AgentState) -> AgentState:
    """安排面试"""
    response = "【安排面试】已发送面试邀请，候选人均已确认时间"
    
    return {
        **state,
        "current_step": "schedule_interview",
        "messages": [("assistant", response)],
    }


def generate_offer(state: AgentState) -> AgentState:
    """生成录用通知"""
    response = "【录用通知】已生成录用通知，候选人已接受"
    
    return {
        **state,
        "current_step": "generate_offer",
        "messages": [("assistant", response)],
        "result": "招聘流程完成，已录用 1 人",
    }


# ============ Graph Definition ============

def create_recruiting_graph():
    """创建招聘流程图"""
    graph = StateGraph(AgentState)
    
    # 添加节点
    graph.add_node("analyze", analyze_requirements)
    graph.add_node("search", search_candidates)
    graph.add_node("schedule", schedule_interview)
    graph.add_node("offer", generate_offer)
    
    # 定义流程
    graph.add_edge(START, "analyze")
    graph.add_edge("analyze", "search")
    graph.add_edge("search", "schedule")
    graph.add_edge("schedule", "offer")
    graph.add_edge("offer", END)
    
    # 编译（带 Checkpoint）
    checkpointer = get_checkpointer()
    return graph.compile(checkpointer=checkpointer)


# ============ 便捷函数 ============

def create_recruiting_agent():
    """创建招聘 Agent 实例"""
    return create_recruiting_graph()


def run_recruiting_task(user_input: str, thread_id: str = None):
    """
    运行招聘任务
    
    Args:
        user_input: 用户输入
        thread_id: 线程 ID（用于持久化）
    
    Returns:
        Agent 执行结果
    """
    # 默认使用招聘专用 thread_id
    if thread_id is None:
        thread_id = build_thread_id(
            user_id="default_user",
            namespace="agent/recruiting",
            source_identifier="recruiter_001"
        )
    
    # 创建 config
    config = {"configurable": {"thread_id": thread_id}}
    
    # 获取 Agent
    agent = create_recruiting_agent()
    
    # 执行
    initial_state = {
        "messages": [("user", user_input)],
        "task_type": "recruiting",
        "current_step": "init",
        "result": None,
        "metadata": {},
    }
    
    result = agent.invoke(initial_state, config=config)
    return result


# ============ 演示 ============

if __name__ == "__main__":
    print("=" * 50)
    print("招聘 Agent 演示")
    print("=" * 50)
    
    # 运行任务
    result = run_recruiting_task("我们需要招聘一名高级 Python 工程师")
    
    print(f"\n最终结果: {result.get('result')}")
    print(f"消息历史: {len(result.get('messages', []))} 条")
    for msg in result.get("messages", []):
        print(f"  - {msg}")
