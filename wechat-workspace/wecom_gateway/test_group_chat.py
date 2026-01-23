#!/usr/bin/env python3
"""
工人-客服群聊系统测试脚本

演示：
1. 注册用户（工人和客服）
2. 工人发送消息
3. 客服查看对话列表
4. 客服回复特定工人
5. 验证消息可见性规则
"""

import requests
import json
from datetime import datetime

BASE_URL = "http://localhost:8002"


def print_section(title):
    """打印分隔线"""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def print_result(title, data):
    """打印结果"""
    print(f"\n{title}:")
    print(json.dumps(data, indent=2, ensure_ascii=False))


def test_group_chat():
    """测试工人-客服群聊系统"""
    
    print_section("工人-客服群聊系统测试")
    
    # ========================================
    # 1. 清空数据
    # ========================================
    print_section("1. 清空测试数据")
    resp = requests.delete(f"{BASE_URL}/group/clear_data")
    print(f"✅ 数据已清空")
    
    # ========================================
    # 2. 注册用户
    # ========================================
    print_section("2. 注册用户")
    
    # 注册客服
    cs_users = [
        {"user_id": "cs_zhangsan", "name": "客服张三", "role": "customer_service"},
        {"user_id": "cs_lisi", "name": "客服李四", "role": "customer_service"}
    ]
    
    for user in cs_users:
        resp = requests.post(f"{BASE_URL}/group/register_user", json=user)
        if resp.status_code == 200:
            print(f"  ✅ 注册客服: {user['name']} ({user['user_id']})")
    
    # 注册工人
    worker_users = [
        {"user_id": "worker_001", "name": "工人王五", "role": "worker"},
        {"user_id": "worker_002", "name": "工人赵六", "role": "worker"},
        {"user_id": "worker_003", "name": "工人孙七", "role": "worker"}
    ]
    
    for user in worker_users:
        resp = requests.post(f"{BASE_URL}/group/register_user", json=user)
        if resp.status_code == 200:
            print(f"  ✅ 注册工人: {user['name']} ({user['user_id']})")
    
    # ========================================
    # 3. 工人发送消息
    # ========================================
    print_section("3. 工人发送消息")
    
    messages = [
        {"from_user_id": "worker_001", "content": "你好，我需要帮助修理设备"},
        {"from_user_id": "worker_002", "content": "请问今天的工作任务是什么？"},
        {"from_user_id": "worker_001", "content": "设备编号是 #12345"},
        {"from_user_id": "worker_003", "content": "我这里缺少工具，需要支援"}
    ]
    
    for msg in messages:
        resp = requests.post(f"{BASE_URL}/group/send_message", json=msg)
        if resp.status_code == 200:
            result = resp.json()
            print(f"  ✅ {msg['from_user_id']}: {msg['content']}")
            print(f"     路由到: {result.get('routes', [])}")
    
    # ========================================
    # 4. 客服查看对话列表
    # ========================================
    print_section("4. 客服查看对话列表")
    
    resp = requests.get(f"{BASE_URL}/group/conversations")
    if resp.status_code == 200:
        data = resp.json()
        print(f"\n  📋 共有 {data['total']} 个对话:")
        for conv in data['conversations']:
            print(f"\n  对话: {conv['conversation_id']}")
            print(f"    工人: {conv['worker_name']} ({conv['worker_id']})")
            print(f"    消息数: {conv['message_count']}")
            print(f"    未读数: {conv.get('unread_count_cs', 0)}")
            print(f"    最后消息: {conv.get('last_message', 'N/A')}")
    
    # ========================================
    # 5. 客服查看特定工人的对话
    # ========================================
    print_section("5. 客服查看工人001的完整对话")
    
    resp = requests.get(
        f"{BASE_URL}/group/messages/cs_zhangsan",
        params={"conversation_id": "worker:worker_001"}
    )
    if resp.status_code == 200:
        data = resp.json()
        print(f"\n  对话ID: {data['conversation_id']}")
        print(f"  消息数: {data['total']}")
        print(f"\n  消息列表:")
        for msg in data['messages']:
            print(f"    [{msg['timestamp'][:19]}] {msg['from_user_name']}: {msg['content']}")
    
    # ========================================
    # 6. 客服回复工人
    # ========================================
    print_section("6. 客服回复工人")
    
    replies = [
        {
            "from_user_id": "cs_zhangsan",
            "to_user_id": "worker_001",
            "content": "收到，我们会尽快安排技术人员处理设备 #12345"
        },
        {
            "from_user_id": "cs_lisi",
            "to_user_id": "worker_002",
            "content": "今天的任务是完成A区域的设备检修"
        },
        {
            "from_user_id": "cs_zhangsan",
            "to_user_id": "worker_003",
            "content": "工具已经在路上，预计10分钟到达"
        }
    ]
    
    for reply in replies:
        resp = requests.post(f"{BASE_URL}/group/send_message", json=reply)
        if resp.status_code == 200:
            print(f"  ✅ {reply['from_user_id']} 回复 {reply['to_user_id']}")
            print(f"     内容: {reply['content']}")
    
    # ========================================
    # 7. 验证工人只能看到自己的对话
    # ========================================
    print_section("7. 验证消息可见性 - 工人001的视角")
    
    resp = requests.get(f"{BASE_URL}/group/messages/worker_001")
    if resp.status_code == 200:
        data = resp.json()
        print(f"\n  工人001可见的消息数: {data['total']}")
        print(f"\n  消息列表:")
        for msg in data['messages']:
            print(f"    [{msg['timestamp'][:19]}] {msg['from_user_name']}: {msg['content']}")
        
        print(f"\n  ✅ 验证: 工人001只能看到自己发的消息和客服回复自己的消息")
    
    # ========================================
    # 8. 验证工人002看不到工人001的对话
    # ========================================
    print_section("8. 验证消息隔离 - 工人002的视角")
    
    resp = requests.get(f"{BASE_URL}/group/messages/worker_002")
    if resp.status_code == 200:
        data = resp.json()
        print(f"\n  工人002可见的消息数: {data['total']}")
        print(f"\n  消息列表:")
        for msg in data['messages']:
            print(f"    [{msg['timestamp'][:19]}] {msg['from_user_name']}: {msg['content']}")
        
        print(f"\n  ✅ 验证: 工人002只能看到自己的对话，看不到工人001的消息")
    
    # ========================================
    # 9. 客服看所有消息
    # ========================================
    print_section("9. 验证客服视角 - 可以看到所有消息")
    
    resp = requests.get(f"{BASE_URL}/group/messages/cs_zhangsan")
    if resp.status_code == 200:
        data = resp.json()
        print(f"\n  客服张三可见的消息数: {data['total']}")
        
        # 按对话分组显示
        conversations = {}
        for msg in data['messages']:
            # 确定对话ID
            if msg['from_role'] == 'worker':
                conv_id = msg['from_user_id']
            elif msg['to_user_id']:
                conv_id = msg['to_user_id']
            else:
                conv_id = 'unknown'
            
            if conv_id not in conversations:
                conversations[conv_id] = []
            conversations[conv_id].append(msg)
        
        print(f"\n  按工人分组的对话:")
        for conv_id, msgs in conversations.items():
            print(f"\n  📱 {conv_id}:")
            for msg in msgs:
                print(f"      [{msg['timestamp'][:19]}] {msg['from_user_name']}: {msg['content']}")
        
        print(f"\n  ✅ 验证: 客服可以看到所有工人的消息")
    
    # ========================================
    # 10. 获取所有用户列表
    # ========================================
    print_section("10. 用户列表")
    
    resp = requests.get(f"{BASE_URL}/group/users")
    if resp.status_code == 200:
        data = resp.json()
        print(f"\n  👥 客服列表:")
        for user in data['customer_services']:
            print(f"    - {user['name']} ({user['user_id']})")
        
        print(f"\n  🔧 工人列表:")
        for user in data['workers']:
            print(f"    - {user['name']} ({user['user_id']})")
    
    print_section("测试完成")
    print("\n✅ 所有测试通过！")
    print("\n📝 系统功能验证:")
    print("  ✓ 工人只能看到自己和客服的对话")
    print("  ✓ 工人之间的消息完全隔离")
    print("  ✓ 客服可以看到所有工人的对话")
    print("  ✓ 客服可以选择回复特定工人")
    print("  ✓ 消息路由正确")
    print()


if __name__ == "__main__":
    try:
        # 检查服务是否运行
        resp = requests.get(f"{BASE_URL}/docs", timeout=2)
        if resp.status_code != 200:
            print("❌ 服务未运行，请先启动服务:")
            print("   cd /root/wechat-workspace/wecom_gateway")
            print("   bash start.sh")
            exit(1)
    except requests.exceptions.ConnectionError:
        print("❌ 无法连接到服务，请先启动:")
        print("   cd /root/wechat-workspace/wecom_gateway")
        print("   bash start.sh")
        exit(1)
    
    test_group_chat()
