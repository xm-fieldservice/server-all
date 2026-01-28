from __future__ import annotations

"""通用：检查某个 MD 文件中的“笔记块”在 entries 表中的入库情况（只读）。

用法示例（在 ai-factory 根目录）：

  # 1. 检查实施计划和记录.md 中的 "## 📝 笔记 - ..."，从给定时间点之后开始：
  python check_md_notes_entries_status.py \
      --md "D:/AI/ai-factory/实施计划和记录.md" \
      --header "## 📝 笔记 -" \
      --since "2025-12-14 11:34:56"

  # 2. 检查缺陷笔记汇总（等价于旧脚本的行为）：
  python check_md_notes_entries_status.py \
      --md "D:/AI/数据库+向量库_缺陷笔记汇总.md" \
      --header "## 📝 笔记 -"

规则：
- 以指定 header 前缀的行（默认 "## 📝 笔记 -"）作为每条记录的起点；
- 每条记录的 "全文前 120 字符" 作为 content_head；
- 在 entries 表中查：left(content::text, 120) = content_head；
- 查到 >= 1 条 => 视为“已入库”；否则为“未入库”；
- 可选通过 --since 过滤：只保留 note_datetime > since 的记录
  （note_datetime 默认从 header 行中去掉前缀后的部分）。

本脚本只读：不会写入或修改任何 DB 内容。
"""

import argparse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ai_factory.db.pgvector_client import connection_scope


@dataclass
class NoteBlock:
    index: int
    header_line: str
    note_datetime: str
    content_head: str


def parse_md_blocks(md_path: Path, header_prefix: str) -> List[Tuple[NoteBlock, str]]:
    """解析 MD 文件，按 header_prefix 切块，返回 [(block_meta, full_text)] 列表。"""

    if not md_path.exists():
        raise FileNotFoundError(f"找不到 MD 文件: {md_path}")

    text = md_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    blocks: List[List[str]] = []
    current: Optional[List[str]] = None

    for line in lines:
        if line.startswith(header_prefix):
            if current is not None:
                blocks.append(current)
            current = [line]
        else:
            if current is not None:
                current.append(line)

    if current is not None:
        blocks.append(current)

    results: List[Tuple[NoteBlock, str]] = []

    for i, block_lines in enumerate(blocks, start=1):
        if not block_lines:
            continue
        header_line = block_lines[0]
        # note_datetime 约定为 header_line 去掉前缀后的部分
        note_dt = header_line[len(header_prefix) :].strip() if header_line.startswith(header_prefix) else ""

        full_text = "\n".join(block_lines).strip()
        if full_text:
            full_text = full_text + "\n"
        content_head = full_text[:120]

        meta = NoteBlock(
            index=i,
            header_line=header_line,
            note_datetime=note_dt,
            content_head=content_head,
        )
        results.append((meta, full_text))

    return results


def _parse_since(since_str: Optional[str]) -> Optional[datetime]:
    if not since_str:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(since_str, fmt)
        except ValueError:
            continue
    raise ValueError(f"无法解析 --since 参数: {since_str!r}，请使用 'YYYY-MM-DD HH:MM:SS' 格式")


def _parse_note_dt(note_dt: str) -> Optional[datetime]:
    if not note_dt:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(note_dt, fmt)
        except ValueError:
            continue
    return None


def query_entries_by_content_head(content_head: str) -> List[Dict[str, Any]]:
    sql = """
        SELECT entry_id,
               COALESCE(title, '') AS title,
               project_code,
               user_id,
               created_at,
               left(input_content::text, 120) AS content_head
        FROM entries
        WHERE left(input_content::text, 120) = %s
        ORDER BY created_at ASC, entry_id ASC;
    """

    with connection_scope() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (content_head,))
            rows = cur.fetchall()
            colnames = [d[0] for d in cur.description]

    return [dict(zip(colnames, r)) for r in rows]


def check_md_notes_entries_status(md_path: str, header_prefix: str, since: Optional[str], limit: Optional[int]) -> Tuple[List[NoteBlock], List[Tuple[NoteBlock, List[Dict[str, Any]]]]]:
    path = Path(md_path)
    blocks = parse_md_blocks(path, header_prefix)
    if not blocks:
        print(f"未在 {md_path} 中找到任何以 {header_prefix!r} 开头的记录。")
        return [], []

    since_dt = _parse_since(since)

    filtered: List[Tuple[NoteBlock, str]] = []
    for meta, full_text in blocks:
        if since_dt is not None:
            dt = _parse_note_dt(meta.note_datetime)
            if dt is None or dt <= since_dt:
                continue
        filtered.append((meta, full_text))

    if limit is not None and limit > 0:
        filtered = filtered[:limit]

    results: List[Tuple[NoteBlock, List[Dict[str, Any]]]] = []

    for meta, full_text in filtered:
        matched = query_entries_by_content_head(meta.content_head)
        results.append((meta, matched))

    return [m for m, _ in results], results


def print_report(md_path: str, header_prefix: str, blocks: List[NoteBlock], results: List[Tuple[NoteBlock, List[Dict[str, Any]]]]) -> None:
    total = len(blocks)
    found = sum(1 for _, matched in results if matched)
    missing = total - found

    print("\n=== MD ↔ entries 只读对齐检查 ===")
    print(f"MD 文件       : {md_path}")
    print(f"记录头部前缀  : {header_prefix!r}")
    print(f"检查记录数    : {total}")
    print(f"已入库条数    : {found}")
    print(f"未入库条数    : {missing}")

    if missing <= 0:
        print("\n✅ 所有选定范围内的 MD 记录在 entries 表中均已找到对应记录。")
        return

    print("\n⚠ 以下为未在 entries 中找到匹配的记录（最多展示前 50 条）：")
    shown = 0
    for meta, matched in results:
        if matched:
            continue
        print("-" * 80)
        print(f"index      : {meta.index}")
        print(f"header     : {meta.header_line!r}")
        print(f"note_time  : {meta.note_datetime}")
        head_preview = meta.content_head.replace("\n", " ")
        print(f"content_head: {head_preview!r}")
        shown += 1
        if shown >= 50:
            break


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "通用：检查指定 MD 文件中以某个前缀开头的笔记块，在 entries 表中的入库情况（只读）。"
        )
    )
    parser.add_argument(
        "--md",
        type=str,
        required=True,
        help="源 MD 文件的路径，例如 D:/AI/ai-factory/实施计划和记录.md",
    )
    parser.add_argument(
        "--header",
        type=str,
        default="## 📝 笔记 -",
        help="记录头部前缀，默认 '## 📝 笔记 -'",
    )
    parser.add_argument(
        "--since",
        type=str,
        default=None,
        help="只检查该时间点之后的记录，格式 'YYYY-MM-DD HH:MM:SS'（可选）",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="最多检查前 N 条记录（在时间过滤后），默认检查全部",
    )

    args = parser.parse_args()

    blocks, results = check_md_notes_entries_status(
        md_path=args.md,
        header_prefix=args.header,
        since=args.since,
        limit=args.limit,
    )
    print_report(args.md, args.header, blocks, results)


if __name__ == "__main__":  # pragma: no cover
    main()
