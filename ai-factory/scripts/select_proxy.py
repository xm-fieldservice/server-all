#!/usr/bin/env python3
"""
自动测试 Mihomo 节点连通性，选择最优节点
"""

import requests
import json
import time
import sys

API_URL = "http://127.0.0.1:9097"
PROXIES = {
    "http": "http://127.0.0.1:7897",
    "https": "http://127.0.0.1:7897"
}
TEST_URL = "https://www.google.com"
TIMEOUT = 8

def get_proxies():
    """获取所有代理节点"""
    try:
        resp = requests.get(f"{API_URL}/proxies", timeout=5)
        data = resp.json()
        proxies = data.get("proxies", {})
        # 排除自动选择组
        return {k: v for k, v in proxies.items() 
                if k not in ["LanFanCloud ⛵", "故障转移", "DIRECT"] 
                and v.get("type") != "Selector"}
    except Exception as e:
        print(f"获取节点列表失败: {e}")
        return {}

def get_current_proxy():
    """获取当前选中的节点"""
    try:
        resp = requests.get(f"{API_URL}/proxies/LanFanCloud%20%E2%9B%B5", timeout=5)
        return resp.json().get("now")
    except:
        return None

def test_node(node_name):
    """测试单个节点的连通性"""
    try:
        # 切换到该节点
        requests.put(
            f"{API_URL}/proxies/LanFanCloud%20%E2%9B%B5",
            json={"name": node_name},
            timeout=5
        )
        time.sleep(0.5)
        
        # 测试连通性
        resp = requests.get(TEST_URL, proxies=PROXIES, timeout=TIMEOUT)
        if resp.status_code == 200:
            return True
    except:
        pass
    return False

def select_best_proxy():
    """选择最佳代理节点"""
    print("🚀 开始自动测速...")
    
    # 获取当前节点
    current = get_current_proxy()
    print(f"📌 当前节点: {current}")
    
    # 获取所有节点
    proxies = get_proxies()
    if not proxies:
        print("❌ 无法获取节点列表")
        return False
    
    node_names = list(proxies.keys())
    total = len(node_names)
    print(f"📋 共 {total} 个节点待测试")
    
    # 测试每个节点
    working_nodes = []
    for i, name in enumerate(node_names, 1):
        print(f"  [{i}/{total}] 测试 {name}...", end=" ", flush=True)
        
        if test_node(name):
            print("✅ 可用")
            working_nodes.append(name)
        else:
            print("❌ 超时")
    
    if not working_nodes:
        print("\n❌ 所有节点均不可用")
        return False
    
    # 选择第一个可用的节点
    best = working_nodes[0]
    print(f"\n✅ 选择最佳节点: {best}")
    
    # 验证选择
    current = get_current_proxy()
    if current == best:
        print(f"🎉 节点 {best} 已就绪！")
    else:
        print(f"⚠️ 当前节点是 {current}")
    
    return True

if __name__ == "__main__":
    select_best_proxy()
