#!/usr/bin/env python3
"""创建测试用的数据库表"""

from ai_factory.db.pgvector_client import connection_scope

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
        
        conn.commit()
        print('✅ 数据库表创建成功')
