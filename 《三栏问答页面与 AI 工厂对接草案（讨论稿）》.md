我先把“对接草案”整理成一份可以给项目经理看的 Markdown 结构化说明，重点包括：  
- 整体目标与范围  
- 分阶段方案（输入规整、问答、脑图投射）  
- 清晰的接口草案（入参/出参）  
- 三栏应用侧 vs AI 工厂侧的任务拆分清单  

这份草案只停留在设计层面，不改任何代码，你可以直接复制到《项目总体说明》或新文档里，与项目经理一起评审和细化。

下面是一份可以直接给 AI 工厂项目经理看的**对接草案**，你可以放到《项目总体说明》后面，或者新建一个文档。

---

# 三栏问答页面与 AI 工厂对接草案（讨论稿）

> 版本：草案  
> 范围：只讨论“问答窗口/三栏页面”和 AI 工厂的对齐方案，不涉及整体广义知识库落地细节。

---

## 1. 对齐目标与边界

### 1.1 总体目标

- **目标**：  
  将现有“三栏问答页面”升级为 **AI 工厂的一个标准前台入口**：
  - 输入侧：一切自然语言输入，在写入知识库前先经过一组 Agent 做“规整＋打标签＋空间标记”，为向量化和后续业务解析做准备。
  - 问答侧：用户提问统一走 AI 工厂的 RAG / Agent 能力，由 AI 工厂负责召回、推理、写库。
  - 展示侧：把回答和召回结果**结构化投射**到右侧脑图栏，不改变原有“脑图栏”设计初衷。

- **不做的事**（本草案范围外）：
  - 不讨论整体广义知识库所有模块的实现细节。
  - 不讨论业务事实层（`biz.*` 表）和具体报销/工资等业务逻辑。
  - 不要求一次性迁移全部既有“服务器血库”数据，可阶段性迁移。

### 1.2 三栏页面的角色边界

- **三栏页面负责**：
  - 提供统一的用户输入入口（流水＋问题）。
  - 显示规整结果、问答结果和脑图投射。
  - 调用后端提供的少量标准接口，不直接访问数据库或向量库。

- **AI 工厂负责**：
  - 组织 Agent 链：标题生成、摘要生成、自动打标签、空间标记、问答、脑图投射等。
  - 统一访问本地数据库（`entries`、chunk/向量表、`map_snapshots` 等）。
  - 提供给应用工程的**高层接口**（integrations 层，而不是散落的函数）。

### 1.3 本项目职责收缩说明（与历史实现对比）

- 历史上，本项目同时承担：
  - 原始素材的存储与部分切块；
  - 标签/分组体系的维护；
  - 问答调用与结果展示；
  - 与服务器端知识库/血库的直连读写.
- 接入 AI 工厂后，本项目将逐步**收缩到以下职责**：
  - 提供问答与脑图的交互界面（三栏 UI）。
  - 基于 AI 工厂给出的结构化结果做可视化（中栏回答、右栏脑图）。
  - 维护本项目自己的“货架视图”（标签体系与视图定义），作为 AI 工厂货架的一种前台呈现方式.
- 原始素材的切块、标题/摘要生成、底层标记与存储，将逐步由 AI 工厂统一承担，本项目不再重复实现一套“小型知识库 + 向量检索”。

---

## 2. 目标数据流（从输入到脑图）

### 2.1 概览

**一条典型流程**可以描述为：

1. 用户在三栏左侧输入自由文本（流水 / 记录 / 想法等）。
2. 前端调用“输入规整 API”，由 AI 工厂内部的 Agent 链：
   - 生成标题（Title）
   - 生成概述（Summary）
   - 必要时规整原文（Normalization）
   - 写入 `entries` 表，为向量化做准备.
3. 用户在中间栏发出问题（RAG 问句）。
4. 后端调用“问答 API”（AI 工厂网关），由 AI 工厂：
   - 基于 `entries` + 向量库做召回；
   - 调用问答 Agent 生成答案；
   - 将问答过程和结果按需写入 `entries` / 评测流水.
5. 问答 API 返回：
   - 结构化回答（answer）；
   - 命中的 entries / chunks 列表（citations）。
6. 前端根据 citations：
   - 中间栏展示回答；
   - 右栏把命中内容结构化投射为“脑图视图”（可以通过 Agent 或规则生成）。
7. 如果用户希望保存当前脑图视图：
   - 调“脑图快照 API”，AI 工厂写入 `map_snapshots` 表.

---

### 2.X 数据库与知识库双轨策略（过渡期）

- 过渡阶段，本项目仍保留既有“服务器端知识库/血库”的读写能力，以保障现网稳定.
- 同时，引入本地 AI 工厂数据库（`entries` + 向量表 + `map_snapshots`）作为**新知识库底座**.
- 通过应用内部的 `QA Service` 抽象，在配置层面控制：
  - `QA_BACKEND = "legacy"` 时：继续走服务器端知识库；
  - `QA_BACKEND = "ai_factory"` 时：改由 AI 工厂负责入库与问答.
- 后续根据稳定性评估与迁移进度，逐步从 `legacy` 切换到 `ai_factory`，但旧逻辑不会立即删除，而是作为备用路径保留一段时间.

## 3. 分阶段实施方案

### 阶段 1：输入规整 + 写入 entries（为向量化做准备）

**目标**：
一切“进入知识库的文字”，都必须先经过一组 Agent 做规整，再写入 `entries`.

- **Agent 链（AI 工厂内部，建议放在 `ai_factory.agents.entry_agents`）**：
  - **Title Agent**：生成规范化标题 `title_ai`.
  - **Summary Agent**：生成高信息密度的 `summary_ai`.
  - **（可选）Normalization Agent**：规整原文文本（统一格式，去噪）。

- **v0 实现约定**：
  - 前期不追求复杂的空间标记与业务解析，仅实现：
    - 原始文本的基础切块；
    - 简单标题/摘要生成（可从现有实现开始，逐步增强）；
    - 将结果写入本地 `entries` 表.
  - 本阶段的目标是：**所有新产生的文字，优先在本地 AI 工厂知识库中形成可检索的记录**，而不是一次性重构所有历史数据.

- **写库逻辑（`ai_factory.db.entries_repo`）**：
  - 根据规整结果写入 `entries` 表：
    - `entry_id`
    - `title` / `title_ai`
    - `summary_ai`
    - `content`（原文或规整后的原文）
    - 基础元数据：`created_at`, `project_code`, `user_id` 等

- **三栏应用侧改动**：
  - 左栏输入完成后，不直接写任意库，而是调用：
    - `POST /api/entries/ingest`（实际由 AI 工厂 integrations 层实现）。

### 阶段 2：自动打标签 + 空间标记

**目标**：
让每条 entries 在进入知识库时，尽量自带基本的“位置”和“标签”，为脑图、RAG 过滤、业务解析打基础.

- **新增加的 Agent（AI 工厂内部）**：
  - **SpaceType Agent**：
    - 给出建议的 `space_type`（goal/strategy/plan/project/task/topic/note/...）。
    - 在可能的情况下给出 `parent_entry_id` 建议.
  - **Tagging Agent**：
    - 提取主题标签、领域标签、优先级/重要度等，写入 `extra_meta` 或 `sixw_json`.
  - **（可选）Business Hint Agent**：
    - 标出“可能包含业务事件”的 entries，为后续映射到 `biz.*` 表做准备.

- **写库逻辑**：
  - 同样通过 `entries_repo`，在写入时一并保存这些字段.

- **三栏应用侧改动**：
  - 不需要理解这些字段的细节，只需要在合适的 UI（如右侧树/脑图/属性面板）展示系统建议，并允许人工修正（修正再调用一个更新接口）。

### 阶段 3：问答 + 召回 + 脑图投射

**目标**：
把当前问答能力接入 AI 工厂，使三栏仅作为展示层.

- **问答链（AI 工厂内部）**：
  - 模块：`ai_factory.integrations.qa_gateway`（建议新增）
  - 内部流程：
    1. 接收 `question_text` + 上下文（项目、选中 entry、用户等）。
    2. 调用 `ai_factory.rag.rag_pipeline.search(...)` 做向量检索.
    3. 构造 prompt / context，由问答 Agent 生成 `answer`.
    4. 将必要信息（问题、回答）写入 `entries` 或评测流水（可选）。

- **脑图投射**：
  - 输入：一组命中的 entries / chunks（含 `entry_id`, `space_type`, `parent_entry_id` 等）。
  - 处理方式（两种可选）：
    - 规则型：前端或后端用简单规则根据 parent/space_type 生成树状图.
    - Agent 型：专用 `MindmapProjectionAgent` 把命中内容总结成一个局部脑图结构（nodes/edges），必要时写入 `map_snapshots`.
  - 输出：用于前端脑图组件渲染的数据结构.

- **三栏应用侧改动**：
  - 中间栏问答调用：
    - `POST /api/qa/ask` → 内部转发给 `qa_gateway.answer_query`.
  - 右栏脑图：
    - 使用 `qa/ask` 返回的 citations 直接构建脑图；
    - 或额外调用一个 `GET /api/mindmap/from-qa?trace_id=...`.

---

## 4. 接口草案（面向应用工程）

> 这里列的是“应用工程看到的 API 形态”，具体内部实现由 AI 工厂负责. 命名仅为草案，可与项目经理一起调整.

### 4.1 输入规整接口：`entries_ingest`

- **用途**：
  左栏输入完成后，规范化写入本地知识库，为后续 RAG 使用.

- **请求（示意）**：

```jsonc
POST /api/entries/ingest

{
  "raw_text": "用户输入的大段文字，可以是流水、备忘、会议记录等",
  "project_code": "proj-ai-factory",
  "user_id": "u123",
  "note_datetime": "2025-12-08T10:00:00+08:00",   // 可选，业务时间
  "extra_context": {
    "source": "three_column_ui",
    "client": "desktop_app"
  }
}
```

- **响应（示意）**：

```jsonc
{
  "entry_id": "e_123456",
  "title_ai": "AI 工厂问答对齐方案讨论",
  "summary_ai": "本条记录描述了如何将三栏问答页面接入 AI 工厂，包括输入规整、标签空间和脑图投射等内容.",
  "space_type_suggestion": "topic",
  "parent_entry_id_suggestion": "e_project_xyz",     // 如有
  "tags": ["ai-factory", "问答系统", "架构对齐"],
  "created_at": "2025-12-08T10:01:00+08:00"
}
```

> 说明：
> - 前端只需保存 `entry_id` 等关键字段，用于后续上下文关联.
> - 标签、space_type 建议可以在 UI 上以“系统建议”的形式展示，允许用户调整.

### 4.2 问答接口：`qa_answer`

- **用途**：
  中间栏问答调用. 问题本身不必直接写库，由 AI 工厂决定如何记录.

- **请求（示意）**：

```jsonc
POST /api/qa/ask

{
  "question_text": "请根据最近关于 AI 工厂的记录，帮我总结出三栏页面要做哪些改造？",
  "user_id": "u123",
  "project_code": "proj-ai-factory",
  "context_entry_ids": ["e_123456", "e_123457"],  // 可选，用户当前选中的条目
  "options": {
    "max_context_items": 20,
    "need_citations": true,
    "language": "zh"
  }
}
```

- **响应（示意）**：

```jsonc
{
  "answer": "（大段中文回答，面向用户的自然语言结论）",
  "citations": [
    {
      "entry_id": "e_123456",
      "title": "AI 工厂问答对齐方案讨论",
      "snippet": "......命中的片段......",
      "score": 0.87
    },
    {
      "entry_id": "e_123457",
      "title": "表结构设计（初稿）",
      "snippet": "......关于 entries 与向量检索的设计......",
      "score": 0.81
    }
  ],
  "meta": {
    "trace_id": "qa_20251208_001",
    "used_agent": "qa_default_v1",
    "latency_ms": 1200
  }
}
```

> 说明：
> - 三栏中间栏直接用 `answer` 渲染.
> - 右栏脑图可以基于 `citations` 构建图.
> - `trace_id` 可用于追踪和后续脑图快照保存.

### 4.3 脑图快照接口（可放在后续阶段）

- **用途**：
  当用户希望把当前问答 + 召回结果固化成一个脑图视图时调用.

- **请求（示意）**：

```jsonc
POST /api/mindmap/snapshots

{
  "scope": "project:proj-ai-factory",
  "map_type": "issue_overview",
  "importance_tag": "milestone",
  "source_trace_id": "qa_20251208_001",
  "graph_payload": {
    "nodes": [ ... ],
    "edges": [ ... ]
  }
}
```

- **响应**：

```jsonc
{
  "map_id": "map_987654",
  "created_at": "2025-12-08T10:05:00+08:00"
}
```

---

## 5. 任务拆分建议：三栏应用 vs AI 工厂

### 5.1 三栏应用侧任务（你这边）

- **短期（阶段 1–2）**：
  - **[设计]**  
    - 和 AI 工厂确认 `entries_ingest`、`qa_answer` 接口字段（本草案为初稿）。
  - **[应用改造]**  
    - 输入侧：  
      - 把现有“写入服务器血库”的逻辑封装成一个 `QA Service`，对前端只暴露统一调用方式.  
      - 为将来替换为 `entries_ingest` 预留位置.
    - 问答侧：  
      - 同样通过 `QA Service` 对接 `qa_answer`，中间栏只认一个问答接口.
    - 展示侧：  
      - 中间栏＋右栏适配 `qa_answer` 的响应结构（answer + citations）。

- **中期（阶段 3）**：
  - 集成“系统建议标签/space_type”的 UI（右侧属性面板或脑图节点属性）。
  - 支持用户在界面上修改标签/空间标记，并调用更新接口回写 entries.

### 5.2 AI 工厂侧任务（项目经理那边）

- **模块与接口实现**：
  - 在 `ai_factory.db` 中：
    - 补全 `entries_repo`（读写 entries）。  
    - 规划/实现 chunk 表与向量表的 repo.
  - 在 `ai_factory.rag` 中：
    - 实现 `rag_pipeline`：切块、embedding、索引、检索.
  - 在 `ai_factory.agents` 中：
    - 实现输入规整 Agent 链（Title/Summary/Tagging/SpaceType）。  
    - 实现问答 Agent（QaAnswerAgent）。  
    - （可选）实现 MindmapProjectionAgent.
  - 在 `ai_factory.integrations` 中：
    - 实现 `qa_gateway`，对外暴露：
      - `entries_ingest(payload) -> EntryIngestionResult`  
      - `qa_answer(payload) -> QaAnswerResult`  
      - （可选）`save_mindmap_snapshot(...)`.

- **数据迁移与共存策略**：
  - 确定旧“服务器血库”与新 `entries` 表之间的字段映射.  
  - 设计是否需要一段时间内“两边同时写”，以及如何回收旧系统.

---

## 6. 需要共同确认的几个关键点

在和项目经理沟通时，建议重点确认下面几个问题：

- **Q1：短期内是否要求“三栏必须用本地库 + AI 工厂”？**
  - 如果否，可以先通过 `QA Service` 保持现状，只在 AI 工厂侧搭建完整链路，后续再切换实现.
- **Q2：entries 的最小必填字段是什么？**
  - 是否统一要求：`title_ai` + `summary_ai` + `content` + `project_code` + `user_id`.
- **Q3：标签空间与 space_type 的初始枚举是否固定？**
  - 是否沿用《表结构设计》中的枚举，还是需要项目经理先出一版标签字典.
- **Q4：脑图投射是采用规则优先，还是优先做成 Agent？**
  - 这会影响 AI 工厂 [rag](cci:7://file:///d:/AI/ai-factory/ai_factory/rag:0:0-0:0) / `integrations` 与前端的分工.

---

## 7. 面向 AI 工厂项目经理的共识点（提案）

- 本项目希望在未来版本中，将以下能力下沉到 AI 工厂维护：
  - 原始记录的规整与切块；
  - 标题/摘要/标签/空间标记的自动生成；
  - 知识库与向量库的结构设计与访问实现；
  - 问答链路的 RAG 召回与上下文编排.
- 本项目将重点投入在：
  - 问答与脑图的交互体验（三栏 UI）；
  - 结合本项目标签/视图体系的“货架式展示”；
  - 与现有历史数据/服务器血库的迁移和适配.
- 双方可据此在后续版本规划中，分解和排期各自 backlog.

---

### 小结

- 本草案的核心思想是：
  - **三栏页面 = 高级问答前台 + 结构化展示层**；
  - **AI 工厂 = 一切规整 / 标注 / RAG / 问答 / 写库的统一底座**.
- 通过两个关键接口（`entries_ingest`、`qa_answer`），把双方的职责边界清晰化，后续可以各自独立演进.

你可以先把这份草案给项目经理看，根据他们的反馈，我们再一起微调字段和阶段划分.