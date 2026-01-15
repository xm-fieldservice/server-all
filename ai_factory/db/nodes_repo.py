from __future__ import annotations

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, timezone

from .pgvector_client import connection_scope


class NodeDBFilters:
    """节点查询在 DB 层使用的过滤条件结构。

    说明：
    - 这是对上层 SceneTags / NodeQuery 的“贴近 SQL 版本”；
    - 具体字段设计会随着表结构演进逐步补齐，当前为占位结构。
    """

    def __init__(
        self,
        *,
        tags: Dict[str, List[str]] | None = None,
        time_window_days: Optional[int] = None,
        offset: int = 0,
        limit: int = 50,
        hot_mode: bool = False,
    ) -> None:
        self.tags = tags or {}
        self.time_window_days = time_window_days
        self.offset = offset
        self.limit = limit
        self.hot_mode = hot_mode


def query_nodes_basic(filters: NodeDBFilters) -> List[Dict[str, Any]]:
    """基于标签和时间窗口的基础节点查询（占位实现）。

    后续会根据《表结构设计》中的 entries / 标签字段设计补充具体 SQL。
    当前实现基于 entries 表的 scene_tags/created_at 与分页，
    标签采用 jsonb ?| 进行过滤，未命中则不会出现在结果中。
    """

    # v1: 直接从 entries 表中查询基础字段 + 元数据字段
    # 包含:
    # - entry_id, title, created_at
    # - scene_tags: 用于还原 department/planning 等标签（当前为 text/jsonb 兼容）
    # - space_type, parent_entry_id: 作为元数据提供给上层 NodeQueryService
    # 注意：当前表结构中尚未统一引入 updated_at 字段，这里只选 created_at，
    # 上层 NodeQueryService 会在缺失 updated_at 时自动回退到 created_at。
    sql = (
        "SELECT entry_id, title, created_at, "
        "space_type, parent_entry_id, scene_tags "
        "FROM entries"
    )
    params: List[Any] = []

    where_clauses: List[str] = []
    # 场景标签过滤：假设 entries.scene_tags 为 jsonb，结构含六个固定 key。
    for key in ["department", "planning", "execution", "common", "status", "rating"]:
        values = filters.tags.get(key) if filters.tags else None
        if values:
            # (scene_tags->'key') ?| ARRAY[...]
            where_clauses.append(f"(scene_tags->%s) ?| %s")
            params.append(key)
            params.append(values)
    if filters.time_window_days and filters.time_window_days > 0:
        # 以当前 UTC 时间（带时区）减去 N 天作为下限，避免 naive/aware 混用
        now_utc = datetime.now(timezone.utc)
        since = now_utc - timedelta(days=filters.time_window_days)
        where_clauses.append("created_at >= %s")
        params.append(since)

    if where_clauses:
        sql += " WHERE " + " AND ".join(where_clauses)

    sql += " ORDER BY created_at DESC OFFSET %s LIMIT %s"
    params.extend([filters.offset, filters.limit])

    rows: List[Dict[str, Any]] = []

    with connection_scope() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            fetched = cur.fetchall()
            colnames = [d[0] for d in cur.description]
            for r in fetched:
                rows.append(dict(zip(colnames, r)))

    return rows


def query_nodes_hot(filters: NodeDBFilters) -> List[Dict[str, Any]]:
    """按“近 N 天活动度”排序的节点查询（占位实现）。

    v1 按 created_at 排序，并基于 time_window_days 计算一个简单的 activity_score：
    - 仅当 time_window_days 有效时计算分数；
    - 窗口内越新的记录分数越高。
    """

    rows = query_nodes_basic(filters)

    if not filters.time_window_days or filters.time_window_days <= 0:
        # 未指定窗口时，不计算热度分，保持 None。
        for row in rows:
            row.setdefault("activity_score", None)
        return rows

    # 统一使用带时区的 UTC 时间，避免 naive/aware 混用
    now = datetime.now(timezone.utc)
    window = float(filters.time_window_days)

    for row in rows:
        created_at = row.get("created_at")
        score: Optional[float] = None
        if isinstance(created_at, datetime):
            # 若 created_at 无时区信息，则按 UTC 解释；否则统一转换为 UTC
            if created_at.tzinfo is None:
                created_at_utc = created_at.replace(tzinfo=timezone.utc)
            else:
                created_at_utc = created_at.astimezone(timezone.utc)

            age_days = (now - created_at_utc).total_seconds() / 86400.0
            # 越新 age_days 越小，score 越高，窗口外为 0。
            score = max(0.0, window - age_days + 1.0)
        row["activity_score"] = score

    return rows
