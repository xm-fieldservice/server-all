"""
监控系统测试脚本

测试日志、指标和健康检查功能
"""

import asyncio
import sys
import os
import time

# 添加项目根目录到 Python 路径
test_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(test_dir)))
ai_factory_root = os.path.dirname(project_root)
sys.path.insert(0, ai_factory_root)
sys.path.insert(0, project_root)

from ai_factory.agents.memory import (
    initialize_monitoring,
    get_monitoring_manager,
    get_logger,
    TimedContext,
    increment_counter,
    set_gauge,
    run_health_checks,
    get_last_health_report,
    record_timing
)


async def test_logging():
    """测试日志系统"""
    print("\n=== 测试 1: 日志系统 ===")
    
    # 初始化日志系统（文本格式）
    initialize_monitoring(log_level="INFO", log_format="text")
    
    logger = get_logger("test_logger")
    logger.info("这是一条测试日志")
    logger.warning("这是一条警告日志")
    logger.error("这是一条错误日志")
    
    print("✓ 日志系统测试完成")


async def test_metrics():
    """测试指标收集"""
    print("\n=== 测试 2: 指标收集 ===")
    
    # 记录时间指标
    with TimedContext("test_operation", tags={"service": "memory"}):
        time.sleep(0.1)
    
    # 手动记录时间指标
    record_timing("manual_operation", 150.5, {"type": "sync"})
    
    # 增加计数器
    increment_counter("test_counter", 5)
    increment_counter("test_counter", 3)
    
    # 设置仪表盘
    set_gauge("active_connections", 42)
    
    # 获取指标摘要
    manager = get_monitoring_manager()
    metrics = manager.get_metrics_summary()
    
    print(f"✓ 计数器: {metrics['counters']}")
    print(f"✓ 仪表盘: {metrics['gauges']}")
    print(f"✓ 时间指标数量: {len(metrics['timings'])}")
    
    print("✓ 指标收集测试完成")


async def test_health_checks():
    """测试健康检查"""
    print("\n=== 测试 3: 健康检查 ===")
    
    # 运行健康检查
    report = await run_health_checks()
    
    print(f"✓ 整体状态: {report['status']}")
    print(f"✓ 检查数量: {len(report['checks'])}")
    
    for check in report['checks']:
        print(f"  - {check['name']}: {check['status']} ({check['message']})")
        if 'extra_data' in check and check['extra_data']:
            print(f"    额外数据: {check['extra_data']}")
    
    print("✓ 健康检查测试完成")


async def test_decorated_function():
    """测试装饰器"""
    print("\n=== 测试 4: 装饰器 ===")
    
    from ai_factory.agents.memory import monitored
    
    @monitored("test_operation", tags={"type": "test"})
    async def test_async_function(x: int) -> int:
        await asyncio.sleep(0.1)
        return x * 2
    
    @monitored("test_sync_operation", tags={"type": "sync"})
    def test_sync_function(x: int) -> int:
        time.sleep(0.1)
        return x * 2
    
    # 调用函数
    result1 = await test_async_function(5)
    print(f"✓ 异步函数结果: {result1}")
    
    result2 = test_sync_function(5)
    print(f"✓ 同步函数结果: {result2}")
    
    # 等待指标记录
    await asyncio.sleep(0.2)
    
    # 获取指标
    manager = get_monitoring_manager()
    metrics = manager.get_metrics_summary()
    
    print(f"✓ 操作指标数量: {len(metrics['timings'])}")
    print("✓ 装饰器测试完成")


async def test_json_logging():
    """测试 JSON 格式日志"""
    print("\n=== 测试 5: JSON 格式日志 ===")
    
    # 重新初始化为 JSON 格式
    manager = get_monitoring_manager()
    
    # 导入日志配置模块
    from ai_factory.agents.memory.logging_config import setup_logging
    setup_logging(level="INFO", log_format="json")
    
    logger = get_logger("json_test_logger")
    logger.info("这是一条 JSON 格式的测试日志")
    
    print("✓ JSON 格式日志测试完成")


async def main():
    """主函数"""
    try:
        # 测试 1: 日志系统
        await test_logging()
        
        # 测试 2: 指标收集
        await test_metrics()
        
        # 测试 3: 健康检查
        await test_health_checks()
        
        # 测试 4: 装饰器
        await test_decorated_function()
        
        # 测试 5: JSON 格式日志
        await test_json_logging()
        
        print("\n" + "=" * 60)
        print("✓ 所有测试通过！")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
