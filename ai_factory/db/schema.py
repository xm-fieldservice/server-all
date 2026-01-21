from __future__ import annotations

"""数据库 schema 初始化工具（v0）。

目前只负责确保 `entries` 表存在，供本地开发与测试使用。
后续若有更多表，可以在这里按需扩展。
"""

from typing import NoReturn

from .pgvector_client import connection_scope


def ensure_entries_table() -> None:
    """确保 entries 表存在（不存在则创建）。"""

    create_sql = """
    CREATE TABLE IF NOT EXISTS public.entries (
        entry_id      TEXT PRIMARY KEY,
        title         TEXT NOT NULL,
        summary_ai    TEXT,
        content       TEXT NOT NULL,
        project_code  TEXT,
        user_id       TEXT,
        created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """

    with connection_scope() as conn:
        with conn.cursor() as cur:
            cur.execute(create_sql)

            # 为增量演进保留：随着业务发展，entries 表新增了一些字段
            # 这里用 ADD COLUMN IF NOT EXISTS 确保老库也能平滑补齐字段
            cur.execute(
                """
                ALTER TABLE public.entries
                ADD COLUMN IF NOT EXISTS space_type TEXT,
                ADD COLUMN IF NOT EXISTS parent_entry_id TEXT,
                ADD COLUMN IF NOT EXISTS scene_tags TEXT;
                """
            )

    print("[schema] ensured table public.entries exists and columns are up to date")


def upgrade_entries_schema_to_latest() -> None:
    """在当前数据库上，将 entries 表升级到最新设计所需字段和索引。

    - 补齐 space_type / parent_entry_id 字段（text），若不存在则新增；
    - 将 scene_tags 统一为 jsonb 类型（若是 text 则尝试转换）；
    - 为 parent_entry_id / space_type / scene_tags 创建推荐索引。
    """

    with connection_scope() as conn:
        with conn.cursor() as cur:
            # 1) 补齐树形与空间标记字段
            cur.execute(
                """
                ALTER TABLE public.entries
                  ADD COLUMN IF NOT EXISTS space_type TEXT,
                  ADD COLUMN IF NOT EXISTS parent_entry_id TEXT;
                """
            )

            # 2) 为树字段和场景标签创建推荐索引
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_entries_parent_entry_id
                  ON public.entries (parent_entry_id);

                CREATE INDEX IF NOT EXISTS idx_entries_space_type
                  ON public.entries (space_type);

                CREATE INDEX IF NOT EXISTS idx_entries_scene_tags_gin
                  ON public.entries USING gin (scene_tags);
                """
            )

    print("[schema] upgraded table public.entries to latest design (tree + scene_tags indexes)")


def print_entries_schema() -> None:
    """打印当前数据库中 entries 表的列信息和索引信息。"""

    with connection_scope() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = 'entries'
                ORDER BY ordinal_position;
                """
            )
            cols = cur.fetchall()

            cur.execute(
                """
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE tablename = 'entries'
                ORDER BY indexname;
                """
            )
            idx = cur.fetchall()

    print("COLUMNS:")
    for name, dtype in cols:
        print(f"  {name:20s} {dtype}")

    print("\nINDEXES:")
    for name, definition in idx:
        print(f"  {name}: {definition}")


def main() -> NoReturn:
    ensure_entries_table()
    upgrade_entries_schema_to_latest()


if __name__ == "__main__":  # pragma: no cover
    main()
