我先整理一份「三栏前端排队器」和「AI 工厂 RAG/WEB 通道」的对齐需求清单，用 Markdown 写成可以直接贴进《实施计划和记录》的章节，包含：两侧职责分工、交互协议（字段/状态）、排队策略和并发位设想。先不动代码，只把规格讲清楚。
下面是可以直接贴进《实施计划和记录.md》的规格说明，一次性把「三栏排队器」和「AI 工厂 RAG/WEB 通道」对齐清楚。

---

## 一、整体架构视角：RAG / WEB 双通道 + 前端双排队器

- **AI 工厂侧**  
  - 暴露两条**独立业务通道**：
    - RAG 通道：本地知识库检索 + 答案生成；
    - WEB 通道：联网搜索 + 答案生成。
  - 每条通道内部都走 Node1 → Node2 → Node3 三步，但实现不同：
    - Node1：意图分析 + 守护（共用逻辑，RAG/WEB 区分 `mode`）；
    - Node2：各自的检索实现（RAG → 向量库；WEB → Web 搜索）；
    - Node3：DeepSeek 统一整合回答。

- **三栏前端侧**  
  - 对应维护两个**独立排队器**：
    - RAG 队列：只负责 RAG 通道请求；
    - WEB 队列：只负责 WEB 通道请求。
  - 单用户在三栏页面内：
    - 可以**同时发起一个 RAG + 一个 WEB**，两条请求分别进入两条队列；
    - 避免“先问 RAG 把 WEB 挡在后面”等待 2 倍时间的体感。

---

## 二、AI 工厂：RAG / WEB 通道职责与节点划分

### 1. RAG 通道

- **入口**  
  - [qa_answer_rag](cci:1://file:///d:/AI/ai-factory/ai_factory/integrations/rag_api.py:125:0-155:14) / [qa_answer_rag_v2](cci:1://file:///d:/AI/ai-factory/ai_factory/integrations/rag_pipeline_api_v2.py:81:0-241:5)  
- **Node1：意图分析 + 守护**
  - 调用 [build_query_intent(question_text, mode="RAG", context=...)](cci:1://file:///d:/AI/ai-factory/ai_factory/agents/query_intent_agent.py:281:0-298:64)：
    - 输出 [QueryIntent](cci:2://file:///d:/AI/ai-factory/ai_factory/agents/query_types.py:17:0-52:38)（包含 `need_rag`、`filters`、`sub_queries`、`is_question` 等）；
    - 通过 `_guard` 字段输出“是否为提问”的守护结果。
- **Node2：RAG 检索**
  - 使用 [QueryIntent](cci:2://file:///d:/AI/ai-factory/ai_factory/agents/query_types.py:17:0-52:38) 提供的过滤条件/子查询：
    - 构造向量检索请求；
    - 访问 `entries` + `entry_embeddings`（pgvector）；
    - 调用 Ollama embedding 模型（例如 `qwen3-embedding:4b`）；
    - 返回一批 RAG evidences。
- **Node3：答案生成**
  - 使用 `answer_synthesis_agent.synthesize_answer_from_evidences(...)`：
    - 调用 DeepSeek 回答模型；
    - 生成回答文本 + 结构化信息（如 `_structure`）；
    - 封装成统一输出格式。

### 2. WEB 通道

- **入口**  
  - [qa_answer_web](cci:1://file:///d:/AI/ai-factory/ai_factory/integrations/web_api.py:84:0-304:14)（现有接口）  
  - 或 [run_triple_column_web_qa](cci:1://file:///d:/AI/ai-factory/ai_factory/workflows/triple_column_langchain.py:288:0-303:17)（LangChain 版本 Web QA 链）
- **Node1：意图分析 + 守护**
  - 同样走 [build_query_intent(question_text, mode="WEB", context=...)](cci:1://file:///d:/AI/ai-factory/ai_factory/agents/query_intent_agent.py:281:0-298:64)；
  - `_guard` 逻辑与 RAG 通道一致：
    - 关键词启发式 + 语义 `is_question`；
    - 非提问输入直接在 Node1 拦截。
- **Node2：Web 搜索**
  - `WebSearchExecutor.execute(intent)`：
    - 基于 `sub_queries` 生成多条子查询；
    - 调用 `parallel_web_search_aggregate(...)`，对多子查询并发发起 Web 搜索；
    - 汇总为 WEB evidences。
- **Node3：答案生成**
  - 同样走 `synthesize_answer_from_evidences(...)`：
    - 使用 DeepSeek 回答模型；
    - 输出统一的回答结构（question / answer / sources / `_intent` / `_structure` / `_guard`）。

---

## 三、三栏前端：RAG / WEB 排队器需求对齐

### 1. 前端排队器职责划分

- **RAG 排队器**
  - 管理所有发往 AI 工厂 RAG 通道的请求：
    - 入队条件：用户在 RAG 模式下点“提问”；
    - 出队：当 AI 工厂返回结果，或本地用户取消。
  - 针对单用户：
    - 允许**同时存在至多 1 个活跃 RAG 请求**（执行中）；
    - 其余 RAG 请求：根据策略决定是短队列等待，还是直接拒绝/提示稍后再试。

- **WEB 排队器**
  - 管理所有发往 AI 工厂 WEB 通道的请求：
    - 入队条件：用户在 WEB 模式下点“提问”；
    - 出队规则同 RAG 排队器。
  - 单用户：
    - 允许**同时存在至多 1 个活跃 WEB 请求**；
    - 其余 WEB 请求按策略处理。

### 2. RAG / WEB 双排队器与 AI 工厂的配合要点（单用户体感）

- 单用户在三栏中**先发 RAG 再发 WEB**：
  - RAG 请求通过 RAG 队列 → AI 工厂 RAG 通道；
  - WEB 请求通过 WEB 队列 → AI 工厂 WEB 通道；
  - 若 AI 工厂本地有至少 2 个执行位（worker），则两条请求可以**同时跑**，整体体感为“两个任务在后台一起算”，而不是 30s+30s 串行等待。

- 三栏排队器需要明确的前端状态：
  - **待发送**：排在队列中，尚未发往 AI 工厂；
  - **执行中**：已发往 AI 工厂，对应某个通道上的活跃请求；
  - **已完成**：拿到 AI 工厂返回结果；
  - **已取消/失败**：用户主动取消，或接口调用失败。

---

## 四、本地场景下的执行位（“物理通道”）设想

> 仅做可行性探讨，暂不开发服务端并发调度代码。

- 假设 AI 工厂本地预留 **2 个长任务执行位**（worker）：
  - 每个执行位都具备完整的 RAG/WEB Node1-2-3 能力；
  - 任意时刻一个执行位只跑一个任务；
  - 前 2 个请求（无论 RAG/WEB 组合）可以并行跑在两个执行位上；
  - 第 3 个开始才真正进入队列等待空闲执行位。

- 三栏前端与执行位之间的关系：
  - RAG 排队器 / WEB 排队器负责“**什么时候把请求送给 AI 工厂**”；
  - AI 工厂内部的执行位负责“**请求送进来后什么时候开始真正跑 Node1-2-3**”。

---

## 五、对后续实现/优化的约束提示（从体感出发）

- 单次 RAG / WEB 时延已经是 20–40 秒级，**绝不能无限制排长队**；
- 设计目标应是：
  - **有限的执行位 + 极短的排队长度**；
  - 超过能力上限时，前端/后端应尽快反馈“当前系统繁忙，请稍后再试”，而不是默默让用户等到怀疑工具已失效；
- RAG / WEB 双通道与双排队器的目的：
  - 单用户可以在可接受范围内“同时跑 RAG 与 WEB”；
  - 在不复制大量冗余代码的前提下，逐步演进出更好的多用户并发方案（未来可引入多实例/多模型等）。

---

如果你觉得这个结构可以，我可以再帮你补一小段「面向三栏 PM 的一句话说明」，专门简化成 3–5 行给非技术同学看。