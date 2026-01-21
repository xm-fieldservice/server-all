#!/usr/bin/env python3
import sys
sys.path.insert(0, '.')

from ai_factory.db.pgvector_client import connection_scope

print("=" * 60)
print("数据存储分析报告")
print("=" * 60)

try:
    with connection_scope() as conn:
        with conn.cursor() as cur:
            # 查询消息数量
            cur.execute('SELECT COUNT(*) FROM chat_messages')
            msg_count = cur.fetchone()[0]
            print(f"\n💬 消息总数: {msg_count}")
            
            # 查询最新消息
            if msg_count > 0:
                cur.execute('''
                    SELECT message_id, role, msg_type, content, created_at 
                    FROM chat_messages 
                    ORDER BY created_at DESC 
                    LIMIT 1
                ''')
                row = cur.fetchone()
                print(f"\n📝 最新消息:")
                print(f"   ID: {row[0][:8]}...")
                print(f"   角色: {row[1]}")
                print(f"   类型: {row[2] or '未设置'}")
                print(f"   内容: {row[3][:50]}...")
                print(f"   时间: {row[4]}")
            
            print("\n" + "=" * 60)
            print("存储位置清单:")
            print("=" * 60)
            print("1. chat_sessions - 会话信息")
            print("2. chat_messages - 消息内容（你的输入）")
            print("3. entries - 长期记忆（总结后）")
            print("4. sections - 段落信息")
            
except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()
