#!/usr/bin/env python3
"""
Agent记忆系统调试API测试脚本
用于快速验证API功能
"""

import requests
import json
import time

BASE_URL = "http://localhost:8001"

def print_response(response, title):
    """打印响应结果"""
    print(f"\n{'='*60}")
    print(f"{title}")
    print(f"{'='*60}")
    print(f"状态码: {response.status_code}")
    try:
        print(f"响应内容:\n{json.dumps(response.json(), indent=2, ensure_ascii=False)}")
    except:
        print(f"响应内容: {response.text}")

def test_health_check():
    """测试健康检查"""
    print("\n测试1: 健康检查")
    response = requests.get(f"{BASE_URL}/api/memory/health")
    print_response(response, "健康检查")
    return response.status_code == 200

def test_create_session():
    """测试创建会话"""
    print("\n测试2: 创建会话")
    data = {
        "user_id": "user_test",
        "assistant_id": "assistant_test",
        "title": "测试会话",
        "department": "测试部"
    }
    response = requests.post(f"{BASE_URL}/api/memory/sessions", json=data)
    print_response(response, "创建会话")
    
    if response.status_code == 200:
        return response.json().get("session_id")
    return None

def test_get_sessions():
    """测试获取会话列表"""
    print("\n测试3: 获取会话列表")
    response = requests.get(f"{BASE_URL}/api/memory/sessions?limit=10")
    print_response(response, "获取会话列表")
    return response.status_code == 200

def test_append_message(session_id):
    """测试添加消息"""
    if not session_id:
        print("\n测试4: 添加消息 - 跳过（无会话ID）")
        return None
    
    print("\n测试4: 添加消息")
    data = {
        "role": "user",
        "content": "测试消息：你好，介绍一下AI工厂",
        "agent_id": "assistant_test",
        "metadata_json": {"entry_type": "note"}
    }
    response = requests.post(f"{BASE_URL}/api/memory/sessions/{session_id}/messages", json=data)
    print_response(response, "添加消息")
    
    if response.status_code == 200:
        return response.json().get("message_id")
    return None

def test_get_messages(session_id):
    """测试获取消息列表"""
    if not session_id:
        print("\n测试5: 获取消息列表 - 跳过（无会话ID）")
        return False
    
    print("\n测试5: 获取消息列表")
    response = requests.get(f"{BASE_URL}/api/memory/sessions/{session_id}/messages")
    print_response(response, "获取消息列表")
    return response.status_code == 200

def test_search_entries():
    """测试搜索条目"""
    print("\n测试6: 搜索条目")
    response = requests.get(f"{BASE_URL}/api/memory/entries/search?query=AI工厂&top_k=5")
    print_response(response, "搜索条目")
    return response.status_code == 200

def test_trigger_section(session_id):
    """测试触发段落整理"""
    if not session_id:
        print("\n测试7: 触发段落整理 - 跳过（无会话ID）")
        return False
    
    print("\n测试7: 触发段落整理")
    data = {"trigger_type": "manual"}
    response = requests.post(f"{BASE_URL}/api/memory/sessions/{session_id}/sections/trigger", json=data)
    print_response(response, "触发段落整理")
    return response.status_code == 200

def test_get_metrics():
    """测试获取系统指标"""
    print("\n测试8: 获取系统指标")
    response = requests.get(f"{BASE_URL}/api/memory/metrics")
    print_response(response, "获取系统指标")
    return response.status_code == 200

def main():
    """主测试函数"""
    print("=" * 60)
    print("Agent记忆系统调试API测试")
    print("=" * 60)
    print(f"API地址: {BASE_URL}")
    
    # 检查服务是否启动
    try:
        response = requests.get(BASE_URL, timeout=5)
        if response.status_code != 200:
            print("\n错误: API服务未正常启动")
            return
    except requests.exceptions.ConnectionError:
        print("\n错误: 无法连接到API服务")
        print("请先运行: bash start_memory_debug.sh")
        return
    
    # 运行测试
    session_id = None
    
    test_health_check()
    time.sleep(0.5)
    
    session_id = test_create_session()
    time.sleep(0.5)
    
    test_get_sessions()
    time.sleep(0.5)
    
    test_append_message(session_id)
    time.sleep(0.5)
    
    test_get_messages(session_id)
    time.sleep(0.5)
    
    test_search_entries()
    time.sleep(0.5)
    
    test_trigger_section(session_id)
    time.sleep(0.5)
    
    test_get_metrics()
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)
    print("\n请在浏览器中打开:")
    print("file:///home/ecs-assist-user/ai-factory/ai_factory/web/agent_memory_debug.html")
    print("\n或者访问:")
    print("http://localhost:8000/docs")

if __name__ == "__main__":
    main()
