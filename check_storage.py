#!/usr/bin/env python3
"""
数据存储位置分析报告
"""

import sys
sys.path.insert(0, '.')

from ai_factory.db.pgvector_client import connection_scope

print("=" * 60)
print("数据存储位置清单（entries-only）")
print("=" * 60)

with connection_scope() as conn:
    with conn.cursor() as cur:
        # 1. 查询 entries 表
        print(f"\n📦 entries:")
        cur.execute('SELECT COUNT(*) FROM entries')
        count = cur.fetchone()[0]
        print(f"   记录数: {count}")
        
        if count > 0:
            cur.execute('''
                SELECT entry_id, title, LEFT(content, 80), created_at 
                FROM entries 
                ORDER BY created_at DESC 
                LIMIT 3
            ''')
            rows = cur.fetchall()
            for i, row in enumerate(rows, 1):
                print(f"   {i}. ID: {row[0][:8]}...")
                print(f"      标题: {row[1] or '(无标题)'}")
                print(f"      内容: {row[2]}...")
                print(f"      时间: {row[3]}")
        
        # 2. 可选：检查向量表
        try:
            cur.execute("SELECT COUNT(*) FROM entry_embeddings")
            vec_count = cur.fetchone()[0]
            print(f"\n📦 entry_embeddings:")
            print(f"   向量数: {vec_count}")
        except Exception:
            print("\n⚠️ 未找到 entry_embeddings 表（可能尚未创建向量索引）")

print("\n" + "=" * 60)
print("总结:")
print("=" * 60)
print("✅ entries 表: 存储长期记忆事实条目")
print("✅ entry_embeddings 表: 存储 entries 对应的向量（如已存在）")
