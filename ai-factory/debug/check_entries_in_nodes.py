from __future__ import annotations

from typing import List

from ai_factory.db.pgvector_client import connection_scope


ENTRY_IDS: List[str] = [
    "ent_b97aaab7",
    "ent_bbc2a5cf",
]


def main() -> None:
    sql = (
        "SELECT entry_id, title, created_at, space_type, parent_entry_id, scene_tags "
        "FROM entries "
        "WHERE entry_id = ANY(%s)"
    )

    with connection_scope() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (ENTRY_IDS,))
            rows = cur.fetchall()
            colnames = [d[0] for d in cur.description]

    print("=== query_entries_as_nodes result ===")
    print(f"input ENTRY_IDS = {ENTRY_IDS}")
    if not rows:
        print("no rows found in entries (nodes base view) for given entry_ids")
        return

    for r in rows:
        record = dict(zip(colnames, r))
        print("--- row ---")
        for k, v in record.items():
            print(f"{k}: {v}")


if __name__ == "__main__":
    main()
