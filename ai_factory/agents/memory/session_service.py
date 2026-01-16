"""SessionService implementation.

Responsible for chat_sessions/chat_messages read/write and short-term context.
Follows `Agent记忆系统详细设计与施工文档.md`.
"""

from __future__ import annotations

import uuid
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime

from ai_factory.db.pgvector_client import connection_scope
from psycopg2.extras import Json


@dataclass
class SessionInfo:
    """会话信息"""
    session_id: str
    user_id: str
    assistant_id: str
    title: Optional[str]
    status: str
    metadata: Optional[Dict[str, Any]]
    created_at: datetime
    updated_at: datetime
    related_entry_id: Optional[str]


@dataclass
class MessageInfo:
    """消息信息"""
    message_id: str
    session_id: str
    role: str
    msg_type: Optional[str]
    content: str
    metadata: Optional[Dict[str, Any]]
    created_at: datetime


class SessionService:
    """Manage chat sessions and short-term conversation memory."""

    def __init__(self):
        """初始化 SessionService，使用 connection_scope 获取数据库连接。"""

    def create_session(
        self,
        user_id: str,
        assistant_id: str,
        title: Optional[str] = None,
        related_entry_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """创建新会话。

        Args:
            user_id: 用户ID
            assistant_id: 助手ID
            title: 会话标题（可选）
            related_entry_id: 关联的entry ID（可选）
            metadata: 元数据（可选）

        Returns:
            session_id: 新创建的会话ID
        """
        session_id = f"session_{uuid.uuid4().hex}"
        status = "active"

        with connection_scope() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO chat_sessions
                    (session_id, user_id, assistant_id, title, status, metadata_json, related_entry_id, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    RETURNING session_id
                """, (session_id, user_id, assistant_id, title, status,
                       Json(metadata) if metadata else None, related_entry_id))

        return session_id

    def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        msg_type: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """添加消息到会话。

        Args:
            session_id: 会话ID
            role: 消息角色（user/assistant/system/tool）
            content: 消息内容
            msg_type: 消息类型（question/statement/answer/other，可选）
            metadata: 元数据（可选）

        Returns:
            message_id: 新创建的消息ID
        """
        message_id = f"msg_{uuid.uuid4().hex}"

        with connection_scope() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO chat_messages
                    (message_id, session_id, role, msg_type, content, metadata_json, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    RETURNING message_id
                """, (message_id, session_id, role, msg_type, content,
                       Json(metadata) if metadata else None))

        return message_id

    def get_recent_messages(
        self,
        session_id: str,
        limit: int = 20
    ) -> List[MessageInfo]:
        """获取会话的最近消息（按创建时间倒序）。

        Args:
            session_id: 会话ID
            limit: 返回消息数量限制

        Returns:
            List[MessageInfo]: 消息列表
        """
        with connection_scope() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT message_id, session_id, role, msg_type, content, metadata_json, created_at
                    FROM chat_messages
                    WHERE session_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                """, (session_id, limit))

                rows = cur.fetchall()
                return [
                    MessageInfo(
                        message_id=row[0],
                        session_id=row[1],
                        role=row[2],
                        msg_type=row[3],
                        content=row[4],
                        metadata=row[5] if isinstance(row[5], dict) else None,
                        created_at=row[6]
                    )
                    for row in rows
                ]

    def get_session_info(self, session_id: str) -> Optional[SessionInfo]:
        """获取会话信息。

        Args:
            session_id: 会话ID

        Returns:
            SessionInfo: 会话信息，如果不存在则返回 None
        """
        with connection_scope() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT session_id, user_id, assistant_id, title, status,
                           metadata_json, created_at, updated_at, related_entry_id
                    FROM chat_sessions
                    WHERE session_id = %s
                """, (session_id,))

                row = cur.fetchone()
                if row:
                    return SessionInfo(
                        session_id=row[0],
                        user_id=row[1],
                        assistant_id=row[2],
                        title=row[3],
                        status=row[4],
                        metadata=row[5] if isinstance(row[5], dict) else None,
                        created_at=row[6],
                        updated_at=row[7],
                        related_entry_id=row[8]
                    )
        return None

    def get_session_history(
        self,
        user_id: str,
        assistant_id: Optional[str] = None,
        limit: int = 20
    ) -> List[SessionInfo]:
        """获取用户的会话历史。

        Args:
            user_id: 用户ID
            assistant_id: 可选，过滤特定助手的会话
            limit: 返回会话数量限制

        Returns:
            List[SessionInfo]: 会话列表
        """
        with connection_scope() as conn:
            with conn.cursor() as cur:
                if assistant_id:
                    cur.execute("""
                        SELECT session_id, user_id, assistant_id, title, status,
                               metadata_json, created_at, updated_at, related_entry_id
                        FROM chat_sessions
                        WHERE user_id = %s AND assistant_id = %s
                        ORDER BY updated_at DESC
                        LIMIT %s
                    """, (user_id, assistant_id, limit))
                else:
                    cur.execute("""
                        SELECT session_id, user_id, assistant_id, title, status,
                               metadata_json, created_at, updated_at, related_entry_id
                        FROM chat_sessions
                        WHERE user_id = %s
                        ORDER BY updated_at DESC
                        LIMIT %s
                    """, (user_id, limit))

                rows = cur.fetchall()
                return [
                    SessionInfo(
                        session_id=row[0],
                        user_id=row[1],
                        assistant_id=row[2],
                        title=row[3],
                        status=row[4],
                        metadata=row[5] if isinstance(row[5], dict) else None,
                        created_at=row[6],
                        updated_at=row[7],
                        related_entry_id=row[8]
                    )
                    for row in rows
                ]

    def update_session(self, session_id: str, **kwargs) -> bool:
        """更新会话信息。

        Args:
            session_id: 会话ID
            **kwargs: 要更新的字段（title, status, metadata_json, related_entry_id）

        Returns:
            bool: 是否更新成功
        """
        if not kwargs:
            return False

        updates = []
        params = []
        for key, value in kwargs.items():
            if key in ("title", "status", "related_entry_id"):
                updates.append(f"{key} = %s")
                params.append(value)
            elif key == "metadata" and isinstance(value, dict):
                updates.append("metadata_json = %s")
                params.append(Json(value))

        if not updates:
            return False

        updates.append("updated_at = CURRENT_TIMESTAMP")
        params.append(session_id)

        with connection_scope() as conn:
            with conn.cursor() as cur:
                cur.execute(f"""
                    UPDATE chat_sessions
                    SET {', '.join(updates)}
                    WHERE session_id = %s
                """, params)
                return cur.rowcount > 0

    def archive_session(self, session_id: str) -> bool:
        """归档会话。

        Args:
            session_id: 会话ID

        Returns:
            bool: 是否归档成功
        """
        with connection_scope() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE chat_sessions
                    SET status = 'archived', updated_at = CURRENT_TIMESTAMP
                    WHERE session_id = %s
                """, (session_id,))
                return cur.rowcount > 0

    def delete_session(self, session_id: str) -> bool:
        """删除会话（软删除，标记为 deleted 状态）。

        Args:
            session_id: 会话ID

        Returns:
            bool: 是否删除成功
        """
        with connection_scope() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE chat_sessions
                    SET status = 'deleted', updated_at = CURRENT_TIMESTAMP
                    WHERE session_id = %s
                """, (session_id,))
                return cur.rowcount > 0
