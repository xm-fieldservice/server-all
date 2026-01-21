# 变更履历（服务器版）

- 2025-12-24：在服务器环境中使用的版本，从原始《AI 工厂对外接口与集成规范》复制，并补充统一访问入口（AI_FACTORY_API_BASE / AI_FACTORY_ENTRIES_VIEW_URL）与 /entries/ingest /qa/rag /qa/web HTTP 接口的详细说明。

---

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

> 通道与场景元数据约定（WeCom 等通道）
>
> - `extra_context.source_channel` 用于标记来源通道，例如：
>   - `"three_column_ui"` / `"wecom_note_bot"` / `"wecom_qa_bot"` / `"wecom_dm"` / `"wecom_group"` 等；
> - 若 `extra_context.tags_snapshot` 或其他字段中包含 `channel` / `semantic_type` / `peer` / `conversation` 等键，
>   `entries_ingest` 会将其展平进 `entries.scene_tags`，作为场景标签元数据，
>   典型结构为：
>   ```jsonc
>   {
>     "channel": ["wecom_note_bot"],
>     "semantic_type": ["note"],
>     "peer": ["wecom:note_bot"],
>     "conversation": ["conv_wecom_note_..."],
>     "department": ["软件部"],
>     "execution": ["其他"],
>     "work": ["in_work"]
>   }
>   ```
> - 企业微信通道的具体字段约定和场景拆分，见《企业微信后端开发与部署约定（草案）》第 6 章。

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

### 4.5 统一访问入口与环境变量

- 所有对外 HTTP 接口均以一个统一的 Base URL 为入口，由环境变量提供：
  - `AI_FACTORY_API_BASE`：AI 工厂能力接口基础地址，例如：
    - `http://121.43.126.173:8000`
    - 典型调用形态：`POST {AI_FACTORY_API_BASE}/qa/rag` 等。
  - `AI_FACTORY_ENTRIES_VIEW_URL`：entries 只读浏览页面地址，例如：
    - `http://121.43.126.173:3001`
    - 典型用途：三栏里的“DB 浏览”按钮直接在浏览器打开该地址。

- 约定：
  - 上层应用应只依赖这两个环境变量，不直接拼接内部服务 IP/端口；
  - DB 浏览页面仅用于调试/只读浏览，不承担写库与问答能力。

---

### 4.6 调用上下文 `context` 与多租户约定

- 为支持“服务器版”多用户/多工作空间场景，对外 HTTP 接口统一推荐在请求体中提供 `context` 对象，用于承载调用上下文信息：

  ```jsonc
  {
    "context": {
      "workspace_id": "ws_001",   // 必填：知识空间/租户 ID
      "user_id": "u_123",         // 建议提供：调用方用户标识
      "project_code": "ai-factory"// 建议提供：项目/工作流代码
    },
    "...": "其他业务字段"
  }
  ```

- 约定：
  - `workspace_id` 是 AI 工厂在 DB/RAG 中做隔离的第一维度，所有 entries/RAG/解释层/业务层查询都会带上 `workspace_id` 过滤；
  - `user_id`、`project_code` 主要用于日志追踪、权限判断与结果过滤，可与授权服务（如 pc-authz-service）集成；
  - 旧版协议中顶层的 `user_id` / `project_code` 字段在 v1 仍然受支持：
    - 若提供了 `context.user_id` / `context.project_code`，则以 `context` 为准；
    - 若仅提供顶层字段，AI 工厂侧会在不破坏语义的前提下做向后兼容；
    - 新接入方建议直接使用 `context` 结构，以便后续扩展（如 org_id/role/client_type 等）。

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

### 5.2 笔记写库接口（entries_ingest）

> 下列为统一 HTTP 形态的推荐规范；具体部署路径可在不改变语义的前提下微调。

- 方法与路径（建议）：

  ```http
  POST /entries/ingest
  Content-Type: application/json
  ```

- 请求体（与 `ai_factory.integrations.entries_ingest.entries_ingest` 的 payload 对齐）：

  ```jsonc
  {
    "context": {
      "workspace_id": "ws_001",
      "user_id": "u_123",
      "project_code": "ai-factory"
    },
    "raw_text": "本周三栏页面改版进度记录……",
    "note_datetime": "2025-12-24T10:30:00+08:00",
    "extra_context": {
      "client": "tri-pane-ui",
      "source": "desktop"
    }
  }
  ```

- 响应体（示例）：

  ```jsonc
  {
    "entries": [
      {
        "entry_id": "ent_ab12cd34",
        "title": "三栏页面改版进度记录",
        "content": "本周三栏页面改版进度记录……"
      }
    ]
  }
  ```

- 行为约定：
  - 写库成功仅表示 entries 记录已插入；
  - 同步向量化失败时可以由异步脚本补齐，对外行为保持幂等；
  - 若 payload 缺少 `raw_text` 或为空，应返回参数错误（400）或等价错误码。

### 5.3 RAG 问答接口（qa_answer_rag）

- 方法与路径（建议）：

  ```http
  POST /qa/rag
  Content-Type: application/json
  ```

- 请求体（与 `ai_factory.integrations.rag_api.qa_answer_rag` 对齐）：

  ```jsonc
  {
    "context": {
      "workspace_id": "ws_001",
      "user_id": "u_123",
      "project_code": "ai-factory"
    },
    "question_text": "最近三天 ai-factory 项目的重点是什么？",
    "top_k": 10,
    "since": "2025-12-01T00:00:00+08:00"
  }
  ```

- 响应体（示例）：

  ```jsonc
  {
    "question": "最近三天 ai-factory 项目的重点是什么？",
    "answer": "最近三天主要集中在 AI 工厂对外接口规范和三栏集成的落地……",
    "citations": [
      {
        "entry_id": "ent_xxx",
        "title": "AI 工厂对外接口规范讨论记录",
        "summary_ai": "讨论了 AI 工厂统一 HTTP 接口和访问结构……",
        "project_code": "ai-factory",
        "user_id": "u_123",
        "created_at": "2025-12-21T09:30:00+08:00",
        "score": 0.92
      }
    ],
    "_intent": {},
    "_sources": [],
    "_structure": null,
    "_guard": {}
  }
  ```

- 行为约定：
  - 内部会统一通过 `entry_id` JOIN `entries` 获取 citations；
  - 不返回已在 DB 中删除的记录；
  - 当判断输入内容更像“笔记/记录”而非“问题”时，可以通过 `_guard` 字段给出引导提示。

### 5.4 Web 问答接口（qa_answer_web）

- 方法与路径（建议）：

  ```http
  POST /qa/web
  Content-Type: application/json
  ```

- 请求体（与 `ai_factory.integrations.web_api.qa_answer_web` 对齐）：

  ```jsonc
  {
    "context": {
      "workspace_id": "ws_001",
      "user_id": "u_123",
      "project_code": "ai-factory"
    },
    "question_text": "最近关于 AI 工厂对外接口规范的行业最佳实践有哪些？",
    "top_k": 5,
    "options": {
      "language": "zh-CN"
    }
  }
  ```

- 响应体（示例）：

  ```jsonc
  {
    "question": "最近关于 AI 工厂对外接口规范的行业最佳实践有哪些？",
    "answer": "目前主流做法包括：统一 HTTP 接口层、明确能力与数据边界、通过标签和时间窗控制查询范围……",
    "sources": [
      {
        "kind": "web",
        "id": "src_1",
        "title": "Designing AI Service Interfaces",
        "snippet": "This article discusses unified HTTP APIs for AI capabilities...",
        "source_meta": {
          "url": "https://example.com/ai-service-interfaces",
          "site": "example.com"
        }
      }
    ],
    "_intent": {
      "intent_type": null,
      "mode": "WEB",
      "need_rag": false,
      "need_web": true,
      "filters": {},
      "answer_style": null,
      "intent_analysis": null,
      "sub_queries": []
    },
    "_structure": null,
    "_guard": {
      "ok": true
    }
  }
  ```

- 行为约定：
  - 当前实现中的 WebSearchExecutor 可能仍为占位实现（返回空列表），但接口契约保持稳定；
  - 当 heuristics 或 QueryIntent 判断输入内容更像“笔记/记录”时，可以通过 `_guard` 返回引导信息。

### 5.5 RAG 检索 / 问答接口（占位说明）

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
