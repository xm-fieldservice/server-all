from __future__ import annotations

"""Adapters that convert Web search / HTML results into unified Evidence objects.

当前实现是占位版本：
- 约定 Web 结果为简单的 dict 结构；
- 将其映射为 Evidence(kind="web", ...)。

后续可以接入已有的“3 节点联网 Team”输出结构，
在这里做统一的字段抽取与去 HTML 处理。
"""

from typing import Any, Dict, List

from ai_factory.agents.query_types import Evidence


def web_results_to_evidences(results: List[Dict[str, Any]]) -> List[Evidence]:
    """将 Web 搜索/抓取结果转换为统一 Evidence 列表。

    预期 result 结构（占位约定）：
    {
      "id": str | None,        # 可选的结果 ID 或 URL
      "url": str | None,
      "title": str | None,
      "snippet": str | None,   # 已去 HTML 的文本摘要
      "site": str | None,
      "published_at": str | None,
      ...
    }
    """

    evidences: List[Evidence] = []

    for r in results:
        rid = str(r.get("id") or r.get("url") or "")
        title = r.get("title")
        snippet = r.get("snippet")

        source_meta = {
            "url": r.get("url"),
            "site": r.get("site"),
            "published_at": r.get("published_at"),
        }

        evidences.append(
            Evidence(
                kind="web",
                id=rid or "<missing-web-id>",
                title=str(title) if title is not None else None,
                snippet=str(snippet) if snippet is not None else None,
                source_meta=source_meta,
            )
        )

    return evidences
