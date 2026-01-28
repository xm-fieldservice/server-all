from __future__ import annotations

"""增量同步《实施计划和记录_去重预览.md》到 rag_db.entries，并输出对齐情况。

使用说明（在 ai-factory 根目录、已激活虚拟环境下）：

  # 1. 确保《实施计划和记录_去重预览.md》是最新的
  python bulk_dedup_from_plan_md.py

  # 2. 增量同步 + 对齐检查
  python sync_plan_md_to_entries.py           # 默认真正写入 DB
  python sync_plan_md_to_entries.py --dry-run # 只做对齐检查，不写库

对齐规则：
- 源记录：
  - 来自《实施计划和记录_去重预览.md》中的每个 "## 📝 笔记 - ..." 块；
  - 复用 bulk_ingest_from_plan_md._parse_records 的解析逻辑；
- 匹配 DB：
  - 对每条记录取全文前 120 个字符作为 content_head；
  - 在 entries 表中查找 left(content::text, 120) = content_head；
  - 若能找到 >=1 条记录，则视为“已同步”；
  - 若找不到，则视为“待入库”，在非 dry-run 模式下将调用 entries_ingest 写入。

本脚本只负责 MD↔DB 的对齐和增量写入；DB↔向量库的对齐请继续使用
check_entry_embeddings_alignment.py。
"""

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ai_factory.db.pgvector_client import connection_scope
from ai_factory.integrations.entries_ingest import entries_ingest
from bulk_ingest_from_plan_md import SOURCE_MD as PREVIEW_MD, _parse_records


@dataclass
class SyncItem:
    index: int
    note_datetime: str
    section_id: Optional[str]
    content_head: str
    exists_in_db: bool
    matched_entries: List[Dict[str, Any]]
    inserted_entry_id: Optional[str] = None


def _query_entries_by_head(content_head: str) -> List[Dict[str, Any]]:
    """在 entries 表中按 content 前缀匹配，返回所有匹配记录。"""

    sql = """
        SELECT entry_id,
               title,
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


def _build_payload(text_block: str, note_datetime: str, section_id: Optional[str], tags_raw: str) -> Dict[str, Any]:
    """构造传给 entries_ingest 的 payload，与 bulk_ingest_from_plan_md 保持一致。"""

    payload: Dict[str, Any] = {
        "raw_text": text_block,
        "project_code": None,
        "user_id": None,
        "note_datetime": note_datetime,
        "extra_context": {
            "source": "ai_factory_md_import",
            "md_file": str(PREVIEW_MD),
            "section_id": section_id,
            "tags_raw": tags_raw,
        },
    }
    return payload


def sync_from_preview(dry_run: bool = False, limit: Optional[int] = None) -> List[SyncItem]:
    """从《实施计划和记录_去重预览.md》增量同步到 entries，并返回对齐结果列表。"""

    preview_path = Path(PREVIEW_MD)
    if not preview_path.exists():
        raise FileNotFoundError(
            f"找不到去重预览文件: {preview_path}，请先运行 bulk_dedup_from_plan_md.py 生成。"
        )

    text = preview_path.read_text(encoding="utf-8")
    records = _parse_records(text)
    if not records:
        print("未在去重预览文件中找到任何 '📝 笔记' 记录。")
        return []

    if limit is not None and limit > 0:
        records = records[:limit]

    results: List[SyncItem] = []

    for idx, rec in enumerate(records, start=1):
        text_block = rec.text_block
        content_head = text_block[:120]

        matched = _query_entries_by_head(content_head)
        exists = len(matched) > 0

        item = SyncItem(
            index=idx,
            note_datetime=rec.note_datetime,
            section_id=rec.section_id,
            content_head=content_head,
            exists_in_db=exists,
            matched_entries=matched,
        )

        if not exists and not dry_run:
            payload = _build_payload(text_block, rec.note_datetime, rec.section_id, rec.tags_raw)
            try:
                result = entries_ingest(payload)
                entries = (result or {}).get("entries") or []
                if entries:
                    first = entries[0] or {}
                    item.inserted_entry_id = str(first.get("entry_id"))
                    print(
                        f"[INSERTED] idx={idx} note_datetime={rec.note_datetime} "
                        f"section_id={rec.section_id} entry_id={item.inserted_entry_id}"
                    )
                else:
                    print(
                        f"[WARN] idx={idx} note_datetime={rec.note_datetime} "
                        f"section_id={rec.section_id} entries_ingest 返回空 entries。"
                    )
            except Exception as e:  # noqa: BLE001
                print(
                    f"[ERROR] idx={idx} note_datetime={rec.note_datetime} "
                    f"section_id={rec.section_id} entries_ingest 失败: {e}"
                )

        elif exists:
            # 已在 DB 中存在匹配记录，仅打印轻量信息
            first = matched[0]
            print(
                f"[EXISTS] idx={idx} note_datetime={rec.note_datetime} section_id={rec.section_id} "
                f"entry_id={first.get('entry_id')} created_at={first.get('created_at')}"
            )

        results.append(item)

    return results


def print_summary(items: List[SyncItem], dry_run: bool) -> None:
    total = len(items)
    already = sum(1 for it in items if it.exists_in_db)
    inserted = sum(1 for it in items if it.inserted_entry_id is not None)
    missing = total - already - inserted

    print("\n=== MD ↔ DB 对齐汇总 ===")
    print(f"总记录数       : {total}")
    print(f"已在 DB 中存在 : {already}")
    if dry_run:
        print(f"（dry-run）如执行写库，预计新增 : {total - already}")
    else:
        print(f"本次新增写入   : {inserted}")
        print(f"仍未写入/失败  : {missing}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "从《实施计划和记录_去重预览.md》增量同步到 entries，"
            "并输出 MD↔DB 对齐情况。"
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只做对齐检查，不写入 DB。",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="最多处理前 N 条记录（默认全部）。",
    )

    args = parser.parse_args()

    items = sync_from_preview(dry_run=args.dry_run, limit=args.limit)
    print_summary(items, dry_run=args.dry_run)


if __name__ == "__main__":  # pragma: no cover
    main()
