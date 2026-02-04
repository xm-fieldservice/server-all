"""Repository helpers for the `entries` fact table.

v0 目标：
- 提供最小的插入与基础查询接口；
- 所有访问都通过 `pgvector_client.connection_scope`，不在其他模块直接使用 psycopg2；
- 暂不关心复杂过滤与分页，后续按需要扩展。
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional
from datetime import datetime
from pathlib import Path
import traceback

from psycopg2.extras import Json

from .pgvector_client import connection_scope


def insert_entry(entry: Dict[str, Any]) -> str:
    """插入一条 entry 记录，返回 entry_id。

    v0 约定：调用方负责生成 `entry_id`，并保证必需字段完整。
    这里不做复杂校验，只负责写库。
    """

    # 确保 created_at 使用当前时间（如果未传递）
    if 'created_at' not in entry:
        entry = dict(entry)  # 创建副本
        entry['created_at'] = datetime.utcnow()
    elif entry['created_at'] is None:
        entry = dict(entry)  # 创建副本
        entry['created_at'] = datetime.utcnow()

    columns = list(entry.keys())
    values: List[Any] = []
    for c in columns:
        v = entry[c]
        # 对字典类型(如 scene_tags 等 JSON 字段)使用 Json 包装,
        # 同时也处理 jsonb 类型的字段(如 answer_payload)
        if isinstance(v, dict):
            values.append(Json(v))
        # 对于 jsonb 类型，如果不是字典，也使用 Json 包装
        elif c in ("answer_payload", "scene_tags"):
            values.append(Json(v))
        else:
            values.append(v)
    col_sql = ", ".join(columns)
    placeholders = ", ".join(["%s"] * len(columns))
    sql = f"INSERT INTO entries ({col_sql}) VALUES ({placeholders})"

    # 调试日志：打印即将写入的列名，帮助定位是否仍有 content 残留
    try:
        print(
            "[entries_repo.insert_entry] columns=",
            columns,
            "has_content=",
            ("content" in columns),
            "has_input_content=",
            ("input_content" in columns),
        )
        # 额外写入文件，便于跨进程排查（含调用栈摘要）
        try:
            this_file = Path(__file__).resolve()
            root = this_file.parents[2]
            logs_dir = root / "logs"
            logs_dir.mkdir(parents=True, exist_ok=True)
            log_path = logs_dir / "entries_insert_debug.log"
            stack = " | ".join(
                f"{f.filename}:{f.lineno}:{f.name}" for f in traceback.extract_stack(limit=10)
            )
            ts = datetime.utcnow().isoformat(timespec="seconds") + "Z"
            with log_path.open("a", encoding="utf-8") as f:
                f.write(
                    f"{ts} columns={columns} has_content={('content' in columns)} has_input_content={('input_content' in columns)}\n"
                )
                f.write(f"  stack: {stack}\n")
        except Exception:
            pass
    except Exception:
        # 调试日志失败不影响主流程
        pass

    with connection_scope() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, values)

    return str(entry.get("entry_id"))


def get_entry(entry_id: str) -> Optional[Dict[str, Any]]:
    """按主键获取单条 entry，找不到则返回 None。"""

    sql = "SELECT * FROM entries WHERE entry_id = %s"
    with connection_scope() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (entry_id,))
            row = cur.fetchone()
            if row is None:
                return None
            description = cur.description if cur.description else []
            colnames = [d[0] for d in description]

    return dict(zip(colnames, row))


def list_entries_by_time(limit: int = 100) -> List[Dict[str, Any]]:
    """按 created_at 倒序获取最近若干条 entries。

    仅用于 v0 调试与简单浏览。
    """

    sql = "SELECT * FROM entries ORDER BY created_at DESC LIMIT %s"
    results: List[Dict[str, Any]] = []

    with connection_scope() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (limit,))
            rows = cur.fetchall()
            description = cur.description if cur.description else []
            colnames = [d[0] for d in description]
            for r in rows:
                results.append(dict(zip(colnames, r)))

    return results


def update_entry_fields(entry_id: str, fields: Dict[str, Any]) -> None:
    """按主键部分更新 entries 的指定字段。

    - 不负责任何业务校验，仅执行 UPDATE；
    - 字段值中如包含 dict（如 scene_tags），会使用 Json 包装以适配 json/jsonb 列。
    """

    entry_id = (entry_id or "").strip()
    if not entry_id:
        return
    if not fields:
        return

    columns = list(fields.keys())
    # 将业务字段 content 映射到物理列 input_content
    mapped_columns = ["input_content" if c == "content" else c for c in columns]
    set_clauses = [f"{c} = %s" for c in mapped_columns]
    values: List[Any] = []
    for c in columns:
        v = fields[c]
        if isinstance(v, dict):
            values.append(Json(v))
        else:
            values.append(v)

    sql = "UPDATE entries SET " + ", ".join(set_clauses) + " WHERE entry_id = %s"
    values.append(entry_id)

    with connection_scope() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, values)
