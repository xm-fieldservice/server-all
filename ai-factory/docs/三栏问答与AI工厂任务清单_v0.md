> 状态说明：本文件为 v0 阶段任务清单，记录当时对 5 条链路的任务拆解。当前任务与进度请以《实施计划和记录》等文档为准，本文件仅作为历史参考。

# 三栏问答与 AI 工厂任务清单（v0）

> 用途：作为三栏页面项目与 AI 工厂项目之间的对齐文档，
> 把当前阶段已经讨论清楚的 5 条链路 + 双方任务拆解固化下来。

---

## 一、三栏项目侧任务清单

> 目标：在三栏本地实现 5 条链路的 UI 和调用框架，所有“写库/解释”统一通过 AI 工厂接口完成。

### A. 模式与服务骨架

- **T1：定义 5 种模式枚举**
  - `NOTE`（笔记入库）
  - `RAG`（RAG 问答）
  - `WEB`（联网问答）
  - `INJECT`（注入问答）
  - `MINDMAP`（脑图解释）
  - 顶部 5 个单选按钮只负责设置 `current_mode`。

- **T2：建立本地服务层骨架**
  - `NoteService`
    - 封装“记笔记 / 问答对写回 entries”，内部调用 AI 工厂 `entries_ingest`。
  - `QAService`
    - `ask_rag(question, context)`
    - `ask_web(question, context)`
    - `ask_inject(question, context)`（先占位）
  - `MindmapService`
    - `project_from_output(text_block, context)`
  - 先实现最小骨架（可以只打印日志），接口固定即可。

### B. 五条链路的 UI & 调用逻辑

- **T3：笔记入库链路（NOTE 模式）**
  - 中栏 `Alt+Enter`：
    - 统一调用 `NoteService.save_note(...)`；
    - 内部通过 `entries_ingest` → AI 工厂 `NoteIngestAgent` → 写 entries。
  - 收口所有记笔记入口，避免散落调用。

- **T4：RAG 问答链路（RAG 模式）**
  - 中栏 `Ctrl+Enter`：
    - 在输出框显示“问题”（带明确标记）。
    - 调用 `QAService.ask_rag(question, context)`：
      - v0：如果 AI 工厂 `qa_answer_rag` 未 ready，可以先返回假数据或简单调本地模型；
      - 目标状态：显示 `citations`（entries 片段）及可选 `answer`。
    - 输出框展示：
      - 问题；
      - 召回片段列表（可折叠/展开）。

- **T5：联网问答链路（WEB 模式）**
  - 中栏 `Ctrl+Enter`：
    - 输出框中先显示“问题”；
    - 调用 `QAService.ask_web(question, context)`：
      - v0 可直接调用现有“联网 Team”（3 节点）；
      - 目标状态：走 AI 工厂 `qa_answer_web`。
    - 输出框展示：
      - 问题 + 最终联网答案（标明来源）。

- **T6：注入问答链路（INJECT 模式）**
  - **注入阶段**：
    - `Ctrl+Enter`：按现有逻辑，把结构化文本注入 IDE（未来由 `InjectionStructAgent` 参与）。
  - **写回阶段**：
    - 用户从 IDE 复制回答回中栏；
    - 在合适模式下 `Alt+Enter`：
      - 组合“问+答”文本；
      - 调 `NoteService.save_qa_pair(...)`；
      - 通过 `entries_ingest` → AI 工厂 `NoteIngestAgent` 写入 entries。

- **T7：脑图解释链路（MINDMAP 模式）**
  - `Alt+Enter`：
    - 收集输出框当前所有文本；
    - 调 `MindmapService.project_from_output(text_block, context)`：
      - v0 可先用假数据/简单规则；
      - 目标状态：走 AI 工厂 `mindmap_project` → `MindmapExplainAgent / MindmapProjectionAgent`。
    - 用返回的 `graph_payload` 更新右栏脑图。

### C. Agent 前后处理预留

- **T8：预留前后处理 Hook**
  - 在上述 5 条链路的本地实现中，预留：
    - 前置处理回调（文本清洗、格式统一、模式检测）；
    - 后置处理回调（对 answer/graph 的本地格式化）。
  - 便于后续把更多 Agent 逻辑接到本地或迁移到 AI 工厂。

---

## 二、AI 工厂项目经理侧任务清单

> 目标：在 AI 工厂内部用一组 Agent 链路支撑三栏的 5 个场景，对外只暴露少量稳定的高层接口。

### A. 笔记入库链路 / NoteIngestAgent

- **F1：强化 NoteIngestAgent + entries_ingest**
  - 责任：
    - 输入：`raw_text` + `project_code` + `user_id` + `note_datetime` + `extra_context`；
    - 使用前置模型（当前为 local deepseek-r1）生成：
      - `id/title/summary/content`；
    - 将：
      - `entry_id`（用 id 或 fallback）  
      - `title`  
      - `summary_ai`  
      - `content`  
      - `created_at/project_code/user_id`  
      写入 `entries` 表；
    - 返回：`{"entries": [{"entry_id", "title", "content"}]}`。
  - 使用场景：
    - 链路 1：普通笔记入库；
    - 链路 4：注入问答问答对写回；
    - 其他链路的最终 Q&A 可选写库。

### B. RAG 问答链路

- **F2：RagQueryAgent（意图/查询构造）**
  - 输入：自然语言问题 + context；
  - 输出：
    - `intent_type`、`keywords`、`filters`（project / tag / time 等）；
  - 用途：给 `rag_pipeline.retrieve_for_query` 提供高质量的检索请求。

- **F3：RAG 问答接口：qa_answer_rag(payload)**
  - 对外接口（`ai_factory.integrations`）：
    - 输入：
      - `question_text`
      - `project_code` / `user_id`
      - `context_entry_ids` / 其他上下文（可选）；
    - 内部流程：
      1. `RagQueryAgent`：问句 → 检索请求；
      2. `rag_pipeline.retrieve_for_query`：召回 entries/chunks；
      3. （可选）`QaAnswerAgent`：生成自然语言 `answer`；
    - 返回：
      - `answer`（可选，可以先留空）；
      - `citations`：每条含 `entry_id/title/snippet/score`。

- **F4：RAG 问答写库策略**
  - 设计并实现：
    - 哪些 RAG 问答需要写回 entries；
    - 写成什么结构（如“question entry + answer entry”或单条复合 entry）。

### C. 联网问答链路

- **F5：WebQueryAgent（联网查询意图）**
  - 输入：自然语言问题；
  - 输出：
    - `search_queries`、目标站点、过滤条件等；
  - 用于驱动“联网 Team”的 1 号节点。

- **F6：联网问答接口：qa_answer_web(payload)**
  - 对外接口：
    - 输入：`question_text` + `options`（是否联网、最大结果数等）；
    - 内部：
      - `WebQueryAgent` 生成搜索任务；
      - 串接已有“3 节点 Team”（1 搜索 / 2 整理 / 3 总结）；
      - 3 号节点输出作为 `answer`；
      - 可选：将 Q&A 写入 entries（调用 `entries_ingest`）。
    - 返回：
      - `answer` 
      - （可选）`citations` 或 `sources`。

### D. 注入问答链路

- **F7：InjectionStructAgent 规范与实现**
  - 输入：
    - 口语化/自由文本指令（可能来自语音识别）；
  - 输出：
    - 面向 IDE 的任务样式结构化文本：
      - 清晰的目标；
      - 步骤/约束；
      - 必要上下文。
  - 用途：
    - 在通过注入通道发送给 IDE 之前，先规整语句；
    - 规范由 AI 工厂牵头定义（字段、风格、长度）。

> 注：写回 entries 部分继续复用 F1（`entries_ingest` + `NoteIngestAgent`）。

### E. 脑图解释链路

- **F8：脑图解释与投射 Agent**
  - `MindmapExplainAgent`：
    - 输入：输出框全量文本；
    - 输出：结构化主题/层级/关系表示；
  - `MindmapProjectionAgent`：
    - 输入：上述结构；
    - 输出：`graph_payload = {nodes, edges}`；
    - 可根据需要写入 `map_snapshots`。

- **F9：脑图接口：mindmap_project(payload)**
  - 对外接口：
    - 输入：
      - `text_block`（输出框文本）；
      - `scope`（项目/会话等）；
    - 内部：
      - `MindmapExplainAgent` + `MindmapProjectionAgent`；
      - 可选写 `map_snapshots`。
    - 返回：
      - `graph_payload`：供三栏右栏直接渲染脑图。

---

*说明：本文件只整理任务拆解和接口职责，不强制实现顺序。当前约定：短期内仅推进 F1（NoteIngestAgent/entries_ingest）相关实现，其余链路先停留在设计层面。*
