"""Swimlane view projection interfaces.

This module defines the entrypoints for constructing swimlane
(project lane) views over entries / tasks. A swimlane view is a
visual projection of the same backend data used by mindmaps and
other tools, but organised along lanes (phases / owners / status)
plus time.

Implementations should:
- rely on `ai_factory.query` to obtain node / task selections;
- project those records into a `SwimlanePayload` structure of the
  general form::

      {
        "lanes": [...],
        "items": [...],
        "meta": {...},
      }

- avoid direct SQL, using repositories only via higher layers.
"""

from __future__ import annotations

from typing import Any, Dict, List

from ai_factory.query.models import NodeQuery, SceneTags, NodeRecord
from ai_factory.query.nodes_service import NodeQueryService


def _build_default_scene_tags() -> SceneTags:
    """Construct an empty SceneTags structure.

    v0 实现中，如果调用方未显式提供基于六行标签的过滤条件，
    则默认视为“所有标签均未选中”，由 DB 层自行决定是否放宽过滤。
    """

    return SceneTags(
        department=[],
        planning=[],
        execution=[],
        common=[],
        status=[],
        rating=[],
    )


def _build_scene_tags_from_payload(payload: Dict[str, Any]) -> SceneTags:
    """Parse optional scene_tags structure from payload.

    预期 payload 结构示例：

        {
          "tags": {
            "department": ["总部"],
            "planning": ["目标"],
            "execution": ["项目"],
            "common": [],
            "status": ["进行中"],
            "rating": []
          }
        }

    若缺失或结构不合法，则退回到全空标签。
    """

    raw_tags = payload.get("tags") or {}
    if not isinstance(raw_tags, dict):
        return _build_default_scene_tags()

    def _list(key: str) -> List[str]:
        val = raw_tags.get(key) or []
        if isinstance(val, list):
            return [str(x) for x in val if str(x).strip()]
        # 单个字符串时也做一次包装，便于调试阶段容错
        if isinstance(val, str) and val.strip():
            return [val.strip()]
        return []

    return SceneTags(
        department=_list("department"),
        planning=_list("planning"),
        execution=_list("execution"),
        common=_list("common"),
        status=_list("status"),
        rating=_list("rating"),
    )


def _build_node_query(payload: Dict[str, Any]) -> NodeQuery:
    """Build a minimal NodeQuery from the incoming payload.

    当前 v0 实现：
    - 仅支持按 time_window_days 控制时间窗口；
    - 场景标签默认为全空结构（后续可从 payload 中解析 tags）；
    - mode 默认使用 "node_list_basic" 语义，对应 NodeQuery.mode
      中的 "node_list_query"。
    """

    time_window_days_raw = payload.get("time_window_days")
    time_window_days = None
    if isinstance(time_window_days_raw, int) and time_window_days_raw > 0:
        time_window_days = time_window_days_raw

    # v0：支持从 payload["tags"] 中解析六行标签结构。
    tags = _build_scene_tags_from_payload(payload)

    # NodeQuery.mode 目前仅支持 "node_list_hot" / "node_list_query"
    mode = "node_list_query"

    return NodeQuery(
        tags=tags,
        time_window_days=time_window_days,
        mode=mode,  # type: ignore[arg-type]
    )


def _project_records_to_swimlane_items(
    records: List[NodeRecord],
    *,
    dimension: str,
) -> Dict[str, Any]:
    """Project NodeRecord 列表为 SwimlanePayload.

    v0 策略：
    - 支持按 SceneTags 维度之一拆分泳道：
      {"department", "planning", "execution", "status"}；
    - 若某条记录在该维度下没有标签，则归入 "unassigned" 泳道；
    - start/end/status/assignee 暂时占位，后续根据表结构补齐。
    """

    # 预定义一个“未分配”泳道，便于兼容当前 NodeRecord.tags 占位实现。
    base_lanes: Dict[str, Dict[str, Any]] = {
        "unassigned": {
            "id": "unassigned",
            "title": "未分配",
            "type": dimension,
        }
    }

    def _get_dimension_tags(r: NodeRecord) -> List[str]:
        tags_map = getattr(r, "tags", None) or {}
        dim_tags = tags_map.get(dimension) or []
        # NodeRecord.tags 当前为占位实现，总是空；仍按接口形态实现，
        # 方便未来 tags 落库后自动生效。
        if isinstance(dim_tags, list):
            return [str(x) for x in dim_tags if str(x).strip()]
        return []

    items: List[Dict[str, Any]] = []

    for r in records:
        dim_values = _get_dimension_tags(r)
        if not dim_values:
            lane_ids = ["unassigned"]
        else:
            lane_ids = []
            for v in dim_values:
                lane_id = f"{dimension}:{v}"
                if lane_id not in base_lanes:
                    base_lanes[lane_id] = {
                        "id": lane_id,
                        "title": v,
                        "type": dimension,
                    }
                lane_ids.append(lane_id)

        # 目前一个记录可以在多个 lane 中出现（多标签场景），
        # 视图层可根据需要去重或限制。
        for lane_id in lane_ids:
            items.append(
                {
                    "id": f"{r.entry_id}:{lane_id}",
                    "entry_id": r.entry_id,
                    "title": r.title,
                    "lane_id": lane_id,
                    "start": r.created_at,
                    "end": r.updated_at,
                    "status": None,
                    "assignee": None,
                }
            )

    lanes = list(base_lanes.values())

    meta: Dict[str, Any] = {
        "lane_dimension": dimension,
        "total_items": len(items),
    }

    return {
        "lanes": lanes,
        "items": items,
        "meta": meta,
    }


def get_swimlane_view(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Return a swimlane view payload for the given request.

    v0 contract (to be refined):
    - Input payload may include:
      - "project_code": str | None
      - "user_id": str | None
      - "time_window_days": int | None
      - optional filters (tags, status, department, etc.).

    当前实现：
    - 忽略 project_code/user_id 等高阶过滤，仅使用 time_window_days
      和 payload["tags"]（如有）构造 NodeQuery；
    - 支持按 dimension ∈ {"department", "planning",
      "execution", "status"} 选择泳道维度：
        - 未提供 dimension 时，默认使用 "status"；
    - 调用 NodeQueryService.query_nodes 获取 NodeRecord 列表；
    - 根据所选维度，将记录按标签拆分到多个泳道；
      在当前 NodeRecord.tags 仍为空结构的阶段，大部分记录会
      落在 "unassigned" 泳道中，但返回结构已与最终形态对齐。

    后续迭代中，可以在不破坏返回结构的前提下：
    - 支持基于 project_code / user_id 的更精细过滤；
    - 丰富 NodeRecord.tags 的真实内容，使得维度泳道真正生效；
    - 补充开始/结束时间与责任人等字段来源。
    """

    query = _build_node_query(payload)
    service = NodeQueryService()
    records = service.query_nodes(query)

    dimension_raw = payload.get("dimension") or "status"
    if not isinstance(dimension_raw, str):
        dimension_raw = "status"
    dimension = dimension_raw.strip().lower()
    if dimension not in {"department", "planning", "execution", "status"}:
        dimension = "status"

    return _project_records_to_swimlane_items(records, dimension=dimension)
