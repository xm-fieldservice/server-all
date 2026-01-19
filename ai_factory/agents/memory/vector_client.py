"""Vector client abstraction for memory services.

Provides a unified interface for vector search operations,
wrapping the underlying pgvector implementation.
"""

from __future__ import annotations

from typing import List, Dict, Any, Optional
from ai_factory.db.pgvector_client import connection_scope
import json


class VectorClient:
    """向量检索客户端抽象。

    封装 pgvector 向量检索逻辑，为 EntryService 提供统一的接口。
    """

    def __init__(self):
        """初始化 VectorClient。"""

    def search_entries(
        self,
        query_embedding: List[float],
        filters: Optional[Dict[str, Any]] = None,
        top_k: int = 10,
        threshold: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """在 entries 表中进行向量检索。

        Args:
            query_embedding: 查询向量
            filters: 过滤条件（user_id, agent_id, space_type, scene_tags 等）
            top_k: 返回结果数量限制
            threshold: 相似度阈值（可选）

        Returns:
            List[Dict[str, Any]]: 检索结果列表，包含相似度分数
        """
        with connection_scope() as conn:
            with conn.cursor() as cur:
                # 构建查询条件
                conditions = []
                params = []

                if filters:
                    # section_id 过滤
                    if "section_id" in filters:
                        conditions.append("e.section_id = %s")
                        params.append(filters["section_id"])

                    # entry_type 过滤
                    if "entry_type" in filters:
                        conditions.append("e.entry_type = %s")
                        params.append(filters["entry_type"])

                where_clause = " AND ".join(conditions) if conditions else "TRUE"

                # 简化版向量相似度查询（适配记忆系统表结构）
                sql = f"""
                    SELECT
                        e.entry_id,
                        e.content,
                        e.entry_type,
                        e.section_id,
                        e.created_at,
                        1 - (emb.embedding <=> %s::vector) AS similarity
                    FROM entries e
                    LEFT JOIN entry_embeddings emb ON e.entry_id = emb.entry_id
                    WHERE {where_clause}
                    ORDER BY similarity DESC
                    LIMIT %s
                """

                # 添加查询向量和 top_k 参数
                query_params = [query_embedding] + params + [top_k]
                cur.execute(sql, query_params)

                rows = cur.fetchall()
                results = [
                    {
                        "entry_id": row[0],
                        "content": row[1],
                        "entry_type": row[2],
                        "section_id": row[3],
                        "created_at": row[4].isoformat() if row[4] else None,
                        "similarity": float(row[5]) if row[5] is not None else None,
                    }
                    for row in rows
                ]

                # 应用相似度阈值过滤
                if threshold is not None:
                    results = [r for r in results if r["similarity"] >= threshold]

                return results

    def upsert_embedding(
        self,
        entry_id: str,
        embedding: List[float],
        project_code: Optional[str] = None
    ) -> None:
        """插入或更新向量到 entry_embeddings 表。

        Args:
            entry_id: 条目ID
            embedding: 向量
            project_code: 项目代码（可选）
        """
        with connection_scope() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO entry_embeddings (
                        entry_id,
                        embedding,
                        project_code
                    )
                    VALUES (%s, %s, %s)
                    ON CONFLICT (entry_id) DO UPDATE SET
                        embedding = EXCLUDED.embedding,
                        project_code = EXCLUDED.project_code
                """, (entry_id, embedding, project_code))

    def get_embedding(
        self,
        entry_id: str
    ) -> Optional[List[float]]:
        """获取条目的向量。

        Args:
            entry_id: 条目ID

        Returns:
            Optional[List[float]]: 向量，如果不存在则返回 None
        """
        with connection_scope() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT embedding
                    FROM entry_embeddings
                    WHERE entry_id = %s
                """, (entry_id,))

                row = cur.fetchone()
                if row and row[0]:
                    return list(row[0])
        return None

    def delete_embedding(
        self,
        entry_id: str
    ) -> bool:
        """删除条目的向量。

        Args:
            entry_id: 条目ID

        Returns:
            bool: 是否删除成功
        """
        with connection_scope() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    DELETE FROM entry_embeddings
                    WHERE entry_id = %s
                """, (entry_id,))
                return cur.rowcount > 0

    def batch_search_entries(
        self,
        query_embeddings: List[List[float]],
        filters: Optional[Dict[str, Any]] = None,
        top_k: int = 10,
        threshold: Optional[float] = None
    ) -> Dict[int, List[Dict[str, Any]]]:
        """批量向量检索相似条目。

        对多个查询向量进行并行检索，提高性能。

        Args:
            query_embeddings: 查询向量列表
            filters: 过滤条件（user_id, agent_id, space_type, scene_tags 等）
            top_k: 每个查询返回结果数量限制
            threshold: 相似度阈值（可选）

        Returns:
            Dict[int, List[Dict[str, Any]]]: {索引: 检索结果列表}
        """
        results = {}

        for idx, query_embedding in enumerate(query_embeddings):
            results[idx] = self.search_entries(
                query_embedding=query_embedding,
                filters=filters,
                top_k=top_k,
                threshold=threshold
            )

        return results

    def batch_upsert_embeddings(
        self,
        entries: List[Dict[str, Any]]
    ) -> Dict[str, bool]:
        """批量插入或更新向量到 entry_embeddings 表。

        使用批量操作提高性能。

        Args:
            entries: 条目列表，每个条目必须包含 "entry_id" 和 "embedding" 字段

        Returns:
            Dict[str, bool]: {entry_id: 是否成功}
        """
        if not entries:
            return {}

        results = {}

        with connection_scope() as conn:
            with conn.cursor() as cur:
                for entry in entries:
                    entry_id = entry.get("entry_id")
                    embedding = entry.get("embedding")
                    project_code = entry.get("project_code")

                    if not entry_id or embedding is None:
                        continue

                    try:
                        cur.execute("""
                            INSERT INTO entry_embeddings (
                                entry_id,
                                embedding,
                                project_code
                            )
                            VALUES (%s, %s, %s)
                            ON CONFLICT (entry_id) DO UPDATE SET
                                embedding = EXCLUDED.embedding,
                                project_code = EXCLUDED.project_code
                        """, (entry_id, embedding, project_code))

                        results[entry_id] = True
                    except Exception as e:
                        print(f"[VectorClient] Failed to upsert embedding for {entry_id}: {e}")
                        results[entry_id] = False

        return results

    def batch_get_embeddings(
        self,
        entry_ids: List[str]
    ) -> Dict[str, Optional[List[float]]]:
        """批量获取条目的向量。

        Args:
            entry_ids: 条目ID列表

        Returns:
            Dict[str, Optional[List[float]]]: {entry_id: 向量}
        """
        if not entry_ids:
            return {}

        results = {}

        with connection_scope() as conn:
            with conn.cursor() as cur:
                placeholders = ', '.join(['%s'] * len(entry_ids))
                cur.execute(f"""
                    SELECT entry_id, embedding
                    FROM entry_embeddings
                    WHERE entry_id IN ({placeholders})
                """, entry_ids)

                rows = cur.fetchall()
                # 先将所有 ID 标记为 None（表示不存在）
                for entry_id in entry_ids:
                    results[entry_id] = None

                # 更新存在的向量
                for row in rows:
                    entry_id = row[0]
                    embedding = row[1]
                    if embedding:
                        results[entry_id] = list(embedding)

        return results

