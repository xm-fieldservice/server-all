from __future__ import annotations

from ai_factory.db.pgvector_client import connection_scope


def main() -> None:
    sql = "SELECT AVG(LENGTH(COALESCE(summary_ai, ''))) FROM entries;"

    with connection_scope() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            row = cur.fetchone()

    avg_len = row[0] if row is not None else None
    print("AVG summary_ai length:", avg_len)


if __name__ == "__main__":
    main()
