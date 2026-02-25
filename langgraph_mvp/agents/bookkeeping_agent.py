"""
内务Agent - 记账Agent

功能：
- 处理日常记账场景（收入/支出）
- 写入entries表
"""
import os
import json
import uuid
from datetime import datetime
from typing import TypedDict, Annotated, Sequence
from langgraph.graph import add_messages


# 支出分类
EXPENSE_CATEGORIES = ["餐饮", "交通", "购物", "娱乐", "住房", "医疗", "教育", "通讯", "其他"]

# 收入分类  
INCOME_CATEGORIES = ["工资", "奖金", "兼职", "投资", "礼金", "其他"]


def get_env() -> str:
    """获取当前环境"""
    return os.getenv("WECOM_ENV", "test")


def get_connection_scope():
    """获取数据库连接"""
    from ai_factory.db.pgvector_client import connection_scope
    return connection_scope


def save_internal_affairs_record(
    user_id: str,
    title: str,
    input_content: str,
    sub_type: str,
    extra_data: dict
) -> str:
    """通用保存内务记录到entries表"""
    entry_id = f"{sub_type[:3]}_{uuid.uuid4().hex[:12]}"
    
    env = get_env()
    scene_tags = {
        "type": "internal_affairs",
        "sub_type": sub_type,
        "environment": env,
        "test_marker": env == "test",
        **extra_data
    }
    
    with get_connection_scope() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO entries 
                (entry_id, title, input_content, user_id, created_at, scene_tags, space_type)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                entry_id, 
                title, 
                input_content, 
                user_id, 
                datetime.now(), 
                json.dumps(scene_tags), 
                "internal_affairs"
            ))
    
    print(f"[BookkeepingAgent] 记账记录已保存: {entry_id}")
    return entry_id


def bookkeeping_write_node(state) -> dict:
    """
    记账写入节点
    """
    entities = state.get("entities", {})
    user_id = state.get("metadata", {}).get("user_id", "unknown")
    original_message = state.get("messages", [])[-1].content if state.get("messages") else ""
    
    # 提取实体信息
    amount = entities.get("amount")
    is_income = entities.get("is_income", False)  # 收入还是支出
    category = entities.get("category")
    date = entities.get("date", datetime.now().strftime("%Y-%m-%d"))
    description = entities.get("description", "")
    
    # 自动推断分类
    if not category:
        if is_income:
            category = "其他"
        else:
            category = "其他"
    
    # 方向
    direction = "收入" if is_income else "支出"
    
    # 保存记录
    if amount:
        title = f"[{direction}] {category} - {amount}元"
        entry_id = save_internal_affairs_record(
            user_id=user_id,
            title=title,
            input_content=original_message,
            sub_type="bookkeeping",
            extra_data={
                "amount": amount,
                "category": category,
                "date": date,
                "description": description,
                "is_income": is_income,
                "direction": direction
            }
        )
        
        response = (
            f"【记账成功】\n"
            f"• 类型：{direction}\n"
            f"• 金额：{amount}元\n"
            f"• 分类：{category}\n"
            f"• 日期：{date}\n"
            f"• 描述：{description or '无'}"
        )
        status = "recorded"
    else:
        response = "未能识别记账金额，请重试"
        entry_id = None
        status = "failed"
    
    return {
        **state,
        "current_step": "bookkeeping",
        "result": response,
        "status": status,
        "entry_id": entry_id,
        "messages": [("assistant", response)]
    }


# 测试
if __name__ == "__main__":
    # 测试支出
    test_state1 = {
        "messages": [{"type": "human", "content": "今天午餐花了25元"}],
        "metadata": {"user_id": "test_user"},
        "entities": {
            "amount": 25.0,
            "category": "餐饮",
            "is_income": False,
            "date": "2026-02-25"
        }
    }
    
    # 测试收入
    test_state2 = {
        "messages": [{"type": "human", "content": "本月工资到账8000元"}],
        "metadata": {"user_id": "test_user"},
        "entities": {
            "amount": 8000.0,
            "category": "工资",
            "is_income": True,
            "date": "2026-02-25"
        }
    }
    
    print("=" * 60)
    print("测试记账 - 支出")
    print("=" * 60)
    result1 = bookkeeping_write_node(test_state1)
    print(f"\n结果: {result1['result']}")
    
    print("\n" + "=" * 60)
    print("测试记账 - 收入")
    print("=" * 60)
    result2 = bookkeeping_write_node(test_state2)
    print(f"\n结果: {result2['result']}")
