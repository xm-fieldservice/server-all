#!/usr/bin/env python3
"""
V3多租户架构升级工具
用于执行数据库升级、验证和回滚
"""

import asyncio
import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from ai_factory.agents.memory.config import get_db_pool
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def execute_upgrade():
    """
    执行V3多租户架构升级
    """
    logger.info("========================================")
    logger.info("开始执行V3多租户架构升级")
    logger.info("========================================")

    # 读取升级SQL脚本
    sql_file = project_root / "upgrade_to_v3_multitenancy.sql"
    if not sql_file.exists():
        logger.error(f"升级脚本不存在: {sql_file}")
        return False

    with open(sql_file, 'r', encoding='utf-8') as f:
        sql_content = f.read()

    logger.info(f"读取升级脚本: {sql_file}")

    # 获取数据库连接池
    try:
        pool = await get_db_pool()
        logger.info("数据库连接池创建成功")
    except Exception as e:
        logger.error(f"创建数据库连接池失败: {e}")
        return False

    # 执行升级脚本
    try:
        async with pool.acquire() as conn:
            # 检查当前表结构
            logger.info("\n========== 升级前表结构检查 ==========")
            await check_table_structure(conn)

            # 执行升级脚本
            logger.info("\n========== 执行升级脚本 ==========")
            await conn.execute(sql_content)
            logger.info("升级脚本执行完成")

            # 验证升级结果
            logger.info("\n========== 升级后验证 ==========")
            await verify_upgrade(conn)

        logger.info("\n========================================")
        logger.info("V3多租户架构升级完成！")
        logger.info("========================================")
        return True

    except Exception as e:
        logger.error(f"执行升级失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def check_table_structure(conn):
    """
    检查当前表结构
    """
    tables = ['chat_sessions', 'chat_sections', 'qa_query_index', 'entries']

    for table in tables:
        logger.info(f"\n--- {table} 表结构 ---")
        query = """
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = $1
            ORDER BY ordinal_position
        """
        rows = await conn.fetch(query, table)
        for row in rows:
            nullable = "NULL" if row['is_nullable'] == 'YES' else "NOT NULL"
            logger.info(f"  {row['column_name']}: {row['data_type']} {nullable}")


async def verify_upgrade(conn):
    """
    验证升级结果
    """
    tables = ['chat_sessions', 'chat_sections', 'qa_query_index', 'entries']
    fields = ['user_id', 'agent_type', 'agent_instance_id']

    logger.info("\n四层隔离字段统计:")
    for table in tables:
        logger.info(f"\n--- {table} ---")
        for field in fields:
            query = f"""
                SELECT
                    COUNT(*) as total,
                    COUNT({field}) as filled
                FROM {table}
            """
            result = await conn.fetchrow(query)
            total = result['total']
            filled = result['filled']
            percentage = (filled / total * 100) if total > 0 else 0
            logger.info(f"  {field}: {filled}/{total} ({percentage:.1f}%)")

    # 检查 Knowledge Node 四级结构字段
    logger.info("\nKnowledge Node 四级结构字段统计:")
    kn_fields = [
        'title',          # Level 1
        'summary_ai',     # Level 2
        'content',        # Level 3
        'scene_tags',     # Level 4
        'extra_meta',     # Level 4
        'space_type',     # 分类
        'project_code',    # 项目
        'parent_entry_id' # 树形结构
    ]

    logger.info("\n--- entries ---")
    for field in kn_fields:
        query = f"""
            SELECT
                COUNT(*) as total,
                COUNT({field}) as filled
            FROM entries
        """
        result = await conn.fetchrow(query)
        total = result['total']
        filled = result['filled']
        percentage = (filled / total * 100) if total > 0 else 0
        logger.info(f"  {field}: {filled}/{total} ({percentage:.1f}%)")

    # 检查索引
    logger.info("\n索引检查:")
    indexes = [
        'idx_entries_user_agent',
        'idx_entries_agent_type_user',
        'idx_entries_section_user_agent',
        'idx_entries_scene_tags',
        'idx_entries_space_type',
        'idx_entries_project_code',
        'idx_entries_parent',
        'idx_chat_sessions_user_agent',
        'idx_chat_sections_user_agent',
        'idx_qa_query_index_user_agent'
    ]

    for index in indexes:
        query = """
            SELECT indexname
            FROM pg_indexes
            WHERE indexname = $1
        """
        result = await conn.fetchval(query, index)
        status = "✓" if result else "✗"
        logger.info(f"  {status} {index}")

    # 检查RLS状态
    logger.info("\nRLS（行级安全）状态:")
    query = """
        SELECT tablename, rowsecurity
        FROM pg_tables
        WHERE schemaname = 'public'
          AND tablename IN ('entries', 'chat_sessions', 'chat_sections')
    """
    rows = await conn.fetch(query)
    for row in rows:
        status = "✓ 已启用" if row['rowsecurity'] else "✗ 未启用"
        logger.info(f"  {row['tablename']}: {status}")


async def main():
    """
    主函数
    """
    success = await execute_upgrade()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
