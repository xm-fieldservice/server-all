"""Repository helpers for the `beibei_ticket_*` tables.

v0 目标：
- 先打通 beibei 列表页数据写入主表 `beibei_ticket_items` 的最小链路；
- 复用现有的 pgvector_client / connection_scope 封装，不在业务层直接操作 psycopg2；
- 目前只提供主表的批量 upsert，后续如有需要再按子表拆分仓储接口。
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Sequence

from .pgvector_client import connection_scope


TicketItem = Dict[str, Any]


def upsert_ticket_items(tickets: Sequence[TicketItem]) -> int:
    """批量 upsert 到 `beibei_ticket_items` 主表。

    约定：
    - 调用方保证每个 ticket 至少包含 `order_id` 字段；
    - 如存在 `service_id`，将与 `order_id` 一起作为联合唯一键；
    - 允许只传入字段子集（例如仅最小字段集），SQL 会按提供的列进行 upsert。

    返回：
        实际执行中插入/更新的记录条数（等于传入 tickets 的长度）。
    """

    if not tickets:
        return 0

    # 取第一条记录的字段集，假定同一批 tickets 字段集合一致
    columns: List[str] = list(tickets[0].keys())
    if "order_id" not in columns:
        raise ValueError("ticket item must contain `order_id`")

    # service_id 不是必填字段，但如果存在，应包含在列集中
    # 调用方可决定是否提供 `service_id`，数据库侧联合唯一约束会据此生效

    col_sql = ", ".join(columns)
    placeholders_row = "(" + ", ".join(["%s"] * len(columns)) + ")"

    # 组装 values：按 columns 顺序展开每条 ticket
    values: List[Any] = []
    for t in tickets:
        values.extend([t.get(c) for c in columns])

    # 构建 ON CONFLICT 子句：与 AI 工厂约定使用 (order_id, service_id)
    # 为了兼容 service_id 为空的情况，这里直接使用该联合键，具体行为由数据库约束决定。
    update_assignments = ", ".join(
        [f"{c} = EXCLUDED.{c}" for c in columns if c not in {"order_id", "service_id"}]
    )

    sql = f"""
        INSERT INTO beibei_ticket_items ({col_sql})
        VALUES {', '.join([placeholders_row] * len(tickets))}
        ON CONFLICT (order_id, service_id)
        DO UPDATE SET {update_assignments}
    """.strip()

    with connection_scope() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, values)

    return len(tickets)
