#!/usr/bin/env python3
"""使用管理员权限创建测试表"""

import os
import psycopg2
from contextlib import contextmanager
from typing import Generator

# 使用 postgres 管理员连接
host = os.getenv("AI_PG_HOST", "localhost")
port = os.getenv("AI_PG_PORT", "5433")
db = os.getenv("AI_PG_DB", "rag_db")
user = "postgres"
password = "postgres"

@contextmanager
def connection_scope():
    conn = psycopg2.connect(f"dbname={db} user={user} password={password} host={host} port={port}")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

# 创建表
with connection_scope() as conn:
    with conn.cursor() as cur:
        # 创建 chat_sessions 表
        cur.execute('''
            CREATE TABLE IF NOT EXISTS chat_sessions (
                session_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                agent_id TEXT,
                assistant_id TEXT,
                agent_type VARCHAR(64),
                agent_instance_id VARCHAR(64),
                created_at TIMESTAMPTZ DEFAULT NOW(),
                metadata JSONB
            )
        ''')
        
        # 创建 chat_messages 表
        cur.execute('''
            CREATE TABLE IF NOT EXISTS chat_messages (
                message_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL REFERENCES chat_sessions(session_id) ON DELETE CASCADE,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                metadata JSONB
            )
        ''')
        
        # 创建索引
        cur.execute('CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_id ON chat_sessions(user_id)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_chat_sessions_agent_type ON chat_sessions(agent_type)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_chat_messages_session_id ON chat_messages(session_id)')
        
        print('✅ 数据库表创建成功')
