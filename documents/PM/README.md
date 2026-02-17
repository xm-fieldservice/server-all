# PM-agent 项目管理智能代理

> **项目代号**: pm-agent  
> **核心目标**: 构建具有记忆能力的项目管理Agent系统  
> **状态**: Phase 1 已完成（基础设施部署），Phase 2 待启动

---

## 📊 Phase 1 成果报告（已完成 - 2026-02-17）

### ✅ 基础设施部署

**PostgreSQL + pgvector 数据库**
- 容器：`rag_postgres` 运行中（端口5434）
- 持久化：`pgvector_data` Docker卷
- 自动重启：`always` 策略
- 数据规模：1,560条entries，1,559条embeddings（99.9%向量化）
- 备份机制：`data/postgres/backups/` 目录

**数据底座状态**
```
entries表: 1,560条记录 ✅
entry_embeddings: 1,559条向量（99.9%）✅
scene_tags GIN索引: 2个 ✅
DashScope向量化: 正常 ✅
```

### ✅ Agent配置创建

**配置文件**
- `.opencode/agents/pm-agent.md` - PM项目经理Agent（11个工具）
- `.opencode/agents/pm-clerk.md` - 书记员Agent（8个工具）

**核心能力定义**
- 6大职责矩阵：档案员、调度员、风险控制、边界控制、规则控制、知识沉淀
- 记忆系统规范：1号/2号通道使用、scene_tags标记体系
- 协作协议：PM-agent调用PM-clerk的标准流程

### ✅ 数据导入工具开发

**新方案（当前推荐）**
- `scripts/import_project_sessions.py` - 项目私域直接导入 ⭐
  - 直接从OpenCode SQLite/JSON读取
  - 自动标记项目归属（project_code, operator）
  - 支持PM/书记员角色区分
  - 严格数据隔离（scene_tags.project_code）

**旧方案（已封存）**
- `export_sessions.py` - 导出到all_sessions.md ⏸️ 封存
- `scripts/sync_all_sessions_to_entries.py` - 同步到entries ⏸️ 封存
- 封存原因：中间环节多、项目归属易混淆
- 封存详情：`scripts/archived/all_sessions_channel/README.md`

### ✅ 关键教训与纠正

**错误**: 误将58条sessions全部标记为pm-agent私域数据
**纠正**: 已删除并备份（`pm_agent_wrong_import_*.json`）
**规范**: 以后必须通过PM专属通道导入，明确标记项目归属

### 📋 文档清单

- `README.md` - 本文件（项目总体说明）
- `docs/PROJECT_PRIVATE_DATA_IMPORT.md` - 项目私域导入方案
- `docs/QUICK_START_IMPORT.md` - 快速使用指南
- `docs/DATABASE_SYNC_STATUS.md` - 数据库状态报告
- `scripts/archived/all_sessions_channel/README.md` - 封存脚本说明

---

## 🔍 基础设施检查报告（基线存档 - 2026-02-17）

> **检查目的**: 识别基础设施中的重复实现和不合格节点，作为修复工作的基线
> **检查方法**: 代码审计 + grep搜索 + import验证
> **后续用途**: Agent交叉检查基准、修复工作验收标准

### ⚠️ 严重问题（P0级）

#### 1. 假向量实现 - pgvector_index.py ❌❌❌
- **位置**: `ai_factory/rag/pgvector_index.py`
- **问题**: `_fake_embed()` 函数基于文本长度生成假向量（3维）
- **风险**: 生产环境使用会导致完全错误的相似度检索
- **状态**: ✅ 已修复（2026-02-17）- 添加运行时保护，禁止生产环境导入
- **验证**: `python3 -c "from ai_factory.rag.pgvector_index import search"` 应抛出 RuntimeError

#### 2. 重复向量化代码 - entries_ingest.py ❌
- **位置**: `ai_factory/integrations/entries_ingest.py`
- **问题**: 3处完全相同的向量化代码块（lines 379-388, 538-547, 701-711）
- **代码重复内容**:
  ```python
  emb_text = _build_embedding_text(entry)
  embedding = _call_dashscope_embedding(emb_text)
  print(f"[entries_ingest] 使用DashScope向量化完成 (1024维)")
  entry_for_embedding = dict(entry)
  entry_for_embedding.setdefault("mode", "NOTE")
  upsert_entry_embedding(entry_for_embedding, embedding)
  ```
- **风险**: 维护困难、不一致性风险、代码膨胀
- **状态**: ✅ 已修复（2026-02-17）- 提取为 `_vectorize_entry_sync()` 统一函数
- **验证**: `python3 -c "from ai_factory.integrations.entries_ingest import _vectorize_entry_sync"` 应成功

#### 3. 过时的维度常量文档 - vectorize_entries_with_ollama.py ⚠️
- **位置**: `ai_factory/vectorize_entries_with_ollama.py`
- **问题**: 文档字符串声明维度为2560，实际常量为1024
- **影响**: 误导开发者，可能导致维度不匹配错误
- **状态**: ✅ 已修复（2026-02-17）- 更新文档字符串
- **实际常量**: `EMBEDDING_DIM = 1024`（正确）

### 📊 向量化实现路径统计

| 实现路径 | 维度 | 状态 | 用途 |
|---------|------|------|------|
| `vectorize_entries_with_dashscope.py` | 1024 | ✅ 主用 | 生产环境向量化 |
| `entries_ingest.py` 内嵌逻辑 | 1024 | ✅ 已重构 | 1号/2号通道同步向量化 |
| `vectorize_entries_with_ollama.py` | 1024 | ⏸️ 未使用 | 本地Ollama备用方案 |
| `vectorize_entries_with_deepseek.py` | 1024 | ⏸️ 未使用 | DeepSeek备用方案 |
| `pgvector_index.py` | 3 | ❌ 已禁用 | 假向量实现（已保护） |

### 📊 RAG检索实现路径统计

| 实现路径 | 向量源 | 状态 | 用途 |
|---------|--------|------|------|
| `rag/entries_rag.py` | DashScope 1024维 | ✅ 唯一合格 | 生产环境RAG检索 |
| `rag/pgvector_index.py` | 假向量 | ❌ 已禁用 | v0占位实现（已保护） |
| `rag/rag_pipeline.py` | pgvector_index | ❌ 已隔离 | 依赖假向量实现 |
| `integrations/rag_api.py` | entries_rag | ✅ 在用 | RAG API兼容层 |
| `integrations/rag_pipeline_api_v2.py` | entries_rag | ⏸️ 实验性 | QueryIntent体系v2 |

### 🗄️ 数据状态快照（检查时刻）

```
PostgreSQL (rag_postgres:5434):
├── entries: 1,560条记录
│   ├── pm-agent项目: 0条（已清理）
│   ├── opencode-sessions项目: 189条
│   │   └── ⚠️ 全部title为原文截断（Ollama未运行）
│   └── 其他项目: 1,371条
├── embeddings: 1,559条向量（99.9%向量化率）
└── scene_tags索引: 2个GIN索引
```

**数据质量问题**:
- 189条opencode-sessions记录未经过正确LLM处理（title=content[:60]）
- 向量化使用了DashScope，但title生成回退到原文截断
- 影响：RAG检索效果降低，title无法准确反映内容主题

### ✅ 修复工作清单（已完成）

| 问题 | 修复动作 | 验证方法 | 状态 |
|------|---------|---------|------|
| pgvector_index.py假向量 | 添加运行时保护，禁止生产导入 | import测试应抛出RuntimeError | ✅ |
| entries_ingest.py重复代码 | 提取 `_vectorize_entry_sync()` 统一函数 | import测试应成功 | ✅ |
| ollama.py文档错误 | 更新docstring（2560→1024） | 代码审查 | ✅ |

### 🔒 生产环境保护机制

**pgvector_index.py保护**:
```python
if os.environ.get("ENV", "development") != "test_allow_fake_vectors":
    raise RuntimeError(
        "pgvector_index.py is DEPRECATED and contains FAKE vector implementation. "
        "DO NOT USE in production."
    )
```

**验证命令**:
```bash
# 应失败（生产环境）
python3 -c "from ai_factory.rag.pgvector_index import search"

# 应成功（测试环境）
ENV=test_allow_fake_vectors python3 -c "from ai_factory.rag.pgvector_index import search"
```

### 📝 后续工作建议

1. **数据修复**: 处理189条未正确LLM处理的记录（重新生成title/summary）
2. **架构统一**: 创建向量化策略模式，统一所有向量化入口
3. **代码清理**: 删除/迁移未使用的备用方案（ollama/deepseek）
4. **监控告警**: 添加title质量检查，防止类似问题再次发生

### 🔍 Agent交叉检查指南

当使用多个Agent进行基础设施修复时，以此报告为基线进行验证：

1. **检查重复代码**: grep "emb_text = _build_embedding_text" 应只出现1次（在统一函数中）
2. **检查假向量**: 尝试导入pgvector_index应抛出RuntimeError
3. **检查维度一致性**: 所有向量化路径应使用1024维
4. **检查数据质量**: 抽查entries表title字段，确认不是原文截断

---

## 🎯 Phase 2 计划（待启动）

**核心任务**: 实现记忆检索能力（让PM-agent能"想起"关键信息）

**待完成**
- P1-1: 创建 `pm_memory.py` - RAG检索封装
- P1-2: 更新PM-agent配置 - 添加记忆检索工具
- P1-3: 支持按scene_tags过滤检索
- P2: 场景验证测试

**下一步行动**: 开发 `ai_factory/agents/pm_team/pm_memory.py`

---

---

## 一、项目概述

PM-agent 是一个基于OpenCode Agent框架构建的项目管理智能代理系统，专门负责 documents/PM/ 目录下的项目管理活动。

### 核心特性

- ✅ **记忆能力**：通过1号/2号通道将项目知识持久化到entries表
- ✅ **角色分工**：PM-agent（项目经理）+ PM-clerk（书记员）协作模式
- ✅ **知识分层**：支持record→information→knowledge→wisdom四级知识体系
- ✅ **立体标记**：使用scene_tags进行多维度分类和检索
- ✅ **框架集成**：与现有双通道架构（1号/2号通道）无缝集成

---

## 二、系统架构

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                        PM-agent 系统                          │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐         ┌──────────────┐                │
│  │   PM-agent   │◄───────►│  PM-clerk    │                │
│  │  (项目经理)   │  task   │  (书记员)    │                │
│  └──────┬───────┘         └──────┬───────┘                │
│         │                        │                        │
│         └────────────┬───────────┘                        │
│                      │                                     │
│         ┌────────────▼────────────┐                      │
│         │     双通道架构           │                      │
│         │  ┌──────────────────┐  │                      │
│         │  │   1号通道        │  │  本地同步入库        │
│         │  │  entries_ingest  │  │  (关键信息)          │
│         │  └──────────────────┘  │                      │
│         │  ┌──────────────────┐  │                      │
│         │  │   2号通道        │  │  HTTP异步入库        │
│         │  │  /access/v1/*    │  │  (批量信息)          │
│         │  └──────────────────┘  │                      │
│         └────────────┬───────────┘                      │
│                      │                                   │
│         ┌────────────▼────────────┐                    │
│         │      entries 表         │                    │
│         │  ┌──────────────────┐  │                    │
│         │  │  scene_tags      │  │  立体标记系统      │
│         │  │  (JSONB)         │  │                    │
│         │  └──────────────────┘  │                    │
│         └────────────────────────┘                    │
│                                                        │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 核心组件

| 组件 | 位置 | 职责 |
|------|------|------|
| **PM-agent** | `.opencode/agents/pm-agent.md` | 项目经理，负责决策、调度、风险控制 |
| **PM-clerk** | `.opencode/agents/pm-clerk.md` | 书记员，负责信息采集、整理、入库 |
| **记忆系统** | `entries`表 | 统一存储项目知识，支持RAG检索 |
| **1号通道** | `ai_factory/integrations/entries_ingest.py` | 本地同步入库接口 |
| **2号通道** | `http://121.43.126.173:8001/access/v1/*` | HTTP异步入库接口 |

---

## 三、使用指南

### 3.1 快速开始

**启动PM-agent**：

在OpenCode中，PM-agent会自动加载。你可以直接与之对话：

```
用户: @pm-agent 帮我初始化一个新项目

PM-agent: 我将为您初始化项目。首先让我采集项目基本信息...
[调用PM-clerk采集信息]
[写入entries表]
项目初始化完成！项目ID: proj-001
```

**调用PM-clerk采集信息**：

```
用户: @pm-clerk 请记录刚才的决策

PM-clerk: 检测到决策内容，正在整理...
[整理为决策记录格式]
[通过1号通道入库]
已归档决策记录，entry_id: ent_abc123
```

### 3.2 常用操作

**记录项目决策**：
```
@pm-agent 记录决策：我们决定使用微服务架构
→ PM-agent整理并调用PM-clerk入库
→ 返回entry_id
```

**跟踪项目任务**：
```
@pm-agent 创建任务：完成API设计文档，负责人张三，截止2026-02-20
→ 生成任务记录
→ 入库并建立跟踪
```

**查询项目知识**：
```
@pm-agent 查询我们关于技术栈的决策
→ 检索entries表中type=decision的记录
→ 返回相关决策列表
```

---

## 四、知识管理规范

### 4.1 知识层级

| 层级 | 标记 | 内容示例 | 存储方式 |
|------|------|----------|----------|
| **Record** | `knowledge_level: record` | 原始会话、草稿 | entries表 |
| **Information** | `knowledge_level: information` | 整理后的笔记 | entries表 |
| **Knowledge** | `knowledge_level: knowledge` | 决策、方案 | entries表 |
| **Wisdom** | `knowledge_level: wisdom` | SOP、方法论 | entries表 |

### 4.2 标记系统 (scene_tags)

每条entries记录必须包含以下标记：

```json
{
  "scene_tags": {
    "project_code": "pm-agent",
    "knowledge_level": "knowledge",
    "type": "decision",
    "module": "core",
    "status": "active",
    "priority": "high"
  }
}
```

**类型标记**（type）：
- `session` - 会话记录
- `decision` - 决策记录
- `task` - 任务记录
- `risk` - 风险记录
- `lesson` - 经验教训
- `sop` - 标准流程

**模块标记**（module）：
- `core` - 核心管理
- `planning` - 规划
- `execution` - 执行
- `monitoring` - 监控

### 4.3 入库通道选择

**使用1号通道**（本地同步）：
- 关键决策
- 高优先级任务
- 紧急风险
- 需要立即确认的信息

**使用2号通道**（HTTP异步）：
- 大批量会话归档
- 非关键文档整理
- 定期同步操作

---

## 五、项目文档结构

```
documents/PM/                    # 本目录
├── README.md                   # 本文件：项目说明
├── frameworks/                 # 框架文档（待补充）
│   ├── project-dictionary-template.md
│   └── workflow-examples.md
└── CHANGELOG.md                # 变更记录（待创建）

.opencode/agents/               # Agent配置
├── pm-agent.md                # PM-agent主配置
└── pm-clerk.md                # PM-clerk配置
```

---

## 六、集成接口

### 6.1 1号通道（本地函数调用）

```python
from ai_factory.integrations.entries_ingest import entries_ingest

payload = {
    "raw_text": "项目内容...",
    "project_code": "pm-agent",
    "extra_context": {
        "tags_snapshot": {
            "department": ["项目管理部"],
            "planning": ["战略决策"],
            "execution": ["已批准"]
        }
    }
}

result = entries_ingest(payload)
entry_id = result["entries"][0]["entry_id"]
```

### 6.2 2号通道（HTTP API）

```bash
# 提交入库任务
curl -X POST http://121.43.126.173:8001/access/v1/entries/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "task_type": "note",
    "payload": {
      "raw_text": "项目内容...",
      "project_code": "pm-agent"
    },
    "idempotency_key": "unique-key"
  }'

# 查询任务状态
curl http://121.43.126.173:8001/access/v1/jobs/{job_id}
```

### 6.3 RAG检索

```python
# 检索项目决策
query = "type:decision project_code:pm-agent"

# 检索活跃风险
query = "type:risk status:active"

# 检索知识级文档
query = "knowledge_level:knowledge module:core"
```

---

## 七、开发计划

| 阶段 | 任务 | 状态 |
|------|------|------|
| ✅ Phase 1 | Agent配置创建 | 已完成 |
| ⏳ Phase 2 | 最小闭环验证 | 待进行 |
| ⏳ Phase 3 | 项目字典模板 | 待创建 |
| ⏳ Phase 4 | 工作流示例 | 待补充 |
| ⏳ Phase 5 | 与其他Agent集成 | 待开发 |

---

## 八、注意事项

1. **所有知识必须入库**：禁止仅在会话中保存，必须通过1号/2号通道写入entries
2. **标记必须完整**：每条记录必须有完整的scene_tags
3. **定期验证**：定期检查entries记录完整性
4. **字典同步**：项目字典变更需同步更新entries记录

---

## 九、参考文档

- [PM-Framework-v1.0.md](./PM-Framework-v1.0.md) - 项目管理框架总纲
- [Agent-Role-System-v0.1.md](./Agent-Role-System-v0.1.md) - Agent角色系统
- `.opencode/agents/pm-agent.md` - PM-agent配置
- `.opencode/agents/pm-clerk.md` - PM-clerk配置

---

## 八、使用指南

### 8.1 快速开始

**启动PM-agent**：
```
用户: @pm-agent 帮我初始化一个新项目

PM-agent: 我将为您初始化项目...
[调用PM-clerk采集信息]
[写入entries表]
项目初始化完成！项目ID: proj-001
```

**导入项目私域数据**：
```bash
cd /root/ai-factory
python3 scripts/import_project_sessions.py \
  --project YOUR_PROJECT_CODE \
  --operator pm-agent  # 或 pm-clerk
```

### 8.2 注意事项

1. **所有知识必须入库**：禁止仅在会话中保存，必须通过1号/2号通道写入entries
2. **标记必须完整**：每条记录必须有完整的scene_tags（特别是project_code）
3. **项目归属明确**：导入时必须指定正确的project_code，避免数据污染
4. **定期验证**：定期检查entries记录完整性

---

## 九、参考文档

- [PM-Framework-v1.0.md](./PM-Framework-v1.0.md) - 项目管理框架总纲
- [Agent-Role-System-v0.1.md](./Agent-Role-System-v0.1.md) - Agent角色系统
- `.opencode/agents/pm-agent.md` - PM-agent配置
- `.opencode/agents/pm-clerk.md` - PM-clerk配置
- `docs/PROJECT_PRIVATE_DATA_IMPORT.md` - 项目私域导入方案
- `scripts/archived/all_sessions_channel/README.md` - 封存脚本说明

---

## 十、维护信息

**维护者**: PM-agent Team  
**最后更新**: 2026-02-17  
**当前阶段**: Phase 1 已完成，Phase 2 待启动

---

**维护者**: PM-agent Team  
**最后更新**: 2026-02-17
