from __future__ import annotations

"""从《规整工作记录.md》批量入库到 entries（通过 entries_ingest 入库 agent）。

假设《规整工作记录.md》由 export_clean_records_md.py 生成，结构为：

    <!-- 记录 #1 开始 -->
    ...若干行正文...

    <!-- 记录 #2 开始 -->
    ...

本脚本：
- 按上述标记切分出每条记录；
- 对每条记录构造 payload：
  - raw_text = 该记录完整文本；
  - note_datetime = 若块内存在 "## 📝 笔记 - ..." 则提取时间；
  - extra_context: source/md_file/record_index；
- 调用 ai_factory.integrations.entries_ingest.entries_ingest(payload)，
  使用已存在的入库 agent 规整（title/summary）并写入 entries 表；
- 打印每条写入结果的 entry_id 和 title。
"""

import re
from pathlib import Path
from typing import Any, Dict, List

from ai_factory.integrations.entries_ingest import entries_ingest

ROOT = Path(__file__).resolve().parent
SOURCE_MD = ROOT / "规整工作记录.md"


def _parse_blocks(text: str) -> List[str]:
    """按 <!-- 记录 #n 开始 --> 标记切分记录块，返回每条记录的纯文本。"""

    lines = text.splitlines(keepends=True)
    blocks: List[List[str]] = []

    current: List[str] | None = None
    marker_pat = re.compile(r"<!--\s*记录\s*#(\d+)\s*开始\s*-->")

    for line in lines:
        if marker_pat.search(line):
            # 遇到新记录起点
            if current is not None and current:
                blocks.append(current)
            current = []
            continue
        if current is not None:
            current.append(line)

    if current is not None and current:
        blocks.append(current)

    return ["".join(bl).strip("\n") + "\n" for bl in blocks]


def _extract_note_datetime(block_text: str) -> str:
    """从块内提取 note_datetime（如果存在）。"""

    header_pat = re.compile(r"^##\s*📝\s*笔记\s*-\s*(.+)$")
    for line in block_text.splitlines():
        m = header_pat.match(line.strip())
        if m:
            return m.group(1).strip()
    return ""


def main() -> None:
    if not SOURCE_MD.exists():
        print(f"源文件不存在: {SOURCE_MD}")
        return

    text = SOURCE_MD.read_text(encoding="utf-8")
    blocks = _parse_blocks(text)

    if not blocks:
        print("未在《规整工作记录.md》中找到任何记录块，终止。")
        return

    print(f"准备入库 {len(blocks)} 条正式工作记录。")

    for idx, block_text in enumerate(blocks, start=1):
        note_dt = _extract_note_datetime(block_text)

        payload: Dict[str, Any] = {
            "raw_text": block_text,
            "project_code": None,
            "user_id": None,
            "note_datetime": note_dt,
            "extra_context": {
                "source": "ai_factory_clean_md_import",
                "md_file": str(SOURCE_MD),
                "record_index": idx,
            },
        }

        print(f"\n=== 第 {idx} 条 ===")
        print(f"note_datetime: {note_dt}")

        try:
            result = entries_ingest(payload)
        except Exception as e:  # noqa: BLE001
            print(f"[ERROR] entries_ingest 失败: {e}")
            continue

        entries = (result or {}).get("entries") or []
        if not entries:
            print("[WARN] entries_ingest 调用成功但返回空 entries。")
            continue

        first = entries[0] or {}
        print(f"[OK] 写入成功: entry_id={first.get('entry_id')}, title={first.get('title')}")

    print("\n批量入库脚本执行完毕。")


if __name__ == "__main__":
    main()
