#!/usr/bin/env python3
"""持久化配置验证测试脚本。

测试内容:
1. Clash systemd 服务状态
2. Clash 自动切换到香港节点
3. CLASH_HTTP_PROXY 环境变量配置
4. Web 查询工具封装
"""

import os
import sys
import subprocess
from pathlib import Path

print("=" * 80)
print("持久化配置验证测试")
print("=" * 80)

# 测试 1: Clash 服务状态
print("\n[测试 1/4] 检查 Clash systemd 服务状态")
print("-" * 80)
result = subprocess.run(
    ["systemctl", "is-enabled", "clash.service"],
    capture_output=True,
    text=True
)
if result.returncode == 0:
    print(f"✓ Clash 服务已启用: {result.stdout.strip()}")
    service_active = subprocess.run(
        ["systemctl", "is-active", "clash.service"],
        capture_output=True,
        text=True
    ).stdout.strip()
    if service_active == "active":
        print(f"✓ Clash 服务正在运行: {service_active}")
    else:
        print(f"⚠ Clash 服务状态: {service_active} (需要手动启动)")
else:
    print(f"✗ Clash 服务未启用: {result.stderr}")

# 测试 2: CLASH_HTTP_PROXY 环境变量
print("\n[测试 2/4] 检查 CLASH_HTTP_PROXY 环境变量配置")
print("-" * 80)
if "CLASH_HTTP_PROXY" in os.environ:
    print(f"✓ CLASH_HTTP_PROXY 已配置: {os.environ['CLASH_HTTP_PROXY']}")
else:
    print("✗ CLASH_HTTP_PROXY 未在环境变量中找到")
    # 检查 .env 文件
    env_file = Path("/root/.env")
    if env_file.exists():
        content = env_file.read_text()
        if "CLASH_HTTP_PROXY" in content:
            print("✓ CLASH_HTTP_PROXY 已在 .env 文件中配置")
        else:
            print("✗ CLASH_HTTP_PROXY 未在 .env 文件中找到")
    else:
        print("✗ .env 文件不存在")

# 测试 3: Clash 自动切换脚本
print("\n[测试 3/4] 测试 Clash 自动切换脚本")
print("-" * 80)
script_path = Path("/root/scripts/auto_switch_hk_clash.py")
if script_path.exists():
    print(f"✓ 脚本存在: {script_path}")
    if os.access(script_path, os.X_OK):
        print("✓ 脚本有执行权限")
    else:
        print("✗ 脚本缺少执行权限")
        subprocess.run(["chmod", "+x", str(script_path)], check=True)
        print("✓ 已添加执行权限")
else:
    print(f"✗ 脚本不存在: {script_path}")

# 测试 4: Web 查询工具封装
print("\n[测试 4/4] 检查 Web 查询工具封装")
print("-" * 80)
tool_path = Path("/root/ai-factory/ai_factory/integrations/web_query_tool.py")
if tool_path.exists():
    print(f"✓ Web 查询工具封装存在: {tool_path}")

    # 检查关键组件
    content = tool_path.read_text()
    required_classes = ["WebQueryTool", "WebQueryConfig", "QueryMode"]
    required_functions = ["get_web_query_tool", "reset_web_query_tool"]

    for class_name in required_classes:
        if class_name in content:
            print(f"✓ 找到类: {class_name}")
        else:
            print(f"✗ 缺少类: {class_name}")

    for func_name in required_functions:
        if func_name in content:
            print(f"✓ 找到函数: {func_name}")
        else:
            print(f"✗ 缺少函数: {func_name}")
else:
    print(f"✗ Web 查询工具封装不存在: {tool_path}")

# 总结
print("\n" + "=" * 80)
print("验证完成")
print("=" * 80)
print("\n下一步操作:")
print("1. 启动 Clash 服务: systemctl start clash")
print("2. 测试自动切换: python /root/scripts/auto_switch_hk_clash.py")
print("3. 使用 Web 查询工具: from ai_factory.integrations.web_query_tool import get_web_query_tool")
print()
