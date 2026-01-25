# Agent记忆系统_V4.0_通用知识底座与世界接口设计方案

**文档版本**：v4.0（通用知识底座与世界接口设计）  
**创建时间**：2026-01-24  
**基线版本**：`Agent记忆系统完整设计与实施文档_V3.1.1完备版.md`（PostgreSQL + pgvector）  
**适用范围**：AI 工厂内的记忆系统、知识底座与外部世界接口  

**架构关联说明:**
- 🏗️ **底层依赖**: 本方案完全构建在 [Agent记忆系统完整设计与实施文档_V3.1.1完备版.md](./Agent记忆系统完整设计与实施文档_V3.1.1完备版.md) 定义的物理存储和 RLS 安全基线之上，保持向下兼容。
- 🔮 **演进目标**: 本文档负责将原有的“Agent 记忆系统”升维为“通用知识工厂（Knowledge Factory）”，通过引入万能接口（World Ingress）和知识再生产层，实现全场景数据集成。

---

## 目录

1. [设计目标与增量范围](#1-设计目标与增量范围)  
2. [与 V3.1.1 的兼容策略](#2-与-v311-的兼容策略)  
3. [去 Agent 中心化：Namespace / SourceIdentifier 模型](#3-去-agent-中心化namespace--sourceidentifier-模型)  
4. [动态分类系统：路径式命名空间与标签](#4-动态分类系统路径式命名空间与标签)  
5. [四要素接入模型：Note / QA / File / Workflow](#5-四要素接入模型note--qa--file--workflow)  
6. [工作流追踪：人-人 / 人-机 / 机-机交互模型](#6-工作流追踪人-人--人-机--机-机交互模型)  
7. [知识再生产：KnowledgeOperationLayer 设计](#7-知识再生产knowledgeoperationlayer-设计)  
8. [跨源查询层：查询路由与权限感知聚合](#8-跨源查询层查询路由与权限感知聚合)  
9. [服务划分与对外接口](#9-服务划分与对外接口)  
10. [迁移与实施计划](#10-迁移与实施计划)  
11. [风险评估](#11-风险评估)  

---

## 1. 设计目标与增量范围

### 1.1 总体目标

在 V3.1.1 的多租户记忆系统基础上，将记忆系统升级为面向“通用知识底座 + 世界接口”的统一平台，满足：

1. **去 Agent 中心化**：不再以“某个具体 Agent 实例”为唯一一等公民，而是抽象出 **通用的来源命名空间（Namespace）与来源标识（SourceIdentifier）**。
2. **通用接入模型**：用 **Note / QA / File / Workflow** 四种标准节点契约，承载绝大部分知识与交互形态。
3. **全链路工作流追踪**：能够统一记录 **人-人 / 人-机 / 机-机** 的交互与工作流运行轨迹，并与知识条目关联。
4. **跨源查询与聚合**：构建独立的 **跨源查询层（Query Router）**，在保持 RLS 安全基线的前提下，支持按身份、命名空间与标签进行动态聚合。
5. **知识再生产**：引入 **KnowledgeOperationLayer**，为数据挖掘、聚类、链路分析和高质量摘要提供结构化承载。
6. **动态分类与命名空间**：引入无限层级的路径式命名空间与标签系统，支持长期演进和跨应用的统一视图。

### 1.2 增量范围说明

- **保持不变的部分**  
  - 物理存储：PostgreSQL + pgvector。  
  - 核心表：`entries` / `entry_embeddings` / `chat_sessions` / `chat_messages` / `qa_query_index`。  
  - 四层隔离与 RLS：`user_id + agent_type + agent_instance_id + section_id` 作为生产标准保留。

- **新增/重构的层次（逻辑与新表）**
  1. **概念重构**：将 `agent_type` 语义上升级为 `namespace`；将 `agent_instance_id` 语义上升级为 `source_identifier`。
  2. **契约层**：定义 Note / QA / File / Workflow 的标准数据契约，以 JSON 约定落在 `extra_meta` / `scene_tags` 中。
  3. **追踪与运维层**：新增工作流运行与交互追踪表。  
  4. **知识再生产层**：新增 `knowledge_operations` / `knowledge_relations` 等表。  
  5. **查询路由层**：定义 Query Router 的逻辑模型与接口。

---

## 2. 与 V3.1.1 的兼容策略

### 2.1 存储结构兼容

1. **`entries` 表**  
   - 不删除、不重命名任何现有字段。继续使用 V3.1.1 的表结构与索引、RLS 策略。
   - V4 引入的新语义通过 **字段约定** 与 **新增 JSON key** 完成，不强制 DDL 变更。

2. **`entry_embeddings` 表**  
   - 保持字段与向量索引不变。RLS 继续使用 `user_id + agent_type + agent_instance_id`。

### 2.2 新旧概念映射

| 维度           | V3.1.1 名称          | V4.0 名称（语义）             | 说明 |
|----------------|----------------------|-------------------------------|------|
| 隔离层 1       | `user_id`            | `user_id` / `tenant_id`       | 保持不变 |
| 隔离层 2       | `agent_type`         | `namespace`                   | 从“Agent 类型”提升为“来源命名空间” |
| 隔离层 3       | `agent_instance_id`  | `source_identifier`           | 从“Agent 实例”提升为“来源标识” |
| 隔离层 4       | `section_id`         | `section_id`（议题/会话）     | 保持不变 |

---

## 3. 去 Agent 中心化：Namespace / SourceIdentifier 模型

### 3.1 Namespace 定义

**Namespace（来源命名空间）**：
- 字符串，推荐采用 **路径式** 语法，使用 `/` 分隔层级。  
- 示例：`agent/recruiting`, `app/wechat-note`, `world/github`, `infra/jenkins`。

**SourceIdentifier（来源标识）**：
- 标识同一 Namespace 下的一个具体来源实例（如某个具体的微信用户、某个 GitHub 仓库）。

---

## 4. 动态分类系统：路径式命名空间与标签

在 `entries.scene_tags` 中增加标准 key：

```jsonc
{
  "category_path": ["工作", "AI工厂", "记忆系统", "V4设计"],
  "tags": ["memory", "world-interface"],
  "source": "wechat-note",
  "topic_ns": "work/ai-factory/memory/v4"
}
```

---

## 5. 四要素接入模型：Note / QA / File / Workflow

### 5.1 标准节点契约 (NodePayload)
定义统一的 JSON 结构存储在 `extra_meta.node_payload`：

- **Note**: 承载 Markdown 笔记与碎片知识。
- **QA**: 承载问题与答案对。
- **File**: 承载外部文件引用（file_id）与文本切片（chunk_entry_ids）索引。
- **Workflow**: 承载一次工作流运行的元数据与输入输出关联。

---

## 6. 工作流追踪：交互模型

### 6.1 新增表结构

- **`identities`**: 统一表示交互双方（人类、Agent、外部服务）。
- **`workflow_runs`**: 记录工作流的触发、状态与起止时间。
- **`workflow_events`**: 记录交互细节（人-机对话、LLM 调用结果、工具调用记录）。

---

## 7. 知识再生产：KnowledgeOperationLayer

- **`knowledge_operations`**: 记录“钱生钱”的过程（聚类、摘要、关系发现）。
- **`knowledge_relations`**: 记录知识点之间的关联（类似于知识图谱的边）。

---

## 8. 跨源查询层：Query Router

设计独立的查询路由器，支持按 `QueryContext` 进行动态聚合。Query Router 会根据权限范围，横跨多个 Namespace 检索数据并归一化评分后返回。

---

## 9. 服务划分

- `NamespaceService`: 路由与策略管理。
- `NodeIngestService`: 万能接入适配（Note/QA/File/Workflow）。
- `QueryRouterService`: 跨源聚合检索。
- `WorkflowTraceService`: 全链路追踪。
- `KnowledgeOpsService`: 运营与挖掘。

---

## 10. 风险评估与缓解

- **概念混淆风险**：通过在代码层强制使用 `namespace` 术语来缓解物理层 `agent_type` 的陈旧语义。
- **性能挑战**：跨源聚合查询需要设计好超时与降级策略。
