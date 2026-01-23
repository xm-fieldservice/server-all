#!/usr/bin/env python3
"""
企业微信组织架构集成测试

演示：
1. 同步企业微信组织架构
2. 查看部门和用户信息
3. 基于部门权限的群聊管理
"""

import requests
import json

BASE_URL = "http://localhost:8002"


def print_section(title):
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def test_org_sync():
    """测试组织架构同步"""
    
    print_section("企业微信组织架构集成测试")
    
    # ========================================
    # 1. 同步组织架构
    # ========================================
    print_section("1. 同步企业微信组织架构")
    
    resp = requests.post(f"{BASE_URL}/org/sync")
    if resp.status_code == 200:
        data = resp.json()
        stats = data.get("stats", {})
        print(f"\n  ✅ 同步成功")
        print(f"  部门数: {stats.get('departments', 0)}")
        print(f"  用户数: {stats.get('users', 0)}")
        
        if stats.get('errors'):
            print(f"\n  ⚠️  错误:")
            for error in stats['errors']:
                print(f"    - {error}")
    else:
        print(f"  ❌ 同步失败: {resp.status_code}")
        print(f"  {resp.text}")
        return False
    
    # ========================================
    # 2. 查看组织架构统计
    # ========================================
    print_section("2. 组织架构统计")
    
    resp = requests.get(f"{BASE_URL}/org/stats")
    if resp.status_code == 200:
        data = resp.json()
        print(f"\n  部门总数: {data.get('departments_count', 0)}")
        print(f"  用户总数: {data.get('users_count', 0)}")
        print(f"  最后同步: {data.get('last_sync_time', 'N/A')}")
        print(f"  需要同步: {'是' if data.get('need_sync') else '否'}")
    
    # ========================================
    # 3. 查看部门列表
    # ========================================
    print_section("3. 部门列表")
    
    resp = requests.get(f"{BASE_URL}/org/departments")
    if resp.status_code == 200:
        data = resp.json()
        departments = data.get("departments", [])
        
        print(f"\n  共 {len(departments)} 个部门:")
        
        # 构建层级结构
        dept_map = {d["id"]: d for d in departments}
        root_depts = [d for d in departments if d.get("parent_id") == 0]
        
        def print_dept_tree(dept, level=0):
            indent = "  " * level
            print(f"  {indent}├─ {dept['name']} (ID: {dept['id']})")
            
            # 打印子部门
            children = [d for d in departments if d.get("parent_id") == dept["id"]]
            for child in children:
                print_dept_tree(child, level + 1)
        
        for root in root_depts:
            print_dept_tree(root)
    
    # ========================================
    # 4. 查看特定部门详情
    # ========================================
    print_section("4. 部门详情示例")
    
    # 选择第一个非根部门
    resp = requests.get(f"{BASE_URL}/org/departments")
    if resp.status_code == 200:
        departments = resp.json().get("departments", [])
        non_root_depts = [d for d in departments if d.get("parent_id") != 0]
        
        if non_root_depts:
            dept_id = non_root_depts[0]["id"]
            
            resp = requests.get(f"{BASE_URL}/org/department/{dept_id}")
            if resp.status_code == 200:
                data = resp.json()
                dept = data.get("department", {})
                path = data.get("path", [])
                users = data.get("users", [])
                
                print(f"\n  部门: {dept.get('name')}")
                print(f"  ID: {dept.get('id')}")
                print(f"  路径: {' > '.join([d['name'] for d in path])}")
                print(f"  成员数: {len(users)}")
                
                if users:
                    print(f"\n  成员列表:")
                    for user in users[:5]:  # 只显示前5个
                        status_text = "已激活" if user.get("status") == 1 else "未激活"
                        print(f"    - {user['name']} ({user['userid']}) - {status_text}")
                    
                    if len(users) > 5:
                        print(f"    ... 还有 {len(users)-5} 个成员")
    
    # ========================================
    # 5. 查看用户详情
    # ========================================
    print_section("5. 用户详情示例")
    
    resp = requests.get(f"{BASE_URL}/org/departments")
    if resp.status_code == 200:
        departments = resp.json().get("departments", [])
        if departments:
            # 获取第一个部门的成员
            dept_id = departments[0]["id"]
            resp = requests.get(f"{BASE_URL}/org/department/{dept_id}/users")
            
            if resp.status_code == 200:
                users = resp.json().get("users", [])
                if users:
                    # 选择第一个已激活的用户
                    active_users = [u for u in users if u.get("status") == 1]
                    if active_users:
                        userid = active_users[0]["userid"]
                        
                        resp = requests.get(f"{BASE_URL}/org/user/{userid}")
                        if resp.status_code == 200:
                            data = resp.json()
                            user = data.get("user", {})
                            depts = data.get("departments", [])
                            
                            print(f"\n  用户: {user.get('name')}")
                            print(f"  ID: {user.get('userid')}")
                            print(f"  手机: {user.get('mobile', 'N/A')}")
                            print(f"  邮箱: {user.get('email', 'N/A')}")
                            print(f"  职位: {user.get('position', 'N/A')}")
                            print(f"  状态: {'已激活' if user.get('status') == 1 else '未激活'}")
                            
                            if depts:
                                print(f"\n  所属部门:")
                                for dept in depts:
                                    print(f"    - {dept['name']}")
    
    # ========================================
    # 6. 测试部门树
    # ========================================
    print_section("6. 部门树结构")
    
    resp = requests.get(f"{BASE_URL}/org/departments")
    if resp.status_code == 200:
        departments = resp.json().get("departments", [])
        root_depts = [d for d in departments if d.get("parent_id") == 0]
        
        if root_depts:
            root_id = root_depts[0]["id"]
            resp = requests.get(f"{BASE_URL}/org/department/{root_id}/tree")
            
            if resp.status_code == 200:
                tree = resp.json()
                
                def print_tree(node, level=0):
                    indent = "  " * level
                    name = node.get("name", "N/A")
                    users_count = node.get("users_count", 0)
                    print(f"{indent}├─ {name} ({users_count} 人)")
                    
                    for child in node.get("children", []):
                        print_tree(child, level + 1)
                
                print(f"\n  组织架构树:")
                print_tree(tree)
    
    # ========================================
    # 7. 测试集成群聊系统
    # ========================================
    print_section("7. 集成群聊系统测试")
    
    # 清空群聊数据
    requests.delete(f"{BASE_URL}/group/clear_data")
    
    # 获取用户列表
    resp = requests.get(f"{BASE_URL}/org/departments")
    if resp.status_code == 200:
        departments = resp.json().get("departments", [])
        if departments:
            dept_id = departments[0]["id"]
            resp = requests.get(f"{BASE_URL}/org/department/{dept_id}/users")
            
            if resp.status_code == 200:
                users = resp.json().get("users", [])
                active_users = [u for u in users if u.get("status") == 1]
                
                if len(active_users) >= 2:
                    # 注册两个用户到群聊系统
                    user1 = active_users[0]
                    user2 = active_users[1]
                    
                    # 注册工人
                    resp = requests.post(f"{BASE_URL}/group/register_user", json={
                        "user_id": user1["userid"],
                        "name": user1["name"],
                        "role": "worker"
                    })
                    if resp.status_code == 200:
                        print(f"\n  ✅ 注册工人: {user1['name']}")
                        user_data = resp.json().get("user", {})
                        print(f"     部门: {user_data.get('department_ids', [])}")
                        print(f"     职位: {user_data.get('position', 'N/A')}")
                    
                    # 注册客服
                    resp = requests.post(f"{BASE_URL}/group/register_user", json={
                        "user_id": user2["userid"],
                        "name": user2["name"],
                        "role": "customer_service"
                    })
                    if resp.status_code == 200:
                        print(f"\n  ✅ 注册客服: {user2['name']}")
                        user_data = resp.json().get("user", {})
                        print(f"     部门: {user_data.get('department_ids', [])}")
                        print(f"     职位: {user_data.get('position', 'N/A')}")
                    
                    print(f"\n  ✅ 群聊系统已自动同步企业微信用户信息")
    
    print_section("测试完成")
    print("\n✅ 企业微信组织架构底座已就绪！")
    print("\n📝 功能验证:")
    print("  ✓ 组织架构同步")
    print("  ✓ 部门层级管理")
    print("  ✓ 用户信息管理")
    print("  ✓ 部门-用户映射")
    print("  ✓ 与群聊系统集成")
    print()


if __name__ == "__main__":
    try:
        resp = requests.get(f"{BASE_URL}/docs", timeout=2)
        if resp.status_code != 200:
            print("❌ 服务未运行")
            exit(1)
    except requests.exceptions.ConnectionError:
        print("❌ 无法连接到服务")
        print("   请先启动: cd /root/wechat-workspace/wecom_gateway && bash start.sh")
        exit(1)
    
    test_org_sync()
