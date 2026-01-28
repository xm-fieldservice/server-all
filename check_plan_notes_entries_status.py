from __future__ import annotations

"""检查《实施计划和记录.md》中每条“📝 笔记”在 entries 表中的入库情况（只读）。

- 源文件固定为: D:\AI\ai-factory\实施计划和记录.md
- 笔记分隔符固定为: "## 📝 笔记 -"（系统自动添加的 header）
- 判定规则: 按每条笔记全文的前 120 字符，与 entries.content 前 120 字完全匹配。

支持参数：
- --since "YYYY-MM-DD HH:MM:SS" 只检查该时间点之后的笔记（按标题中的时间解析）；
- --limit N 最多检查前 N 条（在时间过滤之后）。

本脚本只做只读查询，不进行任何删除或修改。
"""

import argparse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from ai_factory.db.pgvector_client import connection_scope


PLAN_MD_PATH = Path(r"D:\AI\ai-factory\实施计划和记录.md")
HEADER_PREFIX = "## 📝 笔记 -"


@dataclass
class PlanBlock:
    index: int
    note_datetime: str
    dt: Optional[datetime]
    content_head: str


def print_header(title: str) -> None:
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)


def _parse_dt(s: str) -> Optional[datetime]:
    if not s:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def parse_plan_blocks() -> List[PlanBlock]:
    """解析《实施计划和记录.md》，返回 PlanBlock 列表。"""

    if not PLAN_MD_PATH.exists():
        raise FileNotFoundError(f"找不到实施计划文件: {PLAN_MD_PATH}")

    text = PLAN_MD_PATH.read_text(encoding="utf-8")
    lines = text.splitlines()

    blocks_raw: List[List[str]] = []
    current: List[str] | None = None

    for line in lines:
        if line.startswith(HEADER_PREFIX):
            # 遇到新的笔记头，先收尾上一个块
            if current is not None:
                blocks_raw.append(current)
            current = [line]
        else:
            if current is not None:
                current.append(line)

    if current is not None:
        blocks_raw.append(current)

    blocks: List[PlanBlock] = []
    for i, block_lines in enumerate(blocks_raw, start=1):
        if not block_lines:
            continue
        header_line = block_lines[0]
        note_dt_str = header_line[len(HEADER_PREFIX) :].strip()
        dt = _parse_dt(note_dt_str)

        full_text = "\n".join(block_lines).strip()
        if full_text:
            full_text = full_text + "\n"
        content_head = full_text[:120]

        blocks.append(
            PlanBlock(
                index=i,
                note_datetime=note_dt_str,
                dt=dt,
                content_head=content_head,
            )
        )

    return blocks


def query_entries_by_content_head(content_head: str) -> List[Tuple[str, str]]:
    """在 entries 表中查找 content 前缀等于给定 head 的记录。

    返回 [(entry_id, title)] 列表。
    """

    sql = """
        SELECT entry_id, COALESCE(title, '') AS title
        FROM entries
        WHERE left(input_content::text, 120) = %s
        ORDER BY created_at ASC, entry_id ASC;
    """

    with connection_scope() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (content_head,))
            rows = cur.fetchall()

    return [(r[0], r[1]) for r in rows]


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "检查《实施计划和记录.md》中每条“📝 笔记”在 entries 表中的入库情况（只读），"
            "header 固定为 '## 📝 笔记 -'。"
        )
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
        help="最多检查前 N 条记录（在时间过滤之后），默认检查全部",
    )

    args = parser.parse_args()

    print_header("解析实施计划和记录.md 文件")
    blocks = parse_plan_blocks()
    print(f"共解析出工作笔记 {len(blocks)} 条。")

    # 时间过滤
    if args.since:
        since_dt = _parse_dt(args.since)
        if since_dt is None:
            raise ValueError(
                f"无法解析 --since 参数: {args.since!r}，请使用 'YYYY-MM-DD HH:MM:SS' 格式"
            )
        blocks = [b for b in blocks if b.dt is not None and b.dt > since_dt]
        print(f"按 since 过滤后剩余笔记数: {len(blocks)}")

    # limit 过滤
    if args.limit is not None and args.limit > 0:
        blocks = blocks[: args.limit]

    print_header("逐条检查在 entries 表中的入库情况")

    success_count = 0
    not_found_count = 0

    for b in blocks:
        print("-" * 80)
        print(f"工作笔记 #{b.index}")
        print(f"note_time   : {b.note_datetime}")
        print(f"content_head: {b.content_head!r}")

        rows = query_entries_by_content_head(b.content_head)
        if not rows:
            print("结果: 未找到对应 entries 记录 (MISSING)")
            not_found_count += 1
        else:
            success_count += 1
            print(f"结果: 找到 {len(rows)} 条 entries 记录:")
            for entry_id, title in rows:
                print(f"  entry_id={entry_id}, title={title!r}")

    print_header("汇总")
    print(f"检查范围内工作笔记数: {len(blocks)}")
    print(f"已入库(找到 entries 记录): {success_count}")
    print(f"未入库(未找到匹配记录): {not_found_count}")


if __name__ == "__main__":
    main()
