"""
监控集成模块

将日志、指标和健康检查集成到现有服务中
"""

import asyncio
import psutil
from typing import Dict, Any, Optional
from datetime import datetime
from .logging_config import get_logger, setup_logging
from .metrics import (
    get_metrics_collector,
    TimedContext,
    increment_counter,
    set_gauge
)
from .health_check import (
    get_health_checker,
    register_health_check,
    HealthCheckResult,
    HealthStatus
)


logger = get_logger(__name__)


class MonitoringManager:
    """
    监控管理器
    
    管理日志、指标和健康检查的初始化和集成
    """
    
    def __init__(self):
        """初始化监控管理器"""
        self._initialized = False
        self._metrics_collector = None
        self._health_checker = None
    
    def initialize(
        self,
        log_level: str = "INFO",
        log_format: str = "text",
        log_file: Optional[str] = None
    ) -> None:
        """
        初始化监控系统
        
        Args:
            log_level: 日志级别
            log_format: 日志格式（text 或 json）
            log_file: 日志文件路径（可选）
        """
        if self._initialized:
            logger.warning("监控系统已经初始化，跳过")
            return
        
        # 初始化日志系统
        setup_logging(level=log_level, log_format=log_format, log_file=log_file)
        
        # 获取指标收集器和健康检查器
        self._metrics_collector = get_metrics_collector()
        self._health_checker = get_health_checker()
        
        # 注册系统健康检查
        self._register_system_health_checks()
        
        # 记录初始化事件
        increment_counter("monitoring.initialized")
        logger.info("监控系统初始化完成")
        
        self._initialized = True
    
    def _register_system_health_checks(self) -> None:
        """注册系统健康检查"""
        # 注册数据库健康检查
        async def check_database() -> HealthCheckResult:
            try:
                # 尝试连接数据库
                from .entry_service import EntryService
                entry_service = EntryService()
                
                # 简单查询测试
                entry_service._db.execute("SELECT 1")
                
                return HealthCheckResult(
                    name="database",
                    status=HealthStatus.HEALTHY,
                    message="数据库连接正常"
                )
            except Exception as e:
                return HealthCheckResult(
                    name="database",
                    status=HealthStatus.UNHEALTHY,
                    message=f"数据库连接失败: {str(e)}"
                )
        
        register_health_check("database", check_database)
        
        # 注册向量数据库健康检查
        async def check_vector_db() -> HealthCheckResult:
            try:
                from .vector_client import VectorClient
                vector_client = VectorClient()
                
                # 简单查询测试
                test_embedding = [0.0] * 1536
                vector_client.search_similar_entries(
                    query_embedding=test_embedding,
                    top_k=1
                )
                
                return HealthCheckResult(
                    name="vector_db",
                    status=HealthStatus.HEALTHY,
                    message="向量数据库连接正常"
                )
            except Exception as e:
                return HealthCheckResult(
                    name="vector_db",
                    status=HealthStatus.UNHEALTHY,
                    message=f"向量数据库连接失败: {str(e)}"
                )
        
        register_health_check("vector_db", check_vector_db)
        
        # 注册 LLM 服务健康检查
        async def check_llm_service() -> HealthCheckResult:
            try:
                from .llm_client import get_llm_client
                llm_client = get_llm_client()
                
                # 简单测试调用
                response = llm_client.chat_completion_sync(
                    messages=[{"role": "user", "content": "ping"}],
                    max_tokens=5,
                    temperature=0.0
                )
                
                return HealthCheckResult(
                    name="llm_service",
                    status=HealthStatus.HEALTHY,
                    message="LLM 服务连接正常"
                )
            except Exception as e:
                return HealthCheckResult(
                    name="llm_service",
                    status=HealthStatus.DEGRADED,
                    message=f"LLM 服务连接失败: {str(e)}"
                )
        
        register_health_check("llm_service", check_llm_service)
        
        # 注册 Embedding 服务健康检查
        async def check_embedding_service() -> HealthCheckResult:
            try:
                from .llm_client import get_llm_client
                llm_client = get_llm_client()
                
                # 简单测试调用
                embedding = llm_client.generate_embedding_sync("test")
                
                if embedding and len(embedding) > 0:
                    return HealthCheckResult(
                        name="embedding_service",
                        status=HealthStatus.HEALTHY,
                        message=f"Embedding 服务连接正常（向量维度: {len(embedding)}）"
                    )
                else:
                    return HealthCheckResult(
                        name="embedding_service",
                        status=HealthStatus.UNHEALTHY,
                        message="Embedding 服务返回空向量"
                    )
            except Exception as e:
                return HealthCheckResult(
                    name="embedding_service",
                    status=HealthStatus.DEGRADED,
                    message=f"Embedding 服务连接失败: {str(e)}"
                )
        
        register_health_check("embedding_service", check_embedding_service)
        
        # 注册系统资源健康检查
        async def check_system_resources() -> HealthCheckResult:
            try:
                # CPU 使用率
                cpu_percent = psutil.cpu_percent(interval=1)
                
                # 内存使用率
                memory = psutil.virtual_memory()
                memory_percent = memory.percent
                
                # 磁盘使用率
                disk = psutil.disk_usage('/')
                disk_percent = disk.percent
                
                # 判断健康状态
                status = HealthStatus.HEALTHY
                messages = []
                
                if cpu_percent > 80:
                    status = HealthStatus.DEGRADED
                    messages.append(f"CPU 使用率过高: {cpu_percent}%")
                
                if memory_percent > 80:
                    status = HealthStatus.DEGRADED
                    messages.append(f"内存使用率过高: {memory_percent}%")
                
                if disk_percent > 90:
                    status = HealthStatus.UNHEALTHY
                    messages.append(f"磁盘使用率过高: {disk_percent}%")
                
                if not messages:
                    messages.append("系统资源正常")
                
                return HealthCheckResult(
                    name="system_resources",
                    status=status,
                    message="; ".join(messages),
                    extra_data={
                        "cpu_percent": cpu_percent,
                        "memory_percent": memory_percent,
                        "disk_percent": disk_percent,
                        "memory_available_gb": round(memory.available / (1024**3), 2),
                        "disk_free_gb": round(disk.free / (1024**3), 2)
                    }
                )
            except Exception as e:
                return HealthCheckResult(
                    name="system_resources",
                    status=HealthStatus.UNHEALTHY,
                    message=f"系统资源检查失败: {str(e)}"
                )
        
        register_health_check("system_resources", check_system_resources)
    
    async def run_health_checks(self) -> Dict[str, Any]:
        """
        运行所有健康检查
        
        Returns:
            Dict: 健康报告
        """
        if not self._initialized:
            raise RuntimeError("监控系统未初始化")
        
        report = await self._health_checker.run_all_checks()
        return report.to_dict()
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """
        获取性能指标摘要
        
        Returns:
            Dict: 性能指标摘要
        """
        if not self._initialized:
            raise RuntimeError("监控系统未初始化")
        
        return self._metrics_collector.get_all_metrics()
    
    def record_operation(
        self,
        operation_name: str,
        duration_ms: float,
        success: bool = True,
        tags: Optional[Dict[str, str]] = None
    ) -> None:
        """
        记录操作指标
        
        Args:
            operation_name: 操作名称
            duration_ms: 持续时间（毫秒）
            success: 是否成功
            tags: 标签字典
        """
        if not self._initialized:
            return
        
        # 记录时间指标
        if tags is None:
            tags = {}
        tags['success'] = str(success)
        
        self._metrics_collector.record_timing(
            f"operations.{operation_name}",
            duration_ms,
            tags
        )
        
        # 记录计数器
        counter_name = f"operations.{operation_name}.{'success' if success else 'failure'}"
        increment_counter(counter_name)


# 全局监控管理器实例
_global_monitoring_manager: Optional[MonitoringManager] = None


def get_monitoring_manager() -> MonitoringManager:
    """
    获取全局监控管理器实例
    
    Returns:
        MonitoringManager: 全局监控管理器
    """
    global _global_monitoring_manager
    
    if _global_monitoring_manager is None:
        _global_monitoring_manager = MonitoringManager()
    
    return _global_monitoring_manager


def initialize_monitoring(
    log_level: str = "INFO",
    log_format: str = "text",
    log_file: Optional[str] = None
) -> MonitoringManager:
    """
    初始化监控系统（便捷方法）
    
    Args:
        log_level: 日志级别
        log_format: 日志格式
        log_file: 日志文件路径
    
    Returns:
        MonitoringManager: 监控管理器
    """
    manager = get_monitoring_manager()
    manager.initialize(log_level, log_format, log_file)
    return manager


# 装饰器：自动记录操作指标
def monitored(operation_name: str, tags: Optional[Dict[str, str]] = None):
    """
    装饰器：自动记录操作指标
    
    用法：
    @monitored("create_entry")
    async def create_entry(self, ...):
        ...
    """
    def decorator(func):
        async def async_wrapper(*args, **kwargs):
            start_time = datetime.utcnow()
            success = False
            
            try:
                result = await func(*args, **kwargs)
                success = True
                return result
            finally:
                duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
                
                manager = get_monitoring_manager()
                if manager._initialized:
                    manager.record_operation(
                        operation_name,
                        duration_ms,
                        success,
                        tags
                    )
        
        def sync_wrapper(*args, **kwargs):
            start_time = datetime.utcnow()
            success = False
            
            try:
                result = func(*args, **kwargs)
                success = True
                return result
            finally:
                duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
                
                manager = get_monitoring_manager()
                if manager._initialized:
                    manager.record_operation(
                        operation_name,
                        duration_ms,
                        success,
                        tags
                    )
        
        # 根据函数类型返回对应的包装器
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator
