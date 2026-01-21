# AI 工厂对外接口与集成规范（v1 草案）

> 面向对象：希望与 AI 工厂集成的应用方（如三栏/五栏工作区、问答系统、业务系统等）。  
> 本文不讲内部实现细节，只说明：AI 工厂**能提供什么能力、暴露哪些接口、如何安全规范地调用**。

---

## 1. 总览：AI 工厂对外提供什么能力

### 1.1 一句话定位

- **AI 工厂 = 面向广义知识库的“AI 能力底座 + 组件装配线 + 通用查询 + 性能评测/货架输出”**。
- 对外提供的主要能力类型：
  - **数据访问**：
    - `entries` 事实流水的写入/浏览/查询；
    - 基于场景标签的节点列表查询（Node Query）。
  - **RAG / 问答能力**：
    - 基于 `entries + entry_embeddings` 的语义检索；
    - 可选的 RAG 问答接口。
  - **（规划中）性能评测与货架视图**：
    - 组件/方案的评测任务触发与结果查询；
    - 货架视图：可用能力与历史表现清单。

### 1.2 与广义知识库/问答系统的关系

- 广义知识库 = 最终目标，承载所有事实/解释/业务数据。  
- AI 工厂 = 为知识库服务的一整套**能力工厂**：数据接入、RAG、Agent、评测等。  
- 问答系统 = 面向用户的“前台入口”，通过统一接口调用 AI 工厂提供的能力。

---

## 2. 对外可见的核心数据与约定

### 2.1 entries：事实流水主表（对外简要视图）

- AI 工厂当前对外开放的核心事实表是 `entries`（详情见《表结构设计25-12-8》）：
  - `entry_id` (`text`，PK)：节点唯一 ID；
  - `title` (`text`)：标题；
  - `content` (`text`)：正文内容；
  - `summary_ai` (`text`, 可空)：AI 生成摘要；
  - `project_code` (`text`, 可空)：项目/工作流代码；
  - `user_id` (`text`, 可空)：记录所属用户；
  - `created_at` (`timestamptz`)：创建时间；
  - `scene_tags` (`jsonb`, 可空)：用于三栏/五栏场景标签查询的标签结构。

- **ID 约定**：
  - 所有对节点/记录的引用都统一使用 `entry_id`；
  - 问答引用、脑图根节点、外部系统链接等，均以 `entry_id` 为主键。

### 2.2 向量与 RAG

- AI 工厂内部维护 `entry_embeddings` 等向量表，用于语义检索（pgvector 等）。
- 对接方通常不直接操作向量表，而是通过：
  - RAG 检索接口（返回 citations 与得分）；
  - 或间接通过问答接口获取引用节点。
- **一致性约定**（简化版）：
  - 检索阶段会始终通过 `entry_id` 回表 `entries`，**不会返回已在 DB 中删除的记录**；
  - 即使存在孤儿向量，也不会出现在对外的检索/问答结果中。

---

## 3. 对外功能清单

### 3.1 写入 / 同步（简要）

> 注：当前写入链路仍以内部 ingest 脚本和集成为主，对外统一写入 API 处于规划中。这里只给出行为约定。

- AI 工厂负责：
  - 将上游系统传来的原始记录（笔记/任务/议题等）切块、清洗后写入 `entries`；
  - 按需触发同步或异步向量化，写入 `entry_embeddings`；
- 行为约定：
  - **写入成功不意味着向量一定同步成功**（向量化可能异步补齐）；
  - 上游系统可以通过对 entries 与 `entry_embeddings` 的对齐检查脚本确认向量补齐情况。

#### 3.1.1 NOTE 笔记写库接口：entries_ingest（对三栏的正式约定）

- Python 调用入口：

  ```python
  from ai_factory.integrations.entries_ingest import entries_ingest

  payload = {
      "raw_text": full_note,             # 必填，完整笔记文本
      "note_datetime": timestamp,        # 可选，业务时间
      "project_code": project_code,      # 可选
      "user_id": user_id,                # 可选
      "extra_context": {
          "log_file": log_file,          # 可选，工作记录 MD 路径
          "tags_snapshot": tags_snapshot # 可选，三栏当前标签快照
      }
  }

  result = entries_ingest(payload)
  # result = {"entries": [{"entry_id", "title", "content"}]}
  ```

- 字段约定（收口自 docs/entries_ingest_对接说明_v0）：

  - `raw_text: str`：必填，三栏中部输出/输入组合形成的完整笔记文本；
  - `project_code: str | None`：可选，写入 `entries.project_code`；
  - `user_id: str | None`：可选，写入 `entries.user_id`；
  - `note_datetime: str | None`：可选，业务时间字符串，缺省则由 AI 工厂在入库时填充当前时间；
  - `extra_context: dict | None`：附加上下文；
    - `extra_context.log_file`：仅用于日志与调试，不影响入库行为；
    - `extra_context.tags_snapshot`：三栏当前标签空间状态快照，当前版本仅透传，不直接参与 DB 字段写入，后续可用于与 `scene_tags` 做一致性检查。

- 行为说明（与 docs/三栏_AI工厂_协议清单_v0 一致）：

  - entries_ingest 内部会对 `raw_text` 做长度分档处理，并调用前置模型生成：
    - `id` / `title` / `summary` / `content`；
  - 按《表结构设计25-12-8》写入 `entries`：
    - `entry_id`（来自 `id` 或内部生成）、`title`、`summary_ai`、`content`、`created_at`、`project_code`、`user_id` 等；
  - 同步或异步触发向量化，写入 `entry_embeddings`；
  - 返回结构：

    ```python
    {
        "entries": [
            {"entry_id": str, "title": str, "content": str},
            # 当前通常只有一条，列表形式为未来切块扩展预留
        ]
    }
    ```

- 错误兜底约定：

  - entries_ingest 发生异常时：
    - 会将 `raw_text` 与基本元数据写入《写库失败笔记保存文档.md》作为兜底；
    - 然后抛出异常，由调用方（如三栏 NOTE 保存线程）在 UI 弹出“笔记入库失败: …”。

#### 3.1.2 元数据更新接口（Entry State APIs）

> 目标：为 entries 的“元数据层字段”提供统一的更新入口，例如：
> - 规划维度：`scene_tags.planning`、`space_type`；
> - 父子关系：`parent_entry_id`；
> - 状态/视图属性：如节点状态、泳道位置、排序权重等。

这些字段在《表结构设计25-12-8》中被归类为“元数据层”，允许频繁修改，但必须通过统一服务更新。

**1）Python 内部调用（推荐）**

AI 工厂内部建议通过一个统一的元数据服务（占位名：`entry_state_service`）来更新元数据字段：

```python
from ai_factory.domain.entry_state_service import (
    move_to_planning_lane,
    set_parent,
    set_status,
)


def on_swimlane_planning_lane_changed(entry_id: str, lane_name: str, parent_id: str | None) -> None:
    """示例：泳道拖拽时更新规划标签与父子关系。"""
    move_to_planning_lane(
        entry_id=entry_id,
        planning_lane=lane_name,          # 如 "战略" / "目标" / "计划" / "项目" / "其他"
        parent_entry_id=parent_id or None,
    )


def on_entry_parent_changed(entry_id: str, new_parent_id: str | None) -> None:
    set_parent(entry_id=entry_id, parent_entry_id=new_parent_id)


def on_entry_status_changed(entry_id: str, new_status: str) -> None:
    set_status(entry_id=entry_id, status=new_status)
```

> 说明：以上函数名与模块名为占位示意，实际实现时只要满足同样的职责即可：
> - **只修改元数据字段**（scene_tags/space_type/parent_entry_id/状态等）；
> - 不修改 `title/content/summary_ai/embedding` 等正文与向量字段；
> - 在一个地方集中维护合法性校验与与向量库的一致性策略。

**2）建议的 REST 形态（如需对外暴露）**

如需要以 HTTP 形式对外开放元数据更新能力，可推荐形态为：

```http
PATCH /api/entries/{entry_id}/state
Content-Type: application/json
```

请求体示例：

```jsonc
{
  "planning_lane": "目标",          // 可选，更新规划维度（映射到 scene_tags.planning / space_type）
  "parent_entry_id": "ent_123",    // 可选，更新父节点 ID
  "status": "active",              // 可选，更新业务状态
  "view_state": {                    // 可选，视图/泳道相关属性
    "swimlane": "战略",
    "order_weight": 10
  }
}
```

行为约定：

- 该接口**只允许修改元数据字段**，不得修改：
  - `title` / `content` / `summary_ai`；
  - 各类向量字段或 embedding；
- 服务器侧实现应调用与上文等价的元数据服务函数，而不是直接拼 SQL；
- 合法性校验（例如：
  - 规划链条上哪种 `space_type` 可以挂到哪种父节点下面；
  - 某些状态值是否允许切换等）
  统一集中在元数据服务内部，避免分散在多个入口。

> 与《表结构设计25-12-8》中的“元数据层字段与状态服务”小节一致：
> - 内容写入走 `entries_ingest` 等专门链路；
> - 元数据更新走 Entry State APIs；
> - 二者职责清晰、互不混用。

### 3.2 场景标签节点查询（Node Query）

**功能：**

- 根据三栏/五栏前端的六行“场景标签” + 时间窗口，
  返回匹配条件的节点列表或“热节点列表”，用于：
  - 左侧节点列表；
  - 热项目/热点节点视图等。

**标签结构（前端 UI 与 DB 对齐）：**

- 部门：`department` —— `"总部" | "现场" | "软件" | "内务"` …
- 规划：`planning` —— `"目标" | "战略" | "计划"` …
- 执行：`execution` —— `"项目" | "工作流" | "任务"` …
- 公共：`common` —— `"笔记" | "议题" | "总结"` …
- 状态：`status` —— `"交付" | "完成" | "验收" | "派发"` …
- 评价：`rating` —— `"节点" | "里程碑" | "关注" | "收藏"` …

这些标签在 DB 中统一落在 `entries.scene_tags` 字段（jsonb）中，对应结构为：

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

### 3.3 RAG / 问答接口

> 当前 RAG/问答接口主要用于内部调试与部分上层系统集成，对外正式 API 将基于此演进。

- **RAG 检索能力**：
  - 输入：问题文本 + 可选过滤条件（时间窗口、project_code/user_id 等）；
  - 输出：若干 `RetrievedEntry`（含 `entry_id/title/summary_ai/content/score` 等）；
  - 行为：
    - 始终通过 `entry_id` JOIN 回 `entries`；
    - 不返回已在 DB 中删除的节点。

- **RAG 问答能力**（如 `qa_answer_rag_legacy`）：
  - 在 RAG 检索基础上，调用 LLM 生成答案文本；
  - 将问题、答案和 citations 一并返回。

> 对外正式问答 API 的统一规范会在后续版本中整理到本文件。

---

## 4. 通用接口规范

### 4.1 调用形态

- 当前阶段支持两类调用方式：
  - **Python 内部调用**：直接 import `ai_factory.integrations.*` 模块的函数；
  - **HTTP/REST 接口**：通过 AI 工厂提供的 Web 服务访问（路径与部署方式由运维/部署文档规定）。

> 本规范中的接口示例既给出 Python 调用方式，也给出推荐的 REST 形态，具体以实际部署配置为准。

### 4.2 认证与鉴权

- 现阶段：
  - 主要在受控环境内使用（开发机 / 内网），默认可信调用；
  - 尚未统一启用 Token/API Key 机制。
- 规划：
  - 对外开放或多团队共享时，将为 REST 接口增加 Token/API Key 鉴权；
  - 具体规则会追加到本节。

### 4.3 错误返回约定

- 建议统一错误返回结构为：

```jsonc
{
  "success": false,
  "error_code": "INVALID_ARGUMENT",
  "message": "xxx",
  "details": { "field": "..." }
}
```

- Python 调用场景下，严重错误以异常形式抛出（ValueError/自定义异常等）。

### 4.4 版本与兼容性

- 本文描述的接口为 **v1**：
  - 新增字段和可选参数应保持向后兼容；
  - 不兼容性变更（字段删除、语义改变）需要通过版本号升级或明确迁移说明。

---

## 5. 典型接口详解

### 5.1 场景标签节点查询接口（Node Query）

#### 5.1.1 功能说明

- 根据场景标签与时间窗口，返回节点列表，用于：
  - 三栏/五栏的“热项目/节点列表”；
  - 其他应用的“按标签过滤的节点视图”。

- 支持两种模式：
  - `node_list_hot`：带简单热度分的“热节点列表”；
  - `node_list_query`：按时间排序的标签过滤列表。

#### 5.1.2 Python 调用示例

```python
from ai_factory.integrations.scene_tags_api import query_nodes_by_scene_tags

payload = {
    "tags": {
        "department": ["总部"],
        "planning": ["目标"],
        "execution": ["项目"],
        "common": [],
        "status": [],
        "rating": [],
    },
    "time_window_days": 3,
    "mode": "node_list_hot",
}

nodes = query_nodes_by_scene_tags(payload)
for n in nodes:
    print(n["entry_id"], n["title"], n["activity_score"])
```

#### 5.1.3 REST 形态（建议）

- 方法与路径：

  ```http
  POST /api/nodes/query_by_scene_tags
  Content-Type: application/json
  ```

- 请求体：

  ```jsonc
  {
    "tags": {
      "department": ["总部"],
      "planning": ["目标"],
      "execution": ["项目"],
      "common": ["笔记"],
      "status": ["交付"],
      "rating": ["节点"]
    },
    "time_window_days": 3,
    "mode": "node_list_hot",
    "page": 1,
    "page_size": 50
  }
  ```

- 响应体（示例）：

  ```jsonc
  [
    {
      "entry_id": "e_123",
      "title": "ai-factory 三栏优化项目",
      "tags": {
        "department": ["总部"],
        "planning": ["目标"],
        "execution": ["项目"],
        "common": ["笔记"],
        "status": ["交付"],
        "rating": ["节点"]
      },
      "created_at": "2025-12-19T10:23:45+08:00",
      "updated_at": "2025-12-19T10:23:45+08:00",
      "activity_score": 3.8
    }
  ]
  ```

#### 5.1.4 行为与约束

- `tags.*`：
  - 值必须来自约定枚举集合（由前端固定按钮控制）；
  - 为空数组或缺省表示“不在该维度上过滤”。

- `time_window_days`：
  - 建议仅使用小整数（如 1/2/3）；
  - 未提供或非正数时，`node_list_hot` 不计算 `activity_score`，仅按时间排序。

- `mode`：
  - 枚举值：`"node_list_hot" | "node_list_query"`；
  - 未提供时默认 `node_list_query`。

### 5.2 RAG 检索 / 问答接口（占位说明）

> 以下接口目前主要用于内部/实验性用途，对外暴露时会进一步梳理与固化。

- **RAG 检索接口（示意）**：

  ```python
  from ai_factory.integrations.rag_api import qa_answer_rag_legacy

  payload = {
      "question_text": "最近三天 ai-factory 项目的重点是什么？",
      "project_code": "ai-factory",
      "user_id": null,
      "top_k": 10,
      "since": "2025-12-01T00:00:00+08:00"
  }

  result = qa_answer_rag_legacy(payload)
  # result = {"question": str, "answer": str | null, "citations": [...]} 
  ```

- 行为约束：
  - 内部会通过向量检索 + `entry_id` JOIN `entries` 获取 citations；
  - 不会返回 DB 中已删除的 entries。

---

## 6. 集成方注意事项

### 6.1 删除与数据一致性

- 建议删除通过 AI 工厂提供的应用接口完成：
  - 接口内部负责先删除向量记录，再删除 `entries` 行（或通过外键/触发器保证）。
- 若直接在 DB 工具中删除 `entries` 行：
  - 可能短期内留下孤儿向量；
  - 但检索与问答阶段会通过回表过滤掉这些记录，不会向外暴露“幽灵数据”。

### 6.2 性能与节流

- 建议：
  - 所有查询接口均使用分页参数（`page/page_size`）；
  - 单次返回记录数控制在合理范围内（例如不超过 200 条）。
- 批量/高频调用场景（大规模同步、批量分析）请提前沟通，以便 AI 工厂侧调优索引与资源配置。

### 6.3 协议演进与对齐

- 标签枚举、`mode` 枚举、新增字段等变更，将通过：
  - 更新本规范文档；
  - 在版本说明中标注变更点；
  - 视情况提供迁移指南。

---

## 7. 小结

- 对外应用可以将 AI 工厂视作：
  - 一个统一的 `entries` 事实层访问入口；
  - 一套支持“场景标签 + 时间窗口”的节点查询服务；
  - 一个逐步开放的 RAG/问答与性能评测能力提供方。

- 集成时优先考虑：
  - 使用结构化参数（标签/时间/分页）而非直接拼 SQL；
  - 通过约定好的接口调用 AI 工厂，不直接操作底层表结构；
  - 在有新标签/新模式需求时，先与 AI 工厂侧对齐并更新本规范。

> 关于三栏与 AI 工厂之间更细粒度的链路与职责拆解（包括 NOTE / RAG / WEB / Node Query 等），
> 可参考 docs/三栏_AI工厂_协议清单_v0.md；该文档作为本规范的补充说明，遇到冲突时以本文件为准。
