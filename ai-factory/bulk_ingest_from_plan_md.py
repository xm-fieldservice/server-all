from __future__ import annotations

"""从《实施计划和记录_去重预览.md》批量入库到 entries。

- 以每个 "## 📝 笔记 - ..." 为一条记录；
- raw_text = 该记录完整文本；
- note_datetime = 标题中的时间字符串；
- extra_context 包含: source/md_file/section_id/tags_raw；
- 调用 ai_factory.integrations.entries_ingest.entries_ingest，
  确保与三栏 NOTE 模式相同的规整+写库流程；
- 可通过命令行参数限制入库条数(默认 10 条)。
"""

import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from ai_factory.integrations.entries_ingest import entries_ingest

ROOT = Path(__file__).resolve().parent
SOURCE_MD = ROOT / "写库失败笔记保存文档.md"


class NoteRecord:
    def __init__(
        self,
        *,
        note_datetime: str,
        section_id: Optional[str],
        tags_raw: str,
        text_block: str,
    ) -> None:
        self.note_datetime = note_datetime
        self.section_id = section_id
        self.tags_raw = tags_raw
        self.text_block = text_block


def _parse_records(text: str) -> List[NoteRecord]:
    lines = text.splitlines(keepends=True)
    n = len(lines)

    header_pat = re.compile(r"^##\s*📝\s*笔记\s*-\s*(.+)$")
    header_idx: List[int] = []
    for i, line in enumerate(lines):
        if header_pat.match(line.strip()):
            header_idx.append(i)

    records: List[NoteRecord] = []
    if not header_idx:
        return records

    for idx, h in enumerate(header_idx):
        start = h
        end = header_idx[idx + 1] if idx + 1 < len(header_idx) else n
        block_lines = lines[start:end]

        header_line = lines[h].strip()
        m = header_pat.match(header_line)
        note_dt = m.group(1).strip() if m else ""

        # 收集标签行 & SectionID
        tags_lines: List[str] = []
        section_id: Optional[str] = None
        for bl in block_lines:
            if "标签：" in bl:
                tags_lines.append(bl.strip())
            if "SectionID=" in bl and section_id is None:
                m_sid = re.search(r"SectionID=([^;\s]+)", bl)
                if m_sid:
                    section_id = m_sid.group(1).strip()

        tags_raw = "\\n".join(tags_lines) if tags_lines else ""
        text_block = "".join(block_lines).strip("\n") + "\n"

        records.append(
            NoteRecord(
                note_datetime=note_dt,
                section_id=section_id,
                tags_raw=tags_raw,
                text_block=text_block,
            )
        )

    return records


def main() -> None:
    if not SOURCE_MD.exists():
        print(f"源文件不存在: {SOURCE_MD}")
        return

    limit = 10
    if len(sys.argv) >= 2:
        try:
            limit = int(sys.argv[1])
        except ValueError:
            print(f"无效的条数参数 {sys.argv[1]!r}, 将使用默认 10 条。")

    text = SOURCE_MD.read_text(encoding="utf-8")
    records = _parse_records(text)

    if not records:
        print("未在去重预览文件中找到任何 '📝 笔记' 记录，终止。")
        return

    to_insert = records[:limit]
    print(f"准备入库 {len(to_insert)} 条记录 (总计 {len(records)} 条)。")

    for idx, rec in enumerate(to_insert, start=1):
        payload: Dict[str, Any] = {
            "raw_text": rec.text_block,
            "project_code": None,
            "user_id": None,
            "note_datetime": rec.note_datetime,
            "extra_context": {
                "source": "ai_factory_md_import",
                "md_file": str(SOURCE_MD),
                "section_id": rec.section_id,
                "tags_raw": rec.tags_raw,
            },
        }

        print(f"\n=== 第 {idx} 条 ===")
        print(f"note_datetime: {rec.note_datetime}")
        print(f"section_id  : {rec.section_id}")

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
