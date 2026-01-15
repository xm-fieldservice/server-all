from __future__ import annotations

"""Initialize the `entry_embeddings` table in rag_db.

只需在 ai-factory 虚拟环境中运行一次：

    python init_entry_embeddings.py

要求：
- 已正确配置 AI_PG_* 环境变量（与现有 entries 表相同）；
- 数据库中已安装 pgvector 扩展。
"""

from ai_factory.db.pgvector_client import connection_scope


SQL_CREATE_EXTENSION = """
CREATE EXTENSION IF NOT EXISTS vector;
"""


SQL_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS entry_embeddings (
  entry_id      TEXT PRIMARY KEY REFERENCES entries(entry_id),
  embedding     VECTOR(2560),
  project_code  TEXT,
  user_id       TEXT,
  mode          TEXT,
  created_at    TIMESTAMP
);
"""


def main() -> None:
    with connection_scope() as conn:
        with conn.cursor() as cur:
            # 确保 pgvector 扩展已启用
            cur.execute(SQL_CREATE_EXTENSION)
            # 创建表
            cur.execute(SQL_CREATE_TABLE)
    print("entry_embeddings table created or already exists.")


if __name__ == "__main__":
    main()
