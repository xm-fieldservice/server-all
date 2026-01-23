#!/usr/bin/env python3
"""
简化版数据库升级脚本
直接使用psycopg2连接数据库执行SQL升级
"""

import asyncio
import sys
from pathlib import Path
import psycopg2
from psycopg2 import sql
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def execute_upgrade():
    """
    执行V3多租户架构升级
    """
    logger.info("========================================")
    logger.info("开始执行V3多租户架构升级")
    logger.info("========================================")

    # 数据库配置
    db_config = {
        'host': 'localhost',
        'port': 5433,
        'database': 'rag_db',
        'user': 'rag_user',
        'password': 'rag_password'
    }

    # 读取升级SQL脚本
    sql_file = Path(__file__).parent / "upgrade_to_v3_multitenancy.sql"
    if not sql_file.exists():
        logger.error(f"升级脚本不存在: {sql_file}")
        return False

    with open(sql_file, 'r', encoding='utf-8') as f:
        sql_content = f.read()

    logger.info(f"读取升级脚本: {sql_file}")

    # 连接数据库
    try:
        conn = psycopg2.connect(**db_config)
        conn.autocommit = True  # 执行DDL需要autocommit
        cursor = conn.cursor()
        logger.info("数据库连接成功")
    except Exception as e:
        logger.error(f"连接数据库失败: {e}")
        return False

    # 执行升级脚本
    try:
        # 检查当前表结构
        logger.info("\n========== 升级前表结构检查 ==========")
        cursor.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name
        """)
        tables = cursor.fetchall()
        for table in tables:
            logger.info(f"  {table[0]}")

        # 执行升级脚本
        logger.info("\n========== 执行升级脚本 ==========")
        cursor.execute(sql_content)
        logger.info("升级脚本执行完成")

        # 验证升级结果
        logger.info("\n========== 升级后验证 ==========")
        
        # 验证四层隔离字段
        logger.info("\n四层隔离字段统计:")
        tables_to_check = ['chat_sessions', 'chat_sections', 'qa_query_index', 'entries']
        fields_to_check = ['user_id', 'agent_type', 'agent_instance_id']

        for table in tables_to_check:
            logger.info(f"\n--- {table} ---")
            for field in fields_to_check:
                cursor.execute(f"""
                    SELECT COUNT(*) as total,
                           COUNT({field}) as filled
                    FROM {table}
                """)
                result = cursor.fetchone()
                total = result[0]
                filled = result[1]
                percentage = (filled / total * 100) if total > 0 else 0
                logger.info(f"  {field}: {filled}/{total} ({percentage:.1f}%)")

        # 验证 Knowledge Node 字段
        logger.info("\nKnowledge Node 四级结构字段统计:")
        kn_fields = [
            'title', 'summary_ai', 'content', 'scene_tags', 'extra_meta',
            'space_type', 'project_code', 'parent_entry_id'
        ]
        
        logger.info("\n--- entries ---")
        for field in kn_fields:
            cursor.execute(f"""
                SELECT COUNT(*) as total, COUNT({field}) as filled
                FROM entries
            """)
            result = cursor.fetchone()
            total = result[0]
            filled = result[1]
            percentage = (filled / total * 100) if total > 0 else 0
            logger.info(f"  {field}: {filled}/{total} ({percentage:.1f}%)")

        # 验证索引
        logger.info("\n索引检查:")
        cursor.execute("""
            SELECT indexname
            FROM pg_indexes
            WHERE schemaname = 'public'
              AND indexname IN (
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
              )
            ORDER BY indexname
        """)
        indexes = cursor.fetchall()
        for index in indexes:
            logger.info(f"  ✓ {index[0]}")

        # 验证RLS状态
        logger.info("\nRLS（行级安全）状态:")
        cursor.execute("""
            SELECT tablename, rowsecurity
            FROM pg_tables
            WHERE schemaname = 'public'
              AND tablename IN ('entries', 'chat_sessions', 'chat_sections')
        """)
        tables_rls = cursor.fetchall()
        for table_rls in tables_rls:
            status = "✓ 已启用" if table_rls[1] else "✗ 未启用"
            logger.info(f"  {table_rls[0]}: {status}")

        cursor.close()
        conn.close()
        
        logger.info("\n========================================")
        logger.info("V3多租户架构升级完成！")
        logger.info("========================================")
        return True

    except Exception as e:
        logger.error(f"执行升级失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """
    主函数
    """
    success = execute_upgrade()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
