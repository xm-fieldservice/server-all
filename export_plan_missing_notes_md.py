from __future__ import annotations

"""从《实施计划和记录.md》导出“未入库”的工作笔记为补齐文档（只读）。

- 源文件固定为: D:\AI\ai-factory\实施计划和记录.md
- 笔记分隔符固定为: "## 📝 笔记 -"（系统自动添加的 header）
- 判定规则: 按每条笔记全文的前 120 字符，与 entries.content 前 120 字完全匹配；
  - 若在 entries 中找不到匹配记录，则视为“未入库”。
- 本脚本会将这些“未入库”的笔记块，原样导出到
  《实施计划和记录_补齐待入库.md》，供批量入库脚本使用。

用法示例（在 ai-factory 根目录）：

  # 只导出 2025-12-14 11:34:56 之后未入库的笔记
  python export_plan_missing_notes_md.py --since "2025-12-14 11:34:56"

  # 导出全部未入库笔记（不按时间过滤）
  python export_plan_missing_notes_md.py

本脚本只读 DB + 写补齐 MD 文件，不写入 entries。
"""

import argparse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from ai_factory.db.pgvector_client import connection_scope


PLAN_MD_PATH = Path(r"D:\AI\ai-factory\实施计划和记录.md")
TARGET_MD_PATH = Path(r"D:\AI\ai-factory\实施计划和记录_补齐待入库.md")
HEADER_PREFIX = "## 📝 笔记 -"


@dataclass
class PlanNote:
    index: int
    note_datetime: str
    dt: Optional[datetime]
    text_block: str
    content_head: str


def _parse_dt(s: str) -> Optional[datetime]:
    if not s:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def parse_plan_notes() -> List[PlanNote]:
    if not PLAN_MD_PATH.exists():
        raise FileNotFoundError(f"找不到实施计划文件: {PLAN_MD_PATH}")

    text = PLAN_MD_PATH.read_text(encoding="utf-8")
    lines = text.splitlines()

    blocks_raw: List[List[str]] = []
    current: List[str] | None = None

    for line in lines:
        if line.startswith(HEADER_PREFIX):
            if current is not None:
                blocks_raw.append(current)
            current = [line]
        else:
            if current is not None:
                current.append(line)

    if current is not None:
        blocks_raw.append(current)

    notes: List[PlanNote] = []
    for i, block_lines in enumerate(blocks_raw, start=1):
        if not block_lines:
            continue
        header_line = block_lines[0]
        note_dt_str = header_line[len(HEADER_PREFIX) :].strip()
        dt = _parse_dt(note_dt_str)

        text_block = "\n".join(block_lines).strip()
        if text_block:
            text_block = text_block + "\n"
        content_head = text_block[:120]

        notes.append(
            PlanNote(
                index=i,
                note_datetime=note_dt_str,
                dt=dt,
                text_block=text_block,
                content_head=content_head,
            )
        )

    return notes


def query_entries_by_content_head(content_head: str):
    sql = """
        SELECT entry_id
        FROM entries
        WHERE left(input_content::text, 120) = %s
        LIMIT 1;
    """

    with connection_scope() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (content_head,))
            row = cur.fetchone()
    return row is not None


def export_missing_notes(since: Optional[str]) -> None:
    notes = parse_plan_notes()
    if not notes:
        print("未在实施计划和记录.md 中解析到任何 '📝 笔记' 记录。")
        return

    since_dt: Optional[datetime] = None
    if since:
        since_dt = _parse_dt(since)
        if since_dt is None:
            raise ValueError(
                f"无法解析 --since 参数: {since!r}，请使用 'YYYY-MM-DD HH:MM:SS' 格式"
            )

    total = len(notes)
    print(f"共解析出工作笔记 {total} 条。")

    # 按时间过滤
    if since_dt is not None:
        notes = [n for n in notes if n.dt is not None and n.dt > since_dt]
        print(f"按 since 过滤后剩余笔记数: {len(notes)}")

    missing_notes: List[PlanNote] = []
    for n in notes:
        exists = query_entries_by_content_head(n.content_head)
        if not exists:
            missing_notes.append(n)

    if not missing_notes:
        print("在选定范围内没有发现未入库的笔记，未生成补齐文档。")
        return

    # 写出补齐文档
    out_lines: List[str] = []
    out_lines.append("<!-- 该文件由 export_plan_missing_notes_md.py 自动生成，用于补齐未入库工作笔记。 -->\n")
    out_lines.append("<!-- 源文件: 实施计划和记录.md，块级单位: '## 📝 笔记 - ...' 自然块。 -->\n\n")

    for idx, n in enumerate(missing_notes, start=1):
        out_lines.append(f"<!-- 补齐记录 #{idx} 开始（原 index={n.index}, note_datetime={n.note_datetime}） -->\n")
        out_lines.append(n.text_block)
        if not n.text_block.endswith("\n"):
            out_lines.append("\n")
        out_lines.append("\n\n")

    TARGET_MD_PATH.write_text("".join(out_lines), encoding="utf-8")

    print(f"时间过滤后笔记数   : {len(notes)}")
    print(f"未入库笔记数       : {len(missing_notes)}")
    print(f"补齐文档已写入     : {TARGET_MD_PATH}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "从《实施计划和记录.md》导出未入库的工作笔记为补齐文档，"
            "供批量入库脚本使用（只读 DB，不写入 entries）。"
        )
    )
    parser.add_argument(
        "--since",
        type=str,
        default=None,
        help="只导出该时间点之后的笔记，格式 'YYYY-MM-DD HH:MM:SS'（可选）",
    )

    args = parser.parse_args()
    export_missing_notes(args.since)


if __name__ == "__main__":  # pragma: no cover
    main()
