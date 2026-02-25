"""
内务Agent - 查询Agent

功能：
- 查询账目记录
- 实时计算统计（不预存统计表）
- 支持多维度筛选
"""
import os
import json
from datetime import datetime, timedelta
from typing import TypedDict, Annotated, Sequence
from langgraph.graph import add_messages


def get_env() -> str:
    """获取当前环境"""
    return os.getenv("WECOM_ENV", "test")


def get_connection_scope():
    """获取数据库连接"""
    from ai_factory.db.pgvector_client import connection_scope
    return connection_scope


def parse_time_range(time_range: str) -> tuple:
    """
    解析时间范围
    
    Returns:
        (start_date, end_date) or (None, None) for all
    """
    today = datetime.now()
    
    if time_range == "this_month":
        # 本月
        start = today.replace(day=1)
        end = today
    elif time_range == "last_month":
        # 上月
        if today.month == 1:
            start = today.replace(year=today.year-1, month=12, day=1)
        else:
            start = today.replace(month=today.month-1, day=1)
        end = today.replace(day=1) - timedelta(days=1)
    elif time_range == "this_week":
        # 本周
        start = today - timedelta(days=today.weekday())
        end = today
    elif time_range == "today":
        start = today.replace(hour=0, minute=0, second=0)
        end = today
    else:
        # 全部
        return None, None
    
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def query_records(
    user_id: str,
    scope: str = "personal",
    time_range: str = "all",
    category: str = None,
    sub_types: list = None
) -> list:
    """
    查询内务记录
    
    Args:
        user_id: 用户ID
        scope: personal(个人) / company(公司)
        time_range: this_month / last_month / this_week / today / all
        category: 分类筛选
        sub_types: 子类型筛选
    
    Returns:
        记录列表
    """
    env = get_env()
    
    # 构建查询
    conditions = [
        "space_type = 'internal_affairs'",
        "scene_tags->>'environment' = %s"
    ]
    params = [env]
    
    # 范围
    if scope == "personal":
        conditions.append("user_id = %s")
        params.append(user_id)
    elif scope == "company":
        conditions.append("user_id = 'company'")
    
    # 时间范围
    start_date, end_date = parse_time_range(time_range)
    if start_date and end_date:
        conditions.append("created_at >= %s AND created_at <= %s")
        params.append(start_date)
        params.append(end_date + " 23:59:59")
    
    # 子类型筛选 (expense/loan/bookkeeping)
    if sub_types:
        conditions.append(f"scene_tags->>'sub_type' IN ({','.join(['%s']*len(sub_types))})")
        params.extend(sub_types)
    
    # 分类筛选
    if category:
        conditions.append("scene_tags->>'category' = %s")
        params.append(category)
    
    where_clause = " AND ".join(conditions)
    
    sql = f"""
        SELECT entry_id, title, input_content, user_id, scene_tags, created_at
        FROM entries
        WHERE {where_clause}
        ORDER BY created_at DESC
        LIMIT 100
    """
    
    with get_connection_scope() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
            
            records = []
            for row in rows:
                scene_tags = row[4]
                if isinstance(scene_tags, str):
                    try:
                        scene_tags = json.loads(scene_tags)
                    except:
                        scene_tags = {}
                
                records.append({
                    "entry_id": row[0],
                    "title": row[1],
                    "content": row[2],
                    "user_id": row[3],
                    "scene_tags": scene_tags,
                    "created_at": row[5].isoformat() if row[5] else None
                })
            
            return records


def calculate_stats(records: list) -> dict:
    """
    实时计算统计
    
    不预存统计表，直接从原始记录聚合
    """
    if not records:
        return {
            "total_count": 0,
            "total_expense": 0.0,
            "total_income": 0.0,
            "total_loan": 0.0,
            "balance": 0.0,
            "by_category": {}
        }
    
    total_expense = 0.0
    total_income = 0.0
    total_loan = 0.0
    by_category = {}
    
    for r in records:
        tags = r.get("scene_tags", {})
        sub_type = tags.get("sub_type")
        amount = tags.get("amount", 0)
        category = tags.get("category", "其他")
        
        if sub_type == "expense":
            total_expense += amount
        elif sub_type == "bookkeeping":
            if tags.get("is_income"):
                total_income += amount
            else:
                total_expense += amount
        elif sub_type == "loan":
            total_loan += amount
        
        # 分类统计
        if category not in by_category:
            by_category[category] = {"count": 0, "amount": 0.0}
        by_category[category]["count"] += 1
        by_category[category]["amount"] += amount
    
    return {
        "total_count": len(records),
        "total_expense": total_expense,
        "total_income": total_income,
        "total_loan": total_loan,
        "balance": total_income - total_expense,
        "by_category": by_category
    }


def query_node(state) -> dict:
    """
    查询节点
    """
    entities = state.get("entities", {})
    user_id = state.get("metadata", {}).get("user_id", "unknown")
    
    # 解析查询参数
    scope = entities.get("query_scope", "personal")  # personal / company
    time_range = entities.get("time_range", "all")
    category = entities.get("category")
    
    # 查询记录
    records = query_records(
        user_id=user_id,
        scope=scope,
        time_range=time_range,
        category=category,
        sub_types=["expense", "bookkeeping"]  # 只查询消费和记账
    )
    
    # 实时计算统计
    stats = calculate_stats(records)
    
    # 构建回复
    scope_name = "个人" if scope == "personal" else "公司"
    time_name = {
        "this_month": "本月",
        "last_month": "上月", 
        "this_week": "本周",
        "today": "今天",
        "all": "全部"
    }.get(time_range, "全部")
    
    lines = [f"【{scope_name}账目查询 - {time_name}】"]
    lines.append(f"\n总记录：{stats['total_count']} 笔")
    lines.append(f"总支出：{stats['total_expense']:.2f} 元")
    lines.append(f"总收入：{stats['total_income']:.2f} 元")
    lines.append(f"结余：{stats['balance']:.2f} 元")
    
    if stats['by_category']:
        lines.append("\n【分类明细】")
        for cat, data in sorted(stats['by_category'].items(), key=lambda x: -x[1]["amount"]):
            lines.append(f"  {cat}: {data['amount']:.2f} 元 ({data['count']}笔)")
    
    # 最近5条记录
    if records:
        lines.append("\n【最近记录】")
        for r in records[:5]:
            tags = r.get("scene_tags", {})
            sub_type = tags.get("sub_type", "")
            amount = tags.get("amount", 0)
            date = r.get("created_at", "")[:10]
            lines.append(f"  {date} {sub_type}: {amount}元")
    
    response = "\n".join(lines)
    
    return {
        **state,
        "current_step": "query",
        "result": response,
        "stats": stats,
        "record_count": len(records),
        "messages": [("assistant", response)]
    }


# 测试
if __name__ == "__main__":
    test_state = {
        "messages": [{"type": "human", "content": "查一下我本月的账"}],
        "metadata": {"user_id": "test_user"},
        "entities": {
            "query_scope": "personal",
            "time_range": "this_month"
        }
    }
    
    print("=" * 60)
    print("测试查询")
    print("=" * 60)
    
    result = query_node(test_state)
    print(f"\n{result['result']}")
