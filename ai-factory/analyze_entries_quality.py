from __future__ import annotations

"""分析 rag_db.entries 表中的重复记录和不规整记录。

本脚本只做只读分析，不执行任何删除操作。

- 重复判定：按 (note_datetime, content 前 120 字) 分组，统计 count>1 的 group；
- 不规整判定：title 为空/全空白，或 summary_ai 为空/长度过短。
"""

from typing import Any

from ai_factory.db.pgvector_client import connection_scope


def print_header(title: str) -> None:
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)


def analyze_total() -> None:
    with connection_scope() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM entries;")
            total = cur.fetchone()[0]
    print_header("ENTRIES TOTAL")
    print(f"TOTAL_ENTRIES = {total}")


def analyze_duplicates(limit_groups: int = 50, limit_entries: int = 200) -> None:
    print_header("DUPLICATE GROUPS (by content_head)")

    with connection_scope() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT left(content::text, 120) AS content_head,
                       count(*) AS cnt
                FROM entries
                GROUP BY content_head
                HAVING count(*) > 1
                ORDER BY cnt DESC
                LIMIT %s;
                """,
                (limit_groups,),
            )
            rows = cur.fetchall()

    if not rows:
        print("没有检测到重复 group。")
    else:
        for head, cnt in rows:
            print(f"cnt={cnt}, head={head!r}")

    print_header("DUPLICATE ENTRIES DETAIL")

    with connection_scope() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH dup AS (
                    SELECT left(content::text, 120) AS content_head
                    FROM entries
                    GROUP BY content_head
                    HAVING count(*) > 1
                )
                SELECT e.entry_id,
                       e.title,
                       e.created_at,
                       left(e.content::text, 120) AS content_head
                FROM entries e
                JOIN dup d
                  ON left(e.content::text, 120) = d.content_head
                ORDER BY e.created_at, e.entry_id
                LIMIT %s;
                """,
                (limit_entries,),
            )
            rows = cur.fetchall()

    if not rows:
        print("没有可展示的重复记录明细。")
    else:
        for entry_id, title, created_at, head in rows:
            print(
                "entry_id={eid}, created_at={ca}, "
                "title={t!r}, head={h!r}".format(
                    eid=entry_id,
                    ca=created_at,
                    t=title,
                    h=head,
                )
            )


def analyze_incomplete(limit_entries: int = 200) -> None:
    print_header("INCOMPLETE ENTRIES (title empty or summary_ai very short)")

    with connection_scope() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT entry_id,
                       title,
                       summary_ai,
                       created_at,
                       left(content::text, 80) AS content_head
                FROM entries
                WHERE (title IS NULL OR trim(title) = '')
                   OR (summary_ai IS NULL OR length(trim(summary_ai)) < 20)
                ORDER BY created_at
                LIMIT %s;
                """,
                (limit_entries,),
            )
            rows = cur.fetchall()

    if not rows:
        print("没有检测到不规整记录（按当前规则）。")
    else:
        for entry_id, title, summary_ai, created_at, head in rows:
            s_preview = (summary_ai or "")[:60].replace("\n", " ")
            print(
                "entry_id={eid}, created_at={ca}, "
                "title={t!r}, summary_preview={sp!r}, head={h!r}".format(
                    eid=entry_id,
                    ca=created_at,
                    t=title,
                    sp=s_preview,
                    h=head,
                )
            )


def main() -> None:
    analyze_total()
    analyze_duplicates()
    analyze_incomplete()


if __name__ == "__main__":
    main()
