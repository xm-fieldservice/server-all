"""
内务Agent - LLM意图路由器

功能：
- 使用LLM进行意图分类
- 提取实体信息（金额、日期、分类等）
- 将意图判断结果写入entries表作为标记
"""
import os
import json
from datetime import datetime
from typing import TypedDict, Annotated, Sequence
from langgraph.graph import add_messages

# 意图路由器System Prompt
INTENT_ROUTER_SYSTEM_PROMPT = """你是一个企业内部助手的意图路由器。

## 你的任务
根据用户的自然语言消息，识别意图并提取关键信息。

## 支持的处理类型

### 1. expense (报销)
用户花钱后申请报销的场景。
关键词：报销、报销xxx元、报销费用、报账、能不能报
提取信息：金额、日期、分类（餐饮/交通/办公/采购/其他）、描述

### 2. loan (借款)
用户提前借钱的场景。
关键词：借款、借xxx元、借支、预支
提取信息：金额、日期、原因、归还日期

### 3. bookkeeping (记账)
日常收支记录。
关键词：记账、记录、花了、收入、支出、工资到账
提取信息：金额、日期、分类（收入分类/支出分类）、描述

### 4. query (查询)
查询账目或统计。
关键词：查账、查询、看看有多少、统计、有多少钱
提取信息：查询范围（personal个人/company公司）、时间范围（this_month本月/last_month上月/all全部）、分类筛选

### 5. unknown
无法识别或不属于以上类型。

## 输出要求

输出严格的JSON格式，不要有其他内容：
```json
{
  "intent": "expense|loan|bookkeeping|query|unknown",
  "confidence": 0.95,
  "entities": {
    "amount": 500.0,
    "date": "2026-02-25",
    "category": "餐饮",
    "description": "客户招待",
    "query_scope": "personal",
    "time_range": "this_month",
    "is_income": false
  },
  "reasoning": "简短的分析理由"
}
```

如果无法确定意图，返回 "intent": "unknown" 并说明原因。
"""


class InternalAffairsState(TypedDict):
    """内务Agent状态"""
    # 对话消息历史
    messages: Annotated[Sequence[dict], add_messages]
    
    # 任务类型
    task_type: str
    
    # 当前步骤
    current_step: str
    
    # 最终结果
    result: str | None
    
    # 附加元数据
    metadata: dict
    
    # 意图识别结果（新增）
    intent: str | None
    entities: dict | None
    confidence: float | None
    intent_reasoning: str | None


def get_llm():
    """获取LLM客户端"""
    from langchain_openai import ChatOpenAI
    
    return ChatOpenAI(
        model="deepseek-chat",
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        temperature=0.1
    )


def get_original_message(messages) -> str:
    """获取用户原始输入"""
    for msg in messages:
        if isinstance(msg, dict):
            if msg.get("type") == "human":
                return msg.get("content", "")
        elif hasattr(msg, "type") and msg.type == "human":
            return msg.content
        elif isinstance(msg, tuple) and msg[0] == "user":
            return msg[1]
    # 如果没找到，返回最后一条
    if messages:
        last = messages[-1]
        if isinstance(last, dict):
            return last.get("content", "")
        elif hasattr(last, "content"):
            return last.content
    return ""


def record_intent_marker(user_id: str, user_message: str, 
                        intent: str, confidence: float,
                        entities: dict, reasoning: str):
    """
    将意图判断结果写入entries表作为标记
    
    这是设计要点：意图判断完成后，将判断结果写入数据表
    """
    import uuid
    from ai_factory.db.pgvector_client import connection_scope
    
    entry_id = f"intent_{uuid.uuid4().hex[:12]}"
    title = f"[意图识别] {intent} - 置信度 {confidence}"
    
    # 构建scene_tags，包含测试标记
    env = os.getenv("WECOM_ENV", "test")
    scene_tags = {
        "type": "internal_affairs",
        "sub_type": "intent_marker",  # 意图标记类型
        "original_intent": intent,
        "intent_confidence": confidence,
        "intent_reasoning": reasoning,
        "original_message": user_message,
        "entities": entities,
        "environment": env,
        "test_marker": env == "test"
    }
    
    with connection_scope() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO entries 
                (entry_id, title, input_content, user_id, created_at, scene_tags, space_type)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                entry_id, 
                title, 
                user_message, 
                user_id, 
                datetime.now(), 
                json.dumps(scene_tags), 
                "internal_affairs"
            ))
    
    print(f"[IntentRouter] 意图标记已写入: {entry_id}, intent={intent}, confidence={confidence}")


def intent_router_node(state: InternalAffairsState) -> InternalAffairsState:
    """
    意图路由节点
    
    1. 获取用户消息
    2. 调用LLM进行意图识别和实体提取
    3. 将意图判断结果写入entries表
    4. 返回扩展后的状态
    """
    user_message = get_original_message(state["messages"])
    user_id = state["metadata"].get("user_id", "unknown")
    
    print(f"[IntentRouter] 处理消息: {user_message[:50]}...")
    
    # 调用LLM
    llm = get_llm()
    response = llm.invoke(
        f"{INTENT_ROUTER_SYSTEM_PROMPT}\n\n用户消息: {user_message}"
    )
    
    # 解析LLM输出
    try:
        content = response.content.strip()
        # 去掉可能的markdown代码块
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        content = content.strip("```").strip()
        
        result = json.loads(content)
    except (json.JSONDecodeError, AttributeError) as e:
        print(f"[IntentRouter] LLM输出解析失败: {e}, content: {content}")
        result = {
            "intent": "unknown",
            "confidence": 0.0,
            "entities": {},
            "reasoning": f"LLM输出解析失败: {str(e)}"
        }
    
    intent = result.get("intent", "unknown")
    confidence = result.get("confidence", 0.0)
    entities = result.get("entities", {})
    reasoning = result.get("reasoning", "")
    
    # 关键：将意图写入entries表
    if intent != "unknown":
        record_intent_marker(
            user_id=user_id,
            user_message=user_message,
            intent=intent,
            confidence=confidence,
            entities=entities,
            reasoning=reasoning
        )
    
    # 构建回复
    intent_display = {
        "expense": "报销",
        "loan": "借款", 
        "bookkeeping": "记账",
        "query": "查询",
        "unknown": "未知"
    }
    
    response_msg = f"【意图识别】{intent_display.get(intent, intent)} (置信度: {confidence:.0%})"
    if reasoning:
        response_msg += f"\n{reasoning}"
    
    return {
        **state,
        "current_step": "router",
        "intent": intent,
        "entities": entities,
        "confidence": confidence,
        "intent_reasoning": reasoning,
        "messages": [("assistant", response_msg)]
    }


def route_by_intent(state: InternalAffairsState) -> str:
    """
    根据意图路由到对应的Agent节点
    
    返回节点名称，用于LangGraph条件边
    """
    intent = state.get("intent", "unknown")
    
    # 意图 → Agent节点 映射
    intent_to_node = {
        "expense": "expense_agent",
        "loan": "loan_agent",
        "bookkeeping": "bookkeeping_agent",
        "query": "query_agent",
        "unknown": "unknown_handler"
    }
    
    return intent_to_node.get(intent, "unknown_handler")


def unknown_handler_node(state: InternalAffairsState) -> InternalAffairsState:
    """无法识别意图的处理节点"""
    user_message = get_original_message(state["messages"])
    
    response = (
        "抱歉，我无法理解您的请求。\n\n"
        "我可以帮助您：\n"
        "• 报销 - 说'报销xxx元'\n"
        "• 借款 - 说'借款xxx元'\n"
        "• 记账 - 说'记账花了xxx元' 或 '收入xxx元'\n"
        "• 查询 - 说'查一下我的账' 或 '本月支出多少'"
    )
    
    return {
        **state,
        "current_step": "unknown",
        "result": response,
        "messages": [("assistant", response)]
    }


# 测试函数
if __name__ == "__main__":
    # 模拟测试
    test_messages = [
        {"type": "human", "content": "老板，我昨天请客户吃饭花了500能不能报一下"}
    ]
    
    state: InternalAffairsState = {
        "messages": test_messages,
        "task_type": "internal_affairs",
        "current_step": "init",
        "result": None,
        "metadata": {"user_id": "test_user"},
        "intent": None,
        "entities": None,
        "confidence": None,
        "intent_reasoning": None
    }
    
    print("=" * 60)
    print("测试意图识别")
    print("=" * 60)
    
    result = intent_router_node(state)
    
    print(f"\n意图: {result['intent']}")
    print(f"置信度: {result['confidence']}")
    print(f"实体: {result['entities']}")
    print(f"推理: {result['intent_reasoning']}")
    print(f"路由目标: {route_by_intent(result)}")
