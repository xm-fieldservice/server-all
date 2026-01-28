#!/usr/bin/env python3
import sys
sys.path.insert(0, '.')

from ai_factory.db.pgvector_client import connection_scope

print("=" * 60)
print("数据存储分析报告（entries-only）")
print("=" * 60)

try:
    with connection_scope() as conn:
        with conn.cursor() as cur:
            # 查询 entries 记录数量
            cur.execute('SELECT COUNT(*) FROM entries')
            entry_count = cur.fetchone()[0]
            print(f"\n📚 entries 总数: {entry_count}")
            
            # 查询最近一条 entry
            if entry_count > 0:
                cur.execute('''
                    SELECT entry_id, title, LEFT(input_content, 80), created_at 
                    FROM entries 
                    ORDER BY created_at DESC 
                    LIMIT 1
                ''')
                row = cur.fetchone()
                print(f"\n📝 最新 entry:")
                print(f"   ID: {row[0][:8]}...")
                print(f"   标题: {row[1] or '(无标题)'}")
                print(f"   内容: {row[2]}...")
                print(f"   时间: {row[3]}")
            
            print("\n" + "=" * 60)
            print("存储位置清单:")
            print("=" * 60)
            print("1. entries - 长期记忆事实表")
            print("2. entry_embeddings - 向量索引表（如已启用）")
            
except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()
