"""High-level RAG pipeline helpers for v0.

提供一个最小的入口：根据 query 在 pgvector 索引中检索 entries，
并返回包含基础字段与分数的结果列表。
"""

from __future__ import annotations

from typing import Any, Dict, List

from ai_factory.db import entries_repo
from .pgvector_index import search


def retrieve_for_query(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """根据 query 检索 entries，返回包含 entry 基础字段和 score 的列表。"""

    hits = search(query, limit=limit)
    results: List[Dict[str, Any]] = []

    for entry_id, score in hits:
        entry = entries_repo.get_entry(entry_id)
        if not entry:
            continue
        item = dict(entry)
        item["score"] = score
        results.append(item)

    return results
