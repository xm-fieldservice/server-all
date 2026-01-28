from __future__ import annotations

"""检查数据库+向量库时序文档中指定记录序号是否已成功入库。

方法：
- 从 D:\AI\数据库+向量库_所有笔记_时序记录.md 中解析出所有段落；
- 对指定的 record_index（例如 123, 184, ...）对应的段落计算内容 hash；
- 从 entries 表中取最近 N 条记录，基于 content 计算同样的 hash；
- 若找到匹配 hash，则认为该段已成功入库，并打印对应 entry 信息；
- 若找不到匹配，则很可能是当时 entries_ingest 失败而未写库。

脚本只读数据库和文件，不对任何数据做修改。
"""

import hashlib
from pathlib import Path
from typing import Any, Dict, List, Tuple

from ai_factory.db.pgvector_client import connection_scope

TIMELINE_MD = Path(r"D:\AI\数据库+向量库_所有笔记_时序记录.md")

TARGET_INDICES = [
    123,
    184,
    225,
    241,
    249,
    251,
    255,
    257,
    259,
    300,
    314,
    316,
    328,
    330,
    331,
    334,
    335,
    336,
    337,
    338,
    339,
    340,
]


def parse_timeline_blocks() -> List[Tuple[int, str]]:
    """返回 (record_index, block_text) 列表。"""

    if not TIMELINE_MD.exists():
        raise FileNotFoundError(f"找不到时序记录文档: {TIMELINE_MD}")

    text = TIMELINE_MD.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)

    blocks: List[Tuple[int, List[str]]] = []
    current: List[str] | None = None
    current_idx: int | None = None

    import re

    marker_pat = re.compile(r"<!--\s*段落\s*#(\d+),")

    for line in lines:
        m = marker_pat.search(line)
        if m:
            # 遇到新段落
            if current is not None and current_idx is not None:
                blocks.append((current_idx, current))
            current_idx = int(m.group(1))
            current = []
            continue
        if current is not None:
            current.append(line)

    if current is not None and current_idx is not None:
        blocks.append((current_idx, current))

    return [
        (idx, "".join(bl).strip("\n") + "\n")
        for idx, bl in blocks
    ]


def fetch_recent_entries(limit: int = 2000) -> List[Dict[str, Any]]:
    sql = "SELECT entry_id, created_at, title, input_content AS content FROM entries ORDER BY created_at DESC LIMIT %s"
    with connection_scope() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (limit,))
            rows = cur.fetchall()
            colnames = [d[0] for d in cur.description]
    return [dict(zip(colnames, row)) for row in rows]


def sha1_text(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def main() -> None:
    blocks = parse_timeline_blocks()
    idx_to_block: Dict[int, str] = {idx: text for idx, text in blocks}

    print(f"时序文档总段落数: {len(blocks)}")

    missing_indices = [i for i in TARGET_INDICES if i not in idx_to_block]
    if missing_indices:
        print(f"警告: 以下索引在时序文档中不存在: {missing_indices}")

    target_hashes: Dict[int, str] = {}
    for idx in TARGET_INDICES:
        text = idx_to_block.get(idx)
        if text is None:
            continue
        target_hashes[idx] = sha1_text(text)

    entries = fetch_recent_entries(2000)
    hash_to_entry: Dict[str, Dict[str, Any]] = {}
    for e in entries:
        content = str(e.get("content") or "")
        h = sha1_text(content)
        # 若有 hash 冲突，保留最新一条即可
        hash_to_entry[h] = e

    print(f"最近 entries 数量: {len(entries)}")

    for idx in TARGET_INDICES:
        h = target_hashes.get(idx)
        if not h:
            print(f"\n记录索引 {idx}: 无法在时序文档中找到对应段落，跳过。")
            continue
        entry = hash_to_entry.get(h)
        if entry is None:
            print(f"\n记录索引 {idx}: 未在 entries 中找到匹配内容，推测当时入库失败或尚未入库。")
        else:
            print(f"\n记录索引 {idx}: 已找到匹配 entries 记录。")
            print("  entry_id  :", entry.get("entry_id"))
            print("  created_at:", entry.get("created_at"))
            print("  title    :", (entry.get("title") or "").strip()[:120])


if __name__ == "__main__":
    main()
