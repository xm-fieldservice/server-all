from __future__ import annotations

"""Adapters that convert RAG retrieval results into unified Evidence objects.

当前仅包含从 qa_answer_rag 返回的 citation dict → Evidence 的适配，
便于后续在整理节点（Node #3）统一消费 RAG / Web 两类证据。
"""

from typing import Any, Dict, List

from ai_factory.agents.query_types import Evidence


def citations_to_evidences(citations: List[Dict[str, Any]]) -> List[Evidence]:
    """将 RAG 的 citations 列表转换为统一的 Evidence 列表。

    预期 citation 结构：
    {
      "entry_id": str,
      "title": str | None,
      "summary_ai": str | None,
      "project_code": str | None,
      "user_id": str | None,
      "created_at": str | None,
      "score": float,
      ...
    }
    """

    evidences: List[Evidence] = []

    for c in citations:
        entry_id = str(c.get("entry_id") or "")
        title = c.get("title")
        summary = c.get("summary_ai")

        source_meta = {
            "entry_id": entry_id,
            "project_code": c.get("project_code"),
            "user_id": c.get("user_id"),
            "created_at": c.get("created_at"),
            "score": c.get("score"),
        }

        evidences.append(
            Evidence(
                kind="rag",
                id=entry_id or "<missing-entry-id>",
                title=str(title) if title is not None else None,
                snippet=str(summary) if summary is not None else None,
                source_meta=source_meta,
            )
        )

    return evidences
