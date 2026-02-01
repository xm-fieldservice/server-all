## 总体说明

三栏页面PM对笔记入库他这一侧的接口描述：已经基本达到了广义插拔接口的程度：

我先帮你在代码里把这条“笔记入库通道”的接口找出来，看三栏页面现在是怎么把数据写入 `entries` 表的，再评估一下它是不是已经是一个可插拔的通用标准。如果不是，再一起整理出一个可以在别处复用的接口形式（包括参数约定、调用方式等）。

我会先在项目里搜索跟三栏页面、entries 写入、note/entry channel 相关的实现。

我先在项目里把“笔记入库通道”真正调用 `entries` 表的代码找出来，看看当前三栏页是通过什么接口写入 entries 的，然后评估它是否已经是一个通用、可插拔的标准。接下来我会总结出一份你可以在别处直接调用的接口说明。

Fast Context 搜索刚才失败了，我改用项目内的常规文件搜索和全文检索来定位“三栏页面笔记入库”的实现，然后再给你结论和接口整理。

我已经找到了核心的 `swimlane_service.py` 和设计文档，接下来会直接打开这些文件，看清楚三栏页面是如何通过服务层把数据写入 `entries` 表的，然后判断这个“通道”是否已经是一个可在别处共用的接口，并给你总结一份接口说明。

我先在仓库里把“笔记入库链路”完整找出来（比如 `sync_full_note_to_md_and_db`、`NoteSessionService`、`entries` 相关 HTTP 调用），梳理目前三栏是通过哪个通道把数据写进 `entries` 表的。然后我会基于实际实现回答两件事： 1）这个通道现在是不是一个“广义可插拔”的标准接口；2）如果要在别的应用里共用，需要遵守哪些请求结构/字段约定，我会帮你整理成一份接口说明。

我需要先把三栏里现有的“笔记入库链路”代码和设计文档看完整（NoteSessionService、ai_factory_ingest、五栏数据管理以及注入工具设计），再判断这个通道是不是已经是一个可插拔的标准接口，并整理出你在别处复用时要调用的那个“官方入口”和参数约定。

我已经在核心文档和服务层代码里看到：目前三栏页面的“笔记入库通道”是通过 [core.ai_factory_ingest.ingest_full_note_via_ai_factory](cci:1://file:///d:/AI/injection-legacy-columns/core/ai_factory_ingest.py:118:0-208:13) 统一封装 AI 工厂的 `entries_ingest`。接下来我会在 `五栏数据管理.py` 里把这一链路完整找出来（尤其是 `log_raw_entry_to_server` 的实现），确认现在这条通道的入参/语义是不是已经对 UI 解耦，能当成一个通用的“工作记录 → entries”接口。然后我会用中文帮你总结两部分：1）这个接口是否已经是广义可插拔标准；2）如果你要在别的应用里用，应该如何构造参数和调用。

我已经定位到三栏页面当前的“笔记入库通道”：`MainWindow.log_raw_entry_to_server` → [core.ai_factory_ingest.ingest_full_note_via_ai_factory](cci:1://file:///d:/AI/injection-legacy-columns/core/ai_factory_ingest.py:118:0-208:13) → AI 工厂的 `entries_ingest`，以及异步 `_enqueue_note_save_task` 的调用点。下一步我会把 `log_raw_entry_to_server` 和 `_enqueue_note_save_task` 的实现细节打开，看它们对上层 UI 的入参约定、如何处理 swimlane 工作父卡（parent_entry_id / execution lane），然后基于这些信息回答你：1）这条通道是否已经是广义可插拔标准；2）如果你在别处想共用，要按什么字段构造 payload。
我已经把三栏当前的笔记入库链路（[log_raw_entry_to_server](cci:1://file:///d:/AI/injection-legacy-columns/%E4%BA%94%E6%A0%8F%E6%95%B0%E6%8D%AE%E7%AE%A1%E7%90%86.py:6926:4-7128:17) → [ingest_full_note_via_ai_factory](cci:1://file:///d:/AI/injection-legacy-columns/core/ai_factory_ingest.py:118:0-208:13) → `entries_ingest`）和相关文档都看完了。下面我先用你的问题的视角，直接给出结论和一份可以在别处复用的“官方接口说明”。



## 1. 结论先说

- **系统级“笔记入库通道”已经是可插拔的**：  
  真正的标准接口在服务层，而不是 UI。  
  目前三栏使用的通道是：

  - UI 层：[MainWindow.log_raw_entry_to_server(...)](cci:1://file:///d:/AI/injection-legacy-columns/%E4%BA%94%E6%A0%8F%E6%95%B0%E6%8D%AE%E7%AE%A1%E7%90%86.py:6926:4-7128:17)
  - 服务层：[core.ai_factory_ingest.ingest_full_note_via_ai_factory(...)](cci:1://file:///d:/AI/injection-legacy-columns/core/ai_factory_ingest.py:118:0-208:13)
  - 后端：`ai_factory.integrations.entries_ingest.entries_ingest(payload)`  
    → 最终写入统一的 `entries` 表

- **只要其他应用也按这个服务层接口（或 payload 协议）调用**，同样可以把“工作记录”写进 `entries` 表，而且能带上：
  - 场景标签 `scene_tags`（department / planning / execution / status / work / rating）
  - 父子关系 `parent_entry_id`
  - 额外系统说明 `system_memo_text` 等

换句话说：**[ingest_full_note_via_ai_factory](cci:1://file:///d:/AI/injection-legacy-columns/core/ai_factory_ingest.py:118:0-208:13) + 其内部构造的 payload，可以视为“广义插拔标准接口”**。  
三栏自己的 [log_raw_entry_to_server](cci:1://file:///d:/AI/injection-legacy-columns/%E4%BA%94%E6%A0%8F%E6%95%B0%E6%8D%AE%E7%AE%A1%E7%90%86.py:6926:4-7128:17) 只是“在这个标准上加了一层泳道维度的便利逻辑”。

---

## 2. 当前三栏笔记入库链路（概览）

从 `docs/架构清单_三栏_v0.md` 和代码看，链路是：

1. Alt+Enter → [take_note()](cci:1://file:///d:/AI/injection-legacy-columns/%E4%BA%94%E6%A0%8F%E6%95%B0%E6%8D%AE%E7%AE%A1%E7%90%86.py:7188:4-7325:57)  
   先写本地 Markdown 工作记录。
2. 然后入队：[_enqueue_note_save_task(full_note, timestamp, tags_snapshot, system_memo_text)](cci:1://file:///d:/AI/injection-legacy-columns/%E4%BA%94%E6%A0%8F%E6%95%B0%E6%8D%AE%E7%AE%A1%E7%90%86.py:7131:4-7147:39)
3. 后台线程 [_note_save_worker_loop](cci:1://file:///d:/AI/injection-legacy-columns/%E4%BA%94%E6%A0%8F%E6%95%B0%E6%8D%AE%E7%AE%A1%E7%90%86.py:7149:4-7180:24) 消费队列，调用：
   - [self.log_raw_entry_to_server(full_note, timestamp, tags_snapshot, system_memo_text)](cci:1://file:///d:/AI/injection-legacy-columns/%E4%BA%94%E6%A0%8F%E6%95%B0%E6%8D%AE%E7%AE%A1%E7%90%86.py:6926:4-7128:17)
4. [log_raw_entry_to_server(...)](cci:1://file:///d:/AI/injection-legacy-columns/%E4%BA%94%E6%A0%8F%E6%95%B0%E6%8D%AE%E7%AE%A1%E7%90%86.py:6926:4-7128:17) 负责两件事：
   - 根据当前泳道维度（planning / execution）**自动补齐 / 覆盖标签**，推导出：
     - `parent_entry_id`
     - `tags_snapshot["planning"]` / `tags_snapshot["execution"]` / `tags_snapshot["work"]` / 默认 `status=["待开始"]`
   - 调用统一服务层：
     - [ingest_full_note_via_ai_factory(full_note=..., timestamp=..., tags_snapshot=..., log_file=self.log_file, project_code=None, user_id=None, parent_entry_id=..., system_memo_text=...)](cci:1://file:///d:/AI/injection-legacy-columns/core/ai_factory_ingest.py:118:0-208:13)
5. [ingest_full_note_via_ai_factory](cci:1://file:///d:/AI/injection-legacy-columns/core/ai_factory_ingest.py:118:0-208:13) 组装 payload，调用 AI 工厂 `entries_ingest(payload)`，落到 `entries` 表。

因此，**真正对“entries 表”有约定的是 [ingest_full_note_via_ai_factory](cci:1://file:///d:/AI/injection-legacy-columns/core/ai_factory_ingest.py:118:0-208:13) 这一层**。

---

## 3. 可复用的标准接口：[ingest_full_note_via_ai_factory](cci:1://file:///d:/AI/injection-legacy-columns/core/ai_factory_ingest.py:118:0-208:13)

### 3.1 函数签名（Python 内复用）

```python
from core.ai_factory_ingest import ingest_full_note_via_ai_factory

ingest_full_note_via_ai_factory(
    *,
    full_note: str,
    timestamp: str,
    tags_snapshot: dict | None = None,
    log_file: str | None = None,
    project_code: str | None = None,
    user_id: str | None = None,
    parent_entry_id: str | None = None,
    system_memo_text: str | None = None,
) -> None
```

**参数语义：**

- **`full_note`（必传）**  
  完整笔记正文（Markdown），即你希望 AI 工厂用来生成标题、摘要、scene_tags 等的原始文本。

- **`timestamp`（推荐传）**  
  字符串时间，例如 `"2026-01-28 15:45:12"`。  
  内部会作为 `note_datetime` 写入 entries，用于排序/分析。

- **`tags_snapshot`（可选 dict）**  
  场景标签快照（UI 自己维护的一份 tag 选择状态）。  
  典型结构（键可以是中文也可以是英文，对应 [_build_scene_tags_line_from_snapshot](cci:1://file:///d:/AI/injection-legacy-columns/core/ai_factory_ingest.py:69:0-115:42) 的 key 映射）：

  ```python
  tags_snapshot = {
      "department": ["软件部"],      # 或 "部门": ["软件部"]
      "planning": ["计划"],          # 或 "规划": ["计划"]
      "execution": ["笔记"],         # 或 "执行": ["笔记"]
      "status": ["进行中"],         # 或 "状态": ["进行中"]
      "work": ["in_work"],          # 工作切片标记
      "rating": ["A"],             # 或 "评价": ["A"]
  }
  ```

  在 AI 工厂侧，`entries_ingest` 会从 `extra_context.tags_snapshot` 里解析出标准的 `scene_tags` 并落库。

- **`log_file`（可选）**  
  溯源：这条记录对应的本地 MD 文件路径或说明；会放进 `payload.extra_context["log_file"]`，方便将来回溯。

- **`project_code` / `user_id`（可选）**  
  预留多项目、多用户场景：
  - `project_code`：如 `"three_column_inject"`、`"db_vector"`；
  - `user_id`：将来用于多用户。

- **`parent_entry_id`（可选）**  
  如果你希望这条笔记成为某个“父节点（工作卡/规划卡）”的子节点，在这里传入父节点的 `entry_id`。  
  函数会把它写到 `payload.extra_meta.parent_entry_id`，由 AI 工厂 `entries_ingest` 写入 `entries.parent_entry_id` 或关系结构。

- **`system_memo_text`（可选）**  
  系统生成的结构化说明/摘要等，作为单独字段传给 AI 工厂，用于写 `entries.memo` 一类的系统备注字段，不污染正文。

---

### 3.2 对 AI 工厂侧 payload 的约定（给非 Python 调用方参考）

[ingest_full_note_via_ai_factory](cci:1://file:///d:/AI/injection-legacy-columns/core/ai_factory_ingest.py:118:0-208:13) 内部构造的 payload 形如：

```jsonc
{
  "raw_text": "完整的 Markdown 笔记内容...",
  "project_code": "optional_project_code",
  "user_id": "optional_user_id",
  "note_datetime": "2026-01-28 15:45:12",   // 来自 timestamp
  "system_memo_text": "可选的系统说明文本",
  "extra_context": {
    "log_file": "D:/AI/xxx/工作记录.md",
    "tags_snapshot": {
      "department": ["软件部"],
      "planning": ["计划"],
      "execution": ["笔记"],
      "status": ["待开始"],
      "work": ["in_work"]
    }
  },
  "extra_meta": {
    "parent_entry_id": "ent_xxx_parent"      // 如有
  }
}
```

**如果你在别处不是用 Python，而是自己直接对接 AI 工厂的 entries_ingest API**，只要按上面这个结构构造请求体即可。  
（具体 HTTP 路径在 AI 工厂仓库里，以 `entries_ingest(payload)` 为准；这里不假设 URL，以免“编造”。）

---

## 4. 三栏特有的泳道逻辑（可选复用）

当前 [MainWindow.log_raw_entry_to_server](cci:1://file:///d:/AI/injection-legacy-columns/%E4%BA%94%E6%A0%8F%E6%95%B0%E6%8D%AE%E7%AE%A1%E7%90%86.py:6926:4-7128:17) 在调用 [ingest_full_note_via_ai_factory](cci:1://file:///d:/AI/injection-legacy-columns/core/ai_factory_ingest.py:118:0-208:13) 之前，做了三件**UI 侧附加处理**（这些不是标准接口要求，只是三栏自己的“约定俗成”）：

1. **补默认状态：**

   - 如果 `tags_snapshot["status"]` 没填，自动补成 `["待开始"]`。

2. **规划维度（`_current_swimlane_dimension == "planning"`）时：**

   - 从 `_current_planning_parent` 取：
     - `entry_id` → 作为 `parent_entry_id`
     - `lane`（父卡所在列，如“战略/目标/计划”）→ 推导子层规划标签：
       - `战略 → 目标 → 计划 → 项目`
   - 如果当前没有锁定父卡，则：
     - 若没显式指定 `planning`，默认 `planning = ["其他"]`。

3. **执行维度（`_current_swimlane_dimension == "execution"`）时：**

   - 从 `_current_execution_target` 取：
     - `parent_id` → `parent_entry_id`
     - `lane_type` → 子卡执行列（规则）：
       - 若以 `"DIRECT:"` 开头，例如 `DIRECT:笔记` → 子卡 `execution = ["笔记"]`
       - 否则按：
         - `工作 → 议题 → 任务 → 笔记`
         - 或直接复用 `lane_type`
   - 如果没有有效目标：
     - 若没指定 `execution`，默认 `execution = ["其他"]`
     - 并保证 `work` 标签中包含 `"in_work"`。

**是否要在别的应用里重用这套逻辑，取决于你是否也需要“泳道 UI → tags + parent_entry_id”的同构语义**。  
如果只是“一个应用简单写日志到 entries”，你可以只做两步：

- 自己构造好 `tags_snapshot`（不必知道 swimlane 概念）
- 直接调用 [ingest_full_note_via_ai_factory(...)](cci:1://file:///d:/AI/injection-legacy-columns/core/ai_factory_ingest.py:118:0-208:13)，按 3.1 的协议来。

---

## 5. 给你的一句话建议

- **如果你在同一 Python 环境里复用**：  
  直接把 [core.ai_factory_ingest.ingest_full_note_via_ai_factory](cci:1://file:///d:/AI/injection-legacy-columns/core/ai_factory_ingest.py:118:0-208:13) 当成“官方笔记入库通道”，别去依赖 MainWindow 的 UI 逻辑。

- **如果你在别的技术栈 / 进程里复用**：  
  按 3.2 构造与 [ingest_full_note_via_ai_factory](cci:1://file:///d:/AI/injection-legacy-columns/core/ai_factory_ingest.py:118:0-208:13) 等价的 payload，调用 AI 工厂的 `entries_ingest` API，即可写入 `entries` 表。

如果你愿意，我可以再帮你画一张很简短的“时序图 / 字段表”，方便你在文档或别的项目里直接引用。



====================

服务器173的PM对服务器侧笔记入库、RAG、web查询通道的描述
你这边已经把「三栏页面 → `ingest_full_note_via_ai_factory`」这一段前端/客户端侧通道梳理清楚了。下面我从 **AI 工厂（服务器）这一侧**，用同一种视角，帮你整理 3 条“官方通道”：

1. **笔记入库通道（entries_ingest）**  
2. **RAG 通道（基于 entries / 其他文档的检索 + 生成）**  
3. **Web 查询通道（调用外部搜索引擎，然后生成或返回结构化结果）**

我会用「服务/接口」的角度来写，这样你可以把三栏那边的客户端接口，和这三条服务器通道拼成一张完整的链路图。

> 说明：下面的 URL 仅是**推荐命名**，真实部署时你可以按自己的网关/路由规则来定。关键在于 **请求体结构 + 语义**，而不是具体路径。

---

# 一、AI 工厂侧：笔记入库通道（entries_ingest）

**双通道设计**：系统提供两条入库通道，满足不同场景需求

## 通道概览

| 通道 | 类型 | 适用场景 | 特点 |
|------|------|----------|------|
| **1号通道** | 同步写库 | 短文本快速入库，不需要LLM处理 | 直接插入数据库，失败立即返回 |
| **2号通道** | 异步整理+写库 | 长文本需要LLM生成标题/摘要 | 先入队列，整理成功后再写库，失败不降级 |

---

## 1.1 1号通道（同步写库）

### 服务职责

- **输入**：一条"完整工作笔记"的结构化 payload
- **核心职责**：
  - 直接调用 `entries_repo.insert_entry` 写入 `entries` 表
  - 不调用 LLM（不生成标题、摘要）
  - 同步向量化（可选，失败不影响入库）
  - 返回本次写入的 `entry_id`
- **适用场景**：
  - 短文本（≤60字符），不需要LLM处理
  - 需要立即返回结果，不接受延迟
  - 三栏页面的快速同步写库

### HTTP 接口

- **Method**：`POST`
- **Path**：`POST /api/entries/ingest`

#### 请求体（与 `ingest_full_note_via_ai_factory` 对应）

```jsonc
{
  "raw_text": "完整的 Markdown 笔记内容...",
  "note_datetime": "2026-01-28 15:45:12",
  "project_code": "three_column_inject",     // 可选
  "user_id": "user_123",                     // 可选
  "system_memo_text": "可选的系统说明文本",
  "extra_context": {
    "log_file": "D:/AI/.../工作记录.md",
    "tags_snapshot": {
      "department": ["软件部"],
      "planning": ["计划"],
      "execution": ["笔记"],
      "status": ["待开始"],
      "work": ["in_work"],
      "rating": ["A"]
    }
  },
  "extra_meta": {
    "parent_entry_id": "ent_xxx_parent"
  }
}
```

#### 响应体

```jsonc
{
  "entries": [
    {
      "entry_id": "ent_20260128_000123",
      "title": "完整笔记内容（短文本场景）",
      "content": "完整的 Markdown 笔记内容..."
    }
  ]
}
```

- **`entry_id`**：写进 `entries` 表后的业务唯一 ID
- **`title`**：短文本场景下，直接使用 `raw_text`
- **`content`**：包含原始 Markdown 内容

---

## 1.2 2号通道（异步整理+写库）

### 服务职责

- **输入**：一条"完整工作笔记"的结构化 payload
- **核心职责**：
  - 提交任务到队列（记录 `job_id`）
  - 异步处理（调用 LLM 生成标题、摘要）
  - 成功后写入 `entries` 表（包含生成的 title/summary/scene_tags）
  - 同步向量化
  - 返回 job_id 和最终状态
- **适用场景**：
  - 长文本（>60字符），需要LLM生成标题和摘要
  - 高并发场景，需要解耦请求和响应
  - 需要任务状态查询和重试
- **LLM 配置**：依赖 `DEEPSEEK_API_KEY`，出错直接标记 failed，不降级

### HTTP 接口

- **提交任务**：`POST /ai-factory/entries/ingest`
- **查询状态**：`GET /ai-factory/entries/ingest/{job_id}`

#### 提交任务 - 请求体

```jsonc
{
  "raw_text": "完整的 Markdown 笔记内容...",
  "note_datetime": "2026-01-28 15:45:12",
  "project_code": "three_column_inject",
  "user_id": "user_123",
  "system_memo_text": "可选的系统说明文本",
  "extra_context": {
    "log_file": "D:/AI/.../工作记录.md",
    "tags_snapshot": {
      "department": ["软件部"],
      "planning": ["计划"],
      "execution": ["笔记"],
      "status": ["待开始"],
      "work": ["in_work"],
      "rating": ["A"]
    }
  },
  "extra_meta": {
    "parent_entry_id": "ent_xxx_parent"
  },
  "idempotency_key": "可选的幂等键（用于去重）"
}
```

#### 提交任务 - 立即响应（202 Accepted）

```jsonc
{
  "ok": true,
  "job_id": "job_20260128_000123",
  "status": "queued"
}
```

- **`job_id`**：任务唯一标识，用于后续查询状态

#### 查询状态 - 成功响应（200 OK）

```jsonc
{
  "ok": true,
  "status": "succeeded",
  "entry_id": "ent_20260128_000123",
  "scene_tags": {
    "department": ["软件部"],
    "planning": ["计划"],
    "execution": ["笔记"],
    "status": ["待开始"],
    "work": ["in_work"],
    "rating": ["A"]
  },
  "derived_meta": {
    "title": "给 X 项目写了一轮规划",
    "summary": "……LLM 生成的摘要……"
  }
}
```

- **`status`**：`queued`/`running`/`succeeded`/`failed`
- **`entry_id`**：成功后写入 `entries` 表的业务唯一 ID
- **`scene_tags`**：AI 工厂侧根据 `tags_snapshot` 标准化/补全后的结果
- **`derived_meta`**：LLM 生成的 title 和 summary

#### 查询状态 - 失败响应（200 OK）

```jsonc
{
  "ok": false,
  "status": "failed",
  "error_code": "LLM_TIMEOUT",
  "error_message": "调用 deepseek-chat 超时，超过 600 秒"
}
```

- **`error_code`**：错误码，便于前端展示
- **`error_message`**：详细错误信息

### 任务队列表（ingest_jobs）

系统使用 `ingest_jobs` 表来管理 2号通道的任务：

```sql
CREATE TABLE ingest_jobs (
    job_id TEXT PRIMARY KEY,
    payload_hash TEXT UNIQUE,          -- 幂等键，用于去重
    raw_text TEXT NOT NULL,
    status TEXT DEFAULT 'queued',      -- queued/running/succeeded/failed
    error_code TEXT,
    error_message TEXT,
    entry_id TEXT,                     -- 成功后写入的 entry_id
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

- **幂等性**：相同 `payload_hash` 的请求会复用同一个 job_id
- **错误追踪**：记录失败原因，支持前端重试

---

## 1.3 两种通道的对比与选择

## 1.2 推荐 HTTP 接口形式

### 1）HTTP

- **Method**：`POST`  
- **Path（示例）**：`/ai-factory/entries/ingest`

#### 请求体（与 `ingest_full_note_via_ai_factory` 对应）

```jsonc
{
  "raw_text": "完整的 Markdown 笔记内容...",
  "note_datetime": "2026-01-28 15:45:12",   // 对应 timestamp
  "project_code": "three_column_inject",     // 可选
  "user_id": "user_123",                     // 可选
  "system_memo_text": "可选的系统说明文本",
  "extra_context": {
    "log_file": "D:/AI/.../工作记录.md",
    "tags_snapshot": {
      "department": ["软件部"],
      "planning": ["计划"],
      "execution": ["笔记"],
      "status": ["待开始"],
      "work": ["in_work"],
      "rating": ["A"]
    }
  },
  "extra_meta": {
    "parent_entry_id": "ent_xxx_parent"      // 如有
  }
}
```

与你前面总结的一致：  
三栏那边 `ingest_full_note_via_ai_factory(...)` 做的事，就是把参数整理成 **完全等价的 payload**，然后调用这个后端通道。

#### 响应体（推荐）

```jsonc
{
  "ok": true,
  "entry_id": "ent_20260128_000123",
  "scene_tags": {
    "department": ["软件部"],
    "planning": ["计划"],
    "execution": ["笔记"],
    "status": ["待开始"],
    "work": ["in_work"],
    "rating": ["A"]
  },
  "derived_meta": {
    "title": "给 X 项目写了一轮规划",
    "summary": "……LLM 生成的摘要……"
  }
}
```

- **`entry_id`**：写进 `entries` 表后的主键或业务唯一 ID；
- **`scene_tags`**：AI 工厂侧根据 `tags_snapshot` 标准化/补全后的结果；
- **`derived_meta`**：可选，给上层 UI 或后续 RAG 用。

### 1.3 内部服务形式（非 HTTP 调用方）

#### 1号通道（同步）

在同一后端/同一进程中，可以直接调用内部函数：

```python
from ai_factory.integrations.entries_ingest import entries_ingest

result = entries_ingest(payload: dict) -> dict
```

- 这里的 `payload` 就是 1号通道的请求体；
- 返回值包含 `entry_id` 和原始 `raw_text`（短文本场景）。

#### 2号通道（异步）

异步任务提交：

```python
from ai_factory.integrations.entries_ingest import enqueue_ingest_job

job = enqueue_ingest_job(payload: dict) -> str
```

- 返回 `job_id`，用于后续查询任务状态；
- 实际的入库和整理在后台线程中完成。

---

## 1.4 entries 表结构

### 基础字段

```sql
CREATE TABLE IF NOT EXISTS entries (
    entry_id      TEXT PRIMARY KEY,
    title         TEXT NOT NULL,
    summary_ai    TEXT,
    content       TEXT NOT NULL,
    project_code  TEXT,
    user_id       TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 场景标签字段

```sql
ALTER TABLE entries
ADD COLUMN IF NOT EXISTS scene_tags jsonb DEFAULT '{}'::jsonb;
```

**scene_tags 结构**：

```json
{
  "department": ["软件部"],
  "planning": ["计划"],
  "execution": ["笔记"],
  "status": ["待开始"],
  "work": ["in_work"],
  "rating": ["A"]
}
```

---

## 1.5 三栏页面的通道选择

### 当前实现（1号通道）

三栏页面使用 **1号通道** 的同步写库方式：

```
三栏 UI
  → Alt+Enter
  → take_note()（写本地 Markdown）
  → enqueue_note_save_task()
  → note_save_worker_loop()
  → log_raw_entry_to_server()
  → ingest_full_note_via_ai_factory()
  → POST /api/entries/ingest（1号通道）
  → entries_ingest(payload)
  → insert_entry()
  → 同步返回 entry_id
```

**特点**：
- 同步响应，用户体验好
- 不调用 LLM（适合短文本快速入库）
- 失败立即返回错误

### 潜在改进（2号通道）

如果需要更规范的标题和摘要，可以改用 **2号通道**：

```
三栏 UI
  → POST /ai-factory/entries/ingest（2号通道）
  → 返回 job_id（202 Accepted）
  → 前端轮询 /ai-factory/entries/ingest/{job_id}
  → 后台 LLM 整理 → 写库 → 同步向量化
  → 返回 entry_id + title + summary + scene_tags
```

**特点**：
- 异步处理，解耦请求和响应
- LLM 生成更规范的 title/summary
- 支持任务状态查询和重试

---

# 二、RAG 通道（基于 entries / 文档的检索 + 生成）

这个通道面向的是“**问知识库**”而不是“写 entries”。  
一般路径是：  
**query → 检索（entries + 其他文档）→ 组装上下文 → LLM 生成回答 + 引用**

## 2.1 服务职责

- 接收一个自然语言问题 `query`，以及：
  - 可选的用户/项目信息；
  - 可选的“上下文提示”（比如最近的 `entry_id`、当前泳道的父卡等）；
- 在 `entries` / 向量库 / 其他文档库中检索相关片段；
- 把检索结果作为 context 喂给 LLM；
- 返回：
  - 生成的 `answer`；
  - 结构化的 `citations`（引用来源）；
  - 可选 debug 信息（命中条目、权重、向量相似度等）。

## 2.2 推荐 HTTP 接口形式

- **Method**：`POST`  
- **Path（示例）**：`/ai-factory/rag/query`

### 请求体（示例）

```jsonc
{
  "query": "我最近一周在这个项目上都做了什么？",
  "project_code": "three_column_inject",
  "user_id": "user_123",
  "top_k": 8,
  "source_types": ["entries", "docs"],     // 可选：只查 entries / 也查其他文档
  "filters": {
    "date_from": "2026-01-21",
    "date_to": "2026-01-28",
    "scene_tags": {
      "work": ["in_work"]
    }
  },
  "context_entries": [
    "ent_20260127_000111",
    "ent_20260128_000222"
  ],                                       // 可选：指定必须优先考虑的 entries
  "conversation_id": "conv_abc",          // 可选：多轮对话用
  "debug": false
}
```

### 响应体（示例）

```jsonc
{
  "ok": true,
  "answer": "根据最近一周的工作记录，你主要完成了……（LLM 生成的自然语言回答）",
  "citations": [
    {
      "source_type": "entry",
      "entry_id": "ent_20260127_000111",
      "chunk_id": "chunk_0",
      "score": 0.89,
      "snippet": "……命中的原文片段……",
      "note_datetime": "2026-01-27 10:23:45",
      "scene_tags": {
        "work": ["in_work"],
        "execution": ["笔记"]
      }
    },
    {
      "source_type": "doc",
      "doc_id": "doc_project_plan",
      "chunk_id": "chunk_3",
      "score": 0.83,
      "snippet": "……命中的项目规划文档片段……"
    }
  ],
  "debug_info": null
}
```

- **对三栏/其他 UI 的意义**：
  - 问“帮我总结这段时间干了什么”，“帮我为这几条 entries 写日报”时，用的就是这个 RAG 通道；
  - `citations` 里给了 `entry_id`，前端可以高亮/跳转原始记录。

---

# 三、Web 查询通道（外部搜索 + 生成）

这个通道负责：**把问题发到外部搜索引擎，然后用 LLM 进行信息汇总/整理**。  
跟 RAG 的区别是：  
- RAG 查的是**内部知识库 / entries**；  
- Web 查询查的是**互联网**。

## 3.1 服务职责

- 接收自然语言 `query`；
- 通过一个或多个搜索引擎（如 Bing / Google / 内部镜像）获取搜索结果；
- 过滤/去重/抽取关键信息；
- 可选地用 LLM 做：
  - 聚合总结；
  - 结构化提取（表格、要点列表等）；
- 返回总结 + 原始搜索结果 + 元数据。

## 3.2 推荐 HTTP 接口形式

- **Method**：`POST`  
- **Path（示例）**：`/ai-factory/web/search`

### 请求体（示例）

```jsonc
{
  "query": "2026 年最新的 RAG 最佳实践",
  "top_k": 5,
  "site_filters": ["*"],          // 可选：["arxiv.org", "openai.com"]
  "lang": "zh",                   // 目标输出语言
  "location": "CN",               // 搜索地点/区域（如果搜索引擎支持）
  "timeout_seconds": 15,
  "need_llm_summary": true,
  "return_raw_results": true
}
```

### 响应体（示例）

```jsonc
{
  "ok": true,
  "answer": "综合最近 2025-2026 年的公开资料，RAG 的最佳实践包括……（LLM 总结）",
  "search_results": [
    {
      "rank": 1,
      "engine": "bing",
      "url": "https://example.com/rag-best-practices-2026",
      "title": "RAG Best Practices 2026",
      "snippet": "This article discusses ...",
      "published_at": "2025-11-03"
    },
    {
      "rank": 2,
      "engine": "bing",
      "url": "https://arxiv.org/abs/xxx",
      "title": "A Survey on Retrieval-Augmented Generation",
      "snippet": "We review recent developments ..."
    }
  ]
}
```

---

---

# 四、把双通道与其它服务拼在一起的完整视图

你可以把整个系统理解成 4 条"官方服务"：

## 1. 笔记入库服务（双通道）

### 1号通道：同步写库
- **入口**：`POST /api/entries/ingest`
- **特点**：直接写库，不调用 LLM，失败立即返回
- **适用**：短文本快速入库

### 2号通道：异步整理+写库
- **入口**：
  - 提交：`POST /ai-factory/entries/ingest`
  - 查询：`GET /ai-factory/entries/ingest/{job_id}`
- **特点**：LLM 生成标题/摘要，失败不降级
- **适用**：长文本高并发场景

## 2. 内部知识库问答服务：`rag/query`
- **入口**：`POST /ai-factory/rag/query`
- **特点**：基于 `entries` 检索 + LLM 生成回答
- **返回**：answer + citations（带 entry_id）

## 3. 外部知识搜索服务：`web/search`
- **入口**：`POST /ai-factory/web/search`
- **特点**：调用外部搜索引擎 + LLM 总结
- **返回**：answer + 原始搜索结果

---

## 五、三栏页面的实现方式

三栏页面当前使用 **1号通道** 的同步写库方式：

```
三栏 UI
  → Alt+Enter
  → take_note()（写本地 Markdown）
  → enqueue_note_save_task()
  → note_save_worker_loop()
  → log_raw_entry_to_server()
  → ingest_full_note_via_ai_factory()
  → POST /api/entries/ingest（1号通道）
  → entries_ingest(payload)
  → insert_entry()
  → 同步返回 entry_id
```

**特点**：
- 同步响应，用户体验好
- 不调用 LLM（适合短文本快速入库）
- 失败立即返回错误

### 潜在改进（2号通道）

如果需要更规范的标题和摘要，可以改用 **2号通道**：

```
三栏 UI
  → POST /ai-factory/entries/ingest（2号通道）
  → 返回 job_id（202 Accepted）
  → 前端轮询 /ai-factory/entries/ingest/{job_id}
  → 后台 LLM 整理 → 写库 → 同步向量化
  → 返回 entry_id + title + summary + scene_tags
```

**特点**：
- 异步处理，解耦请求和响应
- LLM 生成更规范的 title/summary
- 支持任务状态查询和重试

---

## 六、适用场景与选择建议

| 场景 | 推荐通道 | 理由 |
|------|----------|------|
| 短文本快速记录（Alt+Enter） | 1号通道 | 同步响应，用户体验好 |
| 长文本（>60字符） | 2号通道 | LLM 生成标题摘要，更规范 |
| 批量导入/多任务并发 | 2号通道 | 异步处理，避免阻塞 |
| 需要立即反馈结果 | 1号通道 | 失败立即报错，便于调试 |
| 需要任务状态查询 | 2号通道 | 可以轮询查询 job_id |

如果你愿意，我可以再帮你画一张简洁的"ASCII 时序图"或"字段对照表"，方便放进设计文档。
