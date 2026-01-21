from __future__ import annotations

"""从《实施计划和记录.md》解析笔记记录, 按 SectionID 去重后生成预览文件.

- 以每个 "## 📝 笔记 - ..." 标题为一条记录的起点;
- 将同一 SectionID 的多条记录中, 保留**在原文件中最后出现**的那一条;
- 输出到同目录下的 `实施计划和记录_去重预览.md`;
- 不做任何入库操作, 仅用于人工检查和后续批量入库脚本的输入.
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent
SOURCE_MD = ROOT / "实施计划和记录.md"
DEDUP_MD = ROOT / "实施计划和记录_去重预览.md"


class NoteBlock:
    def __init__(self, key: str, section_id: Optional[str], start: int, end: int, lines: List[str]) -> None:
        self.key = key  # section_id 或 备选 key
        self.section_id = section_id
        self.start = start
        self.end = end
        self.lines = lines


def _parse_blocks(text: str) -> List[NoteBlock]:
    lines = text.splitlines(keepends=True)
    n = len(lines)

    # 找到所有 "## 📝 笔记 -" 的行号
    header_idx: List[int] = []
    header_pat = re.compile(r"^##\s*📝\s*笔记\s*-\s*(.+)$")
    for i, line in enumerate(lines):
        if header_pat.match(line.strip()):
            header_idx.append(i)

    if not header_idx:
        return []

    blocks: List[NoteBlock] = []

    for idx, h in enumerate(header_idx):
        start = h  # 从标题行开始
        end = header_idx[idx + 1] if idx + 1 < len(header_idx) else n
        block_lines = lines[start:end]

        header_line = lines[h].strip()
        m = header_pat.match(header_line)
        note_ts = m.group(1).strip() if m else ""

        # 解析 SectionID 和首行正文作为备选 key
        section_id = None
        tags_line = ""
        for bl in reversed(block_lines):
            if "SectionID=" in bl:
                tags_line = bl.strip()
                break
        if tags_line:
            m_sid = re.search(r"SectionID=([^;\s]+)", tags_line)
            if m_sid:
                section_id = m_sid.group(1).strip()

        # 备选: 标题行下第一行非空正文
        title_hint = ""
        for bl in block_lines[1:]:
            s = bl.strip()
            if s and not s.startswith("标签："):
                title_hint = s
                break

        if section_id:
            key = f"sec:{section_id}"
        else:
            key = f"ts:{note_ts}|{title_hint[:50]}"

        blocks.append(NoteBlock(key=key, section_id=section_id, start=start, end=end, lines=block_lines))

    return blocks


def main() -> None:
    if not SOURCE_MD.exists():
        print(f"源文件不存在: {SOURCE_MD}")
        return

    text = SOURCE_MD.read_text(encoding="utf-8")
    blocks = _parse_blocks(text)

    if not blocks:
        print("未在文档中找到任何 '📝 笔记' 记录, 不生成预览文件。")
        return

    # 以 key 为准保留最后一条
    dedup_map: Dict[str, NoteBlock] = {}
    for blk in blocks:
        dedup_map[blk.key] = blk

    # 按在原文中的 start 行号排序, 保持阅读顺序
    dedup_blocks: List[Tuple[int, NoteBlock]] = sorted(
        ((blk.start, blk) for blk in dedup_map.values()), key=lambda x: x[0]
    )

    out_lines: List[str] = []
    out_lines.append("<!-- 该文件由 bulk_dedup_from_plan_md.py 自动生成, 原文: 实施计划和记录.md -->\n")
    out_lines.append("<!-- 去重规则: 以 SectionID 为主键, 对同一 SectionID 仅保留在原文件中最后出现的一条记录。 -->\n\n")

    for _, blk in dedup_blocks:
        out_lines.extend(blk.lines)
        if not blk.lines[-1].endswith("\n"):
            out_lines.append("\n")
        out_lines.append("\n\n")

    DEDUP_MD.write_text("".join(out_lines), encoding="utf-8")
    print(f"去重完成: 共解析 {len(blocks)} 条记录, 去重后保留 {len(dedup_blocks)} 条。")
    print(f"预览文件已写入: {DEDUP_MD}")


if __name__ == "__main__":
    main()
