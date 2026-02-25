# 内务Agent MVP 详细设计文档

> **版本**: v1.0  
> **状态**: MVP设计  
> **更新日期**: 2026-02-25  
> **测试标记**: 所有数据均带 `environment: test` 标记

---

## 一、整体架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                         企业微信                                     │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐              │
│  │ 消息输入 │  │ 用户ID  │  │ 部门/角色│  │ 消息推送 │              │
│  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘              │
└───────┼────────────┼────────────┼────────────┼──────────────────────┘
        │            │            │            │
        ▼            ▼            ▼            ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    InternalAffairsAgent (LangGraph)                  │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   ┌─────────────────────────────────────────────────────────────┐   │
│   │              IntentRouter (LLM)                            │   │
│   │  ┌─────────────────────────────────────────────────────┐   │   │
│   │  │ 1. 意图分类: 报销/借款/记账/查询                      │   │   │
│   │  │ 2. 实体提取: 金额/日期/分类/描述                      │   │   │
│   │  │ 3. 意图标记写入: 将判断结果写入entries表               │   │   │
│   │  └─────────────────────────────────────────────────────┘   │   │
│   └─────────────────────────────────────────────────────────────┘   │
│                              │                                      │
│          ┌──────────────────┼──────────────────┐                   │
│          ▼                  ▼                  ▼                   │
│   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐          │
│   │ WriteAgent  │    │ WriteAgent  │    │ QueryAgent  │          │
│   │ (报销/借款) │    │   (记账)    │    │   (查询)    │          │
│   └──────┬──────┘    └──────┬──────┘    └──────┬──────┘          │
│          │                   │                   │                  │
│          └───────────────────┼───────────────────┘                  │
│                              ▼                                      │
│                    ┌─────────────────┐                             │
│                    │  ResultFormatter │ ← LLM生成自然语言回复       │
│                    └────────┬────────┘                              │
│                             │                                       │
└─────────────────────────────┼───────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐
│   PostgreSQL    │   │   Redis         │   │   企微消息推送   │
│   (entries表)   │   │   (会话状态)     │   │   (结果通知)    │
└─────────────────┘   └─────────────────┘   └─────────────────┘
```

---

## 二、核心流程

### 2.1 消息处理流程

```
用户发送消息
       ↓
┌─────────────────────────────────────┐
│      InternalAffairsHandler         │  ← 入口 (复用 finance_bot)
└─────────────────────────────────────┘
       ↓
┌─────────────────────────────────────┐
│     IntentRouter (LLM)             │
│  • 意图分类                         │
│  • 实体提取                         │
│  • 意图标记写入数据表               │  ← 关键：将意图写入 entries
└─────────────────────────────────────┘
       ↓
┌─────────────────────────────────────┐
│    Agent Dispatcher                 │
│  • expense → ExpenseWriteAgent     │
│  • loan    → LoanWriteAgent       │
│  • bookkeeping → BookkeepingAgent │
│  • query   → QueryAgent           │
└─────────────────────────────────────┘
       ↓
┌─────────────────────────────────────┐
│     ResultFormatter (LLM)           │
│  • 生成自然语言回复                 │
└─────────────────────────────────────┘
       ↓
┌─────────────────────────────────────┐
│     企微消息推送                    │
└─────────────────────────────────────┘
```

### 2.2 意图标记写入示例

```python
# IntentRouter 完成后，将意图写入 entries 表
scene_tags = {
    "type": "internal_affairs",
    "sub_type": "expense",           # ← 意图判断结果
    "intent_confidence": 0.95,
    "intent_reasoning": "用户提到'报销'关键词...",
    "entities": {
        "amount": 500.0,
        "category": "餐饮",
        "date": "2026-02-25"
    },
    "environment": "test",           # ← 测试标记
    "test_marker": True               # ← 测试标记
}
```

---

## 三、数据模型

### 3.1 entries 表复用

**新增/扩展字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `entry_id` | VARCHAR | 主键 |
| `title` | VARCHAR | 标题，如 "[报销] 餐饮 - 500元" |
| `input_content` | TEXT | 用户原始输入 |
| `user_id` | VARCHAR | 企微用户ID |
| `space_type` | VARCHAR | 固定值: `internal_affairs` |
| `scene_tags` | JSONB | 扩展属性（见下） |

### 3.2 scene_tags 结构

```json
{
  "type": "internal_affairs",
  "sub_type": "expense|loan|bookkeeping|query",
  "environment": "test",
  "test_marker": true,
  
  "intent_confidence": 0.95,
  "intent_reasoning": "分析理由...",
  
  "entities": {
    "amount": 500.0,
    "date": "2026-02-25",
    "category": "餐饮",
    "description": "客户招待"
  },
  
  "status": "pending|approved|rejected",
  "attachments": ["file_id_1"],
  "approver": null
}
```

---

## 四、IntentRouter 设计

### 4.1 LLM Prompt

```python
INTENT_ROUTER_SYSTEM_PROMPT = """你是一个企业内部助手的意图路由器。

## 你的任务
根据用户的自然语言消息，识别意图并提取关键信息。

## 支持的处理类型

### 1. expense (报销)
用户花钱后申请报销的场景。
关键词：报销、报销xxx元、报销费用、报账
提取信息：金额、日期、分类（餐饮/交通/办公/其他）、描述

### 2. loan (借款)
用户提前借钱的场景。
关键词：借款、借xxx元、借支
提取信息：金额、日期、原因、归还日期

### 3. bookkeeping (记账)
日常收支记录。
关键词：记账、记录、花了、收入、支出
提取信息：金额、日期、分类（收入/支出）、描述

### 4. query (查询)
查询账目或统计。
关键词：查账、查询、看看有多少、统计
提取信息：查询范围（个人/公司）、时间范围、分类筛选

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
    "time_range": "this_month"
  },
  "reasoning": "简短的分析理由"
}
```

如果无法确定意图，返回 "intent": "unknown" 并说明原因。
"""
```

### 4.2 实现代码

```python
import json
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END

llm = ChatOpenAI(
    model="deepseek-chat",
    base_url="https://api.deepseek.com/v1",
    api_key=os.getenv("DEEPSEEK_API_KEY")
)

def intent_router_node(state: AgentState) -> AgentState:
    """意图路由节点"""
    user_message = get_original_message(state["messages"])
    
    # LLM 调用
    response = llm.invoke(
        f"{INTENT_ROUTER_SYSTEM_PROMPT}\n\n用户消息: {user_message}"
    )
    
    # 解析结果
    result = json.loads(response.content.strip("```json").strip("```"))
    
    # 关键：将意图写入 entries 表作为标记
    record_intent_marker(
        user_id=state["metadata"]["user_id"],
        user_message=user_message,
        intent=result["intent"],
        confidence=result["confidence"],
        entities=result.get("entities", {}),
        reasoning=result.get("reasoning", "")
    )
    
    return {
        **state,
        "intent": result["intent"],
        "entities": result.get("entities", {}),
        "confidence": result["confidence"],
        "intent_reasoning": result.get("reasoning", "")
    }


def record_intent_marker(user_id: str, user_message: str, 
                         intent: str, confidence: float,
                         entities: dict, reasoning: str):
    """将意图判断结果写入 entries 表"""
    import uuid
    from datetime import datetime
    
    entry_id = f"intent_{uuid.uuid4().hex[:12]}"
    title = f"[意图识别] {intent} - 置信度 {confidence}"
    
    scene_tags = json.dumps({
        "type": "internal_affairs",
        "sub_type": "intent_marker",  # 意图标记类型
        "original_intent": intent,
        "intent_confidence": confidence,
        "intent_reasoning": reasoning,
        "original_message": user_message,
        "entities": entities,
        "environment": "test",  # 测试标记
        "test_marker": True     # 测试标记
    })
    
    from ai_factory.db.pgvector_client import connection_scope
    
    with connection_scope() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO entries 
                (entry_id, title, input_content, user_id, created_at, scene_tags, space_type)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (entry_id, title, user_message, user_id, datetime.now(), 
                  scene_tags, "internal_affairs"))
```

---

## 五、多Agent调度

### 5.1 Agent 分类

| Agent | 处理意图 | 功能 |
|-------|----------|------|
| `ExpenseWriteAgent` | expense | 报销写入 |
| `LoanWriteAgent` | loan | 借款写入 |
| `BookkeepingAgent` | bookkeeping | 记账写入 |
| `QueryAgent` | query | 查询统计 |

### 5.2 条件路由

```python
def route_by_intent(state: AgentState) -> str:
    """根据意图路由到对应Agent"""
    intent = state.get("intent", "unknown")
    
    # 意图 → Agent 映射
    intent_to_agent = {
        "expense": "expense_agent",
        "loan": "loan_agent",
        "bookkeeping": "bookkeeping_agent",
        "query": "query_agent"
    }
    
    return intent_to_agent.get(intent, "unknown_handler")
```

### 5.3 完整 LangGraph 定义

```python
def create_internal_affairs_graph():
    """创建内务Agent工作流"""
    graph = StateGraph(AgentState)
    
    # 节点
    graph.add_node("router", intent_router_node)
    graph.add_node("expense_agent", expense_write_node)
    graph.add_node("loan_agent", loan_write_node)
    graph.add_node("bookkeeping_agent", bookkeeping_write_node)
    graph.add_node("query_agent", query_node)
    graph.add_node("formatter", result_formatter_node)
    graph.add_node("unknown_handler", unknown_handler_node)
    
    # 边
    graph.add_edge(START, "router")
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
    
    # 所有写入/查询节点 → 格式化 → 结束
    for node in ["expense_agent", "loan_agent", "bookkeeping_agent", "query_agent"]:
        graph.add_edge(node, "formatter")
    
    graph.add_edge("unknown_handler", "formatter")
    graph.add_edge("formatter", END)
    
    return graph.compile(checkpointer=get_checkpointer())
```

---

## 六、Write Agent 设计

### 6.1 ExpenseWriteAgent

```python
def expense_write_node(state: AgentState) -> AgentState:
    """报销写入节点"""
    entities = state.get("entities", {})
    user_id = state["metadata"]["user_id"]
    
    # 提取实体
    amount = entities.get("amount")
    category = entities.get("category", "其他")
    date = entities.get("date", today())
    description = entities.get("description", "")
    
    # 权限检查
    permission = get_user_permission(user_id)
    if not permission.get("can_write_expense"):
        return {
            **state,
            "result": "您没有报销权限",
            "status": "rejected"
        }
    
    # 写入 entries
    entry_id = save_expense_record(
        user_id=user_id,
        amount=amount,
        category=category,
        date=date,
        description=description
    )
    
    return {
        **state,
        "result": f"报销记录已保存：{category} - {amount}元",
        "status": "pending",
        "entry_id": entry_id
    }


def save_expense_record(user_id: str, amount: float, category: str, 
                       date: str, description: str) -> str:
    """保存报销记录"""
    import uuid
    import json
    from datetime import datetime
    
    entry_id = f"exp_{uuid.uuid4().hex[:12]}"
    title = f"[报销] {category} - {amount}元"
    
    scene_tags = json.dumps({
        "type": "internal_affairs",
        "sub_type": "expense",
        "environment": "test",
        "test_marker": True,
        "amount": amount,
        "category": category,
        "date": date,
        "description": description,
        "status": "pending"
    })
    
    with connection_scope() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO entries 
                (entry_id, title, input_content, user_id, created_at, scene_tags, space_type)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (entry_id, title, description, user_id, datetime.now(), 
                  scene_tags, "internal_affairs"))
    
    return entry_id
```

### 6.2 LoanWriteAgent

```python
def loan_write_node(state: AgentState) -> AgentState:
    """借款写入节点"""
    entities = state.get("entities", {})
    user_id = state["metadata"]["user_id"]
    
    amount = entities.get("amount")
    reason = entities.get("description", "")
    date = entities.get("date", today())
    
    entry_id = save_loan_record(
        user_id=user_id,
        amount=amount,
        reason=reason,
        date=date
    )
    
    return {
        **state,
        "result": f"借款记录已保存：{amount}元（{reason}）",
        "status": "pending",
        "entry_id": entry_id
    }
```

### 6.3 BookkeepingAgent

```python
def bookkeeping_write_node(state: AgentState) -> AgentState:
    """记账写入节点"""
    entities = state.get("entities", {})
    user_id = state["metadata"]["user_id"]
    
    amount = entities.get("amount")
    is_income = entities.get("is_income", False)  # 收入还是支出
    category = entities.get("category", "其他")
    description = entities.get("description", "")
    
    entry_id = save_bookkeeping_record(
        user_id=user_id,
        amount=amount,
        is_income=is_income,
        category=category,
        description=description
    )
    
    direction = "收入" if is_income else "支出"
    return {
        **state,
        "result": f"记账成功：{direction} {amount}元 ({category})",
        "status": "recorded",
        "entry_id": entry_id
    }
```

---

## 七、Query Agent 设计

### 7.1 核心逻辑

```python
def query_node(state: AgentState) -> AgentState:
    """查询节点：实时计算，不预存统计"""
    entities = state.get("entities", {})
    user_id = state["metadata"]["user_id"]
    
    # 参数解析
    scope = entities.get("query_scope", "personal")  # personal / company
    time_range = entities.get("time_range", "all")   # this_month / last_month / all
    category = entities.get("category")             # 筛选分类
    
    # 实时查询原始记录
    records = query_records(
        user_id=user_id,
        scope=scope,
        time_range=time_range,
        category=category
    )
    
    # 实时计算统计
    stats = calculate_stats(records)
    
    # LLM 生成自然语言回复
    response_text = llm.invoke(
        f"""根据以下统计数据，生成简洁的自然语言回复：
        
        查询范围：{'个人' if scope == 'personal' else '公司'}
        时间范围：{time_range}
        分类筛选：{category or '全部'}
        
        统计结果：
        - 总笔数：{stats['count']}
        - {'总收入' if is_income_query else '总支出'}：{stats['total']}元
        - 分类明细：{stats['by_category']}
        
        最近5条记录：
        {format_recent_records(records[:5])}
        
        请用友好的语气回复。
        """
    )
    
    return {
        **state,
        "result": response_text.content,
        "stats": stats,
        "record_count": len(records)
    }


def calculate_stats(records: list) -> dict:
    """实时计算统计"""
    total = sum(r["amount"] for r in records)
    by_category = {}
    for r in records:
        cat = r.get("category", "其他")
        by_category[cat] = by_category.get(cat, 0) + r["amount"]
    
    return {
        "count": len(records),
        "total": total,
        "by_category": by_category
    }
```

---

## 八、企微集成

### 8.1 消息入口

复用现有 `finance_bot.py`：

```python
@register_handler(
    agent_id=os.getenv("WECOM_INTERNAL_AFFAIRS_AGENT_ID"),
    name="内务助手",
    description="企业内务助手，支持报销、借款、记账、查账",
)
async def handle_internal_affairs(userid: str, content: str, msg_type: str, **kwargs):
    """内务Agent消息处理入口"""
    if msg_type != "text":
        return {"type": "text", "content": "暂只支持文字消息"}
    
    # 创建/获取会话
    thread_id = build_thread_id(userid, "agent/internal_affairs", "default")
    
    # 调用工作流
    agent = create_internal_affairs_graph()
    result = agent.invoke(
        {
            "messages": [("user", content)],
            "metadata": {"user_id": userid}
        },
        {"configurable": {"thread_id": thread_id}}
    )
    
    # 提取回复
    response = result.get("messages", [])[-1].content
    
    # 发送回复
    send_wecom_message(userid, response)
    
    return None
```

### 8.2 环境配置

```python
# 环境变量
WECOM_INTERNAL_AFFAIRS_AGENT_ID = os.getenv("WECOM_INTERNAL_AFFAIRS_AGENT_ID")
WECOM_ENV = os.getenv("WECOM_ENV", "test")  # test / production

# 所有写入自动带测试标记
if WECOM_ENV == "test":
    scene_tags["environment"] = "test"
    scene_tags["test_marker"] = True
```

---

## 九、测试标记机制

### 9.1 统一标记函数

```python
def add_test_marker(scene_tags: dict) -> dict:
    """统一添加测试标记"""
    env = os.getenv("WECOM_ENV", "test")
    
    if env == "test":
        scene_tags["environment"] = "test"
        scene_tags["test_marker"] = True
    else:
        scene_tags["environment"] = "production"
        scene_tags["test_marker"] = False
    
    return scene_tags
```

### 9.2 数据隔离

测试环境数据查询自动过滤：

```python
def query_with_env_filter(user_id: str, extra_where: str = "") -> list:
    """带环境过滤的查询"""
    env = os.getenv("WECOM_ENV", "test")
    
    where_clause = f"user_id = %s AND scene_tags->>'environment' = %s"
    if extra_where:
        where_clause += f" AND {extra_where}"
    
    # 测试环境只能查测试数据
    cur.execute(
        f"SELECT * FROM entries WHERE {where_clause}",
        [user_id, env]
    )
```

---

## 十、文件结构

```
langgraph_mvp/
├── internal_affairs_bot.py      # ⭐ 企微消息入口
├── agents/
│   ├── __init__.py
│   ├── finance.py               # 现有财务Agent
│   ├── internal_affairs.py     # ⭐ 内务Agent主入口
│   ├── intent_router.py        # ⭐ LLM意图路由
│   ├── expense_agent.py         # ⭐ 报销Agent
│   ├── loan_agent.py           # ⭐ 借款Agent
│   ├── bookkeeping_agent.py     # ⭐ 记账Agent
│   └── query_agent.py          # ⭐ 查询Agent
├── config/
│   ├── __init__.py
│   ├── state.py
│   ├── checkpointer.py
│   ├── store.py
│   └── internal_affairs_prompts.py  # ⭐ 意图识别Prompt
└── demo_internal_affairs.py    # ⭐ 演示脚本
```

---

## 十一、实施计划

### Phase 1: 基础能力（3天）

- [ ] 创建 `intent_router.py` - LLM意图识别
- [ ] 创建 `internal_affairs.py` - 主工作流
- [ ] 扩展 `scene_tags` 测试标记支持

### Phase 2: Write Agent（2天）

- [ ] 实现 `expense_agent.py`
- [ ] 实现 `loan_agent.py`
- [ ] 实现 `bookkeeping_agent.py`

### Phase 3: Query Agent（2天）

- [ ] 实现 `query_agent.py`
- [ ] 实现实时统计计算

### Phase 4: 集成测试（2天）

- [ ] 企微消息接入测试
- [ ] 意图识别准确率测试
- [ ] 数据测试标记验证

---

## 附录：LLM 意图识别示例

**输入**：
```
"老板，我昨天请客户吃饭花了500能不能报一下"
```

**LLM 输出**：
```json
{
  "intent": "expense",
  "confidence": 0.92,
  "entities": {
    "amount": 500.0,
    "date": "2026-02-24",
    "category": "餐饮",
    "description": "请客户吃饭"
  },
  "reasoning": "用户提到'报销'，描述了请客户吃饭的场景，金额500元，日期为昨天"
}
```

**输入**：
```
"我本月工资收入了8000"
```

**LLM 输出**：
```json
{
  "intent": "bookkeeping",
  "confidence": 0.98,
  "entities": {
    "amount": 8000.0,
    "category": "工资",
    "is_income": true
  },
  "reasoning": "用户记录收入，提到'工资'和'收入'关键词"
}
```
