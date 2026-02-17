from __future__ import annotations

"""RAG 检索基础模块：基于 entry_embeddings 做向量检索。

v0 目标：
- 提供 embed_query(text) 调用 DashScope text-embedding-v4；
- 提供 search_entries(query, ...) 在 Postgres + pgvector 上做语义检索；
- 仅返回 citations（entries + score），answer 交给上层 Agent 决定。

v1 更新：使用统一向量化策略模式
"""

import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from ai_factory.db.pgvector_client import connection_scope

# 使用新的统一向量化策略模式
from ai_factory.vectorization import get_strategy


# 向后兼容的常量定义
EMBEDDING_MODEL = "text-embedding-v4"
EMBEDDING_DIM = 1024


@dataclass
class RetrievedEntry:
    entry_id: str
    title: Optional[str]
    summary_ai: Optional[str]
    content: Optional[str]
    project_code: Optional[str]
    user_id: Optional[str]
    created_at: Optional[datetime]
    score: float  # 越小越相似（基于余弦距离）


def _call_dashscope_embedding(text: str) -> List[float]:
    """调用DashScope API生成query embedding。
    
    使用统一向量化策略模式。
    """
    strategy = get_strategy()
    return strategy.embed(text)


def embed_query(text: str) -> List[float]:
    """对检索问题做向量化，复用 entries 向量化的同一模型。"""

    cleaned = text.strip()
    if not cleaned:
        raise ValueError("query text is empty")
    return _call_dashscope_embedding(cleaned)


def search_entries(
    query: str,
    top_k: int = 10,
    *,
    project_code: Optional[str] = None,
    user_id: Optional[str] = None,
    since: Optional[datetime] = None,
) -> List[RetrievedEntry]:
    """在 entry_embeddings 上做向量检索，返回最相似的若干 entries。

    排序规则：embedding <#> query_vec（余弦距离，越小越近）。
    可选按照 project_code / user_id / created_at 下限进行过滤。
    """

    query_vec = embed_query(query)

    conditions: List[str] = []
    params: List[Any] = []

    if project_code is not None:
        conditions.append("e.project_code = %s")
        params.append(project_code)

    if user_id is not None:
        conditions.append("e.user_id = %s")
        params.append(user_id)

    if since is not None:
        conditions.append("e.created_at >= %s")
        params.append(since)

    where_sql = ""
    if conditions:
        where_sql = "WHERE " + " AND ".join(conditions)

    sql = f"""
        SELECT
            e.entry_id,
            e.title,
            e.summary_ai,
            e.input_content AS content,
            e.project_code,
            e.user_id,
            e.created_at,
            (emb.embedding <#> %s::vector) AS score
        FROM entry_embeddings emb
        JOIN entries e ON e.entry_id = emb.entry_id
        {where_sql}
        ORDER BY score ASC
        LIMIT %s;
    """

    params_with_vec: List[Any] = [query_vec, *params, top_k]

    with connection_scope() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params_with_vec)
            rows = cur.fetchall()

    results: List[RetrievedEntry] = []
    for row in rows:
        (
            entry_id,
            title,
            summary_ai,
            content,
            project_code_val,
            user_id_val,
            created_at_val,
            score,
        ) = row
        results.append(
            RetrievedEntry(
                entry_id=str(entry_id),
                title=title,
                summary_ai=summary_ai,
                content=content,
                project_code=project_code_val,
                user_id=user_id_val,
                created_at=created_at_val,
                score=float(score),
            )
        )

    return results
