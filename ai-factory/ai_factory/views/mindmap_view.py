"""Mindmap view projection interfaces.

This module defines the public interfaces for constructing and
mutating mindmap views. Implementations are intentionally minimal
for v0 and should:

- use `ai_factory.query` to obtain node / entry selections;
- project those records into a `graph_payload` structure that the
  existing mindmap frontends can consume;
- translate mindmap edit operations into standard change events
  (delta JSON) that can be applied to `entries` / `map_snapshots`.
"""

from __future__ import annotations

from typing import Any, Dict


def get_mindmap_view(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Return a mindmap view payload for the given request.

    v0 contract (to be refined):
    - Input payload may include:
      - "project_code": str | None
      - "user_id": str | None
      - "time_window_days": int | None
      - other filters for entries / nodes.
    - Output is a dict compatible with the existing mindmap
      frontends, typically of the form::

          {
            "nodes": [...],
            "edges": [...],
            "meta": {...},
          }

    This function is a thin orchestration layer. It should not
    perform direct SQL queries; instead it should:
    - delegate record selection to `ai_factory.query`;
    - perform projection / shaping logic only.
    """

    # v0 placeholder implementation; real logic will be added in
    # subsequent steps of the architecture rollout.
    raise NotImplementedError("get_mindmap_view is not implemented yet")


def apply_mindmap_changes(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Apply a list of standard mindmap change events (deltas).

    v0 contract (to be refined):
    - Input payload may include:
      - "changes": List[Dict[str, Any]]  # standard change JSON
      - optional context (project_code, user_id, etc.).
    - The function is responsible for:
      - validating the change events;
      - translating them into concrete DB operations via
        existing write channels (`entries_ingest`, repositories,
        `map_snapshots_repo`, etc.);
      - returning a summary dict (e.g. counts, new ids).

    This function should *not* be called from frontends directly;
    it is intended to be wrapped by an integrations / API layer.
    """

    raise NotImplementedError("apply_mindmap_changes is not implemented yet")
