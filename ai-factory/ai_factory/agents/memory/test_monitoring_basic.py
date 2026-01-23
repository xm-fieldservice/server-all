"""
监控系统基础测试脚本

测试日志、指标和健康检查的基本功能（不依赖实际服务）
"""

import asyncio
import sys
import os
import time
import json

# 添加项目根目录到 Python 路径
test_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(test_dir)))
ai_factory_root = os.path.dirname(project_root)
sys.path.insert(0, ai_factory_root)
sys.path.insert(0, project_root)

from ai_factory.agents.memory import (
    setup_logging,
    get_logger,
    MetricsCollector,
    get_metrics_collector,
    TimedContext,
    record_timing,
    increment_counter,
    set_gauge,
    HealthStatus,
    HealthCheckResult,
    HealthChecker,
    get_health_checker,
    register_health_check,
    run_health_checks
)


async def test_logging_system():
    """测试日志系统"""
    print("\n=== 测试 1: 日志系统 ===")
    
    # 测试文本格式
    print("测试文本格式日志:")
    setup_logging(level="INFO", log_format="text")
    logger = get_logger("test_logger")
    logger.info("这是一条测试日志（文本格式）")
    logger.warning("这是一条警告日志")
    
    # 测试 JSON 格式
    print("\n测试 JSON 格式日志:")
    setup_logging(level="INFO", log_format="json")
    logger_json = get_logger("test_logger_json")
    logger_json.info("这是一条测试日志（JSON格式）")
    
    print("✓ 日志系统测试完成")


async def test_metrics_collector():
    """测试指标收集器"""
    print("\n=== 测试 2: 指标收集器 ===")
    
    collector = MetricsCollector()
    
    # 记录时间指标
    collector.record_timing("operation1", 100.5, {"tag": "value1"})
    collector.record_timing("operation1", 150.3, {"tag": "value2"})
    collector.record_timing("operation2", 200.1)
    
    # 增加计数器
    collector.increment_counter("counter1", 5)
    collector.increment_counter("counter1", 3)
    collector.increment_counter("counter2", 10)
    
    # 设置仪表盘
    collector.set_gauge("gauge1", 42.5)
    collector.set_gauge("gauge2", 100.0)
    
    # 获取统计信息
    stats1 = collector.get_metric_stats("operation1")
    print(f"operation1 统计:")
    print(f"  数量: {stats1.count}")
    print(f"  最小值: {stats1.min_value}ms")
    print(f"  最大值: {stats1.max_value}ms")
    print(f"  平均值: {stats1.avg_value}ms")
    print(f"  P95: {stats1.p95}ms")
    
    # 获取计数器和仪表盘
    print(f"\ncounter1: {collector.get_counter('counter1')}")
    print(f"gauge1: {collector.get_gauge('gauge1')}")
    
    # 获取所有指标
    all_metrics = collector.get_all_metrics()
    print(f"\n所有指标摘要:")
    print(f"  计数器: {all_metrics['counters']}")
    print(f"  仪表盘: {all_metrics['gauges']}")
    print(f"  时间指标数量: {len(all_metrics['timings'])}")
    
    print("✓ 指标收集器测试完成")


async def test_global_metrics():
    """测试全局指标收集"""
    print("\n=== 测试 3: 全局指标收集 ===")
    
    # 使用 TimedContext
    with TimedContext("timed_operation", tags={"type": "context"}):
        time.sleep(0.05)
    
    # 使用便捷函数
    record_timing("manual_operation", 123.4, {"type": "manual"})
    increment_counter("test_counter", 7)
    set_gauge("test_gauge", 99.9)
    
    # 获取全局指标收集器
    global_collector = get_metrics_collector()
    all_metrics = global_collector.get_all_metrics()
    
    print(f"全局指标收集器:")
    print(f"  计数器: {all_metrics['counters']}")
    print(f"  仪表盘: {all_metrics['gauges']}")
    print(f"  时间指标:")
    for name, stats in all_metrics['timings'].items():
        print(f"    {name}: avg={stats['avg_ms']}ms, count={stats['count']}")
    
    print("✓ 全局指标收集测试完成")


async def test_health_checker():
    """测试健康检查"""
    print("\n=== 测试 4: 健康检查 ===")
    
    # 创建健康检查器
    checker = HealthChecker()
    
    # 注册健康检查函数
    async def check_service1() -> HealthCheckResult:
        return HealthCheckResult(
            name="service1",
            status=HealthStatus.HEALTHY,
            message="服务1运行正常"
        )
    
    async def check_service2() -> HealthCheckResult:
        return HealthCheckResult(
            name="service2",
            status=HealthStatus.DEGRADED,
            message="服务2降级运行"
        )
    
    async def check_service3() -> HealthCheckResult:
        return HealthCheckResult(
            name="service3",
            status=HealthStatus.UNHEALTHY,
            message="服务3不可用"
        )
    
    checker.register_check("service1", check_service1)
    checker.register_check("service2", check_service2)
    checker.register_check("service3", check_service3)
    
    # 运行健康检查
    report = await checker.run_all_checks()
    
    print(f"整体状态: {report.overall_status.value}")
    print(f"检查数量: {len(report.checks)}")
    print(f"\n检查结果:")
    for check in report.checks:
        print(f"  {check.name}: {check.status.value} - {check.message} ({check.duration_ms:.2f}ms)")
    
    # 转换为字典
    report_dict = report.to_dict()
    print(f"\nJSON 格式报告:")
    print(json.dumps(report_dict, indent=2, ensure_ascii=False))
    
    print("✓ 健康检查测试完成")


async def test_global_health_checker():
    """测试全局健康检查"""
    print("\n=== 测试 5: 全局健康检查 ===")
    
    # 使用便捷函数注册检查
    async def check_test() -> HealthCheckResult:
        return HealthCheckResult(
            name="test",
            status=HealthStatus.HEALTHY,
            message="测试检查通过"
        )
    
    register_health_check("test_check", check_test)
    
    # 运行所有检查
    report = await run_health_checks()
    
    print(f"全局健康检查结果:")
    print(f"  状态: {report['status']}")
    print(f"  检查数量: {len(report['checks'])}")
    
    print("✓ 全局健康检查测试完成")


async def test_concurrent_operations():
    """测试并发操作"""
    print("\n=== 测试 6: 并发操作 ===")
    
    # 并发记录多个指标
    async def record_metrics(task_id: int):
        for i in range(5):
            record_timing(f"task_{task_id}", 100 + i, {"task": str(task_id)})
            increment_counter(f"task_{task_id}_counter")
        await asyncio.sleep(0.01)
    
    # 启动10个并发任务
    tasks = [record_metrics(i) for i in range(10)]
    await asyncio.gather(*tasks)
    
    # 获取指标
    global_collector = get_metrics_collector()
    all_metrics = global_collector.get_all_metrics()
    
    print(f"并发记录完成:")
    print(f"  时间指标数量: {len(all_metrics['timings'])}")
    print(f"  计数器数量: {len(all_metrics['counters'])}")
    
    print("✓ 并发操作测试完成")


async def main():
    """主函数"""
    try:
        # 测试 1: 日志系统
        await test_logging_system()
        
        # 测试 2: 指标收集器
        await test_metrics_collector()
        
        # 测试 3: 全局指标收集
        await test_global_metrics()
        
        # 测试 4: 健康检查
        await test_health_checker()
        
        # 测试 5: 全局健康检查
        await test_global_health_checker()
        
        # 测试 6: 并发操作
        await test_concurrent_operations()
        
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
