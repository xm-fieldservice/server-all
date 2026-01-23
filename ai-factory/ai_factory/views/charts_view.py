"""Chart view projection interfaces.

This module defines entrypoints for building chart-oriented views
(status distribution, burndown charts, time series, etc.) over the
same backend data used by entries / nodes.

Implementations are expected to:
- accept high-level filters (project_code, time range, user, etc.);
- delegate data selection to `ai_factory.query` (or dedicated
  query services);
- aggregate / group data into series suitable for charting
  components.
"""

from __future__ import annotations

from typing import Any, Dict


def get_chart_view(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Return a chart view payload for the given request.

    v0 contract (to be refined):
    - Input payload may include:
      - "project_code": str | None
      - "user_id": str | None
      - "time_window_days": int | None
      - "chart_type": str  # e.g. "status_distribution" etc.
      - additional options depending on chart_type.
    - Output payload is expected to be a dict, e.g.::

          {
            "type": "status_distribution",
            "series": [...],
            "meta": {...},
          }

    Concrete aggregation logic will be added in later iterations.
    This function currently only defines the stable interface.
    """

    raise NotImplementedError("get_chart_view is not implemented yet")
