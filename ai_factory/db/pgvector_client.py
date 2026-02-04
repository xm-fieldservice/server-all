"""PostgreSQL/pgvector client helpers.

当前假设：
- Docker 中运行了一套带 pgvector 的 PostgreSQL 实例：
  host=localhost, port=5433, db=rag_db, user=rag_user, password=rag_password
- 也允许通过环境变量覆盖这些默认值：
  AI_PG_HOST / AI_PG_PORT / AI_PG_DB / AI_PG_USER / AI_PG_PASSWORD

依赖：
- 代码示例使用 psycopg2，请在对应环境中安装：
  pip install psycopg2-binary
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Generator

import psycopg2
from psycopg2.extensions import connection as PgConnection

# 导入pgvector适配器
try:
    from pgvector.psycopg2 import register_vector
    _HAS_PGVECTOR = True
except ImportError:
    _HAS_PGVECTOR = False
    print("[警告] pgvector未安装，向量将以字符串形式存储")


def _get_dsn() -> str:
    host = os.getenv("AI_PG_HOST") or "localhost"
    port = os.getenv("AI_PG_PORT") or "5433"
    db = os.getenv("AI_PG_DB") or "rag_db"
    user = os.getenv("AI_PG_USER") or "rag_user"
    password = os.getenv("AI_PG_PASSWORD") or "rag_password"

    return f"dbname={db} user={user} password={password} host={host} port={port}"


def get_connection() -> PgConnection:
    """获取一个新的 PostgreSQL 连接。

    调用方负责关闭连接，或者通过 ``with get_connection() as conn:`` 使用。
    """

    dsn = _get_dsn()
    conn = psycopg2.connect(dsn)
    
    # 注册pgvector适配器
    if _HAS_PGVECTOR:
        register_vector(conn)
    
    # 设置会话时区，统一 NOW() 与 timestamptz 的显示/排序语义
    try:
        tz = os.getenv("AI_TZ", "Asia/Shanghai")
        with conn.cursor() as cur:
            cur.execute("SET TIME ZONE %s", (tz,))
        conn.commit()
    except Exception:
        # 若设置失败，不影响连接使用
        conn.rollback()
    return conn


@contextmanager
def connection_scope() -> Generator[PgConnection, None, None]:
    """上下文管理器形式的连接，自动提交并关闭。

    Example::

        from ai_factory.db.pgvector_client import connection_scope

        with connection_scope() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                print(cur.fetchone())
    """

    conn: PgConnection | None = None
    try:
        conn = get_connection()
        yield conn
        conn.commit()
    except Exception:
        if conn is not None:
            conn.rollback()
        raise
    finally:
        if conn is not None:
            conn.close()


def test_connection() -> bool:
    """简单测试当前配置下是否可以连通数据库。

    返回 True 表示 ``SELECT 1`` 成功执行；否则抛出异常。
    """

    with connection_scope() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            _ = cur.fetchone()
    return True
