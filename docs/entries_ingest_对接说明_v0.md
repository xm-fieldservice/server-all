> 状态说明：本文件为 NOTE 写库链路的 v0 对接说明。关键字段与行为约定已收口到《AI工厂-对外接口与集成规范》的 3.1.1 小节，本文件主要面向三栏项目开发者，不再单独作为权威规范。

# entries_ingest 对接说明（v0）

> 面向对象：三栏页面项目的开发/PM。
>
> 目标：只描述“笔记入库链路（NOTE 模式）”如何调用 AI 工厂，不涉及 RAG / 联网 / 脑图等其它链路。

---

## 1. 总体行为概述

三栏在「笔记模式」下，通过调用 AI 工厂的 `entries_ingest(payload)` 完成：

1. 将中间栏输入的完整笔记文本作为 `raw_text` 传给 AI 工厂；
2. AI 工厂内部使用本地前置模型（当前为 Ollama 的 `deepseek-r1:8b`）对原文进行规整，生成：
   - `id`
   - `title`
   - `summary`
   - `content`
3. 根据规整结果写入本地数据库 `entries` 表，记录字段包括：
   - `entry_id`（来自 `id` 或自动生成）
   - `title`
   - `summary_ai`
   - `content`
   - `created_at`
   - `project_code`
   - `user_id`
4. 返回一个简单的结构体，包含本次写入 entries 的 `entry_id/title/content`，供三栏做本地缓存或 UI 使用。

> 注意：
> - v0 版本中，三栏不需要关心内部具体如何调用模型和写库；
> - 只需要按本文约定构造 `payload` 并处理返回值即可。

---

## 2. Python 调用入口

在与 AI 工厂共享的 Python 环境中，通过以下方式调用：

```python
from ai_factory.integrations.entries_ingest import entries_ingest

result = entries_ingest(payload)
```

- 模块路径：`ai_factory.integrations.entries_ingest`
- 函数签名：`entries_ingest(payload: Dict[str, Any]) -> Dict[str, Any]`

要求：
- 三栏项目运行时的 Python 解释器需要能够 `import ai_factory`；
- AI 工厂的 `.env` / 数据库连接等由 AI 工厂侧维护，三栏侧不需要额外配置。

---

## 3. payload 字段说明（输入）

`payload` 为一个普通的 Python `dict`，v0 版本约定字段如下：

```python
payload = {
    "raw_text": str,              # 必填，完整笔记原文
    "project_code": Optional[str],
    "user_id": Optional[str],
    "note_datetime": Optional[str],
    "extra_context": Optional[dict],
}
```

### 3.1 必填字段

- **`raw_text: str`**
  - 含义：中间栏当前要写入的一整条笔记内容（允许多行）。
  - 要求：
    - 不做额外裁剪，AI 工厂内部会负责规整；
    - 三栏可以在前面附加最小的上下文（如当前 Section 标题），但建议保持简洁。

### 3.2 建议可选字段

- **`project_code: str | None`**
  - 含义：当前笔记所属的“项目/空间/主题”代码。
  - 作用：
    - AI 工厂会将其写入 `entries.project_code`，利于后续按项目过滤检索；
  - 建议：
    - 三栏如有现成的「场景/项目标识」，可以直接映射到此字段。

- **`user_id: str | None`**
  - 含义：当前使用者的标识（用户名/账号等）。
  - 作用：
    - 写入 `entries.user_id`，便于多用户场景下区分数据。

- **`note_datetime: str | None`**
  - 含义：笔记时间（字符串）。
  - 格式：
    - 建议使用 ISO8601，如：`"2025-12-09T00:38:30+08:00"`；
    - 也可以是其它字符串，AI 工厂会按原样写入 `created_at`，或在缺省时使用当前 UTC 时间。

- **`extra_context: dict | None`**
  - 含义：额外上下文字段，完全自定义，用于调试或后续扩展。
  - 示例：

    ```python
    extra_context = {
        "source": "three_column_ui",
        "section_id": "ea08bfc7-f417-4e08-bc53-5872eca0e42a",
        "tags_snapshot": {...},
    }
    ```

  - 行为：
    - v0 中 AI 工厂会将该 dict 合并进内部的 `base_meta`，部分字段可能在后续版本写入 entries 的 JSONB/扩展字段；
    - 当前版本不会因为缺少该字段而出错。

---

## 4. 返回结构说明（输出）

`entries_ingest(payload)` 返回一个 `dict`，v0 结构如下：

```python
{
    "entries": [
        {
            "entry_id": str,
            "title": str,
            "content": str,
        },
        # 目前通常只有一条，预留为列表
    ]
}
```

- 当前实现中，一次调用通常只返回 **一条** entry，列表形式是为未来切块扩展预留。

### 字段含义

- **`entry_id: str`**
  - 来自前置模型生成的 `id` 字段，或 AI 工厂内部自动生成的占位 ID（如 `ent_xxxxxxxx`）。
  - 与 `entries` 表中的主键 `entry_id` 一一对应。

- **`title: str`**
  - 来自前置模型生成的标题（中文，简要概括笔记内容）。
  - 与 `entries.title` 对应。

- **`content: str`**
  - 通常为原文全文，或模型返回的 `content` 字段（若为空则回退为原文 `raw_text`）。
  - 与 `entries.content` 对应。

> 三栏侧如需构建本地缓存或 UI 列表，可以只使用这三个字段；
> 如需更多字段（`summary_ai` 等），可通过后续的查询接口或专门的浏览脚本获取。

---

## 5. 三栏侧典型调用示例

以 Python 为例，简化示意：

```python
from ai_factory.integrations.entries_ingest import entries_ingest


def log_note_via_ai_factory(full_note: str, project_code: str | None, user_id: str | None, timestamp: str | None) -> None:
    payload = {
        "raw_text": full_note,
        "project_code": project_code,
        "user_id": user_id,
        "note_datetime": timestamp,
        "extra_context": {
            "source": "three_column_ui",
            # 可以按需补充：section_id / tags_snapshot 等
        },
    }

    result = entries_ingest(payload)
    entries = result.get("entries") or []
    if not entries:
        print("[three-column] entries_ingest 返回空 entries")
        return

    first = entries[0]
    print(
        "[three-column] entries_ingest ok, entry_id=",
        first.get("entry_id"),
        "title=",
        (first.get("title") or "")[:50],
    )
```

在三栏实际项目中，这段逻辑已经被封装在 `core.ai_factory_ingest.ingest_full_note_via_ai_factory(...)` 内部，这里只是给出一个“独立可理解”的示例。

---

## 6. 端到端联调建议（v0）

### 6.1 环境前提

- AI 工厂项目已在本地可用，并能成功：
  - `python test_deepseek_r1_local_endpoint.py`  （验证本地 deepseek-r1 接口可用）；
  - `python test_entries_ingest_local.py`        （验证样例文档可规整并写入 entries）；
- `entries` 表已创建，并可用 `python print_recent_entries.py` 浏览。

### 6.2 三栏 → AI 工厂 联调步骤（笔记入库链路）

1. **在三栏项目中启用 AI 工厂写库模式**

   在启动三栏应用的 Shell 中设置环境变量：

   ```powershell
   $env:RAW_ENTRY_BACKEND = "ai_factory"
   python 五栏数据管理.py
   ```

   - 这样 Alt+Enter 记笔记会优先调用 `ingest_full_note_via_ai_factory(...)` → `entries_ingest(payload)` → 写本地 `entries` 表；
   - 如 AI 工厂写入失败，会自动回退到原来的 legacy 写服务器 `raw_entries` 模式。

2. **在三栏中间栏输入一段测试内容，按 Alt+Enter 提交**

   - 建议使用与你在 AI 工厂本地测试时相同的样例文档内容，便于对比。

3. **在 AI 工厂项目目录中查看 entries**

   在 `d:\AI\ai-factory` 下运行：

   ```powershell
   python print_recent_entries.py 3
   ```

   检查输出中最近一条是否符合预期：

   - `title`：应能概括刚才输入的笔记内容；
   - `summary_ai`：为 deepseek-r1 生成的中文摘要；
   - `project_code` / `user_id`：与三栏侧传入的值一致；
   - `created_at`：为指定的 `note_datetime` 或当前时间。

4. **如有异常，建议回传信息**

   - 若 `entries_ingest` 抛出异常或返回结构异常：
     - 记录完整的错误日志；
     - 保留本次 `payload` 示例（可做敏感脱敏处理）；
     - 将上述信息反馈给 AI 工厂侧进行排查。

---

## 7. 当前版本范围说明

- 本文档仅覆盖：
  - 「链路 1：笔记入库」中三栏调用 AI 工厂 `entries_ingest` 的方式；
  - 不涵盖 RAG 问答 / 联网问答 / 注入问答 / 脑图解释等其它 4 条链路。

- 后续若在 AI 工厂侧新增：
  - `qa_answer_rag(payload)`、`qa_answer_web(payload)`、`mindmap_project(payload)` 等接口，
  - 将会在 `docs/三栏问答与AI工厂任务清单_v0.md` 的基础上，另行补充对应的对接说明文档。
