"""SessionService implementation.

Responsible for chat_sessions/chat_messages read/write and short-term context.
Follows `Agent记忆系统详细设计与施工文档.md`.

V3.0 Upgrade: Added four-layer isolation support (user_id, agent_type, agent_instance_id)
"""

from __future__ import annotations

import uuid
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime

from ai_factory.db.pgvector_client import connection_scope
from psycopg2.extras import Json

logger = logging.getLogger(__name__)


@dataclass
class SessionInfo:
    """会话信息（V3.0: 支持四层隔离）"""
    session_id: str
    user_id: str
    assistant_id: str
    title: Optional[str]
    status: str
    metadata: Optional[Dict[str, Any]]
    created_at: datetime
    updated_at: datetime
    related_entry_id: Optional[str]
    agent_type: Optional[str]  # V3.0: 四层隔离 - L2
    agent_instance_id: Optional[str]  # V3.0: 四层隔离 - L3


@dataclass
class MessageInfo:
    """消息信息（V3.0: 支持四层继承）"""
    message_id: str
    session_id: str
    role: str
    msg_type: Optional[str]
    content: str
    metadata: Optional[Dict[str, Any]]
    created_at: datetime
    user_id: Optional[str]  # V3.0: 从session继承
    agent_type: Optional[str]  # V3.0: 从session继承
    agent_instance_id: Optional[str]  # V3.0: 从session继承


class SessionService:
    """Manage chat sessions and short-term conversation memory (V3.0: 四层隔离)."""

    def set_rls_context(
        self,
        user_id: str,
        agent_type: Optional[str] = None,
        agent_instance_id: Optional[str] = None,
        conn=None
    ) -> None:
        """设置RLS上下文（V3.0）。

        注意：`connection_scope()` 返回的是 psycopg2 connection，需要通过 cursor 执行 SQL。

        Args:
            user_id: 用户ID（必需）
            agent_type: Agent类型（可选）
            agent_instance_id: Agent实例ID（可选）
            conn: 数据库连接（可选）
        """
        try:
            if conn is None:
                with connection_scope() as conn:
                    with conn.cursor() as cur:
                        cur.execute("SET LOCAL app.current_user_id = %s", (user_id,))
                        if agent_type:
                            cur.execute("SET LOCAL app.current_agent_type = %s", (agent_type,))
                        if agent_instance_id:
                            cur.execute("SET LOCAL app.current_agent_instance_id = %s", (agent_instance_id,))
            else:
                with conn.cursor() as cur:
                    cur.execute("SET LOCAL app.current_user_id = %s", (user_id,))
                    if agent_type:
                        cur.execute("SET LOCAL app.current_agent_type = %s", (agent_type,))
                    if agent_instance_id:
                        cur.execute("SET LOCAL app.current_agent_instance_id = %s", (agent_instance_id,))

            logger.debug(
                "RLS context set: user_id=%s, agent_type=%s, agent_instance_id=%s",
                user_id,
                agent_type,
                agent_instance_id,
            )
        except Exception as e:
            logger.error(f"Failed to set RLS context: {e}")
            raise

    def clear_rls_context(self, conn=None) -> None:
        """清除RLS上下文（V3.0）。

        Args:
            conn: 数据库连接（可选）
        """
        try:
            if conn is None:
                with connection_scope() as conn:
                    with conn.cursor() as cur:
                        cur.execute("RESET app.current_user_id")
                        cur.execute("RESET app.current_agent_type")
                        cur.execute("RESET app.current_agent_instance_id")
            else:
                with conn.cursor() as cur:
                    cur.execute("RESET app.current_user_id")
                    cur.execute("RESET app.current_agent_type")
                    cur.execute("RESET app.current_agent_instance_id")

            logger.debug("RLS context cleared")
        except Exception as e:
            logger.error(f"Failed to clear RLS context: {e}")
            raise

    def __init__(self):
        """初始化 SessionService，使用 connection_scope 获取数据库连接。"""

    def create_session(
        self,
        user_id: str,
        assistant_id: str,
        title: Optional[str] = None,
        related_entry_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        agent_type: Optional[str] = None,  # V3.0
        agent_instance_id: Optional[str] = None  # V3.0
    ) -> str:
        """创建新会话（V3.0: 支持四层隔离）。

        Args:
            user_id: 用户ID
            assistant_id: 助手ID
            title: 会话标题（可选）
            related_entry_id: 关联的entry ID（可选）
            metadata: 元数据（可选）
            agent_type: Agent类型（V3.0: 可选）
            agent_instance_id: Agent实例ID（V3.0: 可选）

        Returns:
            session_id: 新创建的会话ID
        """
        session_id = f"session_{uuid.uuid4().hex}"
        status = "active"

        with connection_scope() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO chat_sessions
                    (session_id, user_id, assistant_id, title, status, metadata_json, related_entry_id,
                     agent_type, agent_instance_id, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    RETURNING session_id
                """, (session_id, user_id, assistant_id, title, status,
                       Json(metadata) if metadata else None, related_entry_id,
                       agent_type, agent_instance_id))

        logger.info(f"Created session {session_id} with isolation: user_id={user_id}, agent_type={agent_type}, agent_instance_id={agent_instance_id}")
        return session_id

    def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        msg_type: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """添加消息到会话（V3.0: 从session继承四层隔离字段）。

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
                # V3.0: 从session获取四层隔离字段并继承到message
                cur.execute("""
                    INSERT INTO chat_messages
                    (message_id, session_id, role, msg_type, content, metadata_json, created_at,
                     user_id, agent_type, agent_instance_id)
                    VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP,
                            (SELECT user_id FROM chat_sessions WHERE session_id = %s),
                            (SELECT agent_type FROM chat_sessions WHERE session_id = %s),
                            (SELECT agent_instance_id FROM chat_sessions WHERE session_id = %s))
                    RETURNING message_id
                """, (message_id, session_id, role, msg_type, content,
                       Json(metadata) if metadata else None,
                       session_id, session_id, session_id))

        logger.debug(f"Appended message {message_id} to session {session_id} (V3.0: inherited isolation)")
        return message_id

    def get_recent_messages(
        self,
        session_id: str,
        limit: int = 20,
        user_id: Optional[str] = None  # V3.0: 可选隔离过滤
    ) -> List[MessageInfo]:
        """获取会话的最近消息（按创建时间倒序）（V3.0: 支持四层继承）。

        Args:
            session_id: 会话ID
            limit: 返回消息数量限制
            user_id: 用户ID（V3.0: 可选过滤）

        Returns:
            List[MessageInfo]: 消息列表
        """
        with connection_scope() as conn:
            with conn.cursor() as cur:
                # V3.0: 添加四层隔离过滤（可选）
                conditions = ["cm.session_id = %s"]
                params = [session_id]

                if user_id:
                    # 直接按 session 归属用户过滤，避免别名错误
                    conditions.append("cs.user_id = %s")
                    params.append(user_id)

                cur.execute(f"""
                    SELECT cm.message_id, cm.session_id, cm.role, cm.msg_type, cm.content, cm.metadata_json, cm.created_at,
                           cs.user_id, cs.agent_type, cs.agent_instance_id  -- V3.0: 四层继承字段
                    FROM chat_messages cm
                    LEFT JOIN chat_sessions cs ON cm.session_id = cs.session_id
                    WHERE {' AND '.join(conditions)}
                    ORDER BY cm.created_at DESC
                    LIMIT %s
                """, params + [limit])

                rows = cur.fetchall()
                return [
                    MessageInfo(
                        message_id=row[0],
                        session_id=row[1],
                        role=row[2],
                        msg_type=row[3],
                        content=row[4],
                        metadata=row[5] if isinstance(row[5], dict) else None,
                        created_at=row[6],
                        user_id=row[7],  # V3.0
                        agent_type=row[8],  # V3.0
                        agent_instance_id=row[9]  # V3.0
                    )
                    for row in rows
                ]

    def get_session_info(
        self,
        session_id: str,
        user_id: Optional[str] = None  # V3.0: 可选隔离过滤
    ) -> Optional[SessionInfo]:
        """获取会话信息（V3.0: 支持四层隔离过滤）。

        Args:
            session_id: 会话ID
            user_id: 用户ID（V3.0: 可选过滤）

        Returns:
            SessionInfo: 会话信息，如果不存在则返回 None
        """
        with connection_scope() as conn:
            with conn.cursor() as cur:
                # V3.0: 添加四层隔离过滤（可选）
                conditions = ["session_id = %s"]
                params = [session_id]

                if user_id:
                    conditions.append("user_id = %s")
                    params.append(user_id)

                cur.execute(f"""
                    SELECT session_id, user_id, assistant_id, title, status,
                           metadata_json, created_at, updated_at, related_entry_id,
                           agent_type, agent_instance_id  -- V3.0: 四层隔离字段
                    FROM chat_sessions
                    WHERE {' AND '.join(conditions)}
                """, params)

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
                        related_entry_id=row[8],
                        agent_type=row[9],  # V3.0
                        agent_instance_id=row[10]  # V3.0
                    )
        return None

    def get_session_history(
        self,
        user_id: str,
        assistant_id: Optional[str] = None,
        agent_type: Optional[str] = None,  # V3.0
        agent_instance_id: Optional[str] = None,  # V3.0
        limit: int = 20
    ) -> List[SessionInfo]:
        """获取用户的会话历史（V3.0: 支持四层隔离过滤）。

        Args:
            user_id: 用户ID
            assistant_id: 可选，过滤特定助手的会话
            agent_type: Agent类型（V3.0: 可选）
            agent_instance_id: Agent实例ID（V3.0: 可选）
            limit: 返回会话数量限制

        Returns:
            List[SessionInfo]: 会话列表
        """
        with connection_scope() as conn:
            with conn.cursor() as cur:
                conditions = ["user_id = %s"]
                params = [user_id]

                if assistant_id:
                    conditions.append("assistant_id = %s")
                    params.append(assistant_id)

                # V3.0: 添加四层隔离过滤（可选）
                if agent_type:
                    conditions.append("agent_type = %s")
                    params.append(agent_type)
                if agent_instance_id:
                    conditions.append("agent_instance_id = %s")
                    params.append(agent_instance_id)

                cur.execute(f"""
                    SELECT session_id, user_id, assistant_id, title, status,
                           metadata_json, created_at, updated_at, related_entry_id,
                           agent_type, agent_instance_id  -- V3.0: 四层隔离字段
                    FROM chat_sessions
                    WHERE {' AND '.join(conditions)}
                    ORDER BY updated_at DESC
                    LIMIT %s
                """, params + [limit])

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
                        related_entry_id=row[8],
                        agent_type=row[9],  # V3.0
                        agent_instance_id=row[10]  # V3.0
                    )
                    for row in rows
                ]

    def update_session(
        self,
        session_id: str,
        user_id: Optional[str] = None,  # V3.0: 可选隔离检查
        **kwargs
    ) -> bool:
        """更新会话信息（V3.0: 支持四层隔离检查）。

        Args:
            session_id: 会话ID
            user_id: 用户ID（V3.0: 可选，用于隔离验证）
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

        # V3.0: 添加user_id隔离检查（可选）
        if user_id:
            with connection_scope() as conn:
                with conn.cursor() as cur:
                    cur.execute(f"""
                        UPDATE chat_sessions
                        SET {', '.join(updates)}
                        WHERE session_id = %s AND user_id = %s
                    """, params + [user_id])
                    updated = cur.rowcount > 0
                    if updated:
                        logger.debug(f"Updated session {session_id} with user_id check: {user_id}")
                    return updated
        else:
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

    def batch_append_messages(
        self,
        messages: List[Dict[str, Any]]
    ) -> List[str]:
        """批量添加消息到会话（V3.0: 从session继承四层隔离字段）。

        使用批量插入提高性能。

        Args:
            messages: 消息列表，每个消息必须包含 "session_id", "role", "content" 字段

        Returns:
            List[str]: message_id 列表
        """
        if not messages:
            return []

        message_ids = []

        with connection_scope() as conn:
            with conn.cursor() as cur:
                for msg_data in messages:
                    message_id = f"msg_{uuid.uuid4().hex}"
                    session_id = msg_data.get("session_id")
                    role = msg_data.get("role")
                    content = msg_data.get("content")
                    msg_type = msg_data.get("msg_type")
                    metadata = msg_data.get("metadata")

                    # V3.0: 从session获取四层隔离字段并继承到message
                    cur.execute("""
                        INSERT INTO chat_messages
                        (message_id, session_id, role, msg_type, content, metadata_json, created_at,
                         user_id, agent_type, agent_instance_id)
                        VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP,
                                (SELECT user_id FROM chat_sessions WHERE session_id = %s),
                                (SELECT agent_type FROM chat_sessions WHERE session_id = %s),
                                (SELECT agent_instance_id FROM chat_sessions WHERE session_id = %s))
                        RETURNING message_id
                    """, (message_id, session_id, role, msg_type, content,
                           Json(metadata) if metadata else None,
                           session_id, session_id, session_id))

                    row = cur.fetchone()
                    message_ids.append(row[0] if row else message_id)

        logger.debug(f"Batch appended {len(message_ids)} messages (V3.0: inherited isolation)")
        return message_ids

    def batch_get_recent_messages(
        self,
        session_ids: List[str],
        limit: int = 20
    ) -> Dict[str, List[MessageInfo]]:
        """批量获取多个会话的最近消息（V3.0: 支持四层隔离字段）。

        Args:
            session_ids: 会话ID列表
            limit: 每个会话返回消息数量限制

        Returns:
            Dict[str, List[MessageInfo]]: {session_id: 消息列表}
        """
        if not session_ids:
            return {}

        results = {}

        with connection_scope() as conn:
            with conn.cursor() as cur:
                placeholders = ', '.join(['%s'] * len(session_ids))
                # V3.0: 查询包含四层隔离字段
                cur.execute(f"""
                    SELECT message_id, session_id, role, msg_type, content, metadata_json, created_at,
                           cm.user_id, cm.agent_type, cm.agent_instance_id
                    FROM chat_messages cm
                    LEFT JOIN chat_sessions cs ON cm.session_id = cs.session_id
                    WHERE cm.session_id IN ({placeholders})
                    ORDER BY cm.session_id, cm.created_at DESC
                """, session_ids)

                rows = cur.fetchall()

                # 按会话分组
                for row in rows:
                    session_id = row[1]
                    if session_id not in results:
                        results[session_id] = []

                    # V3.0: 包含四层隔离字段
                    results[session_id].append(
                        MessageInfo(
                            message_id=row[0],
                            session_id=row[1],
                            role=row[2],
                            msg_type=row[3],
                            content=row[4],
                            metadata=row[5] if isinstance(row[5], dict) else None,
                            created_at=row[6],
                            user_id=row[7],  # V3.0
                            agent_type=row[8],  # V3.0
                            agent_instance_id=row[9]  # V3.0
                        )
                    )

        # 截断到限制数量
        for session_id in results:
            results[session_id] = results[session_id][:limit]

        logger.debug(f"Batch got recent messages for {len(results)} sessions (V3.0: with isolation)")
        return results

