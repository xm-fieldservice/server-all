#!/usr/bin/env python3
"""
应用数据库迁移脚本
"""

import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'ai_factory'))

from ai_factory.db.pgvector_client import connection_scope

# 读取迁移SQL脚本
with open('ai_factory/agents/memory/003_add_last_section_triggered_at.sql', 'r') as f:
    migration_sql = f.read()

# 应用迁移
print("开始应用数据库迁移...")
print("="*60)

try:
    with connection_scope() as conn:
        with conn.cursor() as cur:
            # 执行迁移SQL
            for statement in migration_sql.split(';'):
                statement = statement.strip()
                if statement and not statement.startswith('--'):
                    print(f"执行: {statement[:50]}...")
                    cur.execute(statement)

            conn.commit()
            
    print("="*60)
    print("✅ 数据库迁移成功完成！")
    print("\n验证迁移...")
    
    # 验证列是否添加成功
    with connection_scope() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = 'chat_sessions'
                AND column_name = 'last_section_triggered_at'
            """)
            result = cur.fetchone()
            if result:
                print(f"✅ 列已添加: {result[0]} (类型: {result[1]})")
            else:
                print("❌ 列添加失败")
                sys.exit(1)
                
except Exception as e:
    print(f"❌ 迁移失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "="*60)
print("迁移完成！现在可以重启API服务了。")
