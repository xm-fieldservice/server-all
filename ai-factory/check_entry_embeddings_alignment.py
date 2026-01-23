from __future__ import annotations

"""检查 entries 与 entry_embeddings 是否对齐的小脚本。

用法（在 ai-factory 根目录）：

    python check_entry_embeddings_alignment.py

功能：
- 统计 entries 总数；
- 统计 entry_embeddings 总数；
- 统计还有多少 entries 尚未向量化；
- 列出前若干条未向量化的 entry_id 及关键信息。
"""

from typing import Any, Dict, List

from ai_factory.db.pgvector_client import connection_scope


def _fetch_counts() -> Dict[str, int]:
    sql = {
        "entries_total": "SELECT COUNT(*) FROM entries;",
        "embeddings_total": "SELECT COUNT(*) FROM entry_embeddings;",
        "missing_total": """
            SELECT COUNT(*)
            FROM entries e
            LEFT JOIN entry_embeddings emb
              ON e.entry_id = emb.entry_id
            WHERE emb.entry_id IS NULL;
        """,
    }

    results: Dict[str, int] = {}
    with connection_scope() as conn:
        with conn.cursor() as cur:
            for key, q in sql.items():
                cur.execute(q)
                (cnt,) = cur.fetchone()
                results[key] = int(cnt)
    return results


def _fetch_missing_samples(limit: int = 20) -> List[Dict[str, Any]]:
    sql = """
        SELECT e.entry_id,
               e.title,
               e.project_code,
               e.user_id,
               e.created_at
        FROM entries e
        LEFT JOIN entry_embeddings emb
          ON e.entry_id = emb.entry_id
        WHERE emb.entry_id IS NULL
        ORDER BY e.created_at ASC
        LIMIT %s;
    """

    with connection_scope() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (limit,))
            rows = cur.fetchall()
            colnames = [d[0] for d in cur.description]

    return [dict(zip(colnames, row)) for row in rows]


def main() -> None:
    counts = _fetch_counts()
    print("entries 总数      :", counts.get("entries_total"))
    print("entry_embeddings:", counts.get("embeddings_total"))
    print("未向量化条数    :", counts.get("missing_total"))

    missing_total = counts.get("missing_total", 0) or 0
    if missing_total <= 0:
        print("\n✅ 所有 entries 均已在 entry_embeddings 中找到对应向量。")
        return

    print("\n⚠️ 仍有未向量化的 entries，示例：")
    samples = _fetch_missing_samples(limit=20)
    for idx, e in enumerate(samples, start=1):
        print(
            f"[{idx}] entry_id={e.get('entry_id')} title={e.get('title')!r} "
            f"project_code={e.get('project_code')} user_id={e.get('user_id')} "
            f"created_at={e.get('created_at')}"
        )


if __name__ == "__main__":
    main()
