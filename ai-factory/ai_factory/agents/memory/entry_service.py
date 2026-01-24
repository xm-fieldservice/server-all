"""EntryService implementation.

Unified read/write and vector search for entries table and embeddings.

V3.0 Update: Four-layer isolation support for multi-tenant architecture
- user_id: User isolation layer
- agent_type: Agent type isolation layer
- agent_instance_id: Agent instance isolation layer
- RLS context management for database-level isolation
"""

from __future__ import annotations

import uuid
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from ai_factory.db.pgvector_client import connection_scope
from psycopg2.extras import Json
from .vector_client import VectorClient

logger = logging.getLogger(__name__)


@dataclass
class EntryInfo:
    """Entry信息数据类（V3.0: 支持四层隔离）

    Attributes:
        entry_id: Entry ID
        title: Title（Level 1）
        content: Content（Level 3）
        summary_ai: Summary（Level 2）
        scene_tags: Scene tags（Level 4）
        extra_meta: Extra metadata（Level 4）
        user_id: 用户ID（L1隔离）
        agent_type: Agent类型（L2隔离）
        agent_instance_id: Agent实例ID（L3隔离）
        section_id: Section ID
        section_version: Section版本
        is_latest: 是否最新版本
        agent_id: Agent ID
        space_type: 空间类型
        status: 状态
        created_at: 创建时间
        updated_at: 更新时间
    """
    entry_id: str
    title: Optional[str] = None
    content: Optional[str] = None
    summary_ai: Optional[str] = None
    scene_tags: Optional[Dict[str, Any]] = None
    extra_meta: Optional[Dict[str, Any]] = None
    user_id: Optional[str] = None  # V3.0: L1隔离
    agent_type: Optional[str] = None  # V3.0: L2隔离
    agent_instance_id: Optional[str] = None  # V3.0: L3隔离
    section_id: Optional[str] = None
    section_version: Optional[int] = None
    is_latest: Optional[bool] = None
    agent_id: Optional[str] = None
    space_type: Optional[str] = None
    status: Optional[str] = None
    created_at: Optional[Any] = None
    updated_at: Optional[Any] = None


class EntryService:
    """Provide a high-level API over entries and entry_embeddings.

    V3.0: Added four-layer isolation support and RLS context management.
    """

    # 允许操作的列名白名单，防御 SQL 注入
    ALLOWED_COLUMNS = {
        "entry_id", "section_id", "user_id", "agent_type", "agent_instance_id",
        "agent_id", "title", "summary_ai", "content", "scene_tags", "extra_meta",
        "metadata_json", "space_type", "project_code", "parent_entry_id",
        "section_version", "is_latest", "status", "created_at", "updated_at",
        "importance", "usage_count", "last_seen_at", "source_session_id"
    }

    def _validate_columns(self, columns: List[str]) -> None:
        """校验列名是否在白名单内。"""
        for col in columns:
            if col not in self.ALLOWED_COLUMNS:
                raise ValueError(f"Invalid column name: {col}")

    def __init__(self, vector_client: Optional[VectorClient] = None) -> None:
        """初始化 EntryService。

        Args:
            vector_client: VectorClient 实例，用于向量检索
        """
        self.vector_client = vector_client or VectorClient()

    def set_rls_context(
        self,
        user_id: str,
        agent_type: str,
        agent_instance_id: str,
        conn=None
    ) -> None:
        """设置RLS上下文变量（V3.0）。

        注意：`connection_scope()` 返回 psycopg2 connection，需要通过 cursor 执行 SQL。

        Args:
            user_id: 用户ID
            agent_type: Agent类型
            agent_instance_id: Agent实例ID
            conn: 数据库连接（可选）
        """
        try:
            if conn is None:
                with connection_scope() as conn:
                    with conn.cursor() as cur:
                        cur.execute("SET LOCAL app.current_user_id = %s", (user_id,))
                        cur.execute("SET LOCAL app.current_agent_type = %s", (agent_type,))
                        cur.execute("SET LOCAL app.current_agent_instance_id = %s", (agent_instance_id,))
            else:
                with conn.cursor() as cur:
                    cur.execute("SET LOCAL app.current_user_id = %s", (user_id,))
                    cur.execute("SET LOCAL app.current_agent_type = %s", (agent_type,))
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
        """清除RLS上下文变量（V3.0）。

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

    def create_entry(
        self,
        data: Dict[str, Any],
        user_id: str,  # V3.0: 必需
        agent_type: Optional[str] = None,
        agent_instance_id: Optional[str] = None
    ) -> str:
        """创建新的条目（V3.0: 强制四层隔离）。

        Args:
            data: 条目数据字典
            user_id: 用户ID（V3.0: 必需）
            agent_type: Agent类型（V3.0: 可选）
            agent_instance_id: Agent实例ID（V3.0: 可选）

        Returns:
            str: entry_id
        """
        try:
            entry_id: str = data.get("entry_id") or f"ent_{uuid.uuid4().hex}"
            payload = dict(data)
            payload["entry_id"] = entry_id

            # V3.0: 强制添加四层隔离字段
            payload["user_id"] = user_id
            if agent_type:
                payload["agent_type"] = agent_type
            if agent_instance_id:
                payload["agent_instance_id"] = agent_instance_id

            # 处理 JSONB 字段
            for key in ["scene_tags", "extra_meta", "metadata_json"]:
                if key in payload and isinstance(payload[key], dict):
                    payload[key] = Json(payload[key])

            columns = [k for k in payload.keys()]
            self._validate_columns(columns)  # V3.1.2: 安全校验
            placeholders = [f"%({k})s" for k in columns]
            sql = f"INSERT INTO entries ({', '.join(columns)}) VALUES ({', '.join(placeholders)}) RETURNING entry_id"

            with connection_scope() as conn:
                # V3.1.2: 必须在同一个事务中设置 RLS 上下文
                self.set_rls_context(user_id, agent_type or "", agent_instance_id or "", conn=conn)
                with conn.cursor() as cur:
                    cur.execute(sql, payload)
                    row = cur.fetchone()
                    logger.info(f"Created entry {entry_id} with isolation: user_id={user_id}, agent_type={agent_type}, agent_instance_id={agent_instance_id}")
                    return row[0] if row else entry_id
        except Exception as e:
            logger.error(f"Failed to create entry: {e}")
            raise

    def get_entry(
        self,
        entry_id: str,
        user_id: str,  # V3.0: 必需
        agent_type: Optional[str] = None,
        agent_instance_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """获取条目（V3.0: 强制四层隔离）。

        Args:
            entry_id: 条目ID
            user_id: 用户ID（V3.0: 必需）
            agent_type: Agent类型（V3.0: 可选）
            agent_instance_id: Agent实例ID（V3.0: 可选）

        Returns:
            Optional[Dict[str, Any]]: 条目数据，如果不存在则返回 None
        """
        try:
            with connection_scope() as conn:
                with conn.cursor() as cur:
                    # V3.0: 添加四层隔离过滤条件（user_id 必需）
                    conditions = ["entry_id = %s", "user_id = %s"]
                    params = [entry_id, user_id]

                    if agent_type:
                        conditions.append("agent_type = %s")
                        params.append(agent_type)
                    if agent_instance_id:
                        conditions.append("agent_instance_id = %s")
                        params.append(agent_instance_id)

                    cur.execute(f"SELECT * FROM entries WHERE {' AND '.join(conditions)}", params)
                    row = cur.fetchone()
                    if row is None:
                        logger.debug(f"Entry {entry_id} not found (with isolation filters)")
                        return None

                    # 获取列名
                    col_names = [desc[0] for desc in cur.description]
                    result = dict(zip(col_names, row))

                    # 处理 JSONB 字段
                    for key in ["scene_tags", "extra_meta", "metadata_json"]:
                        if key in result and isinstance(result[key], str):
                            import json
                            try:
                                result[key] = json.loads(result[key])
                            except json.JSONDecodeError:
                                pass

                    logger.debug(f"Retrieved entry {entry_id} with isolation: user_id={user_id}, agent_type={agent_type}, agent_instance_id={agent_instance_id}")
                    return result
        except Exception as e:
            logger.error(f"Failed to get entry {entry_id}: {e}")
            raise

    def search_similar(
        self,
        query_embedding: List[float],
        user_id: str,  # V3.0: 必需
        filters: Dict[str, Any],
        top_k: int = 10,
        threshold: Optional[float] = None,
        agent_type: Optional[str] = None,
        agent_instance_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """向量检索相似条目（V3.0: 强制四层隔离）。

        Args:
            query_embedding: 查询向量
            filters: 过滤条件
            top_k: 返回结果数量限制
            threshold: 相似度阈值（可选）
            user_id: 用户ID（V3.0: 必需）
            agent_type: Agent类型（V3.0: 可选）
            agent_instance_id: Agent实例ID（V3.0: 可选）

        Returns:
            List[Dict[str, Any]]: 检索结果列表
        """
        try:
            # V3.0: 强制添加四层隔离字段到过滤器（user_id 必需）
            filters["user_id"] = user_id
            if agent_type:
                filters["agent_type"] = agent_type
            if agent_instance_id:
                filters["agent_instance_id"] = agent_instance_id

            results = self.vector_client.search_entries(
                query_embedding=query_embedding,
                filters=filters,
                top_k=top_k,
                threshold=threshold,
            )
            logger.debug(f"Found {len(results)} similar entries with isolation: user_id={user_id}, agent_type={agent_type}, agent_instance_id={agent_instance_id}")
            return results
        except Exception as e:
            logger.error(f"Failed to search similar entries: {e}")
            raise

    def update_entry(
        self,
        entry_id: str,
        user_id: str,  # V3.0: 必需
        agent_type: Optional[str] = None,
        agent_instance_id: Optional[str] = None,
        **kwargs
    ) -> bool:
        """更新条目（V3.0: 强制四层隔离）。

        Args:
            entry_id: 条目ID
            user_id: 用户ID（V3.0: 必需）
            agent_type: Agent类型（V3.0: 可选）
            agent_instance_id: Agent实例ID（V3.0: 可选）
            **kwargs: 要更新的字段

        Returns:
            bool: 是否更新成功
        """
        try:
            if not kwargs:
                return False

            updates = []
            params = []

            # V3.1.2: 统一白名单校验
            self._validate_columns(list(kwargs.keys()))

            for key, value in kwargs.items():
                if key in ["title", "content", "space_type", "section_id", "agent_id", "source_session_id",
                           "user_id", "agent_type", "agent_instance_id"]:  # V3.0: 添加四层隔离字段
                    updates.append(f"{key} = %s")
                    params.append(value)
                elif key in ["scene_tags", "extra_meta", "metadata_json"] and isinstance(value, dict):
                    updates.append(f"{key} = %s")
                    params.append(Json(value))
                elif key in ["section_version", "is_latest", "importance", "usage_count"]:
                    updates.append(f"{key} = %s")
                    params.append(value)
                elif key in ["last_seen_at"]:
                    updates.append(f"{key} = %s")
                    params.append(value)

            if not updates:
                return False

            # V3.0: 添加四层隔离过滤条件（user_id 必需）
            conditions = ["entry_id = %s", "user_id = %s"]
            params = [entry_id, user_id] + params

            if agent_type:
                conditions.append("agent_type = %s")
                params.append(agent_type)
            if agent_instance_id:
                conditions.append("agent_instance_id = %s")
                params.append(agent_instance_id)

            with connection_scope() as conn:
                # V3.1.2: 必须在同一个事务中设置 RLS 上下文
                self.set_rls_context(user_id, agent_type or "", agent_instance_id or "", conn=conn)
                with conn.cursor() as cur:
                    cur.execute(f"""
                        UPDATE entries
                        SET {', '.join(updates)}
                        WHERE {' AND '.join(conditions)}
                    """, params)
                    success = cur.rowcount > 0
                    if success:
                        logger.info(f"Updated entry {entry_id} with isolation: user_id={user_id}, agent_type={agent_type}, agent_instance_id={agent_instance_id}")
                    else:
                        logger.warning(f"Failed to update entry {entry_id} (not found or isolation mismatch)")
                    return success
        except Exception as e:
            logger.error(f"Failed to update entry {entry_id}: {e}")
            raise

    def delete_entry(
        self,
        entry_id: str,
        user_id: str,  # V3.0: 必需
        agent_type: Optional[str] = None,  # V3.0
        agent_instance_id: Optional[str] = None  # V3.0
    ) -> bool:
        """删除条目（V3.0: 强制四层隔离）。

        Args:
            entry_id: 条目ID
            user_id: 用户ID（V3.0: 必需）
            agent_type: Agent类型（V3.0: 可选）
            agent_instance_id: Agent实例ID（V3.0: 可选）

        Returns:
            bool: 是否删除成功
        """
        try:
            with connection_scope() as conn:
                # V3.1.2: 必须在同一个事务中设置 RLS 上下文
                self.set_rls_context(user_id, agent_type or "", agent_instance_id or "", conn=conn)
                with conn.cursor() as cur:
                    # V3.0: 添加四层隔离过滤条件（向量删除也要检查）
                    entry_conditions = ["entry_id = %s", "user_id = %s"]
                    entry_params = [entry_id, user_id]

                    if agent_type:
                        entry_conditions.append("agent_type = %s")
                        entry_params.append(agent_type)
                    if agent_instance_id:
                        entry_conditions.append("agent_instance_id = %s")
                        entry_params.append(agent_instance_id)

                    # 先检查条目是否存在且满足隔离条件
                    cur.execute(f"""
                        SELECT entry_id FROM entries
                        WHERE {' AND '.join(entry_conditions)}
                    """, entry_params)

                    if cur.fetchone() is None:
                        logger.warning(f"Failed to delete entry {entry_id} (not found or isolation mismatch)")
                        return False

                    # 先删除向量（V3.1.2 修复：使用子查询确保只删除属于当前用户的条目的向量，防止越权删除）
                    cur.execute(f"""
                        DELETE FROM entry_embeddings
                        WHERE entry_id IN (
                            SELECT entry_id FROM entries
                            WHERE entry_id = %s AND user_id = %s
                        )
                    """, (entry_id, user_id))

                    # 再删除条目（带四层隔离过滤）
                    cur.execute(f"""
                        DELETE FROM entries
                        WHERE {' AND '.join(entry_conditions)}
                    """, entry_params)

                    success = cur.rowcount > 0
                    if success:
                        logger.info(f"Deleted entry {entry_id} with isolation: user_id={user_id}, agent_type={agent_type}, agent_instance_id={agent_instance_id}")
                    return success
        except Exception as e:
            logger.error(f"Failed to delete entry {entry_id}: {e}")
            raise

    def get_agent_entries(
        self,
        agent_id: str,
        user_id: str,  # V3.0: 必需
        agent_type: Optional[str] = None,
        agent_instance_id: Optional[str] = None,
        space_type: Optional[str] = None,
        scene_tags: Optional[Dict[str, Any]] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """获取Agent的所有条目（V3.0: 强制四层隔离）。

        Args:
            agent_id: Agent ID
            user_id: 用户ID（V3.0: 必需）
            agent_type: Agent类型（V3.0: 可选）
            agent_instance_id: Agent实例ID（V3.0: 可选）
            space_type: 可选，过滤特定空间类型的条目
            scene_tags: 可选，过滤特定场景标签的条目
            limit: 返回结果数量限制

        Returns:
            List[Dict[str, Any]]: 条目列表
        """
        try:
            with connection_scope() as conn:
                # V3.1.2: 必须在同一个事务中设置 RLS 上下文
                self.set_rls_context(user_id, agent_type or "", agent_instance_id or "", conn=conn)
                with conn.cursor() as cur:
                    conditions = ["agent_id = %s", "user_id = %s"]
                    params = [agent_id, user_id]

                    # V3.0: 添加四层隔离过滤（user_id 必需）
                    if agent_type:
                        conditions.append("agent_type = %s")
                        params.append(agent_type)
                    if agent_instance_id:
                        conditions.append("agent_instance_id = %s")
                        params.append(agent_instance_id)

                    if space_type:
                        conditions.append("space_type = %s")
                        params.append(space_type)

                    if scene_tags and isinstance(scene_tags, dict):
                        for key, value in scene_tags.items():
                            if isinstance(value, list) and value:
                                conditions.append("scene_tags @> %s")
                                params.append(Json({key: value}))

                    cur.execute(f"""
                        SELECT entry_id, title, content, section_id, section_version, is_latest,
                               scene_tags, agent_id, space_type, created_at, updated_at,
                               user_id, agent_type, agent_instance_id  -- V3.0: 添加四层隔离字段
                        FROM entries
                        WHERE {" AND ".join(conditions)}
                        ORDER BY updated_at DESC
                        LIMIT %s
                    """, params + [limit])

                    rows = cur.fetchall()
                    col_names = [desc[0] for desc in cur.description]

                    results = []
                    for row in rows:
                        result = dict(zip(col_names, row))
                        # 处理 JSONB 字段
                        if result.get("scene_tags") and isinstance(result["scene_tags"], str):
                            import json
                            try:
                                result["scene_tags"] = json.loads(result["scene_tags"])
                            except json.JSONDecodeError:
                                pass
                        results.append(result)

                    logger.debug(f"Retrieved {len(results)} entries for agent {agent_id} with isolation: user_id={user_id}, agent_type={agent_type}, agent_instance_id={agent_instance_id}")
                    return results
        except Exception as e:
            logger.error(f"Failed to get agent entries: {e}")
            raise

    def batch_create_entries(
        self,
        entries: List[Dict[str, Any]],
        user_id: str,
        agent_type: Optional[str] = None,
        agent_instance_id: Optional[str] = None
    ) -> List[str]:
        """批量创建条目（V3.0: 强制四层隔离）。

        使用批量插入提高性能。

        Args:
            entries: 条目数据字典列表
            user_id: 用户ID（V3.0: 必需）
            agent_type: Agent类型（V3.0: 可选）
            agent_instance_id: Agent实例ID（V3.0: 可选）

        Returns:
            List[str]: entry_id 列表
        """
        if not entries:
            return []

        # 准备批量数据
        batch_data = []
        entry_ids = []

        for data in entries:
            entry_id = data.get("entry_id") or f"ent_{uuid.uuid4().hex}"
            entry_ids.append(entry_id)

            payload = dict(data)
            payload["entry_id"] = entry_id

            # V3.0: 强制添加四层隔离字段
            payload["user_id"] = user_id
            if agent_type:
                payload["agent_type"] = agent_type
            if agent_instance_id:
                payload["agent_instance_id"] = agent_instance_id

            # 处理 JSONB 字段
            for key in ["scene_tags", "extra_meta", "metadata_json"]:
                if key in payload and isinstance(payload[key], dict):
                    payload[key] = Json(payload[key])

            batch_data.append(payload)

        # 获取所有可能的字段
        all_fields = set()
        for payload in batch_data:
            all_fields.update(payload.keys())

        columns = sorted(all_fields)
        self._validate_columns(columns)  # V3.1.2: 安全校验
        placeholders = [f"%({k})s" for k in columns]
        sql = f"""
            INSERT INTO entries ({', '.join(columns)})
            VALUES ({', '.join(placeholders)})
            RETURNING entry_id
        """

        with connection_scope() as conn:
            # V3.1.2: 必须在同一个事务中设置 RLS 上下文
            self.set_rls_context(user_id, agent_type or "", agent_instance_id or "", conn=conn)
            with conn.cursor() as cur:
                results = []
                # 批量执行
                for payload in batch_data:
                    cur.execute(sql, payload)
                    row = cur.fetchone()
                    results.append(row[0] if row else payload["entry_id"])

        logger.info(f"Batch created {len(results)} entries with isolation: user_id={user_id}, agent_type={agent_type}, agent_instance_id={agent_instance_id}")
        return results

    def batch_update_entries(
        self,
        updates: List[Dict[str, Any]],
        user_id: str,
        agent_type: Optional[str] = None,
        agent_instance_id: Optional[str] = None
    ) -> Dict[str, bool]:
        """批量更新条目（V3.0: 强制四层隔离检查）。

        Args:
            updates: 更新数据列表，每个字典必须包含 "entry_id" 字段
            user_id: 用户ID（V3.0: 必需）
            agent_type: Agent类型（V3.0: 可选）
            agent_instance_id: Agent实例ID（V3.0: 可选）

        Returns:
            Dict[str, bool]: {entry_id: 是否更新成功}
        """
        if not updates:
            return {}

        results = {}

        with connection_scope() as conn:
            # V3.1.2: 必须在同一个事务中设置 RLS 上下文
            self.set_rls_context(user_id, agent_type or "", agent_instance_id or "", conn=conn)
            with conn.cursor() as cur:
                for update_data in updates:
                    # V3.1.2: 统一白名单校验
                    self._validate_columns([k for k in update_data.keys() if k != "entry_id"])

                    entry_id = update_data.get("entry_id")
                    if not entry_id:
                        continue

                    # 构建更新语句
                    update_fields = []
                    params = []

                    for key, value in update_data.items():
                        if key == "entry_id":
                            continue

                        if key in ["title", "content", "space_type", "section_id", "agent_id", "source_session_id"]:
                            update_fields.append(f"{key} = %s")
                            params.append(value)
                        elif key in ["scene_tags", "extra_meta", "metadata_json"] and isinstance(value, dict):
                            update_fields.append(f"{key} = %s")
                            params.append(Json(value))
                        elif key in ["section_version", "is_latest", "importance", "usage_count"]:
                            update_fields.append(f"{key} = %s")
                            params.append(value)
                        elif key in ["last_seen_at"]:
                            update_fields.append(f"{key} = %s")
                            params.append(value)

                    if update_fields:
                        # V3.0: 添加四层隔离过滤条件
                        conditions = ["entry_id = %s", "user_id = %s"]
                        params.append(entry_id)
                        params.append(user_id)

                        if agent_type:
                            conditions.append("agent_type = %s")
                            params.append(agent_type)
                        if agent_instance_id:
                            conditions.append("agent_instance_id = %s")
                            params.append(agent_instance_id)

                        cur.execute(f"""
                            UPDATE entries
                            SET {', '.join(update_fields)}
                            WHERE {' AND '.join(conditions)}
                        """, params)

                        results[entry_id] = cur.rowcount > 0
                    else:
                        results[entry_id] = False

        logger.info(f"Batch updated {sum(results.values())}/{len(updates)} entries with isolation filters")
        return results

    def batch_get_entries(
        self,
        entry_ids: List[str],
        user_id: str,
        agent_type: Optional[str] = None,
        agent_instance_id: Optional[str] = None
    ) -> Dict[str, Dict[str, Any]]:
        """批量获取条目（V3.0: 强制四层隔离过滤）。

        Args:
            entry_ids: 条目ID列表
            user_id: 用户ID（V3.0: 必需）
            agent_type: Agent类型（V3.0: 可选）
            agent_instance_id: Agent实例ID（V3.0: 可选）

        Returns:
            Dict[str, Dict[str, Any]]: {entry_id: 条目数据}
        """
        if not entry_ids:
            return {}

        with connection_scope() as conn:
            # V3.1.2: 必须在同一个事务中设置 RLS 上下文
            self.set_rls_context(user_id, agent_type or "", agent_instance_id or "", conn=conn)
            with conn.cursor() as cur:
                placeholders = ', '.join(['%s'] * len(entry_ids))

                # V3.0: 添加四层隔离过滤条件
                conditions = ["entry_id IN ({})".format(placeholders), "user_id = %s"]
                params = entry_ids + [user_id]

                if agent_type:
                    conditions.append("agent_type = %s")
                    params.append(agent_type)
                if agent_instance_id:
                    conditions.append("agent_instance_id = %s")
                    params.append(agent_instance_id)

                cur.execute(f"""
                    SELECT * FROM entries
                    WHERE {' AND '.join(conditions)}
                """, params)

                rows = cur.fetchall()
                col_names = [desc[0] for desc in cur.description]

                results = {}
                for row in rows:
                    result = dict(zip(col_names, row))

                    # 处理 JSONB 字段
                    for key in ["scene_tags", "extra_meta", "metadata_json"]:
                        if key in result and isinstance(result[key], str):
                            import json
                            try:
                                result[key] = json.loads(result[key])
                            except json.JSONDecodeError:
                                pass

                    entry_id = result.get("entry_id")
                    if entry_id:
                        results[entry_id] = result

        logger.debug(f"Batch retrieved {len(results)}/{len(entry_ids)} entries with isolation filters")
        return results


    def get_section_entries(
        self,
        section_id: str,
        user_id: str,  # V3.0: 必需
        agent_id: Optional[str] = None,
        agent_type: Optional[str] = None,
        agent_instance_id: Optional[str] = None,
        only_latest: bool = True
    ) -> List[Dict[str, Any]]:
        """获取section的所有条目（V3.0: 强制四层隔离）。

        Args:
            section_id: Section ID
            agent_id: 可选，过滤特定Agent的条目
            user_id: 用户ID（V3.0: 必需）
            agent_type: Agent类型（V3.0: 可选）
            agent_instance_id: Agent实例ID（V3.0: 可选）
            only_latest: 是否只返回最新版本

        Returns:
            List[Dict[str, Any]]: 条目列表
        """
        try:
            with connection_scope() as conn:
                # V3.1.2: 必须在同一个事务中设置 RLS 上下文
                self.set_rls_context(user_id, agent_type or "", agent_instance_id or "", conn=conn)
                with conn.cursor() as cur:
                    conditions = ["section_id = %s", "user_id = %s"]
                    params = [section_id, user_id]

                    # V3.0: 添加四层隔离过滤（user_id 必需）
                    if agent_type:
                        conditions.append("agent_type = %s")
                        params.append(agent_type)
                    if agent_instance_id:
                        conditions.append("agent_instance_id = %s")
                        params.append(agent_instance_id)

                    if agent_id:
                        conditions.append("agent_id = %s")
                        params.append(agent_id)

                    if only_latest:
                        conditions.append("is_latest = TRUE")

                    cur.execute(f"""
                        SELECT entry_id, title, content, section_id, section_version, is_latest,
                               scene_tags, agent_id, created_at, updated_at,
                               user_id, agent_type, agent_instance_id  -- V3.0: 添加四层隔离字段
                        FROM entries
                        WHERE {" AND ".join(conditions)}
                        ORDER BY section_version DESC
                    """, params)

                    rows = cur.fetchall()
                    col_names = [desc[0] for desc in cur.description]

                    results = []
                    for row in rows:
                        result = dict(zip(col_names, row))
                        # 处理 JSONB 字段
                        if result.get("scene_tags") and isinstance(result["scene_tags"], str):
                            import json
                            try:
                                result["scene_tags"] = json.loads(result["scene_tags"])
                            except json.JSONDecodeError:
                                pass
                        results.append(result)

                    logger.debug(f"Retrieved {len(results)} entries for section {section_id} with isolation: user_id={user_id}, agent_type={agent_type}, agent_instance_id={agent_instance_id}")
                    return results
        except Exception as e:
            logger.error(f"Failed to get section entries: {e}")
            raise

