#!/usr/bin/env python3
"""
V3多租户架构升级执行脚本

支持两种执行方式：
1. 使用环境变量配置（默认）
2. 使用命令行参数（推荐用于管理员执行）

使用方法：
    # 方式1：环境变量
    export AI_PG_ADMIN_USER=postgres
    export AI_PG_ADMIN_PASSWORD=your_password
    python3 execute_upgrade.py

    # 方式2：命令行参数
    python3 execute_upgrade.py --user postgres --password your_password
"""

import asyncio
import sys
import argparse
from pathlib import Path
import os

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

import asyncpg
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DatabaseUpgrader:
    """数据库升级器"""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 5433,
        database: str = "rag_db",
        user: str = None,
        password: str = None
    ):
        self.host = host
        self.port = port
        self.database = database
        self.user = user or os.getenv("AI_PG_ADMIN_USER", os.getenv("AI_PG_USER", "rag_user"))
        self.password = password or os.getenv("AI_PG_ADMIN_PASSWORD", os.getenv("AI_PG_PASSWORD", "rag_password"))
        self.pool = None

    async def connect(self):
        """连接数据库"""
        try:
            self.pool = await asyncpg.create_pool(
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.user,
                password=self.password,
                min_size=1,
                max_size=5
            )
            logger.info(f"✓ 数据库连接成功: {self.user}@{self.host}:{self.port}/{self.database}")
            return True
        except Exception as e:
            logger.error(f"✗ 数据库连接失败: {e}")
            return False

    async def close(self):
        """关闭连接"""
        if self.pool:
            await self.pool.close()
            logger.info("✓ 数据库连接已关闭")

    async def check_permissions(self):
        """检查用户权限"""
        async with self.pool.acquire() as conn:
            try:
                # 检查CREATE TABLE权限
                result = await conn.fetchval(
                    "SELECT has_schema_privilege($1, 'public', 'CREATE')",
                    self.user
                )
                if not result:
                    logger.warning(f"⚠ 用户 {self.user} 缺乏 CREATE TABLE 权限")

                # 检查当前数据库权限
                result = await conn.fetchval(
                    """
                    SELECT has_database_privilege(
                        current_database(),
                        $1
                    )
                    """,
                    'CREATE'
                )
                logger.info(f"CREATE权限: {'✓' if result else '✗'}")

                return True
            except Exception as e:
                logger.error(f"✗ 权限检查失败: {e}")
                return False

    async def check_existing_tables(self):
        """检查现有表"""
        async with self.pool.acquire() as conn:
            tables = ['chat_sessions', 'chat_messages', 'chat_sections', 'qa_query_index', 'entries']

            logger.info("\n========== 现有表检查 ==========")
            for table in tables:
                query = """
                    SELECT EXISTS (
                        SELECT 1
                        FROM information_schema.tables
                        WHERE table_name = $1
                    )
                """
                exists = await conn.fetchval(query, table)
                status = "✓ 存在" if exists else "✗ 不存在"
                logger.info(f"  {table}: {status}")

                if exists:
                    # 显示表记录数
                    count_query = f"SELECT COUNT(*) FROM {table}"
                    count = await conn.fetchval(count_query)
                    logger.info(f"    └─ 记录数: {count}")

    async def execute_upgrade_script(self):
        """执行升级脚本"""
        sql_file = project_root / "upgrade_v3_with_admin.sql"

        if not sql_file.exists():
            logger.error(f"✗ 升级脚本不存在: {sql_file}")
            return False

        with open(sql_file, 'r', encoding='utf-8') as f:
            sql_content = f.read()

        logger.info(f"\n========== 执行升级脚本 ==========")
        logger.info(f"读取升级脚本: {sql_file}")
        logger.info(f"脚本大小: {len(sql_content)} 字节")

        try:
            async with self.pool.acquire() as conn:
                # 执行升级脚本
                await conn.execute(sql_content)
                logger.info("✓ 升级脚本执行完成")
                return True
        except Exception as e:
            logger.error(f"✗ 升级脚本执行失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def verify_upgrade(self):
        """验证升级结果"""
        async with self.pool.acquire() as conn:
            # 检查四层隔离字段
            logger.info("\n========== 升级结果验证 ==========")

            tables = ['chat_sessions', 'chat_sections', 'qa_query_index', 'entries']
            fields = ['user_id', 'agent_type', 'agent_instance_id']

            logger.info("\n四层隔离字段统计:")
            for table in tables:
                logger.info(f"\n  {table}:")
                # 先检查表是否存在
                table_exists = await conn.fetchval(
                    "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = $1)",
                    table
                )
                if not table_exists:
                    logger.info(f"    ✗ 表不存在")
                    continue

                for field in fields:
                    # 检查字段是否存在
                    field_exists = await conn.fetchval(
                        """
                        SELECT EXISTS (
                            SELECT 1
                            FROM information_schema.columns
                            WHERE table_name = $1 AND column_name = $2
                        )
                        """,
                        table, field
                    )
                    if not field_exists:
                        logger.info(f"    ✗ {field}: 字段不存在")
                        continue

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
                    status = "✓" if percentage >= 50 else "⚠"
                    logger.info(f"    {status} {field}: {filled}/{total} ({percentage:.1f}%)")

            # 检查 Knowledge Node 四级结构字段
            logger.info("\nKnowledge Node 四级结构字段统计:")
            kn_fields = [
                'title', 'summary_ai', 'content', 'scene_tags',
                'extra_meta', 'space_type', 'project_code', 'parent_entry_id'
            ]

            logger.info(f"\n  entries:")
            for field in kn_fields:
                field_exists = await conn.fetchval(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_name = 'entries' AND column_name = $1
                    )
                    """,
                    field
                )
                if not field_exists:
                    logger.info(f"    ✗ {field}: 字段不存在")
                    continue

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
                status = "✓" if field == 'title' or percentage > 0 else "○"
                logger.info(f"    {status} {field}: {filled}/{total} ({percentage:.1f}%)")

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
                'idx_chat_sessions_agent_user',
                'idx_chat_sections_user_agent',
                'idx_chat_sections_agent_user',
                'idx_qa_query_index_user_agent',
                'idx_qa_query_index_agent_user'
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

    async def run(self):
        """执行完整升级流程"""
        logger.info("========================================")
        logger.info("V3多租户架构升级开始")
        logger.info("========================================")

        # 1. 连接数据库
        if not await self.connect():
            return False

        try:
            # 2. 检查权限
            if not await self.check_permissions():
                logger.warning("⚠ 权限检查发现问题，但继续执行")

            # 3. 检查现有表
            await self.check_existing_tables()

            # 4. 执行升级脚本
            if not await self.execute_upgrade_script():
                return False

            # 5. 验证升级结果
            await self.verify_upgrade()

            logger.info("\n========================================")
            logger.info("✓ V3多租户架构升级完成！")
            logger.info("========================================")
            return True

        finally:
            await self.close()


async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='V3多租户架构升级脚本')
    parser.add_argument('--host', default='localhost', help='数据库主机')
    parser.add_argument('--port', type=int, default=5433, help='数据库端口')
    parser.add_argument('--database', default='rag_db', help='数据库名称')
    parser.add_argument('--user', help='数据库用户（优先使用环境变量AI_PG_ADMIN_USER）')
    parser.add_argument('--password', help='数据库密码（优先使用环境变量AI_PG_ADMIN_PASSWORD）')

    args = parser.parse_args()

    upgrader = DatabaseUpgrader(
        host=args.host,
        port=args.port,
        database=args.database,
        user=args.user,
        password=args.password
    )

    success = await upgrader.run()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
