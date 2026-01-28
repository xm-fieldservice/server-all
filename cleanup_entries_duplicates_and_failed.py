from __future__ import annotations

"""清理 rag_db.entries 表中的失败记录与重复记录。

删除规则：
1. 失败记录（failed entries）：
   - title 为空或全空白，且 summary_ai 为空或长度 < 20。

2. 重复记录（duplicate entries）：
   - content 完全相同的记录组中，只保留一条，其余全部删除；
   - 保留规则：同一 content 下，按 created_at 升序、entry_id 升序，保留第一条，其余视为重复删除。

脚本在执行删除前会先打印统计信息，并要求用户输入 YES 确认。
"""

from typing import List, Tuple

from ai_factory.db.pgvector_client import connection_scope


def fetch_failed_ids() -> List[str]:
    """返回符合失败规则的 entry_id 列表。"""

    sql = """
        SELECT entry_id
        FROM entries
        WHERE (title IS NULL OR trim(title) = '')
          AND (summary_ai IS NULL OR length(trim(summary_ai)) < 20);
    """

    with connection_scope() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()

    return [r[0] for r in rows]


def fetch_duplicate_ids() -> Tuple[int, List[str]]:
    """返回需要删除的重复记录 entry_id 列表。

    重复判定：content 完全相同。
    保留：每个 content 组中保留最早的一条（created_at 最小，其次 entry_id 最小），其余删除。

    返回：(重复组数, 需要删除的 entry_id 列表)。
    """

    # 先找出存在重复的 content 分组
    sql_groups = """
        SELECT input_content::text AS content_text, COUNT(*) AS cnt
        FROM entries
        GROUP BY content_text
        HAVING COUNT(*) > 1;
    """

    groups: List[Tuple[str, int]] = []

    with connection_scope() as conn:
        with conn.cursor() as cur:
            cur.execute(sql_groups)
            for content_text, cnt in cur.fetchall():
                groups.append((content_text, cnt))

    if not groups:
        return 0, []

    # 对每个重复组，找出需要删除的 entry_id
    to_delete: List[str] = []

    with connection_scope() as conn:
        with conn.cursor() as cur:
            for content_text, cnt in groups:
                # 找出该 content 下的所有记录，按 created_at, entry_id 排序
                cur.execute(
                    """
                    SELECT entry_id
                    FROM entries
                    WHERE input_content::text = %s
                    ORDER BY created_at ASC, entry_id ASC;
                    """,
                    (content_text,),
                )
                rows = cur.fetchall()
                # 保留第一条，其余视为重复需要删除
                for r in rows[1:]:
                    to_delete.append(r[0])

    return len(groups), to_delete


def delete_entries(entry_ids: List[str]) -> int:
    """批量删除给定 entry_id 列表，返回删除条数。"""

    if not entry_ids:
        return 0

    with connection_scope() as conn:
        with conn.cursor() as cur:
            # 使用 ANY 语法批量删除
            cur.execute(
                "DELETE FROM entries WHERE entry_id = ANY(%s);",
                (entry_ids,),
            )
            deleted = cur.rowcount
    return deleted


def main() -> None:
    print("开始分析 entries 表中的失败记录与重复记录...")

    failed_ids = fetch_failed_ids()
    print(f"发现失败记录 {len(failed_ids)} 条（title 为空且 summary_ai 为空/过短）")
    if failed_ids:
        print("部分失败记录示例 (最多前 10 条):")
        for eid in failed_ids[:10]:
            print(f"  - {eid}")

    dup_group_count, dup_ids = fetch_duplicate_ids()
    print(f"发现 content 完全相同的重复 group 共 {dup_group_count} 组，需要删除重复记录 {len(dup_ids)} 条（每组保留 1 条）")
    if dup_ids:
        print("部分重复记录示例 (最多前 10 条):")
        for eid in dup_ids[:10]:
            print(f"  - {eid}")

    total_to_delete = len(failed_ids) + len(dup_ids)
    if total_to_delete == 0:
        print("未检测到需要删除的记录，退出。")
        return

    print("\n总结：")
    print(f"  失败记录: {len(failed_ids)} 条")
    print(f"  重复记录: {len(dup_ids)} 条")
    print(f"  合计待删除: {total_to_delete} 条（去重后统计）")

    confirm = input("\n本操作将从 entries 表中删除上述记录。确定要继续吗？输入 YES 确认： ").strip()
    if confirm != "YES":
        print("已取消删除操作，未做任何修改。")
        return

    # 合并并去重 ID，避免重复删除
    all_ids_set = set(failed_ids) | set(dup_ids)
    all_ids = list(all_ids_set)

    deleted = delete_entries(all_ids)
    print(f"删除完成，共删除 {deleted} 条记录。")


if __name__ == "__main__":
    main()
