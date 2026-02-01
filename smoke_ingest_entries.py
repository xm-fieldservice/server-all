#!/usr/bin/env python3
from __future__ import annotations

import sys
import json
from datetime import datetime
from typing import Any, Dict

from dotenv import load_dotenv
load_dotenv('/home/ecs-assist-user/.env')

from ai_factory.integrations.entries_ingest import entries_ingest
from ai_factory.db.pgvector_client import connection_scope
import ai_factory.db.pgvector_client as pgc


def main() -> int:
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    # 简要打印数据库连接目标，便于排错
    import os
    print("[smoke] PGHOST=", os.getenv("PGHOST"), "PGPORT=", os.getenv("PGPORT"), "PGDATABASE=", os.getenv("PGDATABASE"))
    print("[smoke] AI_PG_HOST=", os.getenv("AI_PG_HOST"), "AI_PG_PORT=", os.getenv("AI_PG_PORT"), "AI_PG_DB=", os.getenv("AI_PG_DB"))
    try:
        dsn = pgc._get_dsn()
        print("[smoke] DSN=", dsn)
        with pgc.connection_scope() as _conn:
            with _conn.cursor() as _cur:
                _cur.execute("SELECT 1")
                print("[smoke] DB connectivity OK")
    except Exception as conn_err:
        print("[smoke] DB connectivity failed:", repr(conn_err))
        return 2

    payload: Dict[str, Any] = {
        "raw_text": f"[SMOKE] {now}",
        "project_code": "smoke_test",
        "user_id": "server_smoke",
        "extra_context": {
            "source_channel": "server_smoke",
            "tags_snapshot": {
                "execution": ["测试"],
                "department": ["server"],
            },
        },
        # 可选：如需树形，可补 parent_entry_id/space_type
        # "parent_entry_id": "ent_xxx",
        # "space_type": "note",
    }

    print("[smoke] calling entries_ingest with payload keys:", list(payload.keys()))
    try:
        result = entries_ingest(payload)
    except Exception as e:
        print("[smoke] entries_ingest failed:", repr(e))
        return 2

    print("[smoke] entries_ingest returned:")
    print(json.dumps(result, ensure_ascii=False, indent=2))

    entries = (result or {}).get("entries") or []
    if not entries:
        print("[smoke] no entries in result")
        return 3

    entry_id = entries[0].get("entry_id")
    if not entry_id:
        print("[smoke] entry_id missing in result")
        return 4

    # Verify round-trip in DB
    with connection_scope() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT entry_id, title, input_content,
                       to_char(created_at AT TIME ZONE 'Asia/Shanghai', 'YYYY-MM-DD HH24:MI:SS')
                FROM entries
                WHERE entry_id = %s
                """,
                (entry_id,),
            )
            row = cur.fetchone()
            if not row:
                print(f"[smoke] entry_id {entry_id} not found in DB")
                return 5
            print("[smoke] fetched from DB:")
            eid, title, content, created_at = row
            preview = (content or "")[:120].replace("\n", " ")
            print(f"  entry_id: {eid}")
            print(f"  title   : {title}")
            print(f"  created : {created_at}")
            print(f"  content : {preview}...")

    print("[smoke] SUCCESS: server-side entries_ingest pipeline writes to entries OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
