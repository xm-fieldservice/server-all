"""Integration helpers for beibei ticket ingestion.

v0 目标：
- 提供一个在业务侧更好用的 `Ticket` 数据结构；
- 封装从 `List[Ticket]` 到 `beibei_ticket_items` 批量 upsert 的最小入口；
- 具体的 OCR 解析逻辑由上层负责，这里只关心“结构化后的字段 → 写库”。
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from ai_factory.db.beibei_ticket_repo import upsert_ticket_items


@dataclass
class Ticket:
    """代表主表 `beibei_ticket_items` 的一条记录（v0 版本）。

    约定：
    - 仅 `order_id` 为硬必填字段，其余字段按需填充；
    - `extra` 字段会映射到表中的 `extra_json` 列；
    - 时间字段建议使用 timezone-aware 的 `datetime`，由 psycopg2 负责序列化。
    """

    order_id: str

    service_id: Optional[str] = None
    title: Optional[str] = None
    order_type: Optional[str] = None
    status_text: Optional[str] = None
    status_code: Optional[str] = None

    # 时间类
    created_time: Optional[datetime] = None
    accepted_time: Optional[datetime] = None
    expected_time_raw: Optional[str] = None
    expected_time_start: Optional[datetime] = None
    expected_time_end: Optional[datetime] = None

    # 参与人/客户
    service_provider_name: Optional[str] = None
    service_provider_phone_mask: Optional[str] = None
    receiver_name: Optional[str] = None
    customer_name_mask: Optional[str] = None
    customer_phone_mask: Optional[str] = None

    # 状态/备注
    phone_contact_status: Optional[str] = None
    remark_summary: Optional[str] = None

    # 抓取元数据
    page_index: Optional[int] = None
    row_index: Optional[int] = None
    capture_ts: Optional[datetime] = None
    source_image: Optional[str] = None
    ocr_engine: Optional[str] = None
    signature: Optional[str] = None

    # 预留扩展
    category_tags: Optional[Dict[str, Any]] = None
    extra: Optional[Dict[str, Any]] = None


def save_tickets(tickets: Sequence[Ticket]) -> int:
    """将一批 `Ticket` 写入 `beibei_ticket_items` 主表。

    - 内部会调用 `upsert_ticket_items`，使用 (order_id, service_id) 联合唯一键；
    - `Ticket.extra` 会被映射为表中的 `extra_json` 列；
    - 只要表结构兼容，调用方可以只填第一阶段约定的最小字段集。

    返回：成功 upsert 的记录条数。
    """

    if not tickets:
        return 0

    ticket_dicts: List[Dict[str, Any]] = []
    for t in tickets:
        data = asdict(t)
        # 将 dataclass 字段映射到表字段命名
        extra = data.pop("extra", None)
        if extra is not None:
            data["extra_json"] = extra

        category_tags = data.pop("category_tags", None)
        if category_tags is not None:
            data["category_tags"] = category_tags

        # 保证 order_id 存在
        if not data.get("order_id"):
            raise ValueError("Ticket.order_id is required")

        ticket_dicts.append(data)

    return upsert_ticket_items(ticket_dicts)
