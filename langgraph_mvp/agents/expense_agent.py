"""
内务Agent - 报销Agent

功能：
- 处理报销场景
- 写入entries表
- 权限检查
"""
import os
import json
import uuid
from datetime import datetime
from typing import TypedDict, Annotated, Sequence
from langgraph.graph import add_messages


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
    """
    通用保存内务记录到entries表
    
    Args:
        user_id: 用户ID
        title: 标题
        input_content: 用户原始输入
        sub_type: 子类型 (expense/loan/bookkeeping)
        extra_data: 额外数据
    
    Returns:
        entry_id
    """
    entry_id = f"{sub_type[:3]}_{uuid.uuid4().hex[:12]}"
    
    # 构建scene_tags，包含测试标记
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
    
    print(f"[ExpenseAgent] 报销记录已保存: {entry_id}")
    return entry_id


def check_expense_permission(user_id: str) -> dict:
    """
    检查报销权限
    
    实际应调用企微API获取用户角色
    MVP阶段简化实现
    """
    # TODO: 对接企微通讯录API获取真实权限
    # 暂时允许所有用户报销
    return {
        "can_expense": True,
        "max_amount": 10000.0,
        "department": "测试部门"
    }


def expense_write_node(state) -> dict:
    """
    报销写入节点
    
    从state中提取entities，写入报销记录
    """
    entities = state.get("entities", {})
    user_id = state.get("metadata", {}).get("user_id", "unknown")
    original_message = state.get("messages", [])[-1].content if state.get("messages") else ""
    
    # 提取实体信息
    amount = entities.get("amount")
    category = entities.get("category", "其他")
    date = entities.get("date", datetime.now().strftime("%Y-%m-%d"))
    description = entities.get("description", "")
    
    # 权限检查
    permission = check_expense_permission(user_id)
    if not permission.get("can_expense"):
        response = "抱歉，您没有报销权限"
        return {
            **state,
            "current_step": "expense",
            "result": response,
            "status": "rejected",
            "messages": [("assistant", response)]
        }
    
    # 金额检查
    if amount and amount > permission.get("max_amount", 10000):
        response = f"报销金额超过限额 ({permission.get('max_amount')}元)，请联系管理员"
        return {
            **state,
            "current_step": "expense",
            "result": response,
            "status": "rejected",
            "messages": [("assistant", response)]
        }
    
    # 保存记录
    if amount:
        title = f"[报销] {category} - {amount}元"
        entry_id = save_internal_affairs_record(
            user_id=user_id,
            title=title,
            input_content=original_message,
            sub_type="expense",
            extra_data={
                "amount": amount,
                "category": category,
                "date": date,
                "description": description,
                "status": "pending"  # 待审批
            }
        )
        
        response = (
            f"【报销成功】\n"
            f"• 金额：{amount}元\n"
            f"• 分类：{category}\n"
            f"• 日期：{date}\n"
            f"• 描述：{description or '无'}\n"
            f"• 状态：待审批"
        )
        status = "pending"
    else:
        response = "未能识别报销金额，请重试"
        entry_id = None
        status = "failed"
    
    return {
        **state,
        "current_step": "expense",
        "result": response,
        "status": status,
        "entry_id": entry_id,
        "messages": [("assistant", response)]
    }


# 测试
if __name__ == "__main__":
    test_state = {
        "messages": [{"type": "human", "content": "报销客户招待费用500元"}],
        "metadata": {"user_id": "test_user"},
        "entities": {
            "amount": 500.0,
            "category": "餐饮",
            "date": "2026-02-25",
            "description": "客户招待"
        }
    }
    
    print("=" * 60)
    print("测试报销写入")
    print("=" * 60)
    
    result = expense_write_node(test_state)
    print(f"\n结果: {result['result']}")
    print(f"状态: {result.get('status')}")
