> 状态说明：本文件为 v0 实现视角索引，用于快速浏览当前 ai_factory 包内模块与链路。概念与职责定义以四份核心文档（《项目总体说明》《表结构设计25-12-8》《项目工程结构25-12-8》《AI工厂-对外接口与集成规范》）为准。

# AI 工厂架构清单 v0（实现视角）

> 本清单基于当前代码与以下文档整理而成：
> - 《AI工厂-对外接口与集成规范》
> - 《表结构设计25-12-8》
> - 《AI工厂架构清单和职责草案》
> - 《项目总体说明》

## 1. 顶层定位

- 为广义知识库提供：数据接入、RAG/WEB 问答、场景标签 Node Query，以及后续的评测与货架能力。
- 主要服务对象：三栏/五栏桌面应用、问答系统、其他业务应用。

## 2. 模块清单

- `ai_factory.config`
  - 职责：统一读取 .env / 环境变量、日志配置等。
  - 现状：部分配置仍直接在各模块中 `os.getenv`，后续建议收口到 config 层。

- `ai_factory.db`
  - `pgvector_client`：统一管理 Postgres/pgvector 连接。
  - `entries_repo`：负责 `entries` 事实表的插入与基础查询（已适配 `scene_tags` 为 JSON）。
  - `nodes_repo`：基于 `entries.scene_tags` 实现 Node Query 所需的 SQL（basic/hot 两种模式）。
  - 规划中：maps_repo / eval_repo / biz_*_repo 等。

- `ai_factory.agents`
  - `entry_agents.ChunkResult` 等：入库切块结果结构。
  - `answer_synthesis_agent`：基于 evidences 生成自然语言回答（WEB Node3）。
  - `query_executors.RagSearchExecutor`：对 entries 做 RAG 检索。
  - `query_executors.WebSearchExecutor`：执行 Web 搜索（当前接并发搜索聚合，结果仍多为空）。
  - `query_intent_agent.build_query_intent`：RAG/WEB 查询意图分析。

- `ai_factory.rag`
  - `entries_rag.search_entries`：基于向量/entries 的检索实现。

- `ai_factory.query`
  - `models.SceneTags`：与三栏/五栏的六行场景标签一一对应。
  - `models.NodeQuery` / `NodeRecord`：节点查询请求与返回结构。
  - `nodes_service.NodeQueryService`：对上统一的 Node Query 服务入口，封装 DB 调用与模式分发。

- `ai_factory.integrations`
  - `entries_ingest`：统一写 `entries` 的高层入口（三档长度逻辑 + `scene_tags` 解析 + 同步向量化）。
  - `entries_ingest_debug`：只做 LLM 解析与日志，不写库的调试链路。
  - `rag_api.qa_answer_rag`：对外 RAG 问答入口（包装 v2 流水线）。
  - `rag_api.qa_answer_rag_legacy`：旧版 RAG + Answer Agent 接口，主要用于兼容。
  - `web_api.qa_answer_web`：WEB 问答入口（Node1/2/3 流水线，对外契约已稳定，Node2 仍需完善）。
  - `scene_tags_api.query_nodes_by_scene_tags`：场景标签 Node Query 的对外入口。
  - `task_executor`：RAG/WEB 任务的 2-worker 执行器，供三栏等前端异步调用。

- 规划/部分落地模块（暂略实现细节）：
  - `tools` / `frameworks` / `testing` / `shelf` / `cli` 等，职责在《架构清单和职责草案》中已有定义。

## 3. 核心链路

### 3.1 NOTE 写库（entries + scene_tags）

- 上游：三栏 `ingest_full_note_via_ai_factory(full_note, timestamp, tags_snapshot, log_file, ...)`。
- AI 工厂：
  - `entries_ingest(payload)`：
    - 校验 `raw_text`；
    - 根据长度走三档逻辑（<=60 / 60~600 / >600）；
    - 使用 `_extract_scene_tags_from_raw_text` 从正文解析 `scene_tags`；
    - 构造 `entry`，写入 `entries`；
    - 同步触发向量化写入 `entry_embeddings`（失败时仅记录日志）。
  - `entries_repo.insert_entry(entry)`：
    - 所有 `dict`（含 `scene_tags`）通过 `Json(...)` 适配写入 json/jsonb/text 列。

### 3.2 RAG 问答

- 上游：三栏 `QAService.ask_rag` 通过 `task_executor.submit_task("RAG", payload)` 或回退直连。
- AI 工厂：
  - `rag_api.qa_answer_rag(payload)`：
    - 转发到 v2 流水线 `qa_answer_rag_v2`；
    - 向调用方返回 `question/answer/citations`，并附加 `_intent/_sources/_structure/_guard` 等调试字段。
  - `entries_rag.search_entries`：
    - 基于向量与 entries 做检索，返回 `RetrievedEntry` 列表。

### 3.3 WEB 问答

- 上游：三栏 `QAService.ask_web` 通过 TaskExecutor("WEB") 或回退直连。
- AI 工厂：
  - `web_api.qa_answer_web(payload)`：
    - Node1：`build_query_intent(mode="WEB")`；
    - Node2：`WebSearchExecutor.execute(intent)` → `parallel_web_search_aggregate`；
    - Node3：`synthesize_answer_from_evidences`，生成 `answer + sources`。
  - 当前技术债：WebSearchExecutor/parallel_web_search_aggregate 的实际联网搜索能力尚未完全接好，常返回 0 结果。

### 3.4 场景标签 Node Query

- 对外入口：`scene_tags_api.query_nodes_by_scene_tags(payload)`：
  - 解析 `tags/time_window_days/mode` 为 `SceneTags + NodeQuery`；
  - 调用 `NodeQueryService.query_nodes(query)`；
  - 返回 `NodeRecord` 投影为前端字典列表。
- DB 层：`nodes_repo.query_nodes_basic/hot(filters)`：
  - 基于 `entries.scene_tags`（jsonb）与 `created_at` 做过滤与排序；
  - 使用 `(scene_tags->key) ?| ARRAY[...]` 实现六行标签过滤；
  - `query_nodes_hot` 额外计算 `activity_score`。

## 4. 当前主要技术债

- WEB 通道：
  - 接口契约与流水线结构已稳定，但 Node2 的真实搜索实现/配置未完全落地。
- Node Query 返回：
  - `NodeRecord.tags` 目前统一为空数组，需要从 `entries.scene_tags` 回填，以便前端直接渲染标签。
- config 与错误处理：
  - 多处直接使用 `os.getenv` 与 `print(...)`，未统一通过 config/logging 层；
  - 错误返回结构与异常类型尚未完全按照《接口规范》的统一格式收口。
