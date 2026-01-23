> 状态说明：本文件为三栏 ↔ AI 工厂的 v0 协议清单。写库与查询接口的最终字段和语义以《AI工厂-对外接口与集成规范》为准，本文件作为三栏项目侧的补充“法律条文”备份。

# 三栏 ↔ AI 工厂 协议清单 v0

> 目标：作为三栏与 AI 工厂之间的“法律条文”，明确当前已经生效的接口与行为约定。后续任何改动应先更新本清单，再调整代码。

## 1. NOTE 写库协议：entries_ingest

### 1.1 调用方式（三栏 → AI 工厂）

- Python 内部调用：

```python
from ai_factory.integrations.entries_ingest import entries_ingest

payload = {
    "raw_text": full_note,             # 必填，完整笔记文本（Markdown/纯文本）
    "note_datetime": timestamp,        # 可选，业务时间字符串
    "project_code": project_code,      # 可选
    "user_id": user_id,                # 可选
    "extra_context": {
        "log_file": log_file,          # 可选，工作记录 MD 路径（便于排查）
        "tags_snapshot": tags_snapshot # 可选，场景标签快照（当前仅透传，未来可用于校验）
    }
}

result = entries_ingest(payload)
# result = {"entries": [{"entry_id", "title", "content"}]}  # v0
```

- 三栏侧通过 `core/ai_factory_ingest.ingest_full_note_via_ai_factory(...)` 统一封装上述调用。

### 1.2 语义与行为

- `raw_text`：
  - 由三栏中部输出框/输入框组合生成的完整笔记；
  - 必须为 UTF-8 可编码文本，entries_ingest 内部会按长度三档处理。

- `note_datetime`：
  - 若提供，写入 entries 的 `created_at`/业务时间字段；
  - 若缺省，则由 AI 工厂在入库时填充当前 UTC 时间。

- `extra_context.log_file`：
  - 用于日志与调试，不影响入库行为。

- `extra_context.tags_snapshot`：
  - 三栏当前标签空间状态快照；
  - 当前版本仅随 `payload.extra_context` 透传，不直接参与 DB 字段写入，后续可用于与 `scene_tags` 做一致性检查。

- 标签落库规则：
  - entries_ingest 仅从 `raw_text` 中解析形如：
    - `标签： 部门=总部；规划=目标` 或 `标签:部门=总部;规划=目标` 的行；
  - 将其映射为 `entries.scene_tags jsonb` 字段，结构为：

```jsonc
{
  "department": ["总部"],
  "planning": ["目标"],
  "execution": ["项目"],
  "common": ["笔记"],
  "status": ["交付"],
  "rating": ["节点", "关注"]
}
```

- 写库与向量化：
  - NOTE 写库成功 ≠ 向量化一定成功；
  - 向量化失败不会影响 `entries` 写入，错误信息仅打印日志，由异步脚本后续补齐。

### 1.3 错误与兜底

- entries_ingest 发生异常时：
  - 会将 `raw_text` 与基本元数据写入 `写库失败笔记保存文档.md` 作为兜底；
  - 然后抛出异常，三栏 NOTE 保存线程捕获后在 UI 弹出“笔记入库失败: …”。

---

## 2. RAG 问答协议：qa_answer_rag

### 2.1 调用方式（三栏 → AI 工厂）

- 三栏通过 `QAService.ask_rag` 间接调用：

```python
payload = {
    "question_text": question,          # 必填
    "project_code": project_code,       # 可选
    "user_id": user_id,                 # 可选
    "top_k": top_k,                     # 可选，默认 10
    "since": since_iso,                 # 可选，ISO8601 字符串或 datetime
}

from ai_factory.integrations.rag_api import qa_answer_rag
result = qa_answer_rag(payload)
# result = {"question": str, "answer": str | None, "citations": [...], ...}
```

- 三栏优先通过 `task_executor.submit_task("RAG", payload)` 异步调用；
  - 若 TaskExecutor 不可用或执行失败，回退到直接调用 `qa_answer_rag(payload)`。

### 2.2 返回结构（稳定部分）

- 基础字段：

```jsonc
{
  "question": "...",           // 归一化后的问题文本
  "answer": "..." | null,     // 当前 v2 已可能返回 answer
  "citations": [
    {
      "entry_id": "...",
      "title": "..." | null,
      "summary_ai": "..." | null,
      "project_code": "..." | null,
      "user_id": "..." | null,
      "created_at": "...",   // ISO8601, 可为 null
      "score": 0.123
    }
  ]
}
```

- 扩展调试字段（可选）：`_intent/_sources/_structure/_guard`，三栏可以按需消费，但不得依赖其字段稳定性。

### 2.3 错误处理

- 语义错误（如 `question_text` 为空）：AI 工厂抛出 `ValueError`，由三栏 `QAService` 捕获并转换为 `[RAG] ...` 文本；
- 内部错误（模型/向量库/DB）：
  - 优先在 AI 工厂侧以异常形式抛出，由 `QAService` 转换为 `AnswerResult.answer` 中的错误提示，如：
    - `[RAG] 调用 AI 工厂 qa_answer_rag 失败: ...`；
    - `[RAG] 无法导入 AI 工厂接口 qa_answer_rag: ...`；
  - 三栏 UI 必须始终展示这类文本，而不是吞掉错误。

---

## 3. WEB 问答协议：qa_answer_web

### 3.1 调用方式（三栏 → AI 工厂）

- 三栏通过 `QAService.ask_web` → TaskExecutor("WEB") 或回退直连：

```python
payload = {
  "question_text": question,    # 必填
  "project_code": project_code, # 可选
  "user_id": user_id,           # 可选
  "top_k": 5,                   # 可选，默认 5
  "options": {                  # 可选，搜索偏好等
    "max_results": 5
  }
}

from ai_factory.integrations.web_api import qa_answer_web
result = qa_answer_web(payload)
```

### 3.2 返回结构（v0 契约）

```jsonc
{
  "question": "...",
  "answer": "...",            // 面向用户的自然语言回答
  "sources": [
    {
      "kind": "web",
      "id": "...",
      "title": "..." | null,
      "snippet": "..." | null,
      "source_meta": {
        "url": "...",
        "site": "...",
        "published_at": "..." | null
      }
    }
  ],
  "_intent": {                  // 调试/分析用
    "intent_type": null | "...",
    "mode": "WEB",
    "need_rag": false,
    "need_web": true,
    "filters": { ... },
    "answer_style": "summary" | null,
    "intent_analysis": "..." | null,
    "sub_queries": ["...", "..."]
  },
  "_structure": null | { ... },
  "_guard": { ... }             // 仅在必要时返回
}
```

### 3.3 现状与演进约定

- Node1（意图分析）与 Node3（答案合成）已经按契约实现；
- Node2（WebSearchExecutor）当前为“依赖并发搜索聚合的占位实现”，在未接好真实搜索 Team / API 时：
  - 可能返回 0 条结果，导致 `answer` 为“暂时没有找到相关记录，因此无法给出有依据的回答”一类保守回答；
- 在未完成真实联网接入前：
  - 三栏需将 WEB 模式视为“实验态”，不以此判断 AI 工厂整体健康度；
  - 任何“找不到依据”的回答应理解为“当前通道无有效 evidence”。

---

## 4. 场景标签 Node Query 协议

### 4.1 调用方式（未来三栏 → AI 工厂）

```python
from ai_factory.integrations.scene_tags_api import query_nodes_by_scene_tags

payload = {
  "tags": {
    "department": ["总部"],
    "planning": ["目标"],
    "execution": ["项目"],
    "common": [],
    "status": [],
    "rating": []
  },
  "time_window_days": 3,
  "mode": "node_list_hot"  # 或 "node_list_query"
}

nodes = query_nodes_by_scene_tags(payload)
```

### 4.2 返回结构

```jsonc
[
  {
    "entry_id": "...",
    "title": "..." | null,
    "tags": {                     // 未来将从 scene_tags 回填
      "department": ["总部"],
      "planning": ["目标"],
      "execution": ["项目"],
      "common": ["笔记"],
      "status": ["交付"],
      "rating": ["节点"]
    },
    "created_at": "...",         // ISO8601
    "updated_at": "...",         // ISO8601
    "activity_score": 3.8 | null,
    "extra": { ... }              // 预留调试/扩展字段
  }
]
```

### 4.3 当前实现状态

- DB 侧 `nodes_repo.query_nodes_basic/hot` 已按照《表结构设计》使用 `entries.scene_tags` 做过滤；
- 服务层 `NodeQueryService._row_to_record` 已将 `entries.scene_tags` 解码回 `NodeRecord.tags`，并通过 `NodeRecord.extra` 透传 `space_type`、`parent_entry_id` 等元数据字段；
- 协议约定：
  - 三栏/五栏前端可以安全依赖 `tags` 中的六行标签结构，以及 `extra.space_type` / `extra.parent_entry_id` 用于构建更丰富的节点视图（如泳道、脑图等）。

---

## 5. Swimlane 节点视图与二级联动协议

> 目标：收口三栏在“规划维度”下使用 AI 工厂节点查询结果构建泳道视图的协议，
> 明确请求方式、返回结构，以及“锁定父节点后仅在下一层泳道按 parent_entry_id 过滤”的二级联动语义。

### 5.1 数据来源与管线概览

- 三栏在某部门下切换到泳道视图（规划维度）时，整体数据管线为：

  1. 三栏发起“按部门查询节点列表”的内部调用：
     - 入口：`ai_factory.integrations.scene_tags_api.query_nodes_by_scene_tags(payload)`；
     - `payload.tags.department = [当前部门]`，其余标签维度可为空；
  2. AI 工厂使用 `NodeQueryService` + `nodes_repo.query_nodes_basic` 按标签/时间窗口查询 `entries`；
  3. `query_nodes_by_scene_tags` 将 `NodeRecord` 转为字典列表返回，包含：
     - `entry_id` / `title`；
     - `tags`（六行 scene_tags 结构）；
     - `extra.space_type` / `extra.parent_entry_id`；
  4. 三栏侧 `swimlane_service.build_swimlane_payload_for_department(department)` 在上述结果基础上，构造前端泳道页面所需的轻量 payload。

### 5.2 Swimlane 请求与返回结构

> 本节从三栏视角约定 swimlane_service 的输入/输出结构，
> 实际调用链路可通过 Qt/WebChannel 或内部 Python 调用实现。

#### 5.2.1 请求（按部门获取泳道节点）

- 三栏在某个“部门”上下文中请求泳道数据时，应调用：

  ```python
  from injection_legacy_columns.core import swimlane_service

  payload = swimlane_service.build_swimlane_payload_for_department(department="软件")
  # 返回结构见下文 5.2.2
  ```

- 约定：
  - `department` 为三栏当前左侧选中的部门标签的中文名称（如 "软件"、"内务" 等）；
  - swimlane_service 内部会将其映射为 `SceneTags.department=[department]` 进行节点查询；
  - 其他标签维度（planning/execution/status/rating）在该接口中不参与过滤，由前端自行按列/视图区分呈现。

#### 5.2.2 返回：SwimlanePayload 结构

- `build_swimlane_payload_for_department` 返回的标准结构为：

  ```jsonc
  {
    "items": [
      {
        "id": "ent_xxx",                 // entries.entry_id
        "title": "...",                 // entries.title，若为空则回退为 id
        "department": "软件",            // 来自 scene_tags.department[0]
        "status": "其他",                // 来自 scene_tags.status[0]，缺省时为 "其他"
        "planning_lane": "战略",         // 来自 scene_tags.planning[0]，可为 null
        "parent_entry_id": null | "ent_yyy", // 来自 entries.parent_entry_id/NodeRecord.extra
        "priority": "中"                 // 当前为占位字段，固定 "中"
      }
    ],
    "meta": {
      "department": "软件",
      "lane_dimension": "status"        // v0 中仅作为占位，前端可忽略
    }
  }
  ```

- 说明：
  - `planning_lane`：
    - 若 entries.scene_tags.planning 非空，则取第一个元素作为泳道标签；
    - 当前约定值包括：`"战略" | "目标" | "计划" | "项目" | "其他"`；
  - `parent_entry_id`：
    - 优先从 `NodeRecord.extra.parent_entry_id` 读取；
    - 若不存在，则视为顶层节点（在树形结构中没有父节点）。

### 5.3 前端规划维度渲染与二级联动语义

> 本小节规范三栏前端在“规划维度”下如何基于 SwimlanePayload 渲染泳道，
> 尤其是“锁定父节点后下一层泳道按 parent_entry_id 过滤”的行为。

#### 5.3.1 维度与泳道列

- 在工作视图（`viewMode = work_status`）下，前端支持两种维度：
  - 状态维度：按 `status` 列出（待开始/进行中/已完成/其他）；
  - 规划维度：按 `planning_lane` 列出（其他/战略/目标/计划/项目）。

- 规划维度下的泳道列及其含义：

  - `其他`：
    - `planning_lane` 为空，且 `status = "其他"` 的节点；
  - `战略/目标/计划/项目`：
    - 对应 `planning_lane == "战略" / "目标" / "计划" / "项目"` 的节点。

#### 5.3.2 未锁定父节点时的行为（全局视图）

- 当前无任何锁定父节点（`window.__lockedPlanningParent == null`）时：
  - 前端仅根据 `item.planning_lane` 判断该节点应出现在哪一列；
  - 即：

    ```text
    lane == item.planning_lane
    ```

  - 此时所有“目标/计划/项目”节点都以“全局视图”方式展示，不区分父子关系。

#### 5.3.3 锁定父节点后的行为（二级联动视图）

- 三栏前端在规划维度下支持“锁定父节点”功能：
  - 通过双击某一列中的卡片（或三点菜单“锁定”），将该卡片标记为当前锁定父节点；
  - 全局仅允许存在一个锁定父节点，其状态通过：

    ```js
    window.__lockedPlanningParent = { entryId: "ent_xxx", laneName: "战略" | "目标" | "计划" }
    ```

  进行维护，并通过 Qt/WebChannel 通知后端。

- 锁定父节点后，前端在规划维度下的渲染规则为：

  1. 保持当前列（父节点所在列）与更高层/其他列的“全局视图”不变：
     - 例如锁定某个“战略”节点后，“战略/其他”列仍显示所有对应 `planning_lane` 的节点；
  2. 仅在**下一层规划泳道列**中应用父子过滤逻辑：
     - 定义：

       ```text
       lane_to_child = {
         "战略" -> "目标",
         "目标" -> "计划",
         "计划" -> "项目"
       }
       ```

     - 若当前锁定父节点为（`laneName = "战略"`, `entryId = A`），
       则在“目标”列中仅展示满足：

       ```text
       item.planning_lane == "目标"
       AND item.parent_entry_id == A
       ```

     - 类似地：
       - 锁定某个“目标”节点 B 时，“计划”列仅展示 `planning_lane == "计划"` 且 `parent_entry_id == B` 的节点；
       - 锁定某个“计划”节点 C 时，“项目”列仅展示 `planning_lane == "项目"` 且 `parent_entry_id == C` 的节点。

  3. 若 `parent_entry_id` 为空或与锁定父节点不匹配，则该节点在下一层泳道中不会展示。

#### 5.3.4 行为约束与调试建议

- 行为约束：
  - SwimlanePayload 必须为前端提供：
    - 正确的 `planning_lane`（来自 scene_tags.planning）；
    - 正确的 `parent_entry_id`（来自 entries.parent_entry_id / NodeRecord.extra）；
  - 前端的锁定状态不得直接修改 payload 中的字段，只能作为视图过滤条件使用。

- 调试建议：
  - 当二级联动行为异常时，优先检查：
    1. DB 浏览器中子节点的 `parent_entry_id` 与 `scene_tags.planning` 是否正确；
    2. `build_swimlane_payload_for_department` 返回的 `items` 中相应节点是否携带了正确的 `planning_lane` 与 `parent_entry_id`；
    3. 前端在锁定父节点后，是否重新触发了基于最新 `window.__lockedPlanningParent` 的渲染逻辑。

---

本清单为 v0 版本，后续新增/调整接口时请优先更新本文件，并在三栏/AI 工厂两侧代码中保持与本清单一致。
