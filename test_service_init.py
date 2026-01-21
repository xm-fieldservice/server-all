#!/usr/bin/env python3
"""测试服务初始化"""

import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'ai_factory'))

from ai_factory.agents.memory import (
    SessionService,
    SectionService,
    EntryService,
    VectorClient,
    create_memory_stack,
    initialize_monitoring,
    get_logger
)

try:
    print("1. 初始化监控系统...")
    initialize_monitoring(log_level="INFO", log_format="text")
    print("   ✓ 监控系统初始化成功")
except Exception as e:
    print(f"   ✗ 监控系统初始化失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

try:
    print("\n2. 创建记忆栈...")
    memory_service = create_memory_stack(
        enable_async_memory0=False,
        enable_llm_judgment=False
    )
    print("   ✓ 记忆栈创建成功")
except Exception as e:
    print(f"   ✗ 记忆栈创建失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

try:
    print("\n3. 获取各个服务...")
    session_service = memory_service.session_service
    section_service = memory_service.section_service
    entry_service = memory_service.entry_service
    print("   ✓ SessionService 获取成功")
    print("   ✓ SectionService 获取成功")
    print("   ✓ EntryService 获取成功")
except Exception as e:
    print(f"   ✗ 服务获取失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

try:
    print("\n4. 创建VectorClient...")
    vector_client = VectorClient()
    print("   ✓ VectorClient 创建成功")
except Exception as e:
    print(f"   ✗ VectorClient 创建失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "="*60)
print("所有服务初始化成功！")
print("="*60)
