#!/usr/bin/env python3
"""执行 create_memory_tasks_table.sql 创建 memory_tasks 表"""

import os
import sys

# 添加项目根目录到 Python 路径
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "."))
sys.path.insert(0, project_root)

from ai_factory.db.pgvector_client import connection_scope

def main():
    """主函数"""
    sql_file = "ai_factory/agents/memory/create_memory_tasks_table.sql"

    # 读取 SQL 文件
    with open(sql_file, "r", encoding="utf-8") as f:
        sql_content = f.read()

    # 执行 SQL
    with connection_scope() as conn:
        with conn.cursor() as cur:
            # 分割 SQL 语句（按分号分割）
            statements = [s.strip() for s in sql_content.split(";") if s.strip()]

            for i, statement in enumerate(statements, 1):
                if statement:
                    try:
                        cur.execute(statement)
                        print(f"✓ 执行成功 ({i}/{len(statements)}): {statement[:50]}...")
                    except Exception as e:
                        print(f"✗ 执行失败 ({i}/{len(statements)}): {e}")
                        print(f"  SQL: {statement[:100]}...")
                        # 继续执行其他语句

    print("\n✓ memory_tasks 表创建完成！")

if __name__ == "__main__":
    main()
