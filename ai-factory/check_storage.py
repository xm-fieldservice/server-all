#!/usr/bin/env python3
"""
数据存储位置分析报告
"""

import sys
sys.path.insert(0, '.')

from ai_factory.db.pgvector_client import connection_scope

print("=" * 60)
print("数据存储位置清单")
print("=" * 60)

with connection_scope() as conn:
    with conn.cursor() as cur:
        # 1. 查询所有相关表
        tables = ['chat_sessions', 'chat_messages', 'entries', 'sections']
        
        for table in tables:
            print(f"\n📦 {table}:")
            cur.execute(f'SELECT COUNT(*) FROM {table}')
            count = cur.fetchone()[0]
            print(f"   记录数: {count}")
            
            # 显示示例数据
            if count > 0:
                if table == 'chat_messages':
                    cur.execute(f'''
                        SELECT message_id, role, msg_type, LEFT(content, 40), created_at 
                        FROM {table} 
                        ORDER BY created_at DESC 
                        LIMIT 3
                    ''')
                    rows = cur.fetchall()
                    for i, row in enumerate(rows, 1):
                        print(f"   {i}. ID: {row[0][:8]}...")
                        print(f"      角色: {row[1]} | 类型: {row[2] or '未设置'}")
                        print(f"      内容: {row[3]}...")
                        print(f"      时间: {row[4]}")
                elif table == 'chat_sessions':
                    cur.execute(f'''
                        SELECT session_id, title, created_at 
                        FROM {table} 
                        ORDER BY created_at DESC 
                        LIMIT 2
                    ''')
                    rows = cur.fetchall()
                    for i, row in enumerate(rows, 1):
                        print(f"   {i}. ID: {row[0][:8]}...")
                        print(f"      标题: {row[1]}")
                        print(f"      时间: {row[2]}")
        
        # 2. 查询最新消息详情
        print(f"\n🔍 最新消息详细分析:")
        cur.execute('''
            SELECT 
                m.message_id,
                m.role,
                m.msg_type,
                m.content,
                m.metadata_json,
                s.title as session_title,
                m.created_at
            FROM chat_messages m
            LEFT JOIN chat_sessions s ON m.session_id = s.session_id
            ORDER BY m.created_at DESC 
            LIMIT 1
        ''')
        
        row = cur.fetchone()
        if row:
            print(f"\n最新消息:")
            print(f"  消息ID: {row[0]}")
            print(f"  所属会话: {row[5] or 'N/A'}")
            print(f"  角色: {row[1]}")
            print(f"  消息类型: {row[2] or '未设置(default)'}")
            print(f"  内容: {row[3]}")
            print(f"  元数据: {row[4]}")
            print(f"  时间: {row[6]}")

print("\n" + "=" * 60)
print("总结:")
print("=" * 60)
print("✅ 1. chat_sessions 表: 存储会话元数据")
print("✅ 2. chat_messages 表: 存储所有消息（你的输入）")
print("✅ 3. entries 表: 存储长期记忆（话题总结后）")
print("✅ 4. sections 表: 存储段落信息")
print("\n💡 消息类型说明:")
print("   - msg_type=null: 未分类（默认）")
print("   - msg_type='question': 问题")
print("   - msg_type='answer': 回答")
print("   - msg_type='statement': 陈述")
print("   - msg_type='other': 其他")
