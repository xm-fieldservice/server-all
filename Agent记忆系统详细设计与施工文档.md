# Agent记忆系统详细设计与施工文档

**文档版本:** v2.0
**创建时间:** 2026-01-14
**更新时间:** 2026-01-14
**基于文档:** Agent记忆初期可行性评估文档和计划草案
**架构确认:** 短期记忆缓存 → 整理环节 → 统一存储到entries大库

---

## 目录

1. [架构概述](#1-架构概述)
2. [数据表设计](#2-数据表设计)
3. [Python模块设计](#3-python模块设计)
4. [实施计划](#4-实施计划)
5. [代码示例](#5-代码示例)
6. [与AI工厂集成](#6-与ai工厂集成)
7. [测试计划](#7-测试计划)
8. [部署说明](#8-部署说明)

---

## 1. 架构概述

### 1.1 微信笔记入库场景分析

**问题背景：**
- 微信笔记开通后，大量多用户信息会一拥而入
- 一个议题可能被用户啰啰嗦嗦输入好几次、补齐好几次
- 如果每次message都按照原来的逻辑进入大库，会显得很不合适

**解决方案：增加section（会话）环节**
- 一个section的多个message合起来总结后，将总结内容入库
- 同一个section总结好几次，分别入库，比每次message入库要好
- 原始message作为缓存，整理好以后进入大库

### 1.2 核心设计原则

基于可行性评估文档的分析，结合微信笔记入库场景的讨论，本设计遵循以下原则：

1. **一个物理底座，多层逻辑存储**
   - 物理层：统一的PostgreSQL + pgvector实例
   - 逻辑层：清晰划分为短期记忆缓存、整理环节、大库存储三层

2. **短期记忆作为缓存层**
   - 使用独立的`chat_sessions`和`chat_messages`表
   - 存储原始输入、啰嗦、不完整的message
   - 不直接进大库，避免污染世界知识底座

3. **整理环节（Section）**
   - 对短期记忆进行整理、去重、合并、结构化
   - 形成高质量的笔记内容
   - 通过MCP工具触发，或自动触发（每10条message或每30分钟）

4. **统一存储到entries大库**
    - 所有整理后的内容进入entries表
    - 带section_id、section_version、scene_tags等元数据
    - 支持版本管理，同一section多次总结形成版本链

5. **原始message分层保留**
   - 热数据（近30天）在主库，便于语义挖掘和知识升级
   - 冷数据归档到低成本存储，降低存储成本

### 1.3 架构图

```
┌─────────────────────────────────────────────────────────────┐
│                   用户输入层                        │
│  微信笔记、多用户随意输入、啰嗦、不完整                     │
└─────────────────────────────────────────────────────────────┘
                           │
                           ↓
┌─────────────────────────────────────────────────────────────┐
│            L1: 短期记忆/会话层              │
│  chat_sessions + chat_messages（缓存层）                    │
│  存储原始输入，作为整理的素材                               │
│  不直接进大库                                              │
└─────────────────────────────────────────────────────────────┘
                           │
                           ↓
┌─────────────────────────────────────────────────────────────┐
│              L2: 整理环节（Section）                        │
│  对短期记忆进行：整理、去重、合并、结构化                    │
│  形成高质量的笔记内容                                       │
│  触发方式：MCP工具 + 自动触发（每10条message或每30分钟）        │
└─────────────────────────────────────────────────────────────┘
                           │
                           ↓
┌─────────────────────────────────────────────────────────────┐
│  L3: 大库（entries + entry_embeddings）          │
│  ┌────────────────────────────────────────────────┐     │
│  │  所有整理后的内容进入entries表                 │     │
│  │  - section_id: 标识属于哪个会话/议题           │     │
│  │  - section_version: 该section的版本号          │     │
│  │  - is_latest: 是否为最新版本                   │     │
│  │  - scene_tags: 场景标签（JSONB）               │     │
│  │  - agent_id: 所属助手                          │     │
│  └────────────────────────────────────────────────┘     │
│  向量检索时按section_id聚拢，避免重复返回同一议题的多版本   │
└─────────────────────────────────────────────────────────────┘
                           │
                           ↓
┌─────────────────────────────────────────────────────────────┐
│              L4: Q&A缓存层（可选）                         │
│  qa_query_index                                           │
│  快速响应重复问题                                          │
└─────────────────────────────────────────────────────────────┘
```

### 1.4 数据流程

```
用户输入（微信笔记）
    ↓
chat_sessions + chat_messages（短期记忆缓存）
    ↓
Agent整理（LLM + 规则）
    ↓
写入entries表（带section_id、section_version、scene_tags等元数据）
    ↓
entry_embeddings（向量索引）
    ↓
RAG检索时按section_id聚拢，只返回最新版本（is_latest=TRUE）
```

### 1.5 记忆层次关系

| 层级 | 存储方式 | 数据表 | 生命周期 | 作用 |
|------|----------|--------|----------|------|
| **L1: 短期记忆** | 独立表 | `chat_sessions`<br>`chat_messages` | 热数据30天，冷数据归档 | 存储原始输入，作为整理的素材 |
| **L2: 整理环节** | Agent处理 | - | 实时 | 整理、去重、合并、结构化 |
| **L3: 大库存储** | 现有表扩展 | `entries`<br>`entry_embeddings` | 永久保留 | 所有笔记、任务、议题、记忆等 |
| **L4: Q&A缓存** | 独立表 | `qa_query_index` | 按策略清理 | 快速响应重复问题 |

### 1.6 服务职责划分

| 服务 | 职责 | 主要接口 |
|------|------|----------|
| **SessionService** | 管理会话生命周期和短期记忆缓存 | `create_session()`, `add_message()`, `get_recent_messages()`, `get_session_history()` |
| **SectionService** | 管理section的整理和入库 | `summarize_section()`, `get_section_history()`, `merge_sections()` |
| **EntryService** | 管理entries大库的存储与检索 | `save_entry()`, `retrieve_entries()`, `update_entry()`, `delete_entry()` |
| **QACacheService** | 管理Q&A缓存 | `cache_qa()`, `query_qa()`, `hit_qa()`, `cleanup_old_qa()` |

**注意：不再使用独立的`user_longterm_memory`表，所有记忆统一存储到`entries`大库，通过`scene_tags`和`space_type`字段区分记忆类型。**

### 1.7 记忆与Agent的关系设计

#### 1.7.1 设计目标

记忆机制应该支持**灵活的Agent绑定策略**，既支持记忆与特定Agent绑定，也支持记忆与Agent解耦，实现"同一套记忆，多个Agent共享"的场景。

#### 1.7.2 两种绑定模式

**模式1：共享记忆（推荐用于通用场景）**

```
记忆数据 ←(不绑定agent_id)→ 多个Agent共享
```

- 记忆不绑定特定agent_id
- 通过scene_tags和space_type分类和组织
- 不同Agent可以访问同一套记忆
- 适合：通用知识库、用户偏好、项目记录等

**模式2：专属记忆（推荐用于隔离场景）**

```
记忆数据 ←(绑定agent_id)→ 特定Agent专属
```

- 记忆绑定特定agent_id
- 每个Agent有独立的记忆空间
- 记忆互不干扰，数据隔离
- 适合：个人助手、多角色对话、敏感信息等

#### 1.7.3 混合模式支持

系统支持混合模式，可以同时使用共享记忆和专属记忆：

```python
# 共享记忆 + 专属记忆
memories = entry_service.retrieve_entries(
    query="用户偏好",
    agent_id="agent_001",  # 专属记忆
    include_shared=True,      # 同时包含共享记忆
    scene_tags={"execution": ["笔记"]}
)
```

#### 1.7.4 Agent加载记忆的灵活性

Agent可以灵活配置记忆加载策略：

```python
# 场景1：同一套记忆，更换不同Agent
memory_config = {
    "space_type": "note",
    "scene_tags": {"execution": ["笔记"]}
}

# Agent1：专业项目助手
agent1 = Agent(
    prompt_template="你是一个专业的项目助手...",
    model="gpt-4",
    memory_config=memory_config
)

# Agent2：友好的聊天助手
agent2 = Agent(
    prompt_template="你是一个友好的聊天助手...",
    model="gpt-3.5",
    memory_config=memory_config
)

# 两个Agent访问同一套记忆

# 场景2：每个Agent有专属记忆
agent1 = Agent(
    prompt_template="你是张三的个人助手...",
    model="gpt-4",
    memory_config={"agent_id": "agent_zhangsan"}
)

agent2 = Agent(
    prompt_template="你是李四的个人助手...",
    model="gpt-4",
    memory_config={"agent_id": "agent_lisi"}
)

# 两个Agent有独立的记忆空间
```

#### 1.7.5 agent_id字段的作用

在混合模式中，`agent_id`字段的作用：

| 场景 | agent_id值 | 说明 |
|------|-----------|------|
| 共享记忆 | NULL | 记忆不属于任何特定Agent，所有Agent都可以访问 |
| 专属记忆 | "agent_001" | 记忆只属于agent_001，其他Agent无法访问 |
| 追踪来源 | "agent_001" | 记录是哪个Agent创建的，但不限制访问（可选） |

#### 1.7.6 第三种模式：结构绑定，内容可替换

**设计思路：**

```
Agent（包含记忆机制）
  ├─ 提示词（Prompt）
  ├─ 模型（Model）
  └─ 记忆体（Memory Body）
       ├─ 可清零
       └─ 可加载新记忆
```

**核心特点：**
1. Agent和记忆机制在代码结构上是一体的
2. 记忆体可以清零（清空所有记忆）
3. 可以加载不同的记忆体
4. 效果上与共享模式相同（更换记忆 = 更换Agent）

**具体实现：**

```python
class Agent:
    def __init__(self,
                 prompt_template: str,
                 model: str,
                 agent_id: str):
        """
        Agent初始化，记忆机制与Agent结构绑定
        
        Args:
            prompt_template: 提示词模板
            model: 使用的模型
            agent_id: Agent ID，用于标识记忆归属
        """
        self.prompt_template = prompt_template
        self.model = model
        self.agent_id = agent_id
        self._memory_loaded = False
    
    def load_memory(self, memory_source: str):
        """
        加载记忆体
        
        Args:
            memory_source: 记忆来源
                - "database": 从数据库加载
                - "file": 从文件加载
                - "preset": 加载预设记忆
        """
        if memory_source == "database":
            self._load_from_database()
        elif memory_source == "file":
            self._load_from_file()
        elif memory_source == "preset":
            self._load_preset()
        
        self._memory_loaded = True
    
    def clear_memory(self):
        """清零记忆体"""
        # 删除该Agent的所有记忆
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM entries WHERE agent_id = %s", (self.agent_id,))
                cur.execute("DELETE FROM chat_sections WHERE agent_id = %s", (self.agent_id,))
                cur.execute("DELETE FROM qa_query_index WHERE assistant_id = %s", (self.agent_id,))
        
        self._memory_loaded = False
    
    def switch_memory(self, new_memory_source: str):
        """切换记忆体：先清零当前记忆，再加载新记忆"""
        self.clear_memory()
        self.load_memory(new_memory_source)
```

**使用示例：**

```python
# 创建Agent
agent = Agent(
    prompt_template="你是一个专业的项目助手...",
    model="gpt-4",
    agent_id="agent_project_001"
)

# 场景1：加载项目A的记忆
agent.load_memory("preset_project_a")
response = agent.query("项目A的进展如何？")

# 场景2：切换到项目B的记忆
agent.switch_memory("preset_project_b")
response = agent.query("项目B的进展如何？")

# 场景3：清零记忆，重新加载
agent.clear_memory()
agent.load_memory("database")
```

#### 1.7.7 三种模式对比

| 特性 | 共享记忆 | 专属记忆 | 结构绑定 |
|-------|---------|---------|---------|
| **绑定关系** | 不绑定 | 强绑定 | 结构绑定 |
| **共享能力** | 多Agent共享 | 完全隔离 | 内容可替换 |
| **复杂度** | 中 | 低 | 低 |
| **灵活性** | 高 | 低 | 中 |
| **性能** | 中 | 高 | 高 |
| **隔离性** | 低 | 高 | 高 |
| **适用场景** | 通用知识库、用户偏好 | 个人助手、多角色 | 单Agent、记忆切换 |

#### 1.7.8 记忆体实现方案

##### 方案1：数据库层面的记忆体（推荐）

**核心思路：** 通过`agent_id`区分不同的记忆体

```python
class Agent:
    def __init__(self, prompt_template: str, model: str, agent_id: str):
        self.prompt_template = prompt_template
        self.model = model
        self.agent_id = agent_id
    
    def load_memory(self, memory_body_id: str):
        """
        加载记忆体
        
        Args:
            memory_body_id: 记忆体ID，例如 "memory_project_a"
        """
        # 从预设数据加载新记忆体
        self._load_preset_memory(memory_body_id)
    
    def clear_memory(self):
        """清零记忆体"""
        # 删除该Agent的所有记忆
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM entries WHERE agent_id = %s", (self.agent_id,))
                cur.execute("DELETE FROM chat_sections WHERE agent_id = %s", (self.agent_id,))
                cur.execute("DELETE FROM qa_query_index WHERE assistant_id = %s", (self.agent_id,))
    
    def switch_memory(self, new_memory_body_id: str):
        """切换记忆体"""
        self.clear_memory()
        self._load_preset_memory(new_memory_body_id)
```

##### 方案2：MCP工具实现记忆体管理（推荐）

**是的，可以用MCP实现！** MCP工具非常适合管理记忆体：

```python
# MCP工具：加载记忆体
@mcp_tool
def load_memory_body(
    agent_id: str,
    memory_body_id: str
) -> Dict[str, Any]:
    """
    加载指定的记忆体到Agent
    
    Args:
        agent_id: Agent ID
        memory_body_id: 记忆体ID
    
    Returns:
        加载结果
    """
    from ai_factory.domain.memory_manager import MemoryManager
    
    manager = MemoryManager()
    result = manager.load_memory_body(agent_id, memory_body_id)
    
    return {
        "agent_id": agent_id,
        "memory_body_id": memory_body_id,
        "entries_count": result["entries_count"],
        "sections_count": result["sections_count"]
    }

# MCP工具：清零记忆体
@mcp_tool
def clear_memory_body(
    agent_id: str
) -> Dict[str, Any]:
    """
    清零Agent的记忆体
    
    Args:
        agent_id: Agent ID
    
    Returns:
        清零结果
    """
    from ai_factory.domain.memory_manager import MemoryManager
    
    manager = MemoryManager()
    result = manager.clear_memory_body(agent_id)
    
    return {
        "agent_id": agent_id,
        "deleted_entries": result["entries_count"],
        "deleted_sections": result["sections_count"],
        "deleted_qa": result["qa_count"]
    }

# MCP工具：切换记忆体
@mcp_tool
def switch_memory_body(
    agent_id: str,
    new_memory_body_id: str
) -> Dict[str, Any]:
    """
    切换Agent的记忆体
    
    Args:
        agent_id: Agent ID
        new_memory_body_id: 新的记忆体ID
    
    Returns:
        切换结果
    """
    from ai_factory.domain.memory_manager import MemoryManager
    
    manager = MemoryManager()
    result = manager.switch_memory_body(agent_id, new_memory_body_id)
    
    return {
        "agent_id": agent_id,
        "old_memory_body": result["old_memory_body"],
        "new_memory_body": new_memory_body_id,
        "entries_count": result["entries_count"]
    }

# MCP工具：列出可用的记忆体
@mcp_tool
def list_memory_bodies(
    agent_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    列出可用的记忆体
    
    Args:
        agent_id: 可选，过滤特定Agent的记忆体
    
    Returns:
        记忆体列表
    """
    from ai_factory.domain.memory_manager import MemoryManager
    
    manager = MemoryManager()
    bodies = manager.list_memory_bodies(agent_id)
    
    return {
        "agent_id": agent_id,
        "memory_bodies": bodies
    }

# MCP工具：导出记忆体到文件
@mcp_tool
def export_memory_to_file(
    agent_id: str,
    output_file: str
) -> Dict[str, Any]:
    """
    导出记忆体到文件
    
    Args:
        agent_id: Agent ID
        output_file: 输出文件路径
    
    Returns:
        导出结果
    """
    from ai_factory.domain.memory_manager import MemoryManager
    
    manager = MemoryManager()
    return manager.export_memory_body(agent_id, output_file)

# MCP工具：从文件导入记忆体
@mcp_tool
def import_memory_from_file(
    agent_id: str,
    input_file: str,
    clear_existing: bool = True
) -> Dict[str, Any]:
    """
    从文件导入记忆体
    
    Args:
        agent_id: Agent ID
        input_file: 输入文件路径
        clear_existing: 是否清空现有记忆
    
    Returns:
        导入结果
    """
    from ai_factory.domain.memory_manager import MemoryManager
    
    manager = MemoryManager()
    return manager.import_memory_body(agent_id, input_file, clear_existing)
```

**Agent通过MCP工具调用：**

```python
# Agent的提示词中包含MCP工具调用指令
PROMPT_TEMPLATE = """
你是一个智能助手。你可以使用以下工具管理记忆：

1. load_memory_body(agent_id, memory_body_id) - 加载记忆体
2. clear_memory_body(agent_id) - 清零记忆体
3. switch_memory_body(agent_id, new_memory_body_id) - 切换记忆体
4. list_memory_bodies(agent_id) - 列出可用记忆体
5. export_memory_to_file(agent_id, output_file) - 导出记忆体
6. import_memory_from_file(agent_id, input_file) - 导入记忆体

当用户要求切换到不同的记忆体时，使用switch_memory_body工具。
"""

# 用户对话示例
用户：切换到项目A的记忆体
Agent：[调用switch_memory_body("agent_001", "memory_project_a")]
     已切换到项目A的记忆体，加载了15条记录。

用户：显示当前记忆体
Agent：[调用list_memory_bodies("agent_001")]
     当前可用的记忆体：
     - memory_project_a (15条记录)
     - memory_project_b (23条记录)
     - memory_default (8条记录)

用户：导出当前记忆体到文件
Agent：[调用export_memory_to_file("agent_001", "/tmp/memory_project_a.json")]
     已导出记忆体到 /tmp/memory_project_a.json，包含15条记录。
```

##### 方案3：文件层面的记忆体（辅助方案）

**用于备份和导入导出：**

```python
class MemoryManager:
    def export_memory_body(
        self,
        agent_id: str,
        output_file: str
    ) -> Dict[str, Any]:
        """
        导出记忆体到文件
        
        Args:
            agent_id: Agent ID
            output_file: 输出文件路径
        
        Returns:
            导出结果
        """
        # 从数据库查询该Agent的所有记忆
        entries = self._get_agent_entries(agent_id)
        
        # 写入JSON文件
        import json
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump({
                "agent_id": agent_id,
                "exported_at": datetime.now().isoformat(),
                "entries": entries
            }, f, ensure_ascii=False, indent=2)
        
        return {
            "agent_id": agent_id,
            "output_file": output_file,
            "entries_count": len(entries)
        }
    
    def import_memory_body(
        self,
        agent_id: str,
        input_file: str,
        clear_existing: bool = True
    ) -> Dict[str, Any]:
        """
        从文件导入记忆体
        
        Args:
            agent_id: Agent ID
            input_file: 输入文件路径
            clear_existing: 是否清空现有记忆
        
        Returns:
            导入结果
        """
        # 清空现有记忆
        if clear_existing:
            self.clear_memory_body(agent_id)
        
        # 从JSON文件读取
        import json
        with open(input_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 导入到数据库
        imported_count = 0
        for entry in data["entries"]:
            self._save_entry(agent_id, entry)
            imported_count += 1
        
        return {
            "agent_id": agent_id,
            "input_file": input_file,
            "imported_count": imported_count
        }
```

##### 推荐的实现架构

**结合数据库 + MCP工具：**

```
┌─────────────────────────────────────────────────────────────┐
│                   MCP工具层                              │
│  - load_memory_body()                                   │
│  - clear_memory_body()                                  │
│  - switch_memory_body()                                 │
│  - list_memory_bodies()                                 │
│  - export_memory_to_file()                               │
│  - import_memory_from_file()                             │
└─────────────────────────────────────────────────────────────┘
                            │
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                   MemoryManager                          │
│  - load_memory_body()                                   │
│  - clear_memory_body()                                  │
│  - switch_memory_body()                                 │
│  - export_memory_body()                                 │
│  - import_memory_body()                                 │
└─────────────────────────────────────────────────────────────┘
                            │
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                   数据库层                               │
│  - entries表（通过agent_id区分记忆体）                    │
│  - chat_sections表                                      │
│  - qa_query_index表                                    │
└─────────────────────────────────────────────────────────────┘
```

#### 1.7.9 推荐方案

根据需求分析，**推荐采用结构绑定模式 + MCP工具**，原因如下：

1. **符合需求**：结构上是一体的，可以清零记忆，加载新记忆
2. **实现简单**：不需要复杂的权限和访问控制
3. **性能好**：记忆加载后可以缓存，查询效率高
4. **灵活性高**：可以快速切换不同的记忆体
5. **隔离性好**：不同记忆体完全隔离，不会产生冲突
6. **MCP支持**：Agent可以通过MCP工具自主管理记忆体
7. **文件支持**：支持导入导出，便于备份和迁移

#### 1.7.10 设计原则

1. **记忆独立于Agent实现**：记忆存储不依赖Agent的提示词、模型等实现细节
2. **灵活的访问控制**：支持共享、专属、结构绑定三种模式
3. **向后兼容**：保留agent_id字段，支持现有绑定模式
4. **可扩展性**：未来可以添加更细粒度的权限控制

---

### 1.8 上下文策略（静态 vs 动态）

**目标：** 明确 agent 配置中的静态上下文与每轮调用的动态上下文边界与策略，降低 token 压力并提升一致性。

- **静态上下文（Static Context） = agent 配置/context**
  - 放置：persona/语气、guardrails/合规边界、默认过滤条件（如 `project_code`、`scene_tags`、`time_window`）、工具使用原则与调用约定。
  - 特性：跨会话/跨轮稳定，可被缓存；每轮必达但体量应小、稠密。

- **动态上下文（Dynamic Context） = 每轮由 MemoryService/SessionService/RAG 组装**
  - 不写入 `agent.context`，仅作为本轮消息流的一部分注入。
  - 来源与策略：
    - 短期记忆：自 `SessionService` 取最近 N 条消息（含 user/assistant/system/tool），支持 `pinned`、`importance`，按“近→远”滑窗。
    - RAG 检索：从 `entries/entry_embeddings` 取 Top-K，按 `section_id` 聚拢，仅保留 `is_latest=TRUE`；必要时以“section 摘要”替代全文。
    - 长期偏好/规则：从 `entries` 依据 `scene_tags/space_type` 命中摘要（例如偏好、规则、目标）。
    - 工具/函数输出：仅保留关键结果并做精简摘要，避免重复和超限。

- **Token 预算与溢出处理（建议缺省，可配置）**
  - `max_tokens_for_context`：默认 2000。
  - 角色/权重顺序：`pinned > system > user > assistant > tool`。
  - 超限处理：
    1) 截断远端消息；
    2) 对长消息/检索片段做多级摘要；
    3) 降低 RAG Top-K 或只保留最新 `section` 摘要。
  - 去重与收敛：对同一 `section_id` 多版本仅保留 `is_latest`；对同义/重复片段合并。

- **接口约定（由 MemoryService 提供）**
  - 函数：`get_context_for_turn(session_id, max_tokens, roles, include_tools, time_window, include_pinned, rag_top_k, rag_filters)`
  - 返回：
    - `system_prompt`：静态提示 + 本轮策略化说明（精简）。
    - `history_messages`：滑窗后的对话片段（含排序与权重）。
    - `rag_snippets`：聚拢后的外部知识摘要（含 `section_id` 元数据）。
    - `metadata`：`token_budget`、`applied_rules`、`truncation/summary_notes`。

- **元数据字段与过滤**
  - `chat_messages.metadata_json`：`is_pinned`、`importance_score`、`topic_key`、`token_count`、`tool_name`、`section_id_hint`。
  - `entries.scene_tags/space_type`：用于筛选长期记忆与检索范围。

- **例外**
  - 强约束/安全边界/合规等“不可丢失”的规则应放入静态 context 或系统提示，动态层不得覆盖或省略。

- **与现有设计对齐**
  - 动态上下文走 RAG/SessionService 构建链路，不固化进 `agent.context`。
  - 检索阶段按 `section_id` 聚拢并以 `is_latest` 过滤，减少冲突与重复。

---
---

## 2. 数据表设计

### 2.1 entries表扩展（核心大库）

**现有entries表结构：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `entry_id` | text | 主键 |
| `title` | text | 标题 |
| `summary_ai` | text | AI摘要 |
| `content` | text | 内容 |
| `created_at` | timestamp with time zone | 创建时间 |
| `project_code` | text | 项目代码 |
| `user_id` | text | 用户ID |
| `scene_tags` | jsonb | 场景标签（现有分类体系） |
| `space_type` | text | 空间类型 |
| `parent_entry_id` | text | 父条目ID |
| `memo` | jsonb | 备注 |
| `extra_meta` | jsonb | 额外元数据 |

**扩展字段：**
```sql
-- 为entries表添加记忆相关字段
ALTER TABLE entries ADD COLUMN section_id VARCHAR(64);
ALTER TABLE entries ADD COLUMN section_version INTEGER DEFAULT 1;
ALTER TABLE entries ADD COLUMN is_latest BOOLEAN DEFAULT TRUE;
ALTER TABLE entries ADD COLUMN agent_id VARCHAR(64);
ALTER TABLE entries ADD COLUMN source_session_id VARCHAR(64);

-- 添加索引
CREATE INDEX idx_entries_section_id ON entries(section_id);
CREATE INDEX idx_entries_section_version ON entries(section_id, section_version);
CREATE INDEX idx_entries_is_latest ON entries(is_latest);
CREATE INDEX idx_entries_agent_id ON entries(agent_id);
CREATE INDEX idx_entries_source_session_id ON entries(source_session_id);
CREATE INDEX idx_entries_scene_tags ON entries USING GIN (scene_tags);
```

**新增字段说明：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `section_id` | VARCHAR(64) | 所属section/会话ID，用于聚拢同一议题的多个版本 |
| `section_version` | INTEGER | 该section的版本号，从1开始递增 |
| `is_latest` | BOOLEAN | 是否为该section的最新版本，RAG检索时过滤 |
| `agent_id` | VARCHAR(64) | 所属助手ID，标识该条目属于哪个Agent的记忆 |
| `source_session_id` | VARCHAR(64) | 来源会话ID，用于追溯 |

**现有scene_tags分类体系：**

| 键 | 值示例 | 说明 |
|------|----------|------|
| `department` | 总部、软件、软件部、现场、知识库、内务 | 部门分类 |
| `execution` | 项目、任务、议题、笔记、其他 | 执行类型 |
| `flags` | favorite | 标记（如收藏） |
| `planning` | 项目、计划、战略、目标、其他 | 规划类型 |
| `rating` | 良好 | 评分 |
| `status` | 待开始、进行中 | 状态 |
| `work` | in_work | 工作状态 |

**现有space_type分类：**

| 值 | 说明 | 数量 |
|------|------|------|
| `note` | 笔记 | 557 |
| `strategy` | 战略 | 2 |
| `goal` | 目标 | 1 |
| `plan` | 计划 | 1 |

**示例数据：**
```json
// 使用现有scene_tags和space_type
{
  "scene_tags": {
    "department": ["软件"],
    "execution": ["项目"],
    "status": ["进行中"],
    "planning": ["项目"]
  },
  "space_type": "note",
  "section_id": "sec_abc123",
  "section_version": 1,
  "is_latest": true,
  "agent_id": "agent_001"
}

// 战略类条目
{
  "scene_tags": {
    "department": ["总部"],
    "execution": ["战略"],
    "planning": ["战略"]
  },
  "space_type": "strategy",
  "section_id": "sec_def456",
  "section_version": 1,
  "is_latest": true,
  "agent_id": "agent_001"
}
```

**查询示例：**
```sql
-- 查询某section的最新版本
SELECT * FROM entries WHERE section_id = 'sec_abc123' AND is_latest = TRUE;

-- 查询特定space_type的条目
SELECT * FROM entries WHERE space_type = 'note';

-- 使用scene_tags查询（JSONB查询）
SELECT * FROM entries WHERE scene_tags @> '{"department": ["软件"]}';
SELECT * FROM entries WHERE scene_tags ? 'department';

-- 查询特定agent的条目
SELECT * FROM entries WHERE agent_id = 'agent_001';

-- 组合查询
SELECT * FROM entries
WHERE section_id = 'sec_abc123'
  AND is_latest = TRUE
  AND agent_id = 'agent_001';
```

### 2.2 chat_sessions 表（会话表）

```sql
CREATE TABLE IF NOT EXISTS chat_sessions (
    -- 主键
    session_id VARCHAR(64) PRIMARY KEY,
    
    -- 用户和助手关联
    user_id VARCHAR(64) NOT NULL,
    assistant_id VARCHAR(64) NOT NULL,
    
    -- 会话元数据
    title VARCHAR(256),
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    metadata_json JSONB,
    
    -- 时间戳
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    -- 关联引用
    related_entry_id VARCHAR(64),
    
    -- 索引
    INDEX idx_user_id (user_id),
    INDEX idx_assistant_id (assistant_id),
    INDEX idx_status (status),
    INDEX idx_created_at (created_at)
);

COMMENT ON TABLE chat_sessions IS '会话表，存储用户与助手的对话会话';
```

**字段说明：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `session_id` | VARCHAR(64) | 会话唯一标识，建议使用UUID |
| `user_id` | VARCHAR(64) | 用户ID，用于多用户隔离 |
| `assistant_id` | VARCHAR(64) | 助手ID，用于多助手隔离 |
| `title` | VARCHAR(256) | 会话标题，可选 |
| `status` | VARCHAR(32) | 会话状态：active/archived/deleted |
| `metadata_json` | JSONB | 会话元数据（如当前任务、优先级等） |
| `created_at` | TIMESTAMP | 创建时间 |
| `updated_at` | TIMESTAMP | 最后更新时间 |
| `related_entry_id` | VARCHAR(64) | 关联的entries节点ID（可选） |

### 2.3 qa_query_index 表（Q&A缓存表）

```sql
CREATE TABLE IF NOT EXISTS chat_messages (
    -- 主键
    message_id VARCHAR(64) PRIMARY KEY,
    
    -- 会话关联
    session_id VARCHAR(64) NOT NULL,
    
    -- 消息角色和类型
    role VARCHAR(16) NOT NULL,  -- 'user' | 'assistant' | 'system' | 'tool'
    msg_type VARCHAR(32),            -- 'question' | 'statement' | 'answer' | 'other'
    
    -- 消息内容
    content TEXT NOT NULL,
    
    -- 元数据
    metadata_json JSONB,
    
    -- 时间戳
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    -- 索引
    INDEX idx_session_id (session_id),
    INDEX idx_created_at (created_at),
    INDEX idx_role (role)
);

COMMENT ON TABLE chat_messages IS '消息表，存储会话中的所有消息';
```

**字段说明：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `message_id` | VARCHAR(64) | 消息唯一标识，建议使用UUID |
| `session_id` | VARCHAR(64) | 所属会话ID |
| `role` | VARCHAR(16) | 消息角色：user/assistant/system/tool |
| `msg_type` | VARCHAR(32) | 消息类型：question/statement/answer/other |
| `content` | TEXT | 消息内容 |
| `metadata_json` | JSONB | 消息元数据（如是否被标记为记忆候选） |
| `created_at` | TIMESTAMP | 创建时间 |

### 2.3 chat_messages 表（消息表）

```sql
CREATE TABLE IF NOT EXISTS qa_query_index (
    -- 主键
    qa_id VARCHAR(64) PRIMARY KEY,
    
    -- 用户和助手关联
    user_id VARCHAR(64) NOT NULL,
    assistant_id VARCHAR(64),
    tenant_id VARCHAR(64),
    
    -- 问题信息
    normalized_question TEXT NOT NULL,
    question_embedding vector(1536),
    
    -- 答案关联
    answer_entry_id VARCHAR(64) NOT NULL,
    answer_type VARCHAR(32),  -- 'cached' | 'generated'
    
    -- 命中统计
    hit_count INTEGER NOT NULL DEFAULT 0,
    last_hit_at TIMESTAMP WITH TIME ZONE,
    
    -- 状态和质量
    status VARCHAR(32) NOT NULL DEFAULT 'active',  -- 'active' | 'deprecated' | 'pending_review'
    quality_score DECIMAL(3,2),
    
    -- 元数据
    tags VARCHAR(256)[],
    metadata_json JSONB,
    
    -- 时间戳
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    -- 索引
    INDEX idx_user_id (user_id),
    INDEX idx_assistant_id (assistant_id),
    INDEX idx_tenant_id (tenant_id),
    INDEX idx_status (status),
    INDEX idx_hit_count (hit_count),
    INDEX idx_last_hit_at (last_hit_at),
    INDEX idx_question_embedding USING ivfflat (question_embedding vector_cosine_ops)
);

COMMENT ON TABLE qa_query_index IS 'Q&A缓存表，用于快速响应重复问题';
```

**字段说明：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `qa_id` | VARCHAR(64) | Q&A对唯一标识 |
| `user_id` | VARCHAR(64) | 用户ID |
| `assistant_id` | VARCHAR(64) | 助手ID |
| `tenant_id` | VARCHAR(64) | 租户/组织ID |
| `normalized_question` | TEXT | 规范化问题文本 |
| `question_embedding` | vector(1536) | 问题向量嵌入 |
| `answer_entry_id` | VARCHAR(64) | 答案对应的entries节点ID |
| `answer_type` | VARCHAR(32) | 答案类型 |
| `hit_count` | INTEGER | 命中次数 |
| `last_hit_at` | TIMESTAMP | 最后命中时间 |
| `status` | VARCHAR(32) | 状态：active/deprecated/pending_review |
| `quality_score` | DECIMAL(3,2) | 质量分数 |

---

## 3. Python模块设计

### 3.1 目录结构

```
ai-factory/
├── domain/
│   ├── __init__.py
│   ├── session_service.py      # 会话服务
│   ├── section_service.py     # Section整理服务（新增）
│   ├── entry_service.py       # Entries大库服务（新增）
│   └── qa_cache_service.py     # Q&A缓存服务
├── db/
│   └── pgvector_client.py   # 数据库客户端（已存在）
├── rag/
│   ├── pgvector_index.py      # 向量索引（已存在）
│   └── rag_pipeline.py       # RAG管道（已存在）
└── sql/
    └── create_memory_tables.sql
```

### 3.2 SessionService 设计

```python
"""
会话服务（SessionService）
管理用户与助手的对话会话和短期记忆
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from dataclasses import dataclass
from enum import Enum
import json


class SessionStatus(str, Enum):
    """会话状态"""
    ACTIVE = "active"
    ARCHIVED = "archived"
    DELETED = "deleted"


class MessageRole(str, Enum):
    """消息角色"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class MessageType(str, Enum):
    """消息类型"""
    QUESTION = "question"
    STATEMENT = "statement"
    ANSWER = "answer"
    OTHER = "other"


@dataclass
class SessionInfo:
    """会话信息"""
    session_id: str
    user_id: str
    assistant_id: str
    title: Optional[str] = None
    status: SessionStatus = SessionStatus.ACTIVE
    metadata: Dict[str, Any] = None
    created_at: datetime = None
    updated_at: datetime = None
    related_entry_id: Optional[str] = None


@dataclass
class MessageInfo:
    """消息信息"""
    message_id: str
    session_id: str
    role: MessageRole
    msg_type: Optional[MessageType] = None
    content: str
    metadata: Dict[str, Any] = None
    created_at: datetime = None


class SessionService:
    """会话服务"""
    
    def __init__(self):
        self._conn = None
    
    def _get_connection(self):
        from ai_factory.db.pgvector_client import connection_scope
        return connection_scope()
    
    def create_session(
        self,
        user_id: str,
        assistant_id: str,
        title: Optional[str] = None,
        related_entry_id: Optional[str] = None
    ) -> str:
        """创建新会话"""
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                import uuid
                session_id = f"session_{uuid.uuid4().hex}"
                
                cur.execute("""
                    INSERT INTO chat_sessions
                    (session_id, user_id, assistant_id, title, related_entry_id, status, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    RETURNING session_id
                """, (session_id, user_id, assistant_id, title, related_entry_id, SessionStatus.ACTIVE.value))
                
                return session_id
    
    def add_message(
        self,
        session_id: str,
        role: MessageRole,
        content: str,
        msg_type: Optional[MessageType] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """添加消息到会话"""
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                import uuid
                message_id = f"msg_{uuid.uuid4().hex}"
                msg_type_val = msg_type.value if msg_type else 'other'
                
                cur.execute("""
                    INSERT INTO chat_messages
                    (message_id, session_id, role, msg_type, content, metadata_json, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    RETURNING message_id
                """, (message_id, session_id, role.value, msg_type_val, content, 
                       json.dumps(metadata) if metadata else None))
                
                return message_id
    
    def get_session_info(self, session_id: str) -> Optional[SessionInfo]:
        """获取会话信息"""
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT session_id, user_id, assistant_id, title, status, 
                           metadata_json, created_at, updated_at, related_entry_id
                    FROM chat_sessions
                    WHERE session_id = %s
                """, (session_id,))
                
                row = cur.fetchone()
                if row:
                    return SessionInfo(
                        session_id=row[0],
                        user_id=row[1],
                        assistant_id=row[2],
                        title=row[3],
                        status=SessionStatus(row[4]),
                        metadata=json.loads(row[5]) if row[5] else None,
                        created_at=row[6],
                        updated_at=row[7],
                        related_entry_id=row[8]
                    )
        return None
    
    def get_recent_messages(
        self, 
        session_id: str, 
        limit: int = 10
    ) -> List[MessageInfo]:
        """获取最近的N条消息"""
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT message_id, session_id, role, msg_type, content, metadata_json, created_at
                    FROM chat_messages
                    WHERE session_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                """, (session_id, limit))
                
                rows = cur.fetchall()
                return [
                    MessageInfo(
                        message_id=row[0],
                        session_id=row[1],
                        role=MessageRole(row[2]),
                        msg_type=MessageType(row[3]) if row[3] else None,
                        content=row[4],
                        metadata=json.loads(row[5]) if row[5] else None,
                        created_at=row[6]
                    ) for row in rows
                ]
    
    def get_session_history(
        self, 
        user_id: str, 
        assistant_id: Optional[str] = None,
        limit: int = 20
    ) -> List[SessionInfo]:
        """获取会话历史"""
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                if assistant_id:
                    cur.execute("""
                        SELECT session_id, user_id, assistant_id, title, status, 
                               metadata_json, created_at, updated_at, related_entry_id
                        FROM chat_sessions
                        WHERE user_id = %s AND assistant_id = %s
                        ORDER BY created_at DESC
                        LIMIT %s
                    """, (user_id, assistant_id, limit))
                else:
                    cur.execute("""
                        SELECT session_id, user_id, assistant_id, title, status, 
                               metadata_json, created_at, updated_at, related_entry_id
                        FROM chat_sessions
                        WHERE user_id = %s
                        ORDER BY created_at DESC
                        LIMIT %s
                    """, (user_id, limit))
                
                rows = cur.fetchall()
                return [
                    SessionInfo(
                        session_id=row[0],
                        user_id=row[1],
                        assistant_id=row[2],
                        title=row[3],
                        status=SessionStatus(row[4]),
                        metadata=json.loads(row[5]) if row[5] else None,
                        created_at=row[6],
                        updated_at=row[7],
                        related_entry_id=row[8]
                    ) for row in rows
                ]
    
    def archive_session(self, session_id: str) -> bool:
        """归档会话"""
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE chat_sessions
                    SET status = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE session_id = %s
                """, (SessionStatus.ARCHIVED.value, session_id))
                return cur.rowcount > 0
    
    def delete_session(self, session_id: str) -> bool:
        """删除会话"""
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE chat_sessions
                    SET status = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE session_id = %s
                """, (SessionStatus.DELETED.value, session_id))
                return cur.rowcount > 0
```

### 3.3 SectionService 设计

```python
"""
Section整理服务（SectionService）
负责将短期记忆（chat_messages）整理后写入entries大库
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from dataclasses import dataclass
from enum import Enum
import json


class SectionTrigger(str, Enum):
    """Section整理触发方式"""
    MCP_TOOL = "mcp_tool"           # MCP工具触发
    AUTO_MESSAGE_COUNT = "auto_message_count"  # 自动触发（消息数量）
    AUTO_TIME = "auto_time"         # 自动触发（时间间隔）
    MANUAL = "manual"               # 手动触发


class SectionStatus(str, Enum):
    """Section状态"""
    PENDING = "pending"             # 待整理
    PROCESSING = "processing"       # 整理中
    COMPLETED = "completed"         # 已完成
    FAILED = "failed"               # 失败


@dataclass
class SectionInfo:
    """Section信息"""
    section_id: str
    session_id: str
    title: str
    status: SectionStatus
    trigger_type: SectionTrigger
    message_count: int
    summary_content: Optional[str]
    summary_entry_id: Optional[str]
    agent_id: str
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime]


@dataclass
class SectionSummary:
    """Section总结结果"""
    section_id: str
    entry_id: str
    section_version: int
    content: str
    scene_tags: Dict[str, List[str]]
    agent_id: str
    metadata: Dict[str, Any]


class SectionService:
    """Section整理服务"""
    
    def __init__(self):
        self._conn = None
        self._embedding_model = "nomic-embed-text-v1.5"
    
    def _get_connection(self):
        from ai_factory.db.pgvector_client import connection_scope
        return connection_scope()
    
    def summarize_section(
        self,
        session_id: str,
        section_id: Optional[str] = None,
        agent_id: str = "default",
        trigger_type: SectionTrigger = SectionTrigger.MCP_TOOL,
        manual_section_title: Optional[str] = None
    ) -> SectionSummary:
        """
        整理section并写入entries大库
        
        Args:
            session_id: 会话ID
            section_id: 可选，手动指定的section_id。如果为None，则Agent智能判断
            agent_id: Agent ID，标识该section属于哪个Agent
            trigger_type: 触发类型
            manual_section_title: 可选，手动指定的section标题
        
        Returns:
            SectionSummary: 整理结果
        """
        # 1. 获取会话的最近消息
        messages = self._get_session_messages(session_id, limit=50)
        
        if not messages:
            raise ValueError(f"Session {session_id} has no messages to summarize")
        
        # 2. 如果没有手动指定section_id，Agent智能判断
        if section_id is None:
            section_id = self._generate_section_id(messages, agent_id)
            section_title = manual_section_title or self._generate_section_title(messages)
        else:
            section_title = manual_section_title or f"Section {section_id}"
        
        # 3. 调用LLM进行整理总结
        summary_content = self._summarize_with_llm(messages, section_title)
        
        # 4. 生成scene_tags
        scene_tags = self._generate_scene_tags(summary_content, agent_id)
        
        # 5. 获取当前section的版本号
        section_version = self._get_next_section_version(section_id)
        
        # 6. 将旧版本标记为非最新
        self._mark_old_versions_as_not_latest(section_id)
        
        # 7. 写入entries表
        entry_id = self._save_to_entries(
            session_id=session_id,
            section_id=section_id,
            section_version=section_version,
            content=summary_content,
            scene_tags=scene_tags,
            agent_id=agent_id,
            metadata={
                "trigger_type": trigger_type.value,
                "message_count": len(messages),
                "section_title": section_title
            }
        )
        
        # 8. 创建或更新section记录
        self._create_or_update_section(
            section_id=section_id,
            session_id=session_id,
            title=section_title,
            status=SectionStatus.COMPLETED,
            trigger_type=trigger_type,
            message_count=len(messages),
            summary_content=summary_content,
            summary_entry_id=entry_id,
            agent_id=agent_id
        )
        
        return SectionSummary(
            section_id=section_id,
            entry_id=entry_id,
            section_version=section_version,
            content=summary_content,
            scene_tags=scene_tags,
            agent_id=agent_id,
            metadata={
                "trigger_type": trigger_type.value,
                "message_count": len(messages),
                "section_title": section_title
            }
        )
    
    def get_section_history(
        self,
        section_id: str,
        agent_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """获取section的所有版本历史"""
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                conditions = ["section_id = %s"]
                params = [section_id]
                
                if agent_id:
                    conditions.append("agent_id = %s")
                    params.append(agent_id)
                
                cur.execute(f"""
                    SELECT entry_id, section_id, section_version, is_latest,
                           content, scene_tags, agent_id, created_at
                    FROM entries
                    WHERE {" AND ".join(conditions)}
                    ORDER BY section_version DESC
                """, params)
                
                rows = cur.fetchall()
                return [
                    {
                        "entry_id": row[0],
                        "section_id": row[1],
                        "section_version": row[2],
                        "is_latest": row[3],
                        "content": row[4],
                        "scene_tags": json.loads(row[5]) if row[5] else {},
                        "agent_id": row[6],
                        "created_at": row[7]
                    }
                    for row in rows
                ]
    
    def merge_sections(
        self,
        source_section_ids: List[str],
        target_section_id: str,
        agent_id: str
    ) -> SectionSummary:
        """
        合并多个section为一个
        
        Args:
            source_section_ids: 源section ID列表
            target_section_id: 目标section ID
            agent_id: Agent ID
        
        Returns:
            SectionSummary: 合并后的section总结
        """
        # 1. 获取所有源section的最新版本
        all_content = []
        for sec_id in source_section_ids:
            history = self.get_section_history(sec_id, agent_id)
            if history:
                all_content.append(history[0]["content"])
        
        if not all_content:
            raise ValueError(f"No content found in source sections: {source_section_ids}")
        
        # 2. 合并内容
        merged_content = self._merge_content_with_llm(all_content, target_section_id)
        
        # 3. 生成scene_tags
        scene_tags = self._generate_scene_tags(merged_content, agent_id)
        
        # 4. 获取目标section的版本号
        section_version = self._get_next_section_version(target_section_id)
        
        # 5. 将旧版本标记为非最新
        self._mark_old_versions_as_not_latest(target_section_id)
        
        # 6. 写入entries表
        entry_id = self._save_to_entries(
            session_id=None,  # 合并操作可能没有单一session
            section_id=target_section_id,
            section_version=section_version,
            content=merged_content,
            scene_tags=scene_tags,
            agent_id=agent_id,
            metadata={
                "operation": "merge",
                "source_sections": source_section_ids,
                "merged_at": datetime.now().isoformat()
            }
        )
        
        return SectionSummary(
            section_id=target_section_id,
            entry_id=entry_id,
            section_version=section_version,
            content=merged_content,
            scene_tags=scene_tags,
            agent_id=agent_id,
            metadata={
                "operation": "merge",
                "source_sections": source_section_ids
            }
        )
    
    def _get_session_messages(
        self,
        session_id: str,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """获取会话的消息"""
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT message_id, role, msg_type, content, created_at
                    FROM chat_messages
                    WHERE session_id = %s
                    ORDER BY created_at ASC
                    LIMIT %s
                """, (session_id, limit))
                
                rows = cur.fetchall()
                return [
                    {
                        "message_id": row[0],
                        "role": row[1],
                        "msg_type": row[2],
                        "content": row[3],
                        "created_at": row[4]
                    }
                    for row in rows
                ]
    
    def _generate_section_id(
        self,
        messages: List[Dict[str, Any]],
        agent_id: str
    ) -> str:
        """
        Agent智能判断生成section_id
        
        策略：
        1. 分析消息内容，识别主题
        2. 查询entries表，查找相似的section
        3. 如果相似度高于阈值，返回现有section_id
        4. 否则，生成新的section_id
        """
        # TODO: 实现智能判断逻辑
        # 这里简化处理：生成新的section_id
        import uuid
        return f"sec_{uuid.uuid4().hex[:16]}"
    
    def _generate_section_title(
        self,
        messages: List[Dict[str, Any]]
    ) -> str:
        """生成section标题"""
        # TODO: 实现标题生成逻辑
        # 这里简化处理：使用第一条消息的前20个字符
        if messages:
            first_content = messages[0]["content"]
            return first_content[:50] + "..." if len(first_content) > 50 else first_content
        return "Untitled Section"
    
    def _summarize_with_llm(
        self,
        messages: List[Dict[str, Any]],
        section_title: str
    ) -> str:
        """
        调用LLM进行整理总结
        
        TODO: 集成实际的LLM服务
        """
        # TODO: 实现LLM调用逻辑
        # 这里简化处理：合并所有消息
        summary_parts = []
        for msg in messages:
            summary_parts.append(f"[{msg['role']}]: {msg['content']}")
        return "\n\n".join(summary_parts)
    
    def _generate_scene_tags(
        self,
        content: str,
        agent_id: str
    ) -> Dict[str, List[str]]:
        """
        生成scene_tags
        
        根据内容和agent_id生成合适的场景标签
        
        Returns:
            Dict[str, List[str]]: scene_tags字典
        """
        # TODO: 实现智能标签生成逻辑
        # 这里简化处理：根据agent_id添加标签
        scene_tags = {
            "execution": ["笔记"],
            "planning": ["项目"]
        }
        
        # 根据agent_id添加特定标签
        if "project" in agent_id.lower():
            scene_tags["department"] = ["软件"]
        elif "work" in agent_id.lower():
            scene_tags["department"] = ["总部"]
        
        return scene_tags
    
    def _get_next_section_version(self, section_id: str) -> int:
        """获取section的下一个版本号"""
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COALESCE(MAX(section_version), 0)
                    FROM entries
                    WHERE section_id = %s
                """, (section_id,))
                
                result = cur.fetchone()
                return (result[0] if result else 0) + 1
    
    def _mark_old_versions_as_not_latest(self, section_id: str) -> None:
        """将section的旧版本标记为非最新"""
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE entries
                    SET is_latest = FALSE
                    WHERE section_id = %s AND is_latest = TRUE
                """, (section_id,))
    
    def _save_to_entries(
        self,
        session_id: Optional[str],
        section_id: str,
        section_version: int,
        content: str,
        scene_tags: Dict[str, List[str]],
        agent_id: str,
        metadata: Dict[str, Any]
    ) -> str:
        """保存到entries表"""
        import uuid
        entry_id = f"ent_{uuid.uuid4().hex}"
        
        # 生成embedding
        embedding = self._generate_embedding(content)
        
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                # 插入entries表（使用现有字段）
                cur.execute("""
                    INSERT INTO entries
                    (entry_id, title, content, scene_tags, section_id, section_version, is_latest,
                     agent_id, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    RETURNING entry_id
                """, (entry_id, f"Section {section_id}", content, json.dumps(scene_tags), section_id,
                       section_version, True, agent_id))
                
                # 插入entry_embeddings表（如果存在）
                try:
                    cur.execute("""
                        INSERT INTO entry_embeddings
                        (entry_id, embedding, model_name, created_at)
                        VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                    """, (entry_id, embedding, self._embedding_model))
                except Exception:
                    # 如果entry_embeddings表不存在，忽略
                    pass
                
                return entry_id
    
    def _create_or_update_section(
        self,
        section_id: str,
        session_id: str,
        title: str,
        status: SectionStatus,
        trigger_type: SectionTrigger,
        message_count: int,
        summary_content: Optional[str],
        summary_entry_id: Optional[str],
        agent_id: str
    ) -> None:
        """创建或更新section记录"""
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                # 检查section是否存在
                cur.execute("""
                    SELECT section_id FROM chat_sections
                    WHERE section_id = %s
                """, (section_id,))
                
                exists = cur.fetchone() is not None
                
                if exists:
                    # 更新
                    cur.execute("""
                        UPDATE chat_sections
                        SET title = %s, status = %s, message_count = %s,
                            summary_content = %s, summary_entry_id = %s,
                            updated_at = CURRENT_TIMESTAMP,
                            completed_at = CASE WHEN %s = %s THEN CURRENT_TIMESTAMP ELSE completed_at END
                        WHERE section_id = %s
                    """, (title, status.value, message_count, summary_content,
                           summary_entry_id, status.value, SectionStatus.COMPLETED.value, section_id))
                else:
                    # 创建
                    cur.execute("""
                        INSERT INTO chat_sections
                        (section_id, session_id, title, status, trigger_type, message_count,
                         summary_content, summary_entry_id, agent_id, created_at, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """, (section_id, session_id, title, status.value, trigger_type.value,
                           message_count, summary_content, summary_entry_id, agent_id))
    
    def _merge_content_with_llm(
        self,
        contents: List[str],
        target_section_id: str
    ) -> str:
        """
        调用LLM合并多个内容
        
        TODO: 集成实际的LLM服务
        """
        # TODO: 实现LLM调用逻辑
        # 这里简化处理：用分隔符合并
        return "\n\n---\n\n".join(contents)
    
    def _generate_embedding(self, text: str) -> List[float]:
        """生成文本的向量嵌入（简化版，实际应调用embedding服务）"""
        # TODO: 集成实际的embedding服务
        # 这里返回模拟的随机向量
        import random
        return [random.random() for _ in range(1536)]
```

### 3.4 EntryService 设计

```python
"""
Entries大库服务（EntryService）
管理entries表的存储与检索
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from dataclasses import dataclass
from enum import Enum
import json


class EntryType(str, Enum):
    """条目类型（通过scene_tags和space_type分类）"""
    MEMORY = "memory"           # 记忆
    NOTE = "note"              # 笔记
    TASK = "task"              # 任务
    KNOWLEDGE = "knowledge"    # 知识
    QA = "qa"                  # 问答
    LOG = "log"                # 日志


@dataclass
class EntryInfo:
    """条目信息"""
    entry_id: str
    title: str
    content: str
    section_id: Optional[str]
    section_version: Optional[int]
    is_latest: bool
    scene_tags: Dict[str, List[str]]
    agent_id: str
    created_at: datetime
    updated_at: datetime


@dataclass
class SearchResult:
    """搜索结果"""
    entry_id: str
    title: str
    content: str
    section_id: Optional[str]
    section_version: Optional[int]
    is_latest: bool
    scene_tags: Dict[str, List[str]]
    agent_id: str
    similarity: float  # 相似度分数


class EntryService:
    """Entries大库服务"""
    
    def __init__(self):
        self._conn = None
        self._embedding_model = "nomic-embed-text-v1.5"
    
    def _get_connection(self):
        from ai_factory.db.pgvector_client import connection_scope
        return connection_scope()
    
    def save_entry(
        self,
        title: str,
        content: str,
        scene_tags: Dict[str, List[str]],
        agent_id: str,
        section_id: Optional[str] = None,
        section_version: Optional[int] = None,
        is_latest: bool = True,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        保存条目到entries表
        
        Args:
            title: 标题
            content: 内容
            scene_tags: 场景标签字典
            agent_id: 所属Agent ID
            section_id: 可选，所属section ID
            section_version: 可选，section版本号
            is_latest: 是否为最新版本
            metadata: 可选，元数据
        
        Returns:
            str: entry_id
        """
        import uuid
        entry_id = f"ent_{uuid.uuid4().hex}"
        
        # 生成embedding
        embedding = self._generate_embedding(content)
        
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                # 插入entries表（使用现有字段）
                cur.execute("""
                    INSERT INTO entries
                    (entry_id, title, content, scene_tags, section_id, section_version, is_latest,
                     agent_id, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    RETURNING entry_id
                """, (entry_id, title, content, json.dumps(scene_tags), section_id, section_version,
                       is_latest, agent_id))
                
                # 插入entry_embeddings表（如果存在）
                try:
                    cur.execute("""
                        INSERT INTO entry_embeddings
                        (entry_id, embedding, model_name, created_at)
                        VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                    """, (entry_id, embedding, self._embedding_model))
                except Exception:
                    # 如果entry_embeddings表不存在，忽略
                    pass
                
                return entry_id
    
    def retrieve_entries(
        self,
        query: str,
        agent_id: Optional[str] = None,
        space_type: Optional[str] = None,
        scene_tag_key: Optional[str] = None,
        scene_tag_value: Optional[str] = None,
        section_id: Optional[str] = None,
        only_latest: bool = True,
        limit: int = 10,
        threshold: float = 0.7
    ) -> List[SearchResult]:
        """
        向量检索entries
        
        Args:
            query: 查询文本
            agent_id: 可选，过滤特定Agent的条目
            space_type: 可选，过滤特定空间类型的条目
            scene_tag_key: 可选，过滤特定scene_tags键的条目
            scene_tag_value: 可选，过滤特定scene_tags值的条目
            section_id: 可选，过滤特定section的条目
            only_latest: 是否只返回最新版本
            limit: 返回结果数量限制
            threshold: 相似度阈值
        
        Returns:
            List[SearchResult]: 搜索结果列表
        """
        # 生成查询embedding
        query_embedding = self._generate_embedding(query)
        
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                # 构建查询条件
                conditions = []
                params = []
                
                if agent_id:
                    conditions.append("agent_id = %s")
                    params.append(agent_id)
                
                if space_type:
                    conditions.append("space_type = %s")
                    params.append(space_type)
                
                if scene_tag_key and scene_tag_value:
                    # 使用JSONB查询scene_tags
                    conditions.append("scene_tags @> %s")
                    params.append(json.dumps({scene_tag_key: [scene_tag_value]}))
                
                if section_id:
                    conditions.append("section_id = %s")
                    params.append(section_id)
                
                if only_latest:
                    conditions.append("is_latest = TRUE")
                
                where_clause = " AND ".join(conditions) if conditions else "TRUE"
                
                # 向量相似度查询
                cur.execute(f"""
                    SELECT entry_id, title, content, section_id, section_version, is_latest,
                           scene_tags, agent_id, 1 - (embedding <=> %s) AS similarity
                    FROM entries
                    WHERE {where_clause}
                    ORDER BY similarity DESC
                    LIMIT %s
                """, [query_embedding] + params + [limit])
                
                rows = cur.fetchall()
                return [
                    SearchResult(
                        entry_id=row[0],
                        title=row[1],
                        content=row[2],
                        section_id=row[3],
                        section_version=row[4],
                        is_latest=row[5],
                        scene_tags=json.loads(row[6]) if row[6] else {},
                        agent_id=row[7],
                        similarity=float(row[8])
                    )
                    for row in rows
                    if row[8] >= threshold  # 过滤低于阈值的
                ]
    
    def get_entry(
        self,
        entry_id: str
    ) -> Optional[EntryInfo]:
        """获取单个条目"""
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT entry_id, title, content, section_id, section_version, is_latest,
                           scene_tags, agent_id, created_at, updated_at
                    FROM entries
                    WHERE entry_id = %s
                """, (entry_id,))
                
                row = cur.fetchone()
                if row:
                    return EntryInfo(
                        entry_id=row[0],
                        title=row[1],
                        content=row[2],
                        section_id=row[3],
                        section_version=row[4],
                        is_latest=row[5],
                        scene_tags=json.loads(row[6]) if row[6] else {},
                        agent_id=row[7],
                        created_at=row[8],
                        updated_at=row[9]
                    )
        return None
    
    def update_entry(
        self,
        entry_id: str,
        title: Optional[str] = None,
        content: Optional[str] = None,
        scene_tags: Optional[Dict[str, List[str]]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """更新条目"""
        updates = []
        params = []
        
        if title:
            updates.append("title = %s")
            params.append(title)
        
        if content:
            updates.append("content = %s")
            params.append(content)
        
        if scene_tags is not None:
            updates.append("scene_tags = %s")
            params.append(json.dumps(scene_tags))
        
        if metadata is not None:
            # 注意：现有数据库没有metadata_json字段，使用extra_meta
            updates.append("extra_meta = %s")
            params.append(json.dumps(metadata))
        
        if updates:
            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.append(entry_id)
            
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(f"""
                        UPDATE entries
                        SET {", ".join(updates)}
                        WHERE entry_id = %s
                    """, params)
                    
                    # 如果更新了content，同步更新entry_embeddings（如果存在）
                    if content:
                        embedding = self._generate_embedding(content)
                        try:
                            cur.execute("""
                                UPDATE entry_embeddings
                                SET embedding = %s, updated_at = CURRENT_TIMESTAMP
                                WHERE entry_id = %s
                            """, (embedding, entry_id))
                        except Exception:
                            # 如果entry_embeddings表不存在，忽略
                            pass
                    
                    return cur.rowcount > 0
        return False
    
    def delete_entry(self, entry_id: str) -> bool:
        """删除条目"""
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                # 先删除entry_embeddings
                cur.execute("""
                    DELETE FROM entry_embeddings
                    WHERE entry_id = %s
                """, (entry_id,))
                
                # 再删除entries
                cur.execute("""
                    DELETE FROM entries
                    WHERE id = %s
                """, (entry_id,))
                
                return cur.rowcount > 0
    
    def get_agent_entries(
        self,
        agent_id: str,
        space_type: Optional[str] = None,
        scene_tag_key: Optional[str] = None,
        scene_tag_value: Optional[str] = None,
        limit: int = 50
    ) -> List[EntryInfo]:
        """
        获取Agent的所有条目
        
        Args:
            agent_id: Agent ID
            space_type: 可选，过滤特定空间类型的条目
            scene_tag_key: 可选，过滤特定scene_tags键的条目
            scene_tag_value: 可选，过滤特定scene_tags值的条目
            limit: 返回结果数量限制
        
        Returns:
            List[EntryInfo]: 条目列表
        """
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                conditions = ["agent_id = %s"]
                params = [agent_id]
                
                if space_type:
                    conditions.append("space_type = %s")
                    params.append(space_type)
                
                if scene_tag_key and scene_tag_value:
                    conditions.append("scene_tags @> %s")
                    params.append(json.dumps({scene_tag_key: [scene_tag_value]}))
                
                cur.execute(f"""
                    SELECT entry_id, title, content, section_id, section_version, is_latest,
                           scene_tags, agent_id, created_at, updated_at
                    FROM entries
                    WHERE {" AND ".join(conditions)}
                    ORDER BY updated_at DESC
                    LIMIT %s
                """, params + [limit])
                
                rows = cur.fetchall()
                return [
                    EntryInfo(
                        entry_id=row[0],
                        title=row[1],
                        content=row[2],
                        section_id=row[3],
                        section_version=row[4],
                        is_latest=row[5],
                        scene_tags=json.loads(row[6]) if row[6] else {},
                        agent_id=row[7],
                        created_at=row[8],
                        updated_at=row[9]
                    )
                    for row in rows
                ]
    
    def get_section_entries(
        self,
        section_id: str,
        agent_id: Optional[str] = None,
        only_latest: bool = True
    ) -> List[EntryInfo]:
        """
        获取section的所有条目
        
        Args:
            section_id: Section ID
            agent_id: 可选，过滤特定Agent的条目
            only_latest: 是否只返回最新版本
        
        Returns:
            List[EntryInfo]: 条目列表
        """
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                conditions = ["section_id = %s"]
                params = [section_id]
                
                if agent_id:
                    conditions.append("agent_id = %s")
                    params.append(agent_id)
                
                if only_latest:
                    conditions.append("is_latest = TRUE")
                
                cur.execute(f"""
                    SELECT entry_id, title, content, section_id, section_version, is_latest,
                           scene_tags, agent_id, created_at, updated_at
                    FROM entries
                    WHERE {" AND ".join(conditions)}
                    ORDER BY section_version DESC
                """, params)
                
                rows = cur.fetchall()
                return [
                    EntryInfo(
                        entry_id=row[0],
                        title=row[1],
                        content=row[2],
                        section_id=row[3],
                        section_version=row[4],
                        is_latest=row[5],
                        scene_tags=json.loads(row[6]) if row[6] else {},
                        agent_id=row[7],
                        created_at=row[8],
                        updated_at=row[9]
                    )
                    for row in rows
                ]
    
    def _generate_embedding(self, text: str) -> List[float]:
        """生成文本的向量嵌入（简化版，实际应调用embedding服务）"""
        # TODO: 集成实际的embedding服务
        # 这里返回模拟的随机向量
        import random
        return [random.random() for _ in range(1536)]
```

### 3.5 QACacheService 设计

```python
"""
Q&A缓存服务（QACacheService）
用于快速响应重复问题
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
import json


class QAStatus(str, Enum):
    """Q&A状态"""
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    PENDING_REVIEW = "pending_review"


class AnswerType(str, Enum):
    """答案类型"""
    CACHED = "cached"      # 缓存的答案
    GENERATED = "generated"  # 生成的答案


@dataclass
class QAInfo:
    """Q&A信息"""
    qa_id: str
    user_id: str
    assistant_id: str
    tenant_id: str
    normalized_question: str
    answer_entry_id: str
    answer_type: AnswerType
    hit_count: int
    last_hit_at: Optional[datetime]
    status: QAStatus
    quality_score: Optional[float]
    tags: List[str]
    metadata: Dict[str, Any]
    created_at: datetime
    updated_at: datetime


class QACacheService:
    """Q&A缓存服务"""
    
    def __init__(self):
        self._conn = None
        self.embedding_model = "nomic-embed-text-v1.5"
    
    def _get_connection(self):
        from ai_factory.db.pgvector_client import connection_scope
        return connection_scope()
    
    def cache_qa(
        self,
        user_id: str,
        assistant_id: str,
        question: str,
        answer_entry_id: str,
        tenant_id: str = "default",
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """缓存Q&A对"""
        import uuid
        
        # 规范化问题（简化版）
        normalized_question = self._normalize_question(question)
        question_embedding = self._generate_embedding(normalized_question)
        qa_id = f"qa_{uuid.uuid4().hex()}"
        
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO qa_query_index
                    (qa_id, user_id, assistant_id, tenant_id, 
                     normalized_question, question_embedding, 
                     answer_entry_id, answer_type, 
                     hit_count, last_hit_at, status, quality_score, 
                     tags, metadata_json, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    RETURNING qa_id
                """, (qa_id, user_id, assistant_id, tenant_id, normalized_question,
                       question_embedding, answer_entry_id, AnswerType.CACHED.value,
                       0, None, QAStatus.ACTIVE.value, 0.8,
                       json.dumps(tags) if tags else None,
                       json.dumps(metadata) if metadata else None))
                
                return qa_id
    
    def query_qa(
        self,
        user_id: str,
        assistant_id: str,
        question: str,
        tenant_id: str = "default",
        threshold: float = 0.85,
        limit: int = 5
    ) -> List[QAInfo]:
        """查询相似的Q&A"""
        normalized_question = self._normalize_question(question)
        question_embedding = self._generate_embedding(normalized_question)
        
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT qa_id, user_id, assistant_id, tenant_id, 
                           normalized_question, answer_entry_id, answer_type, 
                           hit_count, last_hit_at, status, quality_score, 
                           tags, metadata_json, created_at, updated_at
                    FROM qa_query_index
                    WHERE user_id = %s AND assistant_id = %s AND tenant_id = %s
                      AND status = %s
                      AND 1 - (question_embedding <=> %s) >= %s
                    ORDER BY last_hit_at DESC, hit_count DESC
                    LIMIT %s
                """, (user_id, assistant_id, tenant_id, QAStatus.ACTIVE.value, question_embedding, threshold, limit))
                
                rows = cur.fetchall()
                return [
                    QAInfo(
                        qa_id=row[0],
                        user_id=row[1],
                        assistant_id=row[2],
                        tenant_id=row[3],
                        normalized_question=row[4],
                        answer_entry_id=row[5],
                        answer_type=AnswerType(row[6]),
                        hit_count=row[7],
                        last_hit_at=row[8],
                        status=QAStatus(row[9]),
                        quality_score=float(row[10]) if row[10] else None,
                        tags=json.loads(row[11]) if row[11] else [],
                        metadata=json.loads(row[12]) if row[12] else {},
                        created_at=row[13],
                        updated_at=row[14]
                    ) for row in rows
                ]
    
    def hit_qa(
        self,
        qa_id: str
    ) -> bool:
        """记录Q&A命中"""
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE qa_query_index
                    SET hit_count = hit_count + 1,
                        last_hit_at = CURRENT_TIMESTAMP
                    WHERE qa_id = %s
                """, (qa_id,))
                
                return cur.rowcount > 0
    
    def deprecate_qa(self, qa_id: str) -> bool:
        """标记Q&A为已废弃"""
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE qa_query_index
                    SET status = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE qa_id = %s
                """, (QAStatus.DEPRECATED.value, qa_id,))
                
                return cur.rowcount > 0
    
    def get_user_qa_stats(
        self,
        user_id: str,
        limit: int = 100
    ) -> Dict[str, Any]:
        """获取用户的Q&A统计"""
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                # 获取用户的所有Q&A
                cur.execute("""
                    SELECT qa_id, user_id, assistant_id, tenant_id, 
                           normalized_question, answer_entry_id, answer_type, 
                           hit_count, last_hit_at, status, quality_score, 
                           tags, metadata_json, created_at, updated_at
                    FROM qa_query_index
                    WHERE user_id = %s
                    ORDER BY hit_count DESC, last_hit_at DESC
                    LIMIT %s
                """, (user_id, limit))
                
                rows = cur.fetchall()
                
                # 按命中次数和最后命中时间分类
                hot_qas = [row for row in rows if row[7] >= 5]  # 高频（≥5次）
                warm_qas = [row for row in rows if 2 <= row[7] < 5]  # 温热（2-4次）
                cold_qas = [row for row in rows if row[7] < 2]  # 冷门（<2次）
                
                return {
                    'total_count': len(rows),
                    'hot_qas_count': len(hot_qas),
                    'warm_qas_count': len(warm_qas),
                    'cold_qas_count': len(cold_qas),
                    'hot_qas': hot_qas[:10],
                    'warm_qas': warm_qas[:10],
                    'cold_qas': cold_qas[:10]
                }
    
    def cleanup_old_qa(
        self,
        user_id: str,
        assistant_id: Optional[str] = None,
        days_threshold: int = 180,  # 180天未命中则清理
        keep_top_n: int = 50,  # 每个用户保留N条高频Q&A
    ) -> int:
        """清理旧的Q&A"""
        cutoff_date = datetime.now() - timedelta(days=days_threshold)
        
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                # 先删除超过阈值未命中的Q&A
                delete_sql = """
                    DELETE FROM qa_query_index
                    WHERE user_id = %s
                      AND (last_hit_at < %s OR last_hit_at IS NULL)
                      AND hit_count <= 1
                      AND status = %s
                """
                
                params = [user_id, cutoff_date, QAStatus.ACTIVE.value]
                cur.execute(delete_sql, params)
                deleted_count = cur.rowcount
                
                # 然后保留top N条高频Q&A
                if keep_top_n > 0:
                    # 先删除低频Q&A，保留top N
                    cur.execute("""
                        DELETE FROM qa_query_index
                        WHERE user_id = %s
                          AND status = %s
                          AND qa_id NOT IN (
                              SELECT qa_id FROM (
                                  SELECT qa_id FROM qa_query_index
                                  WHERE user_id = %s
                                  AND status = %s
                                  ORDER BY hit_count DESC, last_hit_at DESC
                                  LIMIT %s
                              ) AS top_qas
                          )
                    """, (user_id, QAStatus.ACTIVE.value, user_id, QAStatus.ACTIVE.value, keep_top_n))
                    deleted_count += cur.rowcount
                
                return deleted_count
    
    def _normalize_question(self, question: str) -> str:
        """规范化问题文本"""
        import re
        # 去除多余空格和标点
        question = re.sub(r'\s+', ' ', question)
        question = question.strip()
        # 转小写
        question = question.lower()
        return question
    
    def _generate_embedding(self, text: str) -> List[float]:
        """生成文本的向量嵌入（简化版，实际应调用embedding服务）"""
        # TODO: 集成实际的embedding服务
        import random
        return [random.random() for _ in range(1536)]
```

---

## 4. 实施计划

### 4.1 阶段一：数据表创建（第1天）

**目标：** 创建所有必要的数据表和索引

**任务：**
- [ ] 4.1.1 创建`chat_sessions`表
- [ ] 4.1.2 创建`chat_messages`表
- [ ] 4.1.3 创建`chat_sections`表（新增）
- [ ] 4.1.4 扩展`entries`表（添加section_id、section_version、is_latest、agent_id等字段，使用现有scene_tags和space_type）
- [ ] 4.1.5 创建`qa_query_index`表
- [ ] 4.1.6 创建所有必要的索引
- [ ] 4.1.7 验证表结构
- [ ] 4.1.8 测试基本CRUD操作

**验收标准：**
- 所有表创建成功
- 索引创建成功
- 基本CRUD操作正常
- pgvector扩展正常工作

### 4.2 阶段二：SessionService实现（第2-3天）

**目标：** 实现会话服务的基础功能

**任务：**
- [ ] 4.2.1 创建`session_service.py`文件
- [ ] 4.2.2 实现`create_session()`方法
- [ ] 4.2.3 实现`add_message()`方法
- [ ] 4.2.4 实现`get_session_info()`方法
- [ ] 4.2.5 实现`get_recent_messages()`方法
- [ ] 4.2.6 实现`get_session_history()`方法
- [ ] 4.2.7 实现`archive_session()`和`delete_session()`方法
- [ ] 4.2.8 编写单元测试
- [ ] 4.2.9 集成到AI工厂

**验收标准：**
- 所有方法实现完成
- 单元测试通过
- 集成测试通过
- 代码符合PEP8规范
- 有完整的类型注解和文档字符串

### 4.3 阶段三：SectionService实现（第3-5天）

**目标：** 实现Section整理服务的基础功能

**任务：**
- [ ] 4.3.1 创建`section_service.py`文件
- [ ] 4.3.2 实现`summarize_section()`方法（核心方法）
- [ ] 4.3.3 实现`get_section_history()`方法
- [ ] 4.3.4 实现`merge_sections()`方法
- [ ] 4.3.5 实现section_id智能判断逻辑
- [ ] 4.3.6 实现LLM调用接口（简化版）
- [ ] 4.3.7 编写单元测试
- [ ] 4.3.8 集成到AI工厂

**验收标准：**
- 所有方法实现完成
- 单元测试通过
- 集成测试通过
- 代码符合PEP8规范
- 有完整的类型注解和文档字符串

### 4.4 阶段四：EntryService实现（第4-6天）

**目标：** 实现Entries大库服务的基础功能

**任务：**
- [ ] 4.4.1 创建`entry_service.py`文件
- [ ] 4.4.2 实现`save_entry()`方法
- [ ] 4.4.3 实现`retrieve_entries()`方法（向量检索）
- [ ] 4.4.4 实现`get_entry()`方法
- [ ] 4.4.5 实现`update_entry()`方法
- [ ] 4.4.6 实现`delete_entry()`方法
- [ ] 4.4.7 实现`get_agent_entries()`方法
- [ ] 4.4.8 实现`get_section_entries()`方法
- [ ] 4.4.9 编写单元测试
- [ ] 4.4.10 集成到AI工厂

**验收标准：**
- 所有方法实现完成
- 单元测试通过
- 集成测试通过
- 代码符合PEP8规范
- 有完整的类型注解和文档字符串

### 4.5 阶段五：QACacheService实现（第5-7天）

**目标：** 实现Q&A缓存服务

**任务：**
- [ ] 4.5.1 创建`qa_cache_service.py`文件
- [ ] 4.5.2 实现`cache_qa()`方法
- [ ] 4.5.3 实现`query_qa()`方法
- [ ] 4.5.4 实现`hit_qa()`方法
- [ ] 4.5.5 实现`deprecate_qa()`方法
- [ ] 4.5.6 实现`get_user_qa_stats()`方法
- [ ] 4.5.7 实现`cleanup_old_qa()`方法
- [ ] 4.5.8 实现问题规范化
- [ ] 4.5.9 编写单元测试
- [ ] 4.5.10 集成到AI工厂

**验收标准：**
- 所有方法实现完成
- 单元测试通过
- 集成测试通过
- 代码符合PEP8规范
- 有完整的类型注解和文档字符串

### 4.6 阶段六：集成测试（第8-10天）

**目标：** 将记忆服务集成到AI工厂，进行端到端测试

**任务：**
- [ ] 4.6.1 在`ai_factory/domain/__init__.py`中导出SessionService、SectionService、EntryService、QACacheService
- [ ] 4.6.2 创建统一的`memory_manager.py`模块，整合四个服务
- [ ] 4.6.3 在AI工厂web中添加记忆管理API接口
- [ ] 4.6.4 实现MCP工具接口（SectionService.summarize_section()）
- [ ] 4.6.5 进行端到端测试
- [ ] 4.6.6 进行性能测试
- [ ] 4.6.7 进行多用户隔离测试
- [ ] 4.6.8 编写集成文档

**验收标准：**
- 所有API接口正常工作
- MCP工具接口正常工作
- 端到端测试通过
- 性能测试满足要求
- 多用户隔离正确
- 集成文档完整

---

## 5. 代码示例

### 5.1 使用SessionService创建会话

```python
from ai_factory.domain.session_service import SessionService, SessionStatus, MessageRole

# 创建会话服务实例
session_service = SessionService()

# 创建新会话
session_id = session_service.create_session(
    user_id="user_123",
    assistant_id="assistant_456",
    title="工作日总结助手对话",
    related_entry_id="ent_abc123"
)
print(f"创建会话: {session_id}")

# 添加用户消息
msg_id = session_service.add_message(
    session_id=session_id,
    role=MessageRole.USER,
    content="帮我总结今天的工作进展",
    msg_type="question",
    metadata={"priority": "high"}
)
print(f"添加消息: {msg_id}")

# 添加助手回复
msg_id = session_service.add_message(
    session_id=session_id,
    role=MessageRole.ASSISTANT,
    content="好的，我来帮你总结...",
    msg_type="answer",
    metadata={"sources": ["rag", "entries"]}
)
print(f"添加回复: {msg_id}")

# 获取最近消息
recent_messages = session_service.get_recent_messages(
    session_id=session_id,
    limit=5
)
print(f"最近{len(recent_messages)}条消息")

# 获取会话信息
session_info = session_service.get_session_info(session_id=session_id)
print(f"会话状态: {session_info.status}")
```

### 5.2 使用SectionService整理Section

```python
from ai_factory.domain.section_service import SectionService, SectionTrigger

# 创建Section服务实例
section_service = SectionService()

# 整理section（MCP工具触发）
summary = section_service.summarize_section(
    session_id="session_abc123",
    section_id=None,  # Agent智能判断section_id
    agent_id="agent_project_001",
    trigger_type=SectionTrigger.MCP_TOOL,
    manual_section_title="项目进展总结"
)
print(f"整理完成: {summary.entry_id}")
print(f"Section ID: {summary.section_id}")
print(f"版本号: {summary.section_version}")
print(f"场景标签: {summary.scene_tags}")
print(f"内容: {summary.content[:100]}...")

# 获取section历史
history = section_service.get_section_history(
    section_id=summary.section_id,
    agent_id="agent_project_001"
)
print(f"\nSection历史（共{len(history)}个版本）：")
for ver in history:
    print(f"  - 版本{ver['section_version']}: {ver['is_latest']}")

# 合并多个section
merged_summary = section_service.merge_sections(
    source_section_ids=["sec_001", "sec_002"],
    target_section_id="sec_merged_001",
    agent_id="agent_project_001"
)
print(f"\n合并完成: {merged_summary.entry_id}")
```

### 5.3 使用EntryService管理Entries大库

```python
from ai_factory.domain.entry_service import EntryService

# 创建Entry服务实例
entry_service = EntryService()

# 保存条目到entries大库
entry_id = entry_service.save_entry(
    title="用户偏好记录",
    content="我喜欢用中文回答，回答要列小标题",
    scene_tags={
        "department": ["软件"],
        "execution": ["笔记"],
        "planning": ["项目"]
    },
    agent_id="agent_001",
    section_id="sec_pref_001",
    section_version=1,
    is_latest=True,
    metadata={"confidence": 0.9}
)
print(f"保存条目: {entry_id}")

# 向量检索entries
results = entry_service.retrieve_entries(
    query="我的偏好是什么？",
    agent_id="agent_001",
    space_type="note",
    scene_tag_key="department",
    scene_tag_value="软件",
    only_latest=True,
    limit=5,
    threshold=0.7
)
print(f"\n检索到{len(results)}条结果：")
for result in results:
    print(f"  - {result.title}: {result.content[:50]}... (相似度: {result.similarity:.2f})")

# 获取Agent的所有条目
agent_entries = entry_service.get_agent_entries(
    agent_id="agent_001",
    space_type="note",
    scene_tag_key="department",
    scene_tag_value="软件",
    limit=20
)
print(f"\nAgent共有{len(agent_entries)}条记录")

# 获取section的所有条目
section_entries = entry_service.get_section_entries(
    section_id="sec_pref_001",
    agent_id="agent_001",
    only_latest=True
)
print(f"\nSection共有{len(section_entries)}条记录")

# 更新条目
updated = entry_service.update_entry(
    entry_id=entry_id,
    content="我喜欢用中文回答，回答要列小标题，并且要简洁明了",
    scene_tags={
        "department": ["软件"],
        "execution": ["笔记"],
        "planning": ["项目"]
    }
)
print(f"\n更新结果: {updated}")
```

### 5.4 使用QACacheService缓存和查询Q&A

```python
from ai_factory.domain.qa_cache_service import QACacheService, AnswerType

# 创建Q&A缓存服务实例
qa_cache_service = QACacheService()

# 缓存Q&A对
qa_id = qa_cache_service.cache_qa(
    user_id="user_123",
    assistant_id="assistant_456",
    question="帮我总结今天的工作进展",
    answer_entry_id="ent_abc123",
    tags=["工作总结", "日常"],
    metadata={"answer_source": "rag"}
)
print(f"缓存Q&A: {qa_id}")

# 查询相似的Q&A
similar_qas = qa_cache_service.query_qa(
    user_id="user_123",
    assistant_id="assistant_456",
    question="总结一下工作进展",
    threshold=0.85,
    limit=3
)
print(f"查询到{len(similar_qas)}条相似Q&A")
for qa in similar_qas:
    print(f"  - 问题: {qa.normalized_question}")
    print(f"    命中次数: {qa.hit_count}")
    print(f"    最后命中: {qa.last_hit_at}")

# 记录命中
if similar_qas:
    qa_cache_service.hit_qa(similar_qas[0].qa_id)
    print(f"记录命中: {similar_qas[0].qa_id}")

# 获取用户Q&A统计
stats = qa_cache_service.get_user_qa_stats(
    user_id="user_123",
    limit=50
)
print(f"用户Q&A统计:")
print(f"  总数: {stats['total_count']}")
print(f"  高频Q&A: {stats['hot_qas_count']}")
print(f"  温热Q&A: {stats['warm_qas_count']}")
print(f"  冷门Q&A: {stats['cold_qas_count']}")

# 清理旧Q&A
deleted_count = qa_cache_service.cleanup_old_qa(
    user_id="user_123",
    days_threshold=180,
    keep_top_n=50
)
print(f"清理了{deleted_count}条旧Q&A")
```

### 5.5 集成使用示例

```python
from ai_factory.domain.session_service import SessionService
from ai_factory.domain.section_service import SectionService
from ai_factory.domain.entry_service import EntryService
from ai_factory.domain.qa_cache_service import QACacheService

# 创建服务实例
session_service = SessionService()
section_service = SectionService()
entry_service = EntryService()
qa_cache_service = QACacheService()

def get_agent_context(user_id: str, assistant_id: str, query: str) -> Dict[str, Any]:
    """获取Agent的完整上下文"""
    context = {
        'user_id': user_id,
        'assistant_id': assistant_id,
        'query': query,
        'timestamp': datetime.now().isoformat()
    }
    
    # 1. 先查Q&A缓存
    similar_qas = qa_cache_service.query_qa(
        user_id=user_id,
        assistant_id=assistant_id,
        question=query,
        threshold=0.85,
        limit=3
    )
    
    if similar_qas:
        # 命中缓存，直接返回
        context['qa_hit'] = {
            'qa_id': similar_qas[0].qa_id,
            'normalized_question': similar_qas[0].normalized_question,
            'answer_entry_id': similar_qas[0].answer_entry_id,
            'hit_count': similar_qas[0].hit_count
        }
        
        # 记录命中
        qa_cache_service.hit_qa(similar_qas[0].qa_id)
        
        return context
    
    # 2. 获取会话上下文
    # 假设从某个会话ID获取
    session_id = "session_abc123"  # 从前端传入
    recent_messages = session_service.get_recent_messages(
        session_id=session_id,
        limit=10
    )
    
    context['session_messages'] = [
        {
            'message_id': msg.message_id,
            'role': msg.role.value,
            'content': msg.content,
            'created_at': msg.created_at.isoformat()
        }
        for msg in recent_messages
    ]
    
    # 3. 获取Agent记忆（从entries大库）
    memories = entry_service.retrieve_entries(
        query=query,
        agent_id=assistant_id,
        space_type="note",
        scene_tag_key="execution",
        scene_tag_value="笔记",
        only_latest=True,
        limit=5
    )
    
    context['agent_memories'] = [
        {
            'entry_id': mem.entry_id,
            'title': mem.title,
            'content': mem.content[:100] + "...",
            'scene_tags': mem.scene_tags,
            'similarity': mem.similarity
        }
        for mem in memories
    ]
    
    # 4. 调用RAG获取世界知识
    # TODO: 调用现有的RAG服务
    # context['world_knowledge'] = rag_service.retrieve(...)
    
    return context


# 使用示例
context = get_agent_context(
    user_id="user_123",
    assistant_id="assistant_456",
    query="帮我总结今天的工作进展"
)

print("Agent上下文:")
print(f"  Q&A命中: {context.get('qa_hit', {}).get('qa_id')}")
print(f"  会话消息数: {len(context.get('session_messages'))}")
print(f"  Agent记忆数: {len(context.get('agent_memories'))}")
```

---

## 6. 与AI工厂集成

### 6.1 目录结构调整

```
ai-factory/
├── domain/
│   ├── __init__.py
│   ├── session_service.py      # 新增：会话服务
│   ├── section_service.py     # 新增：Section整理服务
│   ├── entry_service.py       # 新增：Entries大库服务
│   ├── qa_cache_service.py     # 新增：Q&A缓存服务
│   └── memory_manager.py       # 新增：统一管理器
├── db/
│   ├── pgvector_client.py       # 已存在
│   └── pgvector_index.py      # 已存在
├── rag/
│   ├── pgvector_index.py      # 已存在
│   └── rag_pipeline.py       # 已存在
└── sql/
    └── create_memory_tables.sql  # 新增：数据表创建脚本
```

### 6.2 模块导出配置

在`ai_factory/domain/__init__.py`中添加：

```python
"""
AI工厂领域模块
包含：会话管理、Section整理、Entries大库管理、Q&A缓存等核心能力
"""

from .session_service import SessionService
from .section_service import SectionService
from .entry_service import EntryService
from .qa_cache_service import QACacheService

__all__ = [
    'SessionService',
    'SectionService',
    'EntryService',
    'QACacheService',
]
```

### 6.3 MCP工具集成

SectionService的`summarize_section()`方法可以作为MCP工具暴露给Agent使用：

```python
# 在MCP服务器中注册工具
@mcp_tool
def summarize_section(
    session_id: str,
    section_id: Optional[str] = None,
    agent_id: str = "default",
    manual_section_title: Optional[str] = None
) -> Dict[str, Any]:
    """
    整理section并写入entries大库
    
    Args:
        session_id: 会话ID
        section_id: 可选，手动指定的section_id。如果为None，则Agent智能判断
        agent_id: Agent ID，标识该section属于哪个Agent
        manual_section_title: 可选，手动指定的section标题
    
    Returns:
        整理结果，包含entry_id、section_id、section_version等信息
    """
    from ai_factory.domain.section_service import SectionService
    
    section_service = SectionService()
    summary = section_service.summarize_section(
        session_id=session_id,
        section_id=section_id,
        agent_id=agent_id,
        manual_section_title=manual_section_title
    )
    
    return {
        "entry_id": summary.entry_id,
        "section_id": summary.section_id,
        "section_version": summary.section_version,
        "scene_tags": summary.scene_tags,
        "agent_id": summary.agent_id
    }
```

---

## 7. 测试计划

### 7.1 单元测试

#### 7.1.1 SessionService单元测试

```python
import unittest
from ai_factory.domain.session_service import SessionService, SessionStatus, MessageRole, MessageType
from datetime import datetime

class TestSessionService(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        cls.service = SessionService()
        cls.user_id = "test_user_001"
        cls.assistant_id = "test_assistant_001"
        cls.test_session_id = None
    
    def test_create_session(self):
        """测试创建会话"""
        session_id = self.service.create_session(
            user_id=self.user_id,
            assistant_id=self.assistant_id,
            title="测试会话"
        )
        self.assertIsNotNone(session_id)
        self.assertTrue(session_id.startswith("session_"))
        
        # 验证会话信息
        session_info = self.service.get_session_info(session_id)
        self.assertEqual(session_info.session_id, session_id)
        self.assertEqual(session_info.user_id, self.user_id)
        self.assertEqual(session_info.assistant_id, self.assistant_id)
        self.assertEqual(session_info.status, SessionStatus.ACTIVE)
        self.assertIsNotNone(session_info.created_at)
    
    def test_add_message(self):
        """测试添加消息"""
        # 先创建会话
        session_id = self.service.create_session(
            user_id=self.user_id,
            assistant_id=self.assistant_id,
            title="测试会话"
        )
        
        # 添加用户消息
        msg_id = self.service.add_message(
            session_id=session_id,
            role=MessageRole.USER,
            content="测试消息内容",
            msg_type=MessageType.QUESTION,
            metadata={"test": True}
        )
        self.assertIsNotNone(msg_id)
        self.assertTrue(msg_id.startswith("msg_"))
        
        # 添加助手回复
        msg_id = self.service.add_message(
            session_id=session_id,
            role=MessageRole.ASSISTANT,
            content="测试回复内容",
            msg_type=MessageType.ANSWER,
            metadata={"test": True}
        )
        self.assertIsNotNone(msg_id)
        self.assertTrue(msg_id.startswith("msg_"))
        
        # 验证消息数量
        messages = self.service.get_recent_messages(session_id, limit=10)
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0].role, MessageRole.USER)
        self.assertEqual(messages[1].role, MessageRole.ASSISTANT)
```

---

## 8. 部署说明

### 8.1 数据库部署

1. **创建数据表**
```bash
psql -h <host> -U <user> -d <database> -f ai-factory/sql/create_memory_tables.sql
```

2. **验证表结构**
```bash
psql -h <host> -U <user> -d <database> -c "\dt chat_sessions"
psql -h <host> -U <user> -d <database> -c "\dt chat_messages"
psql -h <host> -U <user> -d <database> -c "\dt chat_sections"
psql -h <host> -U <user> -d <database> -c "\dt entries"
psql -h <host> -U <user> -d <database> -c "\dt entry_embeddings"
psql -h <host> -U <user> -d <database> -c "\dt qa_query_index"
```

### 8.2 应用部署

1. **安装依赖**
```bash
pip install -r requirements.txt
```

2. **配置环境变量**
```bash
# 在.env文件中添加
DATABASE_URL=postgresql://user:password@host:port/database
```

3. **启动服务**
```bash
python -m ai_factory.web.app
```

---

## 附录

### A. 数据表ER图

```
┌─────────────────┐
│ chat_sessions   │
├─────────────────┤
│ session_id (PK) │
│ user_id         │
│ assistant_id    │
│ title           │
│ status          │
│ metadata_json   │
│ created_at      │
│ updated_at      │
│ related_entry_id│
└────────┬────────┘
         │ 1
         │
         │ N
┌────────┴────────┐
│ chat_messages   │
├─────────────────┤
│ message_id (PK) │
│ session_id (FK) │
│ role            │
│ msg_type        │
│ content         │
│ metadata_json   │
│ created_at      │
└─────────────────┘

┌──────────────────┐
│ chat_sections   │
├──────────────────┤
│ section_id (PK) │
│ session_id (FK) │
│ title           │
│ status          │
│ trigger_type    │
│ message_count   │
│ summary_content │
│ summary_entry_id│
│ agent_id        │
│ created_at      │
│ updated_at      │
│ completed_at    │
└──────────────────┘

┌──────────────────┐
│ entries         │
├──────────────────┤
│ id (PK)         │
│ title           │
│ content         │
│ embedding       │
│ section_id (FK) │
│ section_version │
│ is_latest       │
│ scene_tags      │
│ agent_id        │
│ source_session_id│
│ metadata_json   │
│ created_at      │
│ updated_at      │
└──────────────────┘

┌──────────────────┐
│ qa_query_index   │
├──────────────────┤
│ qa_id (PK)        │
│ user_id           │
│ assistant_id      │
│ tenant_id         │
│ normalized_question│
│ question_embedding│
│ answer_entry_id   │
│ answer_type       │
│ hit_count         │
│ last_hit_at       │
│ status            │
│ quality_score     │
│ tags              │
│ metadata_json     │
│ created_at        │
│ updated_at        │
└──────────────────┘
```

### B. API接口清单

| 接口 | 方法 | 路径 | 说明 |
|------|------|------|------|
| 创建会话 | POST | /api/memory/sessions | 创建新会话 |
| 获取会话 | GET | /api/memory/sessions/{session_id} | 获取会话信息 |
| 添加消息 | POST | /api/memory/sessions/{session_id}/messages | 添加消息到会话 |
| 获取最近消息 | GET | /api/memory/sessions/{session_id}/messages/recent | 获取最近N条消息 |
| 删除会话 | DELETE | /api/memory/sessions/{session_id} | 删除会话 |
| 整理Section | POST | /api/memory/sections/summarize | 整理section并写入entries大库 |
| 获取Section历史 | GET | /api/memory/sections/{section_id}/history | 获取section的所有版本历史 |
| 合并Sections | POST | /api/memory/sections/merge | 合并多个section为一个 |
| 保存条目 | POST | /api/memory/entries | 保存条目到entries大库 |
| 获取条目 | GET | /api/memory/entries/{entry_id} | 获取单个条目 |
| 检索条目 | POST | /api/memory/entries/retrieve | 向量检索entries大库 |
| 获取Agent条目 | GET | /api/memory/entries/agent/{agent_id} | 获取Agent的所有条目 |
| 获取Section条目 | GET | /api/memory/entries/section/{section_id} | 获取section的所有条目 |
| 更新条目 | PUT | /api/memory/entries/{entry_id} | 更新条目 |
| 删除条目 | DELETE | /api/memory/entries/{entry_id} | 删除条目 |
| 缓存Q&A | POST | /api/qa/cache | 缓存Q&A对 |
| 查询Q&A | POST | /api/qa/cache/query | 查询相似的Q&A |
| 记录命中 | POST | /api/qa/cache/{qa_id}/hit | 记录Q&A命中 |
| 获取统计 | GET | /api/qa/cache/user/{user_id}/stats | 获取用户Q&A统计 |

---

**文档结束**
