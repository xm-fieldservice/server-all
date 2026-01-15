from __future__ import annotations

"""简单 CLI：打印最近 N 条 entries，便于本地验证写库结果。

用法示例：

    python print_recent_entries.py          # 默认 10 条
    python print_recent_entries.py 5        # 最近 5 条

依赖：
- ai_factory.db.entries_repo.list_entries_by_time
"""

import sys
from typing import Any, Dict

from ai_factory.db.entries_repo import list_entries_by_time


def _print_entry(i: int, row: Dict[str, Any]) -> None:
    print(f"\n--- 第 {i} 条 ---")
    print("entry_id    :", row.get("entry_id"))
    print("title       :", row.get("title"))
    # 打印完整 summary_ai（仅将换行替换为空格，避免影响终端排版）
    print("summary_ai  :", (row.get("summary_ai") or "").replace("\n", " "))
    print("created_at  :", row.get("created_at"))
    print("project_code:", row.get("project_code"))
    print("user_id     :", row.get("user_id"))


def main() -> None:
    limit = 10
    if len(sys.argv) >= 2:
        try:
            limit = int(sys.argv[1])
        except ValueError:
            print(f"无效的条数参数: {sys.argv[1]!r}, 使用默认 10 条")

    rows = list_entries_by_time(limit=limit)
    if not rows:
        print("entries 表为空或查询不到记录。")
        return

    print(f"最近 {len(rows)} 条 entries：")
    for i, row in enumerate(rows, start=1):
        _print_entry(i, row)


if __name__ == "__main__":
    main()
