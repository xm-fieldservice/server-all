from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

import os
import requests

from ai_factory.db.entries_repo import get_entry
from ai_factory.db.pgvector_client import _get_dsn, test_connection


def main() -> None:
    base_url = os.getenv("AI_FACTORY_BASE_URL", "http://127.0.0.1:8001").rstrip("/")
    api_url = base_url + "/api/entries/ingest"

    print("[debug-http-ingest] 使用的 entries_ingest HTTP 接口:")
    print("  ", api_url)

    print("[debug-http-ingest] 使用的 Postgres DSN:")
    print("  ", _get_dsn())

    print("[debug-http-ingest] 测试数据库连接...")
    test_connection()
    print("[debug-http-ingest] 数据库连接 OK")

    now = datetime.utcnow().isoformat(timespec="seconds") + "Z"

    payload: Dict[str, Any] = {
        "raw_text": f"[HTTP_ENTRIES_INGEST_TEST] {now}",
        "user_id": "wecom:http_test_user",
        "note_datetime": now,
        "extra_context": {
            "source_channel": "wecom",
            "source_app": "http_entries_ingest_test",
            "tags_snapshot": {
                "department": ["软件部"],
            },
        },
    }

    print("[debug-http-ingest] 通过 HTTP 调用 /api/entries/ingest 写入一条测试记录...")
    try:
        resp = requests.post(api_url, json=payload, timeout=30)
        print("[debug-http-ingest] HTTP 状态码:", resp.status_code)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print("[debug-http-ingest][ERROR] HTTP 调用失败:", repr(exc))
        return

    try:
        data = resp.json()
    except ValueError as exc:
        print("[debug-http-ingest][ERROR] 响应 JSON 解析失败:", repr(exc))
        print("响应文本前 500 字符:")
        print(resp.text[:500])
        return

    print("[debug-http-ingest] /api/entries/ingest 返回 JSON:")
    print("  ", data)

    entries = data.get("entries") or []
    if not entries or not isinstance(entries, list):
        print("[debug-http-ingest][ERROR] 返回结果中没有 entries 字段或格式不正确。")
        return

    entry_id = str(entries[0].get("entry_id"))
    print(f"[debug-http-ingest] 新写入的 entry_id = {entry_id!r}")

    row = get_entry(entry_id)
    if not row:
        print("[debug-http-ingest][ERROR] 在 entries 表中找不到这条记录，说明写库未成功。")
        return

    print("[debug-http-ingest] 从 DB 读回的记录关键信息:")
    print("  entry_id  =", row.get("entry_id"))
    print("  title     =", row.get("title"))
    print("  content   =", row.get("content"))
    print("  scene_tags=", row.get("scene_tags"))


if __name__ == "__main__":
    main()
