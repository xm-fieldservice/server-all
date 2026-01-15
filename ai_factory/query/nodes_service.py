from __future__ import annotations

from typing import List, Dict, Any

from ai_factory.db import nodes_repo
from .models import NodeQuery, NodeRecord


class NodeQueryService:
    """通用节点查询服务入口。

    说明：
    - 对外只暴露基于结构化参数的查询接口，不暴露任何 SQL 细节；
    - 内部将根据不同 mode 调用 DB 层或 RAG/Graph 等实现；
    - 当前 v1 仅支持 "node_list_hot" 与 "node_list_query" 两种模式。
    """

    def query_nodes(self, query: NodeQuery) -> List[NodeRecord]:
        """根据查询请求返回节点列表。

        当前实现为占位实现，后续会接入 ai_factory.db.nodes_repo 中的具体查询逻辑。
        """

        if query.mode == "node_list_hot":
            return self._query_hot_nodes(query)
        if query.mode == "node_list_query":
            return self._query_basic_nodes(query)

        raise ValueError(f"Unsupported node query mode: {query.mode!r}")

    def _query_hot_nodes(self, query: NodeQuery) -> List[NodeRecord]:
        """按“近 N 天活动度”返回节点列表的占位实现。"""

        filters = self._build_db_filters(query, hot_mode=True)
        rows = nodes_repo.query_nodes_hot(filters)
        return [self._row_to_record(row) for row in rows]

    def _query_basic_nodes(self, query: NodeQuery) -> List[NodeRecord]:
        """按标签过滤 + 基本时间排序返回节点列表的占位实现。"""

        filters = self._build_db_filters(query, hot_mode=False)
        rows = nodes_repo.query_nodes_basic(filters)
        return [self._row_to_record(row) for row in rows]

    def _build_db_filters(self, query: NodeQuery, *, hot_mode: bool) -> nodes_repo.NodeDBFilters:
        """将 NodeQuery 转换为 DB 层使用的过滤条件结构。"""

        tags: Dict[str, List[str]] = {
            "department": query.tags.department,
            "planning": query.tags.planning,
            "execution": query.tags.execution,
            "common": query.tags.common,
            "status": query.tags.status,
            "rating": query.tags.rating,
        }

        page = max(1, int(query.page))
        page_size = max(1, int(query.page_size))
        offset = (page - 1) * page_size

        return nodes_repo.NodeDBFilters(
            tags=tags,
            time_window_days=query.time_window_days,
            offset=offset,
            limit=page_size,
            hot_mode=hot_mode,
        )

    def _row_to_record(self, row: Dict[str, Any]) -> NodeRecord:
        """将 DB 返回的单行映射为 NodeRecord。

        说明：
        - 当前仅依赖 entries 表中的基础字段（entry_id/title/created_at）；
        - tags 信息暂时统一为空结构，后续会根据真实标签落库方案补齐；
        - activity_score 在 basic 模式下为 None，在 hot 模式下可由 DB 返回。
        """

        entry_id = str(row.get("entry_id"))
        title = row.get("title")
        created_at_val = row.get("created_at")
        updated_at_val = row.get("updated_at", created_at_val)
        activity_score_val = row.get("activity_score")

        # 从 DB 行中解析 scene_tags(jsonb) 字段，映射为统一的 tags 结构。
        # 注意：这里需要完整保留六行标签 + work 维度，供上层(如泳道)使用
        # scene_tags.work=["in_work"] 来判断是否导入工作区。
        raw_scene_tags = row.get("scene_tags") or {}
        tags: Dict[str, List[str]] = {
            "department": [],
            "planning": [],
            "execution": [],
            "common": [],
            "status": [],
            "rating": [],
            "work": [],
        }
        if isinstance(raw_scene_tags, dict):
            for key in tags.keys():
                values = raw_scene_tags.get(key) or []
                if isinstance(values, list):
                    tags[key] = [str(v) for v in values]

        # 将 entries 表中的部分元数据字段透传到 extra，供上层使用
        extra: Dict[str, Any] = {}
        space_type_val = row.get("space_type")
        if space_type_val is not None:
            extra["space_type"] = str(space_type_val)
        parent_entry_id_val = row.get("parent_entry_id")
        if parent_entry_id_val is not None:
            s = str(parent_entry_id_val).strip()
            if s:
                extra["parent_entry_id"] = s

        return NodeRecord(
            entry_id=entry_id,
            title=title,
            tags=tags,
            created_at=created_at_val.isoformat() if hasattr(created_at_val, "isoformat") else None,
            updated_at=updated_at_val.isoformat() if hasattr(updated_at_val, "isoformat") else None,
            activity_score=float(activity_score_val) if activity_score_val is not None else None,
            extra=extra,
        )
