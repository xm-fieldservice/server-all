"""
财务 Agent (Finance Agent)

功能：
- 记账：公司级、个人级记账
- 查账：公司账目（管理员可查）、个人账目（仅己可见）

权限设计：
- 管理员：可读写公司账目
- 普通用户：只能读写个人账目
"""
import os

from langgraph.graph import StateGraph, START, END

from ..config.state import AgentState
from ..config.checkpointer import get_checkpointer, build_thread_id
from ..config.finance_permissions import get_user_permission, build_filter_from_permission


def detect_request_type(user_input: str, current_user: str) -> dict:
    """判断请求类型：记账 vs 查账，以及权限级别"""
    import re
    
    # 查询关键词
    query_patterns = [r"查询", r"查", r"有多少", r"多少", r"开支", r"支出", r"收入", r"账单", r"账目", r"记录", r"看看"]
    # 写入关键词
    write_patterns = [r"记账", r"记录", r"报销", r"付款", r"转账", r"花了", r"花费", r"支出", r"借款", r"还款", r"充值", r"扣款"]
    # 公司关键词
    company_patterns = [r"公司", r"公款", r"全体", r"全员"]
    
    # 判断动作：先看写入（更优先），再看查询
    action = "query"  # 默认是查询
    for pattern in write_patterns:
        if re.search(pattern, user_input):
            action = "write"
            break
    else:
        # 没有写入关键词，看是否有查询关键词
        for pattern in query_patterns:
            if re.search(pattern, user_input):
                action = "query"
                break
    
    # 判断范围
    scope = "personal"
    for pattern in company_patterns:
        if re.search(pattern, user_input):
            scope = "company"
            break
    
    return {"action": action, "scope": scope, "target_user": current_user}


def parse_financial_record(user_input: str) -> dict:
    """解析财务记录"""
    import re
    
    patterns = [r"(\d+)\s*元", r"(\d+)\s*块", r"¥\s*(\d+)", r"\$(\d+)"]
    amount = None
    for pattern in patterns:
        match = re.search(pattern, user_input)
        if match:
            amount = float(match.group(1))
            break
    
    categories = {
        "餐饮": ["餐饮", "吃饭", "餐费", "饭"],
        "交通": ["交通", "打车", "地铁", "公交"],
        "办公": ["办公", "文具", "打印", "设备"],
        "工资": ["工资", "薪资", "奖金"],
        "采购": ["采购", "物料"],
    }
    category = "其他"
    for cat, keywords in categories.items():
        if any(kw in user_input.lower() for kw in keywords):
            category = cat
            break
    
    return {"amount": amount, "category": category}


def _get_message_content(messages) -> str:
    if not messages:
        return ""
    last_msg = messages[-1]
    return last_msg.content if hasattr(last_msg, "content") else str(last_msg)


def _save_financial_entry(user_id: str, content: str, amount: float | None, category: str, request_scope: str):
    """保存财务记录到 entries 表"""
    import uuid
    import json
    from datetime import datetime
    
    entry_id = f"fin_{uuid.uuid4().hex[:12]}"
    now = datetime.now()
    title = f"[{category}] {content[:30]}..."
    scene_tags = json.dumps({"type": "finance", "category": category, "amount": amount, "scope": request_scope})
    
    from ai_factory.db.pgvector_client import connection_scope
    
    with connection_scope() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO entries (entry_id, title, input_content, user_id, created_at, scene_tags, space_type)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (entry_id, title, content, user_id, now, scene_tags, "finance"))


def _query_via_rag(query: str, filter_user_id: str | None) -> dict:
    """查询财务记录（向量搜索 + 关键词回退）"""
    import json
    from ai_factory.db.pgvector_client import connection_scope
    
    # 尝试向量搜索
    query_embedding = _generate_embedding(query)
    
    with connection_scope() as conn:
        with conn.cursor() as cur:
            # 如果有向量，则使用向量搜索
            if query_embedding:
                sql = """
                    SELECT e.entry_id, e.title, e.input_content, e.user_id, e.scene_tags, e.created_at,
                           emb.embedding <=> %s AS distance
                    FROM entries e
                    LEFT JOIN entry_embeddings emb ON e.entry_id = emb.entry_id
                    WHERE e.space_type = 'finance'
                """
                params = [query_embedding]
            else:
                # 无向量时，返回最近记录（按时间排序）
                sql = """
                    SELECT e.entry_id, e.title, e.input_content, e.user_id, e.scene_tags, e.created_at,
                           0 AS distance
                    FROM entries e
                    WHERE e.space_type = 'finance'
                """
                params = []
            
            if filter_user_id:
                sql += " AND e.user_id = %s"
                params.append(filter_user_id)
            else:
                sql += " AND e.user_id = 'company'"
            
            # 有向量时按相似度排序，否则按时间排序
            if query_embedding:
                sql += " ORDER BY distance ASC NULLS LAST LIMIT 10"
            else:
                sql += " ORDER BY e.created_at DESC LIMIT 10"
            
            cur.execute(sql, params)
            rows = cur.fetchall()
            
            citations = []
            for row in rows:
                scene_tags = row[4]
                if isinstance(scene_tags, str):
                    try:
                        scene_tags = json.loads(scene_tags)
                    except:
                        scene_tags = {}
                
                distance = row[6]
                # 距离转换为相似度分数 (1 - distance)
                score = max(0, min(1, 1 - (distance or 0))) if distance is not None else 0.5
                
                citations.append({
                    "entry_id": row[0],
                    "title": row[1],
                    "content": row[2],
                    "user_id": row[3],
                    "scene_tags": scene_tags,
                    "created_at": row[5].isoformat() if row[5] else None,
                    "score": score
                })
            
            return {"answer": None, "citations": citations}


def _query_via_keyword(query: str, filter_user_id: str | None) -> dict:
    """关键词搜索（回退方案）"""
    import json
    from ai_factory.db.pgvector_client import connection_scope
    
    with connection_scope() as conn:
        with conn.cursor() as cur:
            sql = """
                SELECT entry_id, title, input_content, user_id, scene_tags, created_at
                FROM entries
                WHERE space_type = 'finance'
            """
            params = []
            
            if filter_user_id:
                sql += " AND user_id = %s"
                params.append(filter_user_id)
            else:
                sql += " AND user_id = 'company'"
            
            # 关键词匹配
            sql += " AND (input_content ILIKE %s OR title ILIKE %s)"
            params.extend([f"%{query}%", f"%{query}%"])
            
            sql += " ORDER BY created_at DESC LIMIT 10"
            
            cur.execute(sql, params)
            rows = cur.fetchall()
            
            citations = []
            for row in rows:
                scene_tags = row[4]
                if isinstance(scene_tags, str):
                    try:
                        scene_tags = json.loads(scene_tags)
                    except:
                        scene_tags = {}
                
                citations.append({
                    "entry_id": row[0],
                    "title": row[1],
                    "content": row[2],
                    "user_id": row[3],
                    "scene_tags": scene_tags,
                    "created_at": row[5].isoformat() if row[5] else None,
                    "score": 0.5
                })
            
            return {"answer": None, "citations": citations}


def _generate_embedding(text: str):
    """生成文本向量"""
    try:
        import requests
        
        api_key = os.getenv("DEEPSEEK_API_KEY")
        base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
        
        if not api_key:
            print("[Finance Agent] No DEEPSEEK_API_KEY, using keyword search")
            return None
        
        response = requests.post(
            f"{base_url}/embeddings",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": "deepseek-embeddings",
                "input": text
            },
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            embedding = data.get("data", [{}])[0].get("embedding")
            return embedding
        else:
            print(f"[Finance Agent] Embedding API error: {response.status_code}")
            return None
            
    except Exception as e:
        print(f"[Finance Agent] Embedding generation failed: {e}")
        return None


def classify_request(state: AgentState) -> AgentState:
    """解析请求类型"""
    # 获取原始用户输入（第一条消息）
    original_input = _get_original_input(state["messages"])
    current_user = state.get("metadata", {}).get("user_id", "default_user")
    request_info = detect_request_type(original_input, current_user)
    
    response = f"【请求识别】动作: {request_info['action']}, 范围: {request_info['scope']}"
    
    return {
        **state,
        "current_step": "classify",
        "messages": [("assistant", response)],
        "metadata": {**state.get("metadata", {}), "request_info": request_info, "original_input": original_input}
    }


def _get_original_input(messages) -> str:
    """获取原始用户输入"""
    for msg in messages:
        if hasattr(msg, "type") and msg.type == "human":
            return msg.content
        if isinstance(msg, tuple) and msg[0] == "user":
            return msg[1]
    # 如果没找到，返回最后一条
    return _get_message_content(messages)


def write_record(state: AgentState) -> AgentState:
    """记账（带权限检查）"""
    original_input = _get_original_input(state["messages"])
    request_info = state.get("metadata", {}).get("request_info", {})
    current_user = state.get("metadata", {}).get("user_id", "default_user")
    
    # 获取权限
    permission = get_user_permission(current_user)
    requested_scope = request_info.get("scope", "personal")
    
    # 权限检查
    if requested_scope == "company" and not permission["can_write_company"]:
        response = "【权限不足】您无权记录公司账目，只能记录个人账目"
        return {**state, "current_step": "write", "messages": [("assistant", response)]}
    
    # 确定写入的 user_id
    if requested_scope == "company" and permission["can_write_company"]:
        user_id = "company"
    else:
        user_id = permission["internal_user_id"]
    
    record = parse_financial_record(original_input)
    
    _save_financial_entry(
        user_id=user_id,
        content=original_input,
        amount=record.get("amount"),
        category=record.get("category"),
        request_scope=requested_scope
    )
    
    amount_str = f"{record.get('amount')}元" if record.get("amount") else "未识别金额"
    response = f"【记账成功】已记录: {record.get('category')} - {amount_str} (归属: {user_id})"
    
    return {**state, "current_step": "write", "messages": [("assistant", response)]}


def query_records(state: AgentState) -> AgentState:
    """查账（带权限检查）"""
    original_input = _get_original_input(state["messages"])
    request_info = state.get("metadata", {}).get("request_info", {})
    current_user = state.get("metadata", {}).get("user_id", "default_user")
    
    # 获取权限
    permission = get_user_permission(current_user)
    requested_scope = request_info.get("scope", "personal")
    
    # 权限检查
    if requested_scope == "company" and not permission["can_read_company"]:
        response = "【权限不足】您无权查看公司账目，只能查询个人账目"
        return {**state, "current_step": "query", "messages": [("assistant", response)]}
    
    # 构建过滤条件
    filter_user_id = build_filter_from_permission(permission, requested_scope)
    
    rag_result = _query_via_rag(original_input, filter_user_id)
    
    if rag_result.get("answer"):
        answer = rag_result["answer"]
    elif rag_result.get("citations"):
        citations = rag_result["citations"]
        answer = f"找到 {len(citations)} 条记录:\n" + "\n".join(
            f"- {c.get('title', c.get('content', '')[:50])}" for c in citations[:5]
        )
    else:
        answer = "未找到相关账目记录"
    
    response = f"【查询结果】\n{answer}"
    
    return {**state, "current_step": "query", "messages": [("assistant", response)], "result": answer}


def create_finance_graph():
    """创建财务流程图"""
    graph = StateGraph(AgentState)
    
    graph.add_node("classify", classify_request)
    graph.add_node("write", write_record)
    graph.add_node("query", query_records)
    
    def route_decision(state: AgentState) -> str:
        return state.get("metadata", {}).get("request_info", {}).get("action", "query")
    
    graph.add_conditional_edges("classify", route_decision, {"write": "write", "query": "query"})
    graph.add_edge(START, "classify")
    graph.add_edge("write", END)
    graph.add_edge("query", END)
    
    return graph.compile(checkpointer=get_checkpointer())


def create_finance_agent():
    return create_finance_graph()


def run_finance_task(user_input: str, user_id: str = "default_user", thread_id: str = None):
    if thread_id is None:
        thread_id = build_thread_id(user_id, "agent/finance", "finance_001")
    
    config = {"configurable": {"thread_id": thread_id}}
    agent = create_finance_agent()
    
    initial_state = {
        "messages": [("user", user_input)],
        "task_type": "finance",
        "current_step": "init",
        "result": None,
        "metadata": {"user_id": user_id},
    }
    
    return agent.invoke(initial_state, config=config)


if __name__ == "__main__":
    print("=" * 60)
    print("财务 Agent 演示")
    print("=" * 60)
    
    print("\n[1] 公司记账")
    result = run_finance_task("公司购买办公设备花费 5000 元", "admin")
    print(f"结果: {result.get('messages')[-1].content}")
    
    print("\n[2] 个人记账")
    result = run_finance_task("我今天午餐花了 25 元", "zhangsan")
    print(f"结果: {result.get('messages')[-1].content}")
    
    print("\n[3] 查询公司账目")
    result = run_finance_task("公司本月开支有哪些？", "admin")
    print(f"结果: {result.get('messages')[-1].content}")
    
    print("\n[4] 查询个人账目")
    result = run_finance_task("我最近花了多少钱？", "zhangsan")
    print(f"结果: {result.get('messages')[-1].content}")
    
    print("\n" + "=" * 60)
