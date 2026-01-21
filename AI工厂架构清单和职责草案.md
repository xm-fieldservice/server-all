> 状态说明：本文件为 2025-12 月的 E 版草案，核心模块清单与职责已整合进《项目工程结构25-12-8》和 docs/架构清单_AI工厂_v0，后续不再单独作为权威规范，遇到冲突时以四份核心文档为准。

下面这份是**只针对「AI 工厂」本身**的架构草案，不含整个广义知识库，只关注：  
- AI 工厂要有哪些模块  
- 每个模块干什么、目的是什么  
- 这些模块之间怎么配合  

你先看结构和命名是否顺眼，我们再细化。

> **版本说明（E 版，2025-12）**  
> - 已落地的核心模块：`ai_factory.config`、`ai_factory.db`、`ai_factory.agents`、`ai_factory.rag`、`ai_factory.frameworks`、`ai_factory.integrations`，以及配套的 `ai_factory.web` / `ai_factory.workflows` 等。  
> - 仍在规划/逐步落地中的模块：`ai_factory.models`、`ai_factory.tools`、`ai_factory.testing` / `ai_factory.lab`、`ai_factory.shelf`、`ai_factory.cli` 等。  
> - 本说明书作为 AI 工厂后续迭代的**架构底座**，会优先保证模块职责与现有代码保持一致，未实现部分视为规划目标。

---

## 一、整体设计一句话

> **AI 工厂 = 面向广义知识库的“AI 能力底座 + 组件装配线 + 性能评测工具集”**，  
> 提供统一的：数据访问、Agent 组装、RAG 封装、工具/MCP/Memory 挂载、性能评测与货架信息输出。

它本身不负责“所有知识”的最终形态，只负责提供**服务知识库的 AI 能力与评测结果**。

---

## 二、顶层结构（包/模块清单）

建议 `ai_factory` 包内的一级模块大致这样（名称可微调）：

> 注：其中 **1/2/4/5/7/10** 已在当前代码中落地，**3/6/8/9/11** 为规划中或部分存在的模块，后续会按本清单逐步补齐。

1. **`ai_factory.config`**  
2. **`ai_factory.db`**  
3. **`ai_factory.models`**（数据模型/DTO，不是 LLM 模型）  
4. **`ai_factory.agents`**  
5. **`ai_factory.rag`**  
6. **`ai_factory.tools`**  
7. **`ai_factory.frameworks`**  
8. **`ai_factory.testing` / `ai_factory.lab`**（性能评测与对比）  
9. **`ai_factory.shelf`**（对外暴露“货架视图”的接口）  
10. **`ai_factory.integrations`**（与问答系统等上层应用的对接）  
11. **`ai_factory.cli`**（脚本/命令行入口）

下面逐个说明“目的 + 职责 + 大致子模块”。

---

## 三、模块级设计（含目的与功能）

### 1. `ai_factory.config` —— 统一配置层

- **目的**  
  - 把连接串、API Key、默认参数等统一封装，避免到处 `os.environ`。
- **主要功能**  
  - 读取 [.env](cci:7://file:///D:/AI/desktop_app/.env:0:0-0:0)、环境变量、配置文件（如 `config/*.yaml`）。  
  - 导出统一的 `Settings` 对象给其他模块用。  
- **示例子文件**  
  - `settings.py`：全局配置入口。  
  - `logging_config.py`：日志规范。

---

### 2. `ai_factory.db` —— 数据访问 & 仓储层

- **目的**  
  - 统一访问数据库，包括：
    - `entries` / `map_snapshots` / `biz.*` 等知识层表；  
    - RAG、向量库相关表（如果用 pgvector）；  
    - 性能评测相关表（后续扩展）。
- **主要功能**  
  - 连接管理（你已有的 `pgvector_client.py` 属于这里）。  
  - 按“领域/表”划分的 repository：
    - `entries_repo.py`：事实层流水读写；  
    - `maps_repo.py`：解释层快照；  
    - `eval_repo.py`：评测流水、性能指标；  
    - `biz_*_repo.py`：业务事实表访问。
- **示例子文件**  
  - `pgvector_client.py`（已存在）  
  - `entries_repo.py`  
  - `map_snapshots_repo.py`  
  - `eval_runs_repo.py`（存性能测试结果）

---

### 3. `ai_factory.models` —— 内部数据模型

- **目的**  
  - 用 dataclass / Pydantic 把“Agent 配置、评测任务、评测结果、组件描述”等结构化表示出来，方便在模块之间传递，而不是传一堆裸 dict。
- **主要功能**  
  - 定义：`AgentSpec`, `ToolSpec`, `MemorySpec`, `EvalTask`, `EvalResult`, `ShelfItem` 等。
- **示例子文件**  
  - `agent_models.py`  
  - `eval_models.py`  
  - `shelf_models.py`

---

### 4. `ai_factory.agents` —— Agent / Team 组装与管理核心

- **目的**  
  - 把现在 desktop_app 里做的 “AgentConfig 拼装、工具/Memory 挂载、预检、导出 JSON” 下沉到这里，成为**统一的 Agent 工厂**。
- **主要功能**  
  - **配置层**：
    - 根据高层描述（任务类型、所需工具、记忆策略）生成 Agent/Team 配置（不依赖 UI）。  
  - **挂载层**：
    - 根据传入的 `ToolSpec`、`MemorySpec` 挂载工具/MCP/向量库。  
  - **导出层**：
    - 导出为 AutoGen 标准 Component 配置，供脚本、CI、应用工程使用。  
  - **预检层**：
    - 检查所需环境变量、工具依赖、连接可用性。
- **示例子文件**  
  - `builder.py`：从高层描述生成 Agent 配置。  
  - `mounting.py`：实现“三类组件挂载规范”的代码版。  
  - `runtime_factory.py`：根据配置生成 AutoGen 运行时实例。

---

### 5. `ai_factory.rag` —— RAG / Memory / 向量库封装

- **目的**  
  - 把向量库、Memory System（如 ChromaDB、pgvector）集成规范化，  
    实现从 `entries` → 切块 → 索引 → 检索 → 回写 的流水线。
- **主要功能**  
  - 向量库客户端封装（Chroma、pgvector 等）。  
  - Memory System 适配（按 AutoGen 0.7.1 规范）。  
  - 索引/检索 API（对上层隐藏细节）。
- **示例子文件**  
  - `chroma_memory.py`  
  - `pgvector_index.py`  
  - `pipeline.py`：`index_entries(entry_ids)`、`search(query, filters)` 等。

---

### 6. `ai_factory.tools` —— 工具 / MCP / 组件清单

- **目的**  
  - 管理所有工具类组件：
    - 普通 Function Tools；  
    - MCP 服务器；  
    - 其它外部服务型工具。
- **主要功能**  
  - 工具 manifest / registry 读取与校验。  
  - 提供统一的 `ToolRegistry` 接口供 `ai_factory.agents` 调用。  
- **示例子文件**  
  - `registry.py`：统一的工具注册表访问。  
  - `loader.py`：加载/验证工具配置。

---

### 7. `ai_factory.frameworks` —— 对外部框架的适配层

- **目的**  
  - 把 AutoGen、LangChain、LlamaIndex、GraphRAG 等**外部框架的调用细节隔离起来**，  
    让上层只依赖 `ai_factory` 自己的接口。
- **主要功能**  
  - AutoGen 封装（创建 Agent、GroupChat、Memory 等）。  
  - 未来引入 LangChain/LlamaIndex/GraphRAG 时的统一适配。
- **示例子文件**  
  - `autogen_adapter.py`  
  - `graphrag_adapter.py`  
  - `langchain_adapter.py`

---

### 8. `ai_factory.testing` / `ai_factory.lab` —— 性能评测与对比

- **目的**  
  - 实现你说的“性能对比”和“货架式性能管理”的底层能力，  
    把 Prompt / Agent / 组合方案的效果变成可重复、可记录、可比较的结果。
- **主要功能**  
  - 评测任务定义（测试集、指标）。  
  - 执行评测任务，对指定 Agent/方案跑一轮，生成 `EvalResult`。  
  - 把评测流水写入 `db.eval_runs_repo`。  
- **示例子文件**  
  - `eval_runner.py`：执行单个评测任务。  
  - `benchmarks.py`：常用基准任务（例如“个人长记忆测评”、“问答准确率测评”等）。  

---

### 9. `ai_factory.shelf` —— 货架视图输出层

- **目的**  
  - 给上层（问答系统、管理界面、脚本）提供**一个统一的“货架接口”**：  
    - 查“现在有哪些 Agent/模型/工具组合可用”；  
    - 查“这些组合在历史上的表现如何”；  
    - 查“与某个任务/分类相关的推荐方案”。
- **主要功能**  
  - 从 `db` + `models` + `testing` 里聚合数据，返回结构化 `ShelfItem` 列表。  
  - 实现按分类/标签/指标过滤和排序。
- **示例子文件**  
  - `view.py`：对外的查询接口，比如 `list_agents_shelf(...)`、`get_recommended_configs(task_type, domain)`。  

---

### 10. `ai_factory.integrations` —— 与问答系统 / 上层应用的对接

- **目的**  
  - 明确化 AI 工厂“对上”的接口：  
    - 问答系统如何调用？  
    - 桌面/Web 应用如何调用？  
  - 这些统一在这里定义，避免上层应用直接裸调底层实现。
- **主要功能**  
  - 为问答系统提供：
    - `answer_query(query, context, policy)` 这类高层接口；  
    - 内部自动：
      - 选 Agent/方案（基于 `shelf` 推荐）；  
      - 走 RAG/Agent 执行；  
      - 记录本次调用流水（写 `entries` + 评测信息）。
- **示例子文件**  
  - `qa_gateway.py`：问答网关（供 Q&A 系统调用）。  
  - `notes_integration.py`：与笔记/entries 场景的特定集成。

---

### 11. `ai_factory.cli` —— 脚本与命令行入口

- **目的**  
  - 把“生成 Agent 配置”、“跑一次评测”、“刷新货架视图”等操作，  
    做成可在 CI / 终端里运行的命令行工具。
- **主要功能**  
  - `ai-factory gen-agent ...`  
  - `ai-factory run-eval ...`  
  - `ai-factory export-shelf ...` 等。
- **示例子文件**  
  - `main.py`：统一 CLI 入口。  
  - 若干子命令实现。

---

## 四、整体设计关系简述

可以简单理解为三层（只看 AI 工厂内部）：

- **最底层：config + db + frameworks**  
  - 负责“连得上、调得通”。

- **中间层：agents + rag + tools + testing**  
  - 负责“能组装、能跑、能评测”。

- **顶层：shelf + integrations + cli**  
  - 负责“能被上层系统方便使用，并把结果呈现为货架视图”。

---

## 五、下一步建议

如果你觉得这个**模块清单 + 职责划分**大体符合你的直觉，我们可以下一步：

1. 先在 `项目工程结构25-12-8.md` 里，把这份清单整理成一节“AI 工厂内部模块结构”；  
2. 然后选一个你最想先落地的模块组（比如 `db + agents`，或者 `rag + testing`），我帮你细化到“具体文件名 + 核心类/函数签名”的级别。

你可以先告诉我：  
- 这个清单里，哪几个模块是**第一批必须有的**？  
- 优先顺序你更想是：`db/agents/rag` 先，还是 `testing/shelf` 先？