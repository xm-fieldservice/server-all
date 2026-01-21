"""View / projection layer for AI Factory.

This package contains modules that project backend data into
high-level views such as mindmaps, swimlanes, and charts.

All functions here are thin orchestration layers that:
- call into `ai_factory.query` to obtain record sets; and
- project those records into structured payloads for frontends.

Implementations should avoid embedding SQL or direct DB access,
and instead rely on `ai_factory.query` and `ai_factory.db`.
"""

from __future__ import annotations

__all__ = [
    "get_mindmap_view",
    "apply_mindmap_changes",
    "get_swimlane_view",
    "get_chart_view",
]

from .mindmap_view import get_mindmap_view, apply_mindmap_changes  # noqa: F401
from .swimlane_view import get_swimlane_view  # noqa: F401
from .charts_view import get_chart_view  # noqa: F401
