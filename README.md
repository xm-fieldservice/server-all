# AI 工厂核心工程（ai-factory）

本目录为当前工作区的 **核心 AI 工程**，用于集中管理与复用：

- Agents（autogen / MCP 及自研编排）
- RAG 能力（向量检索 + pgvector + 索引流程）
- 数据访问封装（PostgreSQL、pgvector，未来的 Neo4j 等）
- 对 langchain / llamaindex / graphrag 等框架的统一适配层

其它项目（如 `injection-legacy-columns`、`desktop_app` 等）应尽量通过本工程提供的接口来使用 AI 能力，而不是各自维护一套重复的 Agent 代码。

---

## 目录结构

```text
ai-factory/
  pyproject.toml          # 工程元数据与依赖（待逐步完善）
  README.md               # 本说明文件
  ai_factory/
    __init__.py
    agents/               # 各类 Agent 编排逻辑（autogen/MCP 等）
      __init__.py
    db/                   # 数据库与向量库访问封装
      __init__.py
      pgvector_client.py  # 连接 Docker pgvector 实例的帮助函数
    rag/                  # RAG 流程与向量检索统一接口（预留）
      __init__.py
    frameworks/           # langchain / llamaindex / graphrag 等适配层（预留）
      __init__.py
```

随着项目推进，会在 `agents/`、`rag/`、`frameworks/` 下逐步补充具体实现。

---

## 运行环境与依赖（当前阶段）

- **Python**：3.11
- **数据库**：
  - Docker 中的 PostgreSQL 16.11 + pgvector
  - 端口映射：`localhost:5433 -> 容器 5432`
  - 默认数据库：`rag_db`
  - 默认用户：`rag_user / rag_password`
- **Python 依赖（示例）**：
  - `psycopg2-binary`：用于 `pgvector_client` 连接 Postgres
  - 后续会按需增加：autogen / langchain / llamaindex / Neo4j 驱动等

> 提示：依赖管理目前以 `pyproject.toml` 为主，后续可以根据需要补充具体版本约束。

---

## 配置约定（环境变量）

`ai_factory.db.pgvector_client` 支持通过以下环境变量覆盖默认连接信息：

- `AI_PG_HOST`（默认：`localhost`）
- `AI_PG_PORT`（默认：`5433`）
- `AI_PG_DB`（默认：`rag_db`）
- `AI_PG_USER`（默认：`rag_user`）
- `AI_PG_PASSWORD`（默认：`rag_password`）

如果不设置，代码会使用以上默认值连接 Docker pgvector 实例。

---

## 使用示例

在其它项目（如 `injection-legacy-columns`）中，可以这样复用数据库连接：

```python
from ai_factory.db.pgvector_client import connection_scope


def demo():
    with connection_scope() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database(), current_user;")
            db, user = cur.fetchone()
            print("DB:", db, "USER:", user)
```

未来在 `agents/` 与 `rag/` 中补充的能力，也建议以类似方式被其它工程调用：

```python
from ai_factory.agents.some_agent import run_something

result = run_something(...)
```

---

## 与其它工程的关系

- `ai-factory` 集中负责：
  - AI 相关的核心能力抽象、封装与复用；
  - 对基础设施（Postgres / pgvector / 未来 Neo4j 等）的访问封装。
- 其它工程负责：
  - 具体业务流程 / UI / 交互；
  - 调用 `ai_factory.*` 暴露出的接口，而不是在各自内部重新实现一套 Agent / RAG / DB 访问逻辑。

这有助于保持整个工作区的 **能力集中、项目解耦、演进有序**。

