"""EntryService implementation.

Unified read/write and vector search for entries table and embeddings.
"""

from __future__ import annotations

import uuid
from typing import Dict, Any, List, Optional
from ai_factory.db.pgvector_client import connection_scope
from psycopg2.extras import Json
from .vector_client import VectorClient


class EntryService:
    """Provide a high-level API over entries and entry_embeddings."""

    def __init__(self, vector_client: Optional[VectorClient] = None) -> None:
        """初始化 EntryService。

        Args:
            vector_client: VectorClient 实例，用于向量检索
        """
        self.vector_client = vector_client or VectorClient()

    def create_entry(self, data: Dict[str, Any]) -> str:
        """创建新的条目。

        Args:
            data: 条目数据字典

        Returns:
            str: entry_id
        """
        entry_id: str = data.get("entry_id") or f"ent_{uuid.uuid4().hex}"
        payload = dict(data)
        payload["entry_id"] = entry_id

        # 处理 JSONB 字段
        for key in ["scene_tags", "extra_meta", "metadata_json"]:
            if key in payload and isinstance(payload[key], dict):
                payload[key] = Json(payload[key])

        columns = [k for k in payload.keys()]
        placeholders = [f"%({k})s" for k in columns]
        sql = f"INSERT INTO entries ({', '.join(columns)}) VALUES ({', '.join(placeholders)}) RETURNING entry_id"

        with connection_scope() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, payload)
                row = cur.fetchone()
                return row[0] if row else entry_id

    def get_entry(self, entry_id: str) -> Optional[Dict[str, Any]]:
        """获取条目。

        Args:
            entry_id: 条目ID

        Returns:
            Optional[Dict[str, Any]]: 条目数据，如果不存在则返回 None
        """
        with connection_scope() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM entries WHERE entry_id = %s", (entry_id,))
                row = cur.fetchone()
                if row is None:
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

                return result

    def search_similar(
        self,
        query_embedding: List[float],
        filters: Dict[str, Any],
        top_k: int = 10,
        threshold: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """向量检索相似条目。

        Args:
            query_embedding: 查询向量
            filters: 过滤条件
            top_k: 返回结果数量限制
            threshold: 相似度阈值（可选）

        Returns:
            List[Dict[str, Any]]: 检索结果列表
        """
        return self.vector_client.search_entries(
            query_embedding=query_embedding,
            filters=filters,
            top_k=top_k,
            threshold=threshold,
        )

    def update_entry(
        self,
        entry_id: str,
        **kwargs
    ) -> bool:
        """更新条目。

        Args:
            entry_id: 条目ID
            **kwargs: 要更新的字段

        Returns:
            bool: 是否更新成功
        """
        if not kwargs:
            return False

        updates = []
        params = []

        for key, value in kwargs.items():
            if key in ["title", "content", "space_type", "section_id", "agent_id", "source_session_id"]:
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

        params.append(entry_id)

        with connection_scope() as conn:
            with conn.cursor() as cur:
                cur.execute(f"""
                    UPDATE entries
                    SET {', '.join(updates)}
                    WHERE entry_id = %s
                """, params)
                return cur.rowcount > 0

    def delete_entry(self, entry_id: str) -> bool:
        """删除条目。

        Args:
            entry_id: 条目ID

        Returns:
            bool: 是否删除成功
        """
        with connection_scope() as conn:
            with conn.cursor() as cur:
                # 先删除向量
                cur.execute("""
                    DELETE FROM entry_embeddings
                    WHERE entry_id = %s
                """, (entry_id,))

                # 再删除条目
                cur.execute("""
                    DELETE FROM entries
                    WHERE entry_id = %s
                """, (entry_id,))

                return cur.rowcount > 0

    def get_agent_entries(
        self,
        agent_id: str,
        space_type: Optional[str] = None,
        scene_tags: Optional[Dict[str, Any]] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """获取Agent的所有条目。

        Args:
            agent_id: Agent ID
            space_type: 可选，过滤特定空间类型的条目
            scene_tags: 可选，过滤特定场景标签的条目
            limit: 返回结果数量限制

        Returns:
            List[Dict[str, Any]]: 条目列表
        """
        with connection_scope() as conn:
            with conn.cursor() as cur:
                conditions = ["agent_id = %s"]
                params = [agent_id]

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
                           scene_tags, agent_id, space_type, created_at, updated_at
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

                return results

    def get_section_entries(
        self,
        section_id: str,
        agent_id: Optional[str] = None,
        only_latest: bool = True
    ) -> List[Dict[str, Any]]:
        """获取section的所有条目。

        Args:
            section_id: Section ID
            agent_id: 可选，过滤特定Agent的条目
            only_latest: 是否只返回最新版本

        Returns:
            List[Dict[str, Any]]: 条目列表
        """
        with connection_scope() as conn:
            with conn.cursor() as cur:
                conditions = ["section_id = %s"]
                params = [section_id]

                if agent_id:
                    conditions.append("agent_id = %s")
                    params.append(agent_id)

                if only_latest:
                    conditions.append("is_latest = TRUE")

                cur.execute(f"""
                    SELECT entry_id, title, content, section_id, section_version, is_latest,
                           scene_tags, agent_id, created_at, updated_at
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

                return results
