"""
LangGraph Store 配置（长期记忆）

使用 PostgreSQL 作为 Store 后端，存储长期记忆（实体知识、用户偏好等）。
"""
import os
from typing import Generator
from langgraph.store.postgres import PostgresStore


def get_postgres_dsn() -> str:
    """从环境变量获取 PostgreSQL 连接字符串"""
    host = os.getenv("AI_PG_HOST", "localhost")
    port = os.getenv("AI_PG_PORT", "5434")
    db = os.getenv("AI_PG_DB", "rag_db")
    user = os.getenv("AI_PG_USER", "rag_user")
    password = os.getenv("AI_PG_PASSWORD", "rag_password")
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


def create_postgres_store() -> Generator[PostgresStore, None, None]:
    """创建 PostgresStore 生成器（需作为上下文管理器使用）"""
    dsn = get_postgres_dsn()
    return PostgresStore.from_conn_string(dsn)


def init_store():
    """初始化 Store（首次调用 setup）"""
    store = create_postgres_store()
    with store as s:
        s.setup()


def build_memory_namespace(namespace: str, identifier: str) -> tuple:
    """构建 Store 的 namespace"""
    return (namespace, identifier)


def save_item(namespace: tuple, key: str, value: dict):
    """保存数据到 Store"""
    store = create_postgres_store()
    with store as s:
        s.put(namespace, key, value)


def get_item(namespace: tuple, key: str) -> dict | None:
    """从 Store 读取数据"""
    store = create_postgres_store()
    with store as s:
        result = s.get(namespace, key)
    return result.value if result else None


def delete_item(namespace: tuple, key: str):
    """从 Store 删除数据"""
    store = create_postgres_store()
    with store as s:
        s.delete(namespace, key)


if __name__ == "__main__":
    print("Testing PostgresStore...")
    try:
        init_store()
        print("✓ Store initialized")
        
        namespace = ("test", "demo")
        save_item(namespace, "test_key", {"message": "Hello, Store!"})
        result = get_item(namespace, "test_key")
        print(f"✓ Store test: {result}")
        delete_item(namespace, "test_key")
        print("✓ Store cleanup done")
    except Exception as e:
        print(f"✗ Failed: {e}")
