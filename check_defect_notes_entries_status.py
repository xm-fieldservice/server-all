from __future__ import annotations

"""检查“缺陷笔记汇总”中每条笔记在 entries 表中的入库情况。

- 源文件: D:\AI\数据库+向量库_缺陷笔记汇总.md
- 判定规则: 按每条笔记全文的前 120 字符，与 entries.content 前 120 字完全匹配。

输出:
- 每条缺陷笔记的序号、content_head 预览；
- 在 entries 中是否找到记录，若找到则列出 entry_id/title（可能多条）。

本脚本只做只读查询，不进行任何删除或修改。
"""

from pathlib import Path
from typing import List, Tuple

defect_md_path = Path(r"D:\AI\数据库+向量库_缺陷笔记汇总.md")

from ai_factory.db.pgvector_client import connection_scope


def print_header(title: str) -> None:
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)


def parse_defect_blocks() -> List[Tuple[int, str]]:
    """解析缺陷笔记汇总文件，返回 [(index, content_head)] 列表。

    这里简单按 "## 📝 笔记 -" 标题划分块，并以每块全文前 120 个字符
    作为 content_head，用于与 entries.content 前缀匹配。
    """

    if not defect_md_path.exists():
        raise FileNotFoundError(f"找不到缺陷笔记文件: {defect_md_path}")

    text = defect_md_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    blocks: List[str] = []
    current: List[str] | None = None

    header_prefix = "## 📝 笔记 -"

    for line in lines:
        if line.startswith(header_prefix):
            # 遇到新的笔记头，先收尾上一个块
            if current is not None:
                blocks.append("\n".join(current).strip())
            current = [line]
        else:
            if current is not None:
                current.append(line)

    if current is not None:
        blocks.append("\n".join(current).strip())

    results: List[Tuple[int, str]] = []
    for i, block in enumerate(blocks, start=1):
        head = block[:120]
        results.append((i, head))

    return results


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
    print_header("解析缺陷笔记汇总文件")
    blocks = parse_defect_blocks()
    print(f"共解析出缺陷笔记 {len(blocks)} 条。")

    print_header("逐条检查在 entries 表中的入库情况")

    success_count = 0
    not_found_count = 0

    for idx, head in blocks:
        print("-" * 80)
        print(f"缺陷笔记 #{idx}")
        print(f"content_head: {head!r}")

        rows = query_entries_by_content_head(head)
        if not rows:
            print("结果: 未找到对应 entries 记录 (FAILED)")
            not_found_count += 1
        else:
            success_count += 1
            print(f"结果: 找到 {len(rows)} 条 entries 记录:")
            for entry_id, title in rows:
                print(f"  entry_id={entry_id}, title={title!r}")

    print_header("汇总")
    print(f"总缺陷笔记数: {len(blocks)}")
    print(f"已入库(找到 entries 记录): {success_count}")
    print(f"未入库(未找到匹配记录): {not_found_count}")


if __name__ == "__main__":
    main()
