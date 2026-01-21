from __future__ import annotations

from pathlib import Path

from ai_factory.integrations.entries_ingest import entries_ingest
from ai_factory.db.entries_repo import list_entries_by_time


def main() -> None:
    root = Path(__file__).resolve().parent
    sample_path = root / "工作记录测试样例.md"

    if not sample_path.exists():
        print(f"样例文件不存在: {sample_path}")
        return

    raw_text = sample_path.read_text(encoding="utf-8")

    payload = {
        "raw_text": raw_text,
        "note_datetime": "2025-12-08T22:50:00+08:00",
        "project_code": "demo_project",
        "user_id": "demo_user",
        "extra_context": {
            "from": "local_manual_test",
        },
    }

    print("[TEST] 调用 entries_ingest(payload)...")
    result = entries_ingest(payload)
    print("[TEST] entries_ingest 返回:")
    print(result)

    print("\n[TEST] 查询最近 5 条 entries:")
    recent = list_entries_by_time(limit=5)
    if not recent:
        print("[TEST] entries 表目前为空或查询不到记录")
        return

    for i, row in enumerate(recent, start=1):
        print(f"\n--- 最近第 {i} 条 ---")
        print("entry_id    :", row.get("entry_id"))
        print("title       :", row.get("title"))
        print("summary_ai  :", row.get("summary_ai"))
        print("created_at  :", row.get("created_at"))
        print("project_code:", row.get("project_code"))
        print("user_id     :", row.get("user_id"))


if __name__ == "__main__":
    main()
