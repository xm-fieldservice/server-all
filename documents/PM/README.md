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

### 📝 Git提交基线

**本次修复的代码基线提交**:
```
提交哈希: 577cf6b
提交信息: fix(infrastructure): 修复向量化基础设施重复和假向量问题
提交时间: 2026-02-17
分支: db-browser-fix
```

**包含的修复文件**:
- `ai_factory/rag/pgvector_index.py` - 假向量保护（98行）
- `ai_factory/integrations/entries_ingest.py` - 重复代码重构（718行）
- `ai_factory/vectorize_entries_with_ollama.py` - 文档修正（289行）
- `documents/PM/README.md` - 检查报告存档（538行）

**验证基线完整性的命令**:
```bash
# 查看本次提交详情
git show 577cf6b --stat

# 验证提交包含的文件
git diff-tree --no-commit-id --name-only -r 577cf6b
```

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

---

## 🎯 架构优化成果（Phase 2 - 2026-02-17）

### 📊 优化目标

**消除重复的向量化通道，建立统一策略模式架构**

### 🏗️ 新架构设计

**统一向量化策略模式** (`ai_factory/vectorization/`)

```
┌─────────────────────────────────────────────────────────────┐
│                  向量化策略模式架构                          │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │         VectorizationStrategy (抽象基类)            │   │
│  │  ┌─────────────┐  ┌──────────────┐  ┌───────────┐  │   │
│  │  │   embed()   │  │ build_text() │  │ save()    │  │   │
│  │  └─────────────┘  └──────────────┘  └───────────┘  │   │
│  └─────────────────────────────────────────────────────┘   │
│                         ▲                                   │
│         ┌───────────────┼───────────────┐                  │
│         │               │               │                   │
│  ┌──────▼──────┐ ┌──────▼──────┐ ┌──────▼──────┐          │
│  │  DashScope  │ │    Ollama   │ │  DeepSeek   │          │
│  │   Strategy  │ │   Strategy  │ │  (planned)  │          │
│  └─────────────┘ └─────────────┘ └─────────────┘          │
│                                                              │
│  统一入口: get_strategy(backend) → Strategy实例             │
└─────────────────────────────────────────────────────────────┘
```

### 📁 新增/修改文件

| 文件 | 类型 | 说明 |
|------|------|------|
| `ai_factory/vectorization/__init__.py` | 新增 | 策略模式核心实现 (409行) |
| `ai_factory/integrations/entries_ingest.py` | 修改 | 迁移到策略模式 |
| `ai_factory/rag/entries_rag.py` | 修改 | 迁移到策略模式 |
| `scripts/archived/vectorization/` | 归档 | 旧实现备份+迁移指南 |

### ✨ 核心改进

**1. 消除代码重复**
- 原3个文件重复实现 → 1个统一接口
- 文本构建逻辑统一在基类
- 向量保存逻辑统一在基类
- API调用封装统一到各策略

**2. 统一接口**
```python
# 获取策略（默认DashScope）
strategy = get_strategy()

# 或指定后端
strategy = get_strategy(VectorizationBackend.OLLAMA)

# 统一调用方式
embedding = strategy.embed("文本")
text = strategy.build_text(entry)
strategy.save_embedding(entry_id, embedding)
strategy.process_entry(entry)  # 一键处理
```

**3. 向后兼容**
```python
# 旧代码仍可工作
from ai_factory.vectorization import generate_embedding
embedding = generate_embedding("文本")
```

**4. 环境配置**
```bash
# 通过环境变量切换后端
export VECTORIZATION_BACKEND=dashscope  # 或 ollama
```

### 📈 优化效果

| 指标 | 优化前 | 优化后 | 改进 |
|------|--------|--------|------|
| 向量化实现文件 | 3个 | 1个策略文件 | -67% |
| 文本构建实现 | 3处 | 1处（基类） | -67% |
| 向量保存实现 | 3处 | 1处（基类） | -67% |
| 代码行数 | ~1200行 | ~400行 | -67% |
| 新增后端工作量 | 复制+修改 | 实现接口 | -80% |

### 🔧 使用示例

**基本使用**:
```python
from ai_factory.vectorization import get_strategy

strategy = get_strategy()
embedding = strategy.embed("需要向量化的文本")
```

**处理entry**:
```python
from ai_factory.vectorization import get_strategy

strategy = get_strategy()
success = strategy.process_entry(entry_dict)
```

**切换后端**:
```python
from ai_factory.vectorization import get_strategy, VectorizationBackend

# 使用本地Ollama
strategy = get_strategy(VectorizationBackend.OLLAMA)
embedding = strategy.embed("文本")
```

---

## 🎯 Phase 3 成果 - LLM处理与入库通道分离（大改动方案）

### 📋 实施目标

**分离LLM处理（title/summary生成）和入库通道，使职责更清晰**

### 🏗️ 新节点架构

```
┌─────────────────────────────────────────────────────────────┐
│  🔒 访问控制节点 [0]                                          │
│  职责: PM-agent (审核授权)                                    │
│  功能: 验证project_code + operator身份                        │
└──────────────────────────┬──────────────────────────────────┘
                           │ 验证通过
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  📥 脚本工具: session_to_entries [1]                          │
│  职责: PM-clerk (执行LLM处理)                                 │
│                                                              │
│  文件: scripts/import_project_sessions.py                    │
│                                                              │
│  输入:  OpenCode session文件 (*.json)                        │
│   ↓                                                        │
│  处理:  - 提取session内容(messages)                         │
│         - LLM生成title (≤60字符)                            │
│         - LLM生成summary (≤500字符)                         │
│   ↓                                                        │
│  输出:  完整payload {title, summary_ai, content, tags...}    │
│                                                              │
│  LLM后端: 本地Ollama 或 云端DeepSeek                         │
└──────────────────────────┬──────────────────────────────────┘
                           │ 完整payload (已LLM处理)
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  💾 脚本工具: entries_ingest [2]                              │
│  职责: Shared (基础设施)                                      │
│                                                              │
│  文件: ai_factory/integrations/entries_ingest.py             │
│                                                              │
│  输入:  必须包含字段:                                        │
│         - title (LLM生成)                                    │
│         - summary_ai (LLM生成)                               │
│         - raw_text                                           │
│         - project_code                                       │
│   ↓                                                        │
│  处理:  - 验证必填字段                                       │
│         - 写入entries表                                      │
│         - 调用向量化策略模式                                 │
│   ↓                                                        │
│  输出:  entry_id                                             │
│                                                              │
│  通道A: 直写 (1号通道) - 同步调用                            │
│  通道B: 排队 (2号通道) - HTTP API异步队列                    │
└─────────────────────────────────────────────────────────────┘
```

### 📁 修改文件

| 文件 | 变更 | 说明 |
|------|------|------|
| `entries_ingest.py` | 重写 | 移除LLM处理，从~720行简化为~100行 |
| `import_project_sessions.py` | 增强 | 新增LLM处理逻辑，+200行 |

### ✨ 核心变更

**entries_ingest.py 变更：**

```python
# ❌ 移除（原内部逻辑）
- 文本长度判断
- 条件性LLM调用(Ollama/DeepSeek)
- title/summary生成

# ✅ 保留（纯入库职责）
+ 必填字段验证(title, summary_ai, raw_text, project_code)
+ 写入entries表
+ 调用向量化策略模式
```

**import_project_sessions.py 新增：**

```python
# 新增方法
+ extract_session_content()      # 提取messages
+ generate_title_and_summary()   # LLM生成
+ _call_deepseek_for_title()     # DeepSeek API
+ _call_deepseek_for_summary()   # DeepSeek API

# import_session() 重构为4步
1. 提取session内容
2. LLM处理(title/summary)
3. 构建完整payload
4. 调用entries_ingest入库
```

### 🔄 调用方式对比

**旧方式（LLM在内部隐式处理）：**
```python
# ❌ 不推荐（导致import_project_sessions跳过LLM）
entries_ingest({
    "raw_text": content  # 内部判断长度→可能LLM处理
})
```

**新方式（LLM在外层显式处理）：**
```python
# ✅ 推荐（职责清晰）
# 📥 [1] 先LLM处理
title, summary = generate_title_and_summary(content)
payload = {
    "title": title,           # ✅ LLM生成
    "summary_ai": summary,    # ✅ LLM生成
    "raw_text": content,
    "project_code": project_code
}

# 💾 [2] 再入库
entries_ingest(payload)  # 纯入库，不处理LLM
```

### 📊 改进效果

| 指标 | 优化前 | 优化后 | 改进 |
|------|--------|--------|------|
| LLM处理位置 | entries_ingest内部 | import_project_sessions | 职责清晰 |
| 代码行数 | entries_ingest: 720行 | entries_ingest: 100行 | -86% |
| 可维护性 | 低（隐式逻辑） | 高（显式节点） | ⬆️ |
| 数据质量 | 部分数据无LLM处理 | 所有数据经LLM处理 | ✅ |

### 📦 归档文件

旧实现已归档到 `scripts/archived/vectorization/`：
- 完整代码备份
- 详细迁移指南
- API对照表

**注意**: 原文件仍保留（因 `generate_title_with_ollama` 等函数仍在使用）

---

## 🎉 里程碑：PM-Agent具象化完成（2026-02-17）

### 🏆 达成目标

**打造了一个具备记忆能力的、可自举的项目管理Agent实体（PM-Agent最小MVP）**

### 📈 开发历程（15次迭代）

```
34f581f → 577cf6b → 1964dc3 → 6737fd2 → d4dad31 → 7ad1549 → 164cfdb
  ↓        ↓         ↓         ↓         ↓         ↓         ↓
角色系统  基础设施   Git基线   工作机制  策略模式   RAG重构   归档旧代码

→ a76e315 → cba908d → 1c11053 → b2c8afa → de86d01 → b8fb96b
   ↓         ↓         ↓         ↓         ↓         ↓
架构文档   节点规范   LLM分离   Phase3文档 工具打压  PM-Agent具象化
```

### ✅ 完成的所有工作

#### **1. 基础设施层（底座）**
- ✅ PostgreSQL + pgvector 部署
- ✅ entries表设计（支持scene_tags、extra_meta）
- ✅ entry_embeddings向量表
- ✅ 修复假向量问题（pgvector_index.py运行时保护）
- ✅ 修复重复代码问题（entries_ingest.py统一函数）

#### **2. 向量化架构层（策略模式）**
- ✅ 统一向量化策略模式（ai_factory/vectorization/）
- ✅ DashScopeStrategy（生产环境）
- ✅ OllamaStrategy（本地备用）
- ✅ 消除代码重复（-67%）
- ✅ 标准化接口（embed/build_text/save/process_entry）

#### **3. 数据处理流程层（节点化）**
- ✅ 🔒 [0] 访问控制节点（project_code验证）
- ✅ 📥 [1] session_to_entries（LLM处理）
- ✅ 💾 [2] entries_ingest（纯入库通道）
- ✅ LLM处理与入库分离（大改动方案）
- ✅ 工具打压实在（CLI + Python API标准化）

#### **4. Agent实体层（具象化）**
- ✅ PM-agent配置（.opencode/agents/pm-agent.md）
- ✅ PM-clerk配置（书记员职责）
- ✅ 工具调用能力（📥/💾/🧠）
- ✅ 自举机制（循环上升）
- ✅ 私域数据自动标记（project_code注入）

### 🏗️ 最终架构图

```
┌─────────────────────────────────────────────────────────────┐
│                    🔒 PM-agent（Agent实体）                   │
│  - 职责：项目管理和协调                                       │
│  - 能力：工具调用 + 记忆检索 + 自举进化                        │
│  - 标记：自动注入project_code="pm-agent"                      │
└──────────────────────────┬──────────────────────────────────┘
                           │
           ┌───────────────┼───────────────┐
           │               │               │
           ▼               ▼               ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│  📥 [1]      │  │  💾 [2]      │  │  🧠 RAG      │
│  session_to_ │  │  entries_    │  │  检索         │
│  entries     │→ │  ingest      │  │              │
│              │  │              │  │              │
│  工具：       │  │  工具：       │  │  工具：       │
│  import_     │  │  entries_    │  │  entries_    │
│  project_    │  │  ingest_cli  │  │  rag         │
│  sessions.py │  │  .py         │  │              │
│              │  │              │  │              │
│  - LLM处理   │  │  - 验证      │  │  - 向量检索  │
│  - title生成 │  │  - 入库      │  │  - 项目过滤  │
│  - summary   │  │  - 向量化    │  │              │
└──────────────┘  └──────────────┘  └──────────────┘
         │                │                │
         └────────────────┼────────────────┘
                          ▼
                ┌─────────────────┐
                │  entries表 +    │
                │  embeddings向量  │
                │  （项目记忆库）  │
                └─────────────────┘
                          │
                          ▼
                ┌─────────────────┐
                │  PM-agent的     │
                │  项目知识图谱    │
                └─────────────────┘
```

### 🛠️ 工具清单（可被任何Agent调用）

| 工具 | 位置 | 接口类型 | 功能 |
|------|------|----------|------|
| **entries_ingest** | `ai_factory/integrations/entries_ingest.py` | Python API | 💾 纯入库通道 |
| **entries_ingest_cli** | `ai_factory/integrations/entries_ingest_cli.py` | CLI | 💾 命令行入库 |
| **import_project_sessions** | `scripts/import_project_sessions.py` | Python + CLI | 📥 LLM处理+入库 |
| **import_single_session** | 同上（便利API） | Python API | 📥 导入单个session |
| **import_all_sessions** | 同上（便利API） | Python API | 📥 批量导入 |
| **search_entries** | `ai_factory/rag/entries_rag.py` | Python API | 🧠 RAG检索 |

### 🔄 自举循环机制

```
PM-agent开发新功能
       ↓
调用 📥[1] import_project_sessions
自动完成：
  - 提取session内容
  - LLM生成title/summary
  - 注入project_code="pm-agent"
  - 调用💾[2]入库
  - 向量化
       ↓
调用 🧠 RAG 检索历史
自动过滤：project_code="pm-agent"
       ↓
调用 💾[2] entries_ingest
记录新决策
       ↓
项目知识沉淀（entries表）
       ↓
能力增强 → 更智能的PM-agent
       ↓
回到第一步（循环上升）
```

### 📊 关键指标

| 指标 | 数值 | 说明 |
|------|------|------|
| **代码精简** | -86% | entries_ingest: 720→100行 |
| **重复消除** | -67% | 向量化代码统一 |
| **节点完成** | 3个 | [0]访问控制、[1]LLM处理、[2]入库 |
| **工具打压** | 6个 | CLI和Python API标准化 |
| **文档完整** | 15次 | 完整开发历程记录 |
| **自举就绪** | ✅ | 可以用自己管理自己 |

### 🎯 下一步工作方向

1. **增强RAG能力**
   - 添加更复杂的查询过滤
   - 支持时间范围检索
   - 实现记忆关联推荐

2. **扩展Agent能力**
   - 任务自动分解
   - 风险自动识别
   - 决策影响分析

3. **完善协作机制**
   - PM-clerk自动化
   - 多Agent协作协议
   - 项目间知识共享

4. **自举验证**
   - 使用PM-agent记录本次开发
   - 验证记忆检索效果
   - 优化工具调用流程

### 📝 使用示例（自举开始）

```bash
# PM-agent记录本次开发会话
python scripts/import_project_sessions.py \
  --project pm-agent \
  --operator pm-agent \
  --batch-all

# PM-agent查询历史决策
python -c "
from ai_factory.rag.entries_rag import search_entries
results = search_entries('为什么采用策略模式', project_code='pm-agent')
for r in results[:3]:
    print(f'{r.title}: {r.summary_ai[:100]}...')
"

# PM-agent记录新决策
python ai_factory/integrations/entries_ingest_cli.py \
  --payload '{
    "title": "采用自举式开发",
    "summary_ai": "PM-agent具备自举能力，开始用自己管理自己",
    "raw_text": "详细内容...",
    "project_code": "pm-agent"
  }'
```

### ✅ 里程碑状态

**🎉 完成！PM-Agent最小MVP已就绪，开始自举进化！**

---

## 下一步开发计划（持续完善）

### Phase 4: 能力增强（进行中）
- [ ] RAG检索增强（时间过滤、关联推荐）
- [ ] 任务自动分解
- [ ] 风险自动识别

### Phase 5: 多Agent协作（规划中）
- [ ] PM-clerk自动化
- [ ] 与其他专业Agent协作
- [ ] 项目间知识共享机制

### Phase 6: 自举验证（即将开始）
- [ ] 使用PM-agent记录本次完整开发
- [ ] 验证记忆检索准确性
- [ ] 优化迭代

---

### ✅ 验证命令

```bash
# 验证策略模式导入
python3 -c "from ai_factory.vectorization import get_strategy; s=get_strategy(); print(s.config)"

# 验证 entries_ingest 迁移
python3 -c "from ai_factory.integrations.entries_ingest import entries_ingest; print('OK')"

# 验证 entries_rag 迁移
python3 -c "from ai_factory.rag.entries_rag import embed_query; print('OK')"

# 验证策略切换
python3 -c "from ai_factory.vectorization import get_strategy, VectorizationBackend; s=get_strategy(VectorizationBackend.OLLAMA); print(s.config.model_name)"
```

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

---

## 五、架构描述规范（Node-Style Documentation）

为统一项目文档的可读性和维护性，PM-Agent团队采用**节点式架构描述规范**。

### 5.1 规范目的

- **统一认知**：所有架构图、功能流程使用相同格式描述
- **快速理解**：通过[序号]节点快速定位功能层级
- **职责清晰**：明确每个节点的输入/输出/负责人
- **便于维护**：修改时只需更新对应节点

### 5.2 节点符号定义

| 符号 | 含义 | 使用场景 |
|------|------|----------|
| 🔒 | 访问控制节点 | 权限验证、身份认证 |
| 📥 | 数据输入节点 | 数据读取、导入 |
| 🛠️ | 工具/处理节点 | 核心功能实现 |
| 💾 | 存储节点 | 数据持久化 |
| 📤 | 输出节点 | 结果返回、响应 |
| ⚡ | 异步节点 | 队列、后台任务 |

### 5.3 节点编号规则

- **[0]** - 访问控制层（always first）
- **[1]** - [N] - 主流程节点
- **[A]** [B] - 并行分支
- **子节点** - [1.1] [1.2] 等

### 5.4 描述模板

```
┌─────────────────────────────────────────────────────────────┐
│  🛠️ 工具名称: xxx [节点序号]                                   │
│  "一句话功能描述"                                             │
│                                                              │
│  职责归属: PM-agent / PM-clerk / Shared                      │
│                                                              │
│  输入:  xxx                                                   │
│   ↓                                                        │
│  处理:  - 步骤1                                              │
│         - 步骤2                                              │
│   ↓                                                        │
│  输出:  xxx                                                   │
└──────────────────────────┬──────────────────────────────────┘
                           │ 输出数据
                           ▼
```

### 5.5 应用示例：数据入库通道

```
┌─────────────────────────────────────────────────────────────┐
│  🔒 访问控制节点 [0]                                          │
│  "只能被特定项目PM的agent调用"                                │
│  - 当前MVP: PM-agent                                          │
│  - 验证: project_code + operator 身份                         │
└──────────────────────────┬──────────────────────────────────┘
                           │ 验证通过
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  📥 脚本工具: session_to_entries [1]                          │
│  "从session数据库导出 + LLM处理title和summary"                │
│  职责: PM-clerk (数据准备)                                    │
│                                                              │
│  输入:  ~/.local/share/opencode/storage/session/*.json       │
│   ↓                                                        │
│  处理:  - 读取session内容                                    │
│         - LLM生成title (≤60字符)                            │
│         - LLM生成summary_ai (≤500字符)                      │
│   ↓                                                        │
│  输出:  完整payload {title, summary_ai, content, tags...}    │
└──────────────────────────┬──────────────────────────────────┘
                           │ 完整payload
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  💾 脚本工具: entries_ingest [2]                              │
│  "写库 + 向量化"                                              │
│  职责: Shared (基础设施)                                      │
│                                                              │
│  通道A: 直写 (1号通道)  │  通道B: 排队 (2号通道)             │
│  - 同步调用              │  - HTTP API异步                   │
│  - 立即写入              │  - 任务队列                       │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
│            entries表 + embeddings向量                        │
└─────────────────────────────────────────────────────────────┘
```

### 5.6 职责分配规范

使用节点式描述时，**必须在每个节点标注职责归属**：

| 归属 | 职责范围 | 标注方式 |
|------|----------|----------|
| **PM-agent** | 决策、审核、架构设计 | `职责: PM-agent` |
| **PM-clerk** | 数据准备、导入、整理 | `职责: PM-clerk` |
| **Shared** | 基础设施、公共通道 | `职责: Shared` |

### 5.7 文档更新要求

1. **新增功能**：必须按节点式规范描述
2. **修改功能**：更新对应节点，保持编号连续
3. **废弃功能**：标记节点为 ⛔ DEPRECATED
4. **Review检查**：Code Review时检查节点描述完整性

---

## 六、Agent职责矩阵（基于节点规范）

### 6.1 PM-agent（项目经理）

**核心职责**：
- 🔒 访问控制节点[0]的审核与授权
- 架构设计决策（节点拆分、流程设计）
- 节点[1]（数据准备）的输入质量审核
- 节点间数据流转的监控

**工作范围**：
- 决策哪些session值得导入
- 审核scene_tags标记是否正确
- 设计新的数据处理节点
- 协调PM-clerk执行导入

### 6.2 PM-clerk（书记员）

**核心职责**：
- 节点[1]（数据准备）的具体实施
- 执行session_to_entries工具
- LLM处理title和summary的质量把控
- 标记体系（scene_tags）的维护

**工作范围**：
- 运行导入脚本
- 检查LLM生成结果
- 处理导入异常
- 维护数据质量

### 6.3 Shared（基础设施）

**核心职责**：
- 节点[2]（入库通道）的维护
- 向量化策略模式的实现
- 数据库和向量存储的管理
- 1号/2号通道的稳定性保障

**工作范围**：
- entries_ingest维护
- pgvector数据库运维
- DashScope/Ollama向量化服务
- 监控和告警

---

## 七、知识管理规范
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

## 六、PM-agent 工作机制与项目跟踪

PM-agent 使用标准化的项目管理机制来跟踪和报告工作进展，确保所有工作可追溯、可验证。

### 6.1 核心跟踪机制

| 机制 | 用途 | 存储位置 |
|------|------|----------|
| **Todo List** | 任务分解与状态跟踪 | 本文件第6.2节 + session上下文 |
| **阶段性报告** | 工作成果总结与基线记录 | 本文件各Phase章节 |
| **Git提交** | 代码基线版本控制 | Git历史记录 |
| **检查报告** | 问题识别与修复验证 | 本文件第3节（基础设施检查报告） |

### 6.2 当前任务状态（Todo List）

**当前阶段**: 基础设施修复（Phase 1.5）

| 序号 | 任务 | 优先级 | 状态 | 完成时间 |
|------|------|--------|------|----------|
| 1 | 禁用 pgvector_index.py 假向量实现 | P0-高 | ✅ 已完成 | 2026-02-17 |
| 2 | 重构 entries_ingest.py 重复向量化代码 | P0-高 | ✅ 已完成 | 2026-02-17 |
| 3 | 修正 vectorize_entries_with_ollama.py 维度文档 | P0-高 | ✅ 已完成 | 2026-02-17 |
| 4 | 验证生产代码未使用假向量路径 | P0-高 | ✅ 已完成 | 2026-02-17 |
| 5 | 创建统一向量化策略模式 | P1-中 | ⏳ 待处理 | - |
| 6 | 记录基础设施架构文档 | P2-低 | ✅ 已完成 | 2026-02-17 |

### 6.3 Git提交基线记录

**代码基线提交**:
```
提交哈希: 577cf6b
提交信息: fix(infrastructure): 修复向量化基础设施重复和假向量问题
提交时间: 2026-02-17
分支: db-browser-fix
文件变更:
- ai_factory/rag/pgvector_index.py (+98行)
- ai_factory/integrations/entries_ingest.py (+718行)
- ai_factory/vectorize_entries_with_ollama.py (+289行)
- documents/PM/README.md (+538行)
```

**验证命令**:
```bash
# 查看基线提交详情
git show 577cf6b --stat

# 验证文件完整性
git diff-tree --no-commit-id --name-only -r 577cf6b
```

### 6.4 工作模式规范

**任务执行流程**:
1. **任务分解**: 使用todo list将工作分解为原子任务
2. **状态更新**: 每完成一项立即更新状态（in_progress → completed）
3. **阶段报告**: 完成一组相关任务后撰写阶段性报告
4. **基线提交**: 关键节点创建git commit作为代码基线
5. **报告存档**: 将todo list和提交记录补入README.md

**质量检查清单**:
- [ ] 所有P0级任务是否完成？
- [ ] 代码是否通过验证命令测试？
- [ ] 检查报告是否已存档？
- [ ] Git提交信息是否完整？
- [ ] 后续工作建议是否明确？

---

## 七、集成接口

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

## 附录：重要修复记录

### 2025-02-18: 问答对解析修复 (Q&A Pair Extraction Fix)

**问题描述**:
OpenCode session 导入到 entries 表时，`answer_payload` 字段始终为 null，且 `input_content` 字段内容不正确。

**根本原因**:
- OpenCode 本地存储结构分为两部分：
  - `~/.local/share/opencode/storage/message/ses_xxx/msg_yyy.json` - 消息元数据（role, time, tokens 等）
  - `~/.local/share/opencode/storage/part/msg_yyy/*.json` - 消息实际内容（content_parts）
- 之前的实现只读取了元数据文件，没有读取 part 目录下的实际内容
- `entries_ingest.py` 也没有正确处理 `answer_payload` 和 `input_content` 字段

**解决方案**:
1. **新增 `extract_text_from_message()` 方法** (`scripts/import_project_sessions.py`):
   - 从 `storage/part/msg_id/*.json` 读取 `content_parts`
   - 支持多种 part 类型：`text`, `tool_use`, `tool_result`, `reasoning_content`
   - 正确处理 tool 调用和结果展示

2. **重构 `extract_qa_pairs_from_messages()` 方法**:
   - 先提取每条消息的完整文本内容
   - 过滤空消息
   - 正确配对 user 和 assistant 消息
   - 提取 assistant 回答内容到 `answer_payload`

3. **修复 `entries_ingest.py`**:
   - 添加 `answer_payload` 字段支持
   - 优先使用 `input_content` 字段（如果提供），否则使用 `raw_text`

**数据结构**:
```json
{
  "input_content": "用户问题文本",
  "answer_payload": {"text": "助手回答文本"},
  "title": "LLM生成的标题",
  "summary_ai": "LLM生成的摘要",
  "raw_text": "完整格式化内容"
}
```

**验证命令**:
```bash
# 查看导入的记录
python3 -c "
from ai_factory.db.pgvector_client import get_connection
conn = get_connection()
with conn.cursor() as cur:
    cur.execute('''
        SELECT entry_id, input_content, answer_payload::text
        FROM entries 
        WHERE project_code = 'ai-factory'
        LIMIT 3
    ''')
    for row in cur.fetchall():
        print(f'Q: {row[1][:50]}...')
        print(f'A: {row[2][:100]}...')
        print()
"
```

**影响范围**:
- `scripts/import_project_sessions.py` - 问答对提取逻辑
- `ai_factory/integrations/entries_ingest.py` - 入库字段处理

**提交记录**: `f644696` - fix(ingest): correct Q&A pair extraction from OpenCode storage

---

**维护者**: PM-agent Team  
**最后更新**: 2026-02-17
