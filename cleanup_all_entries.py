from __future__ import annotations

"""清空 rag_db.entries 表中的所有数据。

注意：这是一个一次性清理脚本，只适用于当前“全部都是测试数据”的场景。
运行前请确认没有需要保留的正式数据。
"""

from ai_factory.db.pgvector_client import connection_scope


def main() -> None:
    confirm = input(
        "本操作将删除 rag_db 数据库中 entries 表的所有记录，仅在全部为测试数据时使用。\n"
        "确定要继续吗？输入 YES 确认： "
    ).strip()
    if confirm != "YES":
        print("已取消，未做任何修改。")
        return

    with connection_scope() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM entries;")
            deleted = cur.rowcount
    print(f"已删除 entries 表中的 {deleted} 条记录。")


if __name__ == "__main__":
    main()
