from __future__ import annotations

"""从《实施计划和记录.md》补齐 2025-12-14 11:34:56 之后在 entries 中缺失的工作笔记。

逻辑：
- 源：D:\AI\ai-factory\实施计划和记录.md；
- 以每个 "## 📝 笔记 -" 开头的块作为一条记录；
- 从标题行中解析 note_datetime 字符串；
- 只处理 note_datetime > 指定时间点（默认 "2025-12-14 11:34:56"）；
- 对每条记录取全文前 120 字符作为 content_head；
- 在 entries 表中执行：left(content::text, 120) = content_head；
  - 若已存在 >=1 条记录 => 不再写入（视为已入库）；
  - 若不存在 => 调用 entries_ingest 补写入 DB；
- 打印每条补写入记录的 entry_id 以及最终汇总。

注意：
- 本脚本会真正向 entries 写入数据，请在确认只读检查结果后再执行。
- 依赖 ai_factory.integrations.entries_ingest 与 Docker 中的 rag_db。
"""

import argparse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ai_factory.db.pgvector_client import connection_scope
from ai_factory.integrations.entries_ingest import entries_ingest


PLAN_MD_PATH = Path(r"D:\AI\ai-factory\实施计划和记录.md")
HEADER_PREFIX = "## 📝 笔记 -"


@dataclass
class PlanNote:
    index: int
    note_datetime: str
    dt: Optional[datetime]
    text_block: str
    content_head: str


def parse_plan_notes() -> List[PlanNote]:
    """从实施计划和记录.md 解析所有 "📝 笔记" 记录。"""

    if not PLAN_MD_PATH.exists():
        raise FileNotFoundError(f"找不到实施计划文件: {PLAN_MD_PATH}")

    text = PLAN_MD_PATH.read_text(encoding="utf-8")
    lines = text.splitlines()

    blocks: List[List[str]] = []
    current: Optional[List[str]] = None

    for line in lines:
        if line.startswith(HEADER_PREFIX):
            if current is not None:
                blocks.append(current)
            current = [line]
        else:
            if current is not None:
                current.append(line)

    if current is not None:
        blocks.append(current)

    notes: List[PlanNote] = []
    for i, block_lines in enumerate(blocks, start=1):
        if not block_lines:
            continue
        header_line = block_lines[0]
        note_dt_str = header_line[len(HEADER_PREFIX) :].strip() if header_line.startswith(HEADER_PREFIX) else ""

        dt: Optional[datetime] = None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                dt = datetime.strptime(note_dt_str, fmt)
                break
            except ValueError:
                continue

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


def query_entries_by_content_head(content_head: str) -> List[Dict[str, Any]]:
    sql = """
        SELECT entry_id,
               COALESCE(title, '') AS title,
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


def build_payload(text_block: str, note_datetime: str) -> Dict[str, Any]:
    """构造传给 entries_ingest 的 payload。"""

    payload: Dict[str, Any] = {
        "raw_text": text_block,
        "project_code": None,
        "user_id": None,
        "note_datetime": note_datetime,
        "extra_context": {
            "source": "ai_factory_plan_md_import",
            "md_file": str(PLAN_MD_PATH),
        },
    }
    return payload


def sync_plan_notes(since: str) -> None:
    # 解析 since
    since_dt: Optional[datetime] = None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            since_dt = datetime.strptime(since, fmt)
            break
        except ValueError:
            continue
    if since_dt is None:
        raise ValueError(f"无法解析 since 参数: {since!r}，请使用 'YYYY-MM-DD HH:MM:SS' 格式")

    notes = parse_plan_notes()
    if not notes:
        print("未在实施计划和记录.md 中解析到任何 '📝 笔记' 记录。")
        return

    # 只保留指定时间点之后的记录
    target_notes: List[PlanNote] = []
    for n in notes:
        if n.dt is None:
            continue
        if n.dt > since_dt:
            target_notes.append(n)

    if not target_notes:
        print(f"没有找到 note_datetime > {since} 的笔记记录。")
        return

    print(f"总共解析到 {len(notes)} 条笔记，其中 {len(target_notes)} 条 note_datetime > {since}。")

    already = 0
    inserted = 0
    failed = 0

    for n in target_notes:
        print("-" * 80)
        print(f"index       : {n.index}")
        print(f"note_time   : {n.note_datetime}")
        head_preview = n.content_head.replace("\n", " ")
        print(f"content_head: {head_preview!r}")

        matched = query_entries_by_content_head(n.content_head)
        if matched:
            first = matched[0]
            print(
                f"[EXISTS] entry_id={first.get('entry_id')} created_at={first.get('created_at')} title={first.get('title')!r}"
            )
            already += 1
            continue

        # 未找到 => 调用 entries_ingest 补齐
        payload = build_payload(n.text_block, n.note_datetime)
        try:
            result = entries_ingest(payload)
            entries = (result or {}).get("entries") or []
            if not entries:
                print("[WARN] entries_ingest 成功但返回空 entries。")
                failed += 1
                continue
            first = entries[0] or {}
            print(
                f"[INSERTED] entry_id={first.get('entry_id')} title={first.get('title')!r}"
            )
            inserted += 1
        except Exception as e:  # noqa: BLE001
            print(f"[ERROR] entries_ingest 失败: {e}")
            failed += 1

    print("\n=== 补齐汇总 ===")
    print(f"时间点之后的笔记数 : {len(target_notes)}")
    print(f"已存在(跳过)      : {already}")
    print(f"本次成功写入      : {inserted}")
    print(f"写入失败          : {failed}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "从《实施计划和记录.md》中补齐指定时间点之后，在 entries 中缺失的工作笔记。"
        )
    )
    parser.add_argument(
        "--since",
        type=str,
        default="2025-12-14 11:34:56",
        help="只补齐该时间点之后的记录，格式 'YYYY-MM-DD HH:MM:SS'，默认 '2025-12-14 11:34:56'",
    )

    args = parser.parse_args()
    sync_plan_notes(since=args.since)


if __name__ == "__main__":  # pragma: no cover
    main()
