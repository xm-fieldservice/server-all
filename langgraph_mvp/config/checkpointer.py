"""
LangGraph PostgreSQL Checkpointer 配置

使用你现有的 PostgreSQL (localhost:5434) 作为 Checkpoint 存储后端。
"""
import os
from typing import Optional
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg import connect
from psycopg.rows import dict_row


def get_postgres_dsn() -> str:
    """从环境变量获取 PostgreSQL 连接字符串"""
    host = os.getenv("AI_PG_HOST", "localhost")
    port = os.getenv("AI_PG_PORT", "5434")
    db = os.getenv("AI_PG_DB", "rag_db")
    user = os.getenv("AI_PG_USER", "rag_user")
    password = os.getenv("AI_PG_PASSWORD", "rag_password")
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


def create_postgres_saver() -> PostgresSaver:
    """
    创建同步 PostgresSaver
    
    使用场景：需要同步调用时使用（如 Flask 同步端点）
    """
    dsn = get_postgres_dsn()
    conn = connect(dsn, autocommit=True, row_factory=dict_row)
    saver = PostgresSaver(conn)
    # 首次使用需要初始化表结构
    saver.setup()  # 可以放在启动时或单独的健康检查中
    return saver


# 全局单例（可选，用于同步场景）
_checkpointer: Optional[PostgresSaver] = None


def get_checkpointer() -> PostgresSaver:
    """获取全局 Checkpointer 实例（同步版）"""
    global _checkpointer
    if _checkpointer is None:
        _checkpointer = create_postgres_saver()
    return _checkpointer


def build_thread_id(user_id: str, namespace: str, source_identifier: str) -> str:
    """
    构建 thread_id，遵循原有的四层隔离模型
    
    格式: user_id:namespace:source_identifier
    示例: user_001:agent/recruiting:hr_agent_001
    """
    return f"{user_id}:{namespace}:{source_identifier}"


def parse_thread_id(thread_id: str) -> dict:
    """解析 thread_id 为各组成部分"""
    parts = thread_id.split(":")
    if len(parts) != 3:
        raise ValueError(f"Invalid thread_id format: {thread_id}")
    return {
        "user_id": parts[0],
        "namespace": parts[1],
        "source_identifier": parts[2],
    }


if __name__ == "__main__":
    # 测试连接
    print("Testing PostgreSQL connection...")
    try:
        saver = create_postgres_saver()
        print("✓ PostgresSaver created successfully")
        print(f"  DSN: {get_postgres_dsn()}")
    except Exception as e:
        print(f"✗ Failed to create PostgresSaver: {e}")
