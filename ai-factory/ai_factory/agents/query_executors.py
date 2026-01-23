from __future__ import annotations

"""Executors for Node #2 of the unified query pipeline.

- RagSearchExecutor: 调用本地 entries RAG 检索；
- WebSearchExecutor: 预留联网搜索执行入口（当前为占位实现）。

后续可以在此模块内接入/适配现有的“3 节点联网 Team”。
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Protocol

from ai_factory.agents.query_types import QueryIntent
from ai_factory.rag.entries_rag import RetrievedEntry, search_entries
from ai_factory.web.search_team_web import parallel_web_search_aggregate


class QueryExecutor(Protocol):
    """Node #2 执行器统一接口。"""

    def execute(self, intent: QueryIntent) -> List[Dict[str, Any]]:  # pragma: no cover - protocol
        """根据意图执行检索/查询，返回原始结果列表（dict）。"""


@dataclass
class RagSearchExecutor:
    """基于 entries 表的 RAG 检索执行器。"""

    default_top_k: int = 10

    def execute(self, intent: QueryIntent) -> List[Dict[str, Any]]:
        # 允许使用 Node #1 拆解出的 sub_queries 进行多次 RAG 检索，
        # 这里只负责“捞素材”，不做去重/合并，整理工作交给 Node #3。

        base_question = intent.question_text.strip()
        sub_queries = [q.strip() for q in getattr(intent, "sub_queries", []) or [] if q and q.strip()]

        if sub_queries:
            queries: List[str] = sub_queries
        else:
            if not base_question:
                return []
            queries = [base_question]

        top_k = intent.filters.get("top_k") or self.default_top_k
        try:
            top_k_int = int(top_k)
        except Exception:  # noqa: BLE001
            top_k_int = self.default_top_k

        project_code = intent.filters.get("project_code")
        user_id = intent.filters.get("user_id")

        # 素材收集：对每个查询独立调用 search_entries（RAG 检索），
        # 将所有 RetrievedEntry 直接累加到一个列表中，不在此处去重。
        collected: List[RetrievedEntry] = []

        for q in queries:
            if not q:
                continue
            retrieved: List[RetrievedEntry] = search_entries(
                q,
                top_k=top_k_int,
                project_code=project_code,
                user_id=user_id,
                since=None,
            )
            collected.extend(retrieved)

        # 将 RetrievedEntry 转成 dict，留给后续 adapter / Node #3 处理
        results: List[Dict[str, Any]] = []
        for e in collected:
            results.append(
                {
                    "entry_id": e.entry_id,
                    "title": e.title,
                    "summary_ai": e.summary_ai,
                    "project_code": e.project_code,
                    "user_id": e.user_id,
                    "created_at": e.created_at.isoformat() if e.created_at else None,
                    "score": e.score,
                }
            )

        return results


@dataclass
class WebSearchExecutor:
    """基于 Google Custom Search 的 Web 搜索执行器。

    - 使用 Node #1 拆解出的 sub_queries 作为子查询列表；
    - 若 sub_queries 为空，则退回到使用原始 question_text 作为单一查询；
    - 实际联网搜索逻辑由 ai_factory.web.search_team_web 提供。
    """

    default_top_k: int = 5

    def execute(self, intent: QueryIntent) -> List[Dict[str, Any]]:  # noqa: D401
        print("[WebSearchExecutor] execute() called with intent:", {
            "question_text": intent.question_text,
            "mode": intent.mode,
            "filters": intent.filters,
            "sub_queries": getattr(intent, "sub_queries", []),
        })

        # 1) 准备查询列表：优先使用 Node #1 提供的 sub_queries
        sub_queries_raw = getattr(intent, "sub_queries", []) or []
        sub_queries: List[Dict[str, Any]] = []

        for item in sub_queries_raw:
            if isinstance(item, str) and item.strip():
                sub_queries.append({"query": item.strip()})

        if not sub_queries:
            q = intent.question_text.strip()
            if q:
                sub_queries.append({"query": q})

        if not sub_queries:
            print("[WebSearchExecutor] no valid queries, return empty list")
            return []

        print("[WebSearchExecutor] prepared sub_queries:", sub_queries)

        # 2) 结果条数：优先从 filters.top_k 读取
        top_k = intent.filters.get("top_k") or self.default_top_k
        try:
            top_k_int = int(top_k)
        except Exception:  # noqa: BLE001
            top_k_int = self.default_top_k

        if top_k_int <= 0:
            top_k_int = self.default_top_k

        print("[WebSearchExecutor] resolved top_k_int =", top_k_int)

        # 3) 调用并发 Web 搜索聚合
        print("[WebSearchExecutor] calling parallel_web_search_aggregate ...")
        results = parallel_web_search_aggregate(sub_queries, num=top_k_int)
        print("[WebSearchExecutor] parallel_web_search_aggregate returned", len(results), "results")

        return results
