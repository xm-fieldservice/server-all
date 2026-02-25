"""
内务Agent - 借款Agent

功能：
- 处理借款场景
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
    
    print(f"[LoanAgent] 借款记录已保存: {entry_id}")
    return entry_id


def check_loan_permission(user_id: str) -> dict:
    """
    检查借款权限
    
    MVP阶段简化实现
    """
    # TODO: 对接企微通讯录API获取真实权限
    return {
        "can_loan": True,
        "max_amount": 5000.0,
        "department": "测试部门"
    }


def loan_write_node(state) -> dict:
    """
    借款写入节点
    """
    entities = state.get("entities", {})
    user_id = state.get("metadata", {}).get("user_id", "unknown")
    original_message = state.get("messages", [])[-1].content if state.get("messages") else ""
    
    # 提取实体信息
    amount = entities.get("amount")
    reason = entities.get("description", "")
    date = entities.get("date", datetime.now().strftime("%Y-%m-%d"))
    return_date = entities.get("return_date")  # 计划归还日期
    
    # 权限检查
    permission = check_loan_permission(user_id)
    if not permission.get("can_loan"):
        response = "抱歉，您没有借款权限"
        return {
            **state,
            "current_step": "loan",
            "result": response,
            "status": "rejected",
            "messages": [("assistant", response)]
        }
    
    # 金额检查
    if amount and amount > permission.get("max_amount", 5000):
        response = f"借款金额超过限额 ({permission.get('max_amount')}元)，请联系管理员"
        return {
            **state,
            "current_step": "loan",
            "result": response,
            "status": "rejected",
            "messages": [("assistant", response)]
        }
    
    # 保存记录
    if amount:
        title = f"[借款] {amount}元"
        entry_id = save_internal_affairs_record(
            user_id=user_id,
            title=title,
            input_content=original_message,
            sub_type="loan",
            extra_data={
                "amount": amount,
                "reason": reason,
                "date": date,
                "return_date": return_date,
                "status": "pending",  # 待审批
                "balance": amount  # 待还余额
            }
        )
        
        response = (
            f"【借款成功】\n"
            f"• 金额：{amount}元\n"
            f"• 原因：{reason or '未说明'}\n"
            f"• 借款日期：{date}\n"
            f"• 计划归还：{return_date or '未指定'}\n"
            f"• 状态：待审批"
        )
        status = "pending"
    else:
        response = "未能识别借款金额，请重试"
        entry_id = None
        status = "failed"
    
    return {
        **state,
        "current_step": "loan",
        "result": response,
        "status": status,
        "entry_id": entry_id,
        "messages": [("assistant", response)]
    }


# 测试
if __name__ == "__main__":
    test_state = {
        "messages": [{"type": "human", "content": "借款2000元用于购买办公用品"}],
        "metadata": {"user_id": "test_user"},
        "entities": {
            "amount": 2000.0,
            "description": "购买办公用品",
            "date": "2026-02-25",
            "return_date": "2026-03-25"
        }
    }
    
    print("=" * 60)
    print("测试借款写入")
    print("=" * 60)
    
    result = loan_write_node(test_state)
    print(f"\n结果: {result['result']}")
    print(f"状态: {result.get('status')}")
