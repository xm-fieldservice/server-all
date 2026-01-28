"""v0 pgvector-based indexing and search helpers for entries.

本模块提供最小的索引/检索接口：
- index_entries(entry_ids): 根据 entry_id 列表，为其生成占位向量并写入向量表；
- search(query, filters): 根据查询向量，在向量表中检索相似 entries。

v0 版本不集成真实 embedding 模型，仅保留接口与 SQL 结构，
后续可替换为真正的向量化与相似度计算。
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from ai_factory.db import entries_repo
from ai_factory.db.pgvector_client import connection_scope


VECTOR_TABLE = "entry_embeddings"  # v0 占位表名


def _ensure_vector_table() -> None:
    """确保向量表存在（v0 占位实现，使用简单 float[] 列）。"""

    sql = f"""
    CREATE TABLE IF NOT EXISTS {VECTOR_TABLE} (
        entry_id text PRIMARY KEY,
        embedding vector(3)
    )
    """
    with connection_scope() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)


def _fake_embed(text: str) -> List[float]:
    """v0 假 embedding：基于长度/简单特征生成 3 维向量，占位用。"""

    length = float(len(text))
    return [length, length % 10, (length % 100) / 10.0]


def index_entries(entry_ids: List[str]) -> int:
    """为指定 entry 列表生成占位向量并写入向量表，返回成功条数。"""

    _ensure_vector_table()
    count = 0

    for eid in entry_ids:
        entry = entries_repo.get_entry(eid)
        if not entry:
            continue
        text = f"{entry.get('title', '')}\n{entry.get('input_content', '')}"
        vec = _fake_embed(text)

        sql = f"""
        INSERT INTO {VECTOR_TABLE} (entry_id, embedding)
        VALUES (%s, %s)
        ON CONFLICT (entry_id) DO UPDATE SET embedding = EXCLUDED.embedding
        """
        with connection_scope() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (eid, vec))
        count += 1

    return count


def search(query: str, limit: int = 10) -> List[Tuple[str, float]]:
    """基于占位向量的简单相似度检索，返回 (entry_id, score) 列表。"""

    _ensure_vector_table()
    qvec = _fake_embed(query)

    sql = f"""
    SELECT entry_id, (embedding <#> %s::vector) AS distance
    FROM {VECTOR_TABLE}
    ORDER BY distance ASC
    LIMIT %s
    """
    results: List[Tuple[str, float]] = []

    with connection_scope() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (qvec, limit))
            for eid, dist in cur.fetchall():
                # v0 中将 distance 反向成 score（越小越相似）
                score = float(-dist)
                results.append((str(eid), score))

    return results
