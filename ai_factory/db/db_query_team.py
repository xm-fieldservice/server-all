from __future__ import annotations

"""DB 查询 team（v0）：基于 entries 表做简单模糊查询。

设计目标（v0）：
- 提供一个高层入口 `run_db_query_team(question, ...)`，供 UI / 三栏页面调用；
- 暂不做复杂意图拆解，只是把自然语言问题作为关键字在 title / content 上做 ILIKE 查询；
- 返回原始 entries 记录列表（按 created_at 倒序），方便上层自行规整或后续接 LLM 总结。

后续可以在此基础上演进：
- 1 号：真正的意图分析 / 拆解 Agent，生成结构化查询条件；
- 2 号：更聪明的 DB 检索（多关键字、字段过滤、时间范围）；
- 3 号：结果规整 / 总结 Agent，输出给前端直接展示的 Markdown。
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from .pgvector_client import connection_scope


@dataclass
class DbQueryResultItem:
    entry_id: str
    title: str
    summary_ai: Optional[str]
    content: str
    project_code: Optional[str]
    user_id: Optional[str]
    created_at: datetime


@dataclass
class DbQueryResult:
    question: str
    total_hits: int
    items: List[DbQueryResultItem]


def _parse_since(since: Optional[str]) -> Optional[datetime]:
    if not since:
        return None
    s = since.strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise ValueError(f"无法解析 since 参数: {since!r}，请使用 'YYYY-MM-DD HH:MM[:SS]' 格式")


def _build_like_pattern(keyword: str) -> str:
    """为 ILIKE 构造简单模式：在前后加 %。

    目前不做转义与分词，适合作为 v0 简单模糊查询。
    """

    kw = keyword.strip()
    if not kw:
        return "%"
    return f"%{kw}%"


def run_db_query_team(
    question: str,
    *,
    limit: int = 20,
    since: Optional[str] = None,
) -> DbQueryResult:
    """在 entries 表上进行简单模糊查询，返回匹配记录。

    参数说明：
    - question: 自然语言问题，目前直接作为模糊查询关键字使用；
    - limit: 返回记录上限；
    - since: 只查询该时间点之后的记录，字符串格式 'YYYY-MM-DD HH:MM[:SS]'；

    返回：DbQueryResult，其中 items 为按 created_at 倒序的匹配列表。
    """

    q = (question or "").strip()
    if not q:
        raise ValueError("question 不能为空")

    since_dt = _parse_since(since)
    pattern = _build_like_pattern(q)

    conditions: List[str] = []
    params: List[Any] = []

    # 在 title / input_content 上做简单模糊匹配
    conditions.append("(title ILIKE %s OR input_content ILIKE %s)")
    params.extend([pattern, pattern])

    if since_dt is not None:
        conditions.append("created_at >= %s")
        params.append(since_dt)

    where_sql = "WHERE " + " AND ".join(conditions)

    sql = f"""
        SELECT
            entry_id,
            title,
            summary_ai,
            input_content AS content,
            project_code,
            user_id,
            created_at
        FROM entries
        {where_sql}
        ORDER BY created_at DESC
        LIMIT %s;
    """

    params_with_limit: List[Any] = [*params, limit]

    items: List[DbQueryResultItem] = []
    total_hits = 0

    with connection_scope() as conn:
        with conn.cursor() as cur:
            # 查询匹配总数
            count_sql = f"SELECT COUNT(*) FROM entries {where_sql};"
            cur.execute(count_sql, params)
            row = cur.fetchone()
            total_hits = int(row[0]) if row else 0

            # 查询实际返回的记录
            cur.execute(sql, params_with_limit)
            rows = cur.fetchall()

    for (
        entry_id,
        title,
        summary_ai,
        content,
        project_code,
        user_id,
        created_at,
    ) in rows:
        items.append(
            DbQueryResultItem(
                entry_id=str(entry_id),
                title=str(title or ""),
                summary_ai=str(summary_ai) if summary_ai is not None else None,
                content=str(content or ""),
                project_code=str(project_code) if project_code is not None else None,
                user_id=str(user_id) if user_id is not None else None,
                created_at=created_at,
            )
        )

    return DbQueryResult(question=question, total_hits=total_hits, items=items)
