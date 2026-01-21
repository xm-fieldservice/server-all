from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from ai_factory.integrations.entries_ingest import entries_ingest
from ai_factory.db.entries_repo import get_entry
from ai_factory.db.pgvector_client import _get_dsn, test_connection


def main() -> None:
    print("[debug-wecom-ingest] 使用的 Postgres DSN:")
    print("  ", _get_dsn())

    print("[debug-wecom-ingest] 测试数据库连接...")
    test_connection()
    print("[debug-wecom-ingest] 数据库连接 OK")

    now = datetime.utcnow().isoformat(timespec="seconds") + "Z"

    payload: Dict[str, Any] = {
        "raw_text": f"[WECHAT_DEBUG_LOCAL] {now}",
        "user_id": "wecom:local_debug_user",
        "note_datetime": now,
        "extra_context": {
            "source_channel": "wecom",
            "source_app": "wecom_local_debug_script",
            "tags_snapshot": {
                # 随便指定一个部门名，便于在 scene_tags.department 中辨识
                "department": ["软件部"],
            },
        },
    }

    print("[debug-wecom-ingest] 调用 entries_ingest() 写入一条模拟企业微信笔记...")
    result = entries_ingest(payload)
    print("[debug-wecom-ingest] entries_ingest 返回:")
    print("  ", result)

    entries = result.get("entries") or []
    if not entries:
        print("[debug-wecom-ingest][ERROR] 返回结果中没有 entries 字段，无法继续调试。")
        return

    entry_id = str(entries[0].get("entry_id"))
    print(f"[debug-wecom-ingest] 新写入的 entry_id = {entry_id!r}")

    row = get_entry(entry_id)
    if not row:
        print("[debug-wecom-ingest][ERROR] 在 entries 表中找不到这条记录，说明写库未成功。")
        return

    print("[debug-wecom-ingest] 从 DB 读回的记录关键信息:")
    print("  entry_id =", row.get("entry_id"))
    print("  title    =", row.get("title"))
    print("  content  =", row.get("content"))
    print("  scene_tags =", row.get("scene_tags"))


if __name__ == "__main__":
    main()
