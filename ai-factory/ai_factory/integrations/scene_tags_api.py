from __future__ import annotations

from typing import Any, Dict, List

from ai_factory.query.models import SceneTags, NodeQuery, NodeRecord
from ai_factory.query.nodes_service import NodeQueryService


_service = NodeQueryService()


def query_nodes_by_scene_tags(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """基于场景标签的节点列表查询入口（供上层应用/接口调用）。

    预期 payload 结构示例：
    {
      "tags": {
        "department": ["总部"],
        "planning": ["目标"],
        "execution": ["项目"],
        "common": [],
        "status": [],
        "rating": []
      },
      "time_window_days": 3,
      "mode": "node_list_hot"
    }

    返回值为适合前端渲染的字典列表，每个元素对应一个节点记录。
    当前实现为占位，将随着 NodeQueryService 与 DB 层实现的完善而同步更新。
    """

    raw_tags: Dict[str, Any] = payload.get("tags") or {}

    scene_tags = SceneTags(
        department=list(raw_tags.get("department") or []),
        planning=list(raw_tags.get("planning") or []),
        execution=list(raw_tags.get("execution") or []),
        common=list(raw_tags.get("common") or []),
        status=list(raw_tags.get("status") or []),
        rating=list(raw_tags.get("rating") or []),
    )

    time_window_days_raw = payload.get("time_window_days")
    time_window_days = None
    if isinstance(time_window_days_raw, int):
        time_window_days = time_window_days_raw

    mode = payload.get("mode") or "node_list_query"

    # 说明：
    # - NodeQuery.page_size 默认仅为 50 条，对于泳道等需要“看全局”的视图，
    #   容易出现前端只能看到前 50 条节点、后续新增记录被静默截断的问题；
    # - 这里将 page_size 显式提高到一个相对安全的上限（如 500），
    #   以避免 "原来可以，现在不可以" 这类由分页截断导致的缺失。
    query = NodeQuery(
        tags=scene_tags,
        time_window_days=time_window_days,
        mode=mode,  # type: ignore[arg-type]
        page=1,
        page_size=500,
    )

    records: List[NodeRecord] = _service.query_nodes(query)

    result: List[Dict[str, Any]] = []
    for r in records:
        item: Dict[str, Any] = {
            "entry_id": r.entry_id,
            "title": r.title,
            "tags": r.tags,
            "created_at": r.created_at,
            "updated_at": r.updated_at,
            "activity_score": r.activity_score,
        }
        if r.extra:
            item["extra"] = r.extra
        result.append(item)

    return result
