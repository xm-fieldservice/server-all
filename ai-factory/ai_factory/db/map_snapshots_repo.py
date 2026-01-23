"""Repository helpers for the `map_snapshots` interpretation-layer table.

v0 目标：
- 提供插入与按 map_id/时间获取快照的最小接口；
- 结构字段与《表结构设计》中的草案保持基本对齐；
- 复杂筛选与版本管理后续再扩展。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .pgvector_client import connection_scope


def insert_snapshot(snapshot: Dict[str, Any]) -> str:
    """插入一条 map_snapshots 记录，返回 map_id。

    v0 约定：调用方负责生成 `map_id` 与必需字段。
    """

    columns = list(snapshot.keys())
    values = [snapshot[c] for c in columns]
    col_sql = ", ".join(columns)
    placeholders = ", ".join(["%s"] * len(columns))
    sql = f"INSERT INTO map_snapshots ({col_sql}) VALUES ({placeholders})"

    with connection_scope() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, values)

    return str(snapshot.get("map_id"))


def get_snapshot(map_id: str) -> Optional[Dict[str, Any]]:
    """按主键获取单条快照。"""

    sql = "SELECT * FROM map_snapshots WHERE map_id = %s"

    with connection_scope() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (map_id,))
            row = cur.fetchone()
            if row is None:
                return None
            colnames = [d[0] for d in cur.description]

    return dict(zip(colnames, row))


def list_recent_snapshots(limit: int = 50) -> List[Dict[str, Any]]:
    """按 created_at 倒序获取最近若干条快照。"""

    sql = "SELECT * FROM map_snapshots ORDER BY created_at DESC LIMIT %s"
    results: List[Dict[str, Any]] = []

    with connection_scope() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (limit,))
            rows = cur.fetchall()
            colnames = [d[0] for d in cur.description]
            for r in rows:
                results.append(dict(zip(colnames, r)))

    return results
