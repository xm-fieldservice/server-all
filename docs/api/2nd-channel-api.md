# 2号通道API文档

## 概述

2号通道是一个异步任务管理接口，支持三种任务类型：
- **NOTE**: 笔记整理入库（整理+写库+向量化）
- **RAG**: RAG查询
- **WEB**: Web查询

所有任务都通过统一的任务队列管理，支持幂等性去重、任务状态查询和错误追踪。

---

## 基础URL

```
{AI_FACTORY_API_BASE}/ai-factory/tasks/ingest
{AI_FACTORY_API_BASE}/ai-factory/tasks/ingest/{job_id}
{AI_FACTORY_API_BASE}/ai-factory/tasks
```

---

## 1. 提交任务

### 请求

**Method**: `POST`
**Path**: `/ai-factory/tasks/ingest`

#### 请求体

```json
{
  "task_type": "note",              // 必填：任务类型 (note/rag/web)
  "payload": {                      // 任务具体参数
    // NOTE任务参数
    "raw_text": "笔记内容",
    "project_code": "project_name",  // 可选
    "user_id": "user_name",          // 可选
    "note_datetime": "2026-01-29 10:00:00",  // 可选
    "extra_context": {
      "tags_snapshot": { ... }
    },
    "extra_meta": {
      "parent_entry_id": "xxx"
    }
  },
  "idempotency_key": "unique_key"    // 可选：幂等键
}
```

#### RAG任务参数

```json
{
  "task_type": "rag",
  "payload": {
    "question_text": "问题内容",     // 必填
    "project_code": "project_name",  // 可选
    "user_id": "user_name",          // 可选
    "top_k": 10,                     // 可选
    "since": "2026-01-01"            // 可选
  }
}
```

#### WEB任务参数

```json
{
  "task_type": "web",
  "payload": {
    "question_text": "问题内容",     // 必填
    "project_code": "project_name",  // 可选
    "user_id": "user_name",          // 可选
    "top_k": 5,                      // 可选
    "options": { ... }               // 可选
  }
}
```

### 响应

**状态码**: `202 Accepted`

```json
{
  "ok": true,
  "job_id": "job_abc123def456",
  "status": "queued"
}
```

---

## 2. 查询任务状态

### 请求

**Method**: `GET`
**Path**: `/ai-factory/tasks/ingest/{job_id}`

#### 路径参数

- `job_id`: 任务ID

### 响应

**状态码**: `200 OK`

```json
{
  "ok": true,
  "status": "succeeded",    // queued/running/succeeded/failed
  "entry_id": "ent_123",    // NOTE任务成功时返回
  "result": {               // 任务结果
    "question": "问题",
    "answer": "回答",
    "citations": [ ... ]
  },
  "error_code": null,       // 失败时返回
  "error_message": null
}
```

#### 成功示例（NOTE任务）

```json
{
  "ok": true,
  "status": "succeeded",
  "entry_id": "ent_20260129_000123",
  "result": {
    "entries": [{
      "entry_id": "ent_20260129_000123",
      "title": "笔记标题",
      "content": "笔记内容"
    }]
  }
}
```

#### 成功示例（RAG任务）

```json
{
  "ok": true,
  "status": "succeeded",
  "result": {
    "question": "问题",
    "answer": "回答内容",
    "citations": [
      {
        "entry_id": "ent_xxx",
        "title": "标题",
        "summary_ai": "摘要",
        "score": 0.89
      }
    ]
  }
}
```

#### 失败示例

```json
{
  "ok": true,
  "status": "failed",
  "error_code": "DeepSeekAPIError",
  "error_message": "调用 deepseek-chat 失败"
}
```

---

## 3. 列出任务

### 请求

**Method**: `GET`
**Path**: `/ai-factory/tasks`

#### 查询参数

- `status`: 任务状态过滤（可选）
- `task_type`: 任务类型过滤（可选）
- `limit`: 返回数量限制（默认100，最大1000）

### 响应

**状态码**: `200 OK`

```json
{
  "ok": true,
  "tasks": [
    {
      "job_id": "job_abc123",
      "payload_hash": "abc123...",
      "raw_text": "笔记内容",
      "task_type": "note",
      "status": "succeeded",
      "error_code": null,
      "error_message": null,
      "entry_id": "ent_123",
      "result": null,
      "created_at": "2026-01-29T10:00:00Z",
      "updated_at": "2026-01-29T10:00:10Z"
    }
  ],
  "count": 1
}
```

---

## 幂等性说明

系统支持基于 `idempotency_key` 或 `payload_hash` 的幂等性：

1. **使用idempotency_key**：
   - 客户端生成唯一ID（如：`SHA256(raw_text + timestamp + user_id)`）
   - 相同的 `idempotency_key` 会复用已有任务，避免重复处理

2. **使用payload_hash**：
   - 系统对 `raw_text` + `task_type` 计算 SHA256 hash
   - 相同的 payload_hash 会复用已有任务

---

## 错误码

| 错误码 | 说明 | 解决方案 |
|--------|------|----------|
| `TaskTypeError` | 不支持的任务类型 | 检查 task_type 参数（必须是 note/rag/web） |
| `MissingRequiredField` | 必填字段缺失 | 确保传入 `raw_text` 或 `question_text` |
| `PayloadValidationError` | 参数验证失败 | 检查参数类型和格式 |
| `TaskNotFound` | 任务不存在 | 检查 job_id 是否正确 |

---

## 性能指标

- **队列长度**: 当前在队列中的任务数
- **成功率**: 已完成任务的成功比例
- **平均处理时长**: 从提交到完成的时间（近似）
- **LLM调用错误码统计**: DeepSeek等LLM调用失败统计

---

## 使用示例

### Python客户端示例

```python
import requests

API_BASE = "http://localhost:8001"

# 1. 提交NOTE任务
payload = {
    "task_type": "note",
    "payload": {
        "raw_text": "今天完成了双通道设计...",
        "project_code": "project1",
    }
}
response = requests.post(f"{API_BASE}/ai-factory/tasks/ingest", json=payload)
job_id = response.json()["job_id"]

# 2. 轮询任务状态
while True:
    response = requests.get(f"{API_BASE}/ai-factory/tasks/ingest/{job_id}")
    result = response.json()

    if result["status"] == "succeeded":
        print(f"任务成功完成: {result['entry_id']}")
        break
    elif result["status"] == "failed":
        print(f"任务失败: {result['error_message']}")
        break

    time.sleep(2)

# 3. 查询所有任务
response = requests.get(f"{API_BASE}/ai-factory/tasks?limit=20")
tasks = response.json()["tasks"]
```

---

## 与1号通道的区别

| 特性 | 1号通道 | 2号通道 |
|------|---------|---------|
| **类型** | 同步写库 | 异步任务管理 |
| **LLM处理** | 仅短文本（≤60字符） | 全部任务（短/长文本+RAG+Web） |
| **响应时间** | 立即返回 | 异步处理，需轮询 |
| **失败处理** | 立即返回错误 | 队列中重试（可配置） |
| **任务状态** | 无 | 有（queued/running/succeeded/failed） |
| **适用场景** | 快速同步入库 | 批量导入/长文本/RAG/Web查询 |

---

## 注意事项

1. **任务ID生成**: job_id 是服务器端生成的 UUID
2. **任务类型**: 必须是 `note`、`rag` 或 `web` 之一
3. **payload参数**: 根据 task_type 不同，payload结构不同
4. **轮询间隔**: 建议轮询间隔 2-5 秒
5. **超时设置**: RAG/Web任务可能需要较长时间（建议超时120秒）
