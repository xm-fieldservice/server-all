"""
健康检查模块

提供健康检查接口和状态报告功能
"""

import asyncio
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import threading


class HealthStatus(str, Enum):
    """健康状态"""
    HEALTHY = "healthy"         # 健康
    DEGRADED = "degraded"       # 降级（部分功能可用）
    UNHEALTHY = "unhealthy"     # 不健康（不可用）


@dataclass
class HealthCheckResult:
    """健康检查结果"""
    name: str
    status: HealthStatus
    message: str
    duration_ms: float = 0.0
    extra_data: Dict[str, Any] = field(default_factory=dict)
    checked_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class HealthReport:
    """健康报告"""
    overall_status: HealthStatus
    checks: List[HealthCheckResult]
    timestamp: datetime = field(default_factory=datetime.utcnow)
    version: str = "1.0.0"
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "status": self.overall_status.value,
            "timestamp": self.timestamp.isoformat() + "Z",
            "version": self.version,
            "checks": [
                {
                    "name": check.name,
                    "status": check.status.value,
                    "message": check.message,
                    "duration_ms": round(check.duration_ms, 2),
                    "extra_data": check.extra_data,
                    "checked_at": check.checked_at.isoformat() + "Z"
                }
                for check in self.checks
            ]
        }


class HealthChecker:
    """
    健康检查器
    
    管理多个健康检查并提供整体健康报告
    """
    
    def __init__(self):
        """初始化健康检查器"""
        self._checks: Dict[str, Callable] = {}
        self._last_results: Dict[str, HealthCheckResult] = {}
        self._lock = threading.Lock()
    
    def register_check(self, name: str, check_func: Callable) -> None:
        """
        注册健康检查函数
        
        Args:
            name: 检查名称
            check_func: 检查函数，应返回 HealthCheckResult
        """
        with self._lock:
            self._checks[name] = check_func
    
    def unregister_check(self, name: str) -> None:
        """
        取消注册健康检查函数
        
        Args:
            name: 检查名称
        """
        with self._lock:
            self._checks.pop(name, None)
            self._last_results.pop(name, None)
    
    async def run_check(self, name: str) -> HealthCheckResult:
        """
        运行单个健康检查
        
        Args:
            name: 检查名称
        
        Returns:
            HealthCheckResult: 检查结果
        """
        if name not in self._checks:
            return HealthCheckResult(
                name=name,
                status=HealthStatus.UNHEALTHY,
                message=f"Check '{name}' not registered"
            )
        
        start_time = datetime.utcnow()
        
        try:
            # 如果检查函数是协程函数，则使用 await
            if asyncio.iscoroutinefunction(self._checks[name]):
                result = await self._checks[name]()
            else:
                result = self._checks[name]()
            
            # 确保返回的是 HealthCheckResult
            if not isinstance(result, HealthCheckResult):
                result = HealthCheckResult(
                    name=name,
                    status=HealthStatus.UNHEALTHY,
                    message=f"Check function returned invalid type: {type(result)}"
                )
            else:
                result.name = name  # 确保名称正确
            
        except Exception as e:
            result = HealthCheckResult(
                name=name,
                status=HealthStatus.UNHEALTHY,
                message=f"Check failed with exception: {str(e)}"
            )
        
        # 计算持续时间
        duration = (datetime.utcnow() - start_time).total_seconds() * 1000
        result.duration_ms = duration
        result.checked_at = datetime.utcnow()
        
        # 缓存结果
        with self._lock:
            self._last_results[name] = result
        
        return result
    
    async def run_all_checks(self) -> HealthReport:
        """
        运行所有健康检查
        
        Returns:
            HealthReport: 健康报告
        """
        check_results = []
        
        # 并发运行所有检查
        tasks = [self.run_check(name) for name in self._checks.keys()]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in results:
            if isinstance(result, Exception):
                check_results.append(HealthCheckResult(
                    name="unknown",
                    status=HealthStatus.UNHEALTHY,
                    message=f"Check raised exception: {str(result)}"
                ))
            else:
                check_results.append(result)
        
        # 确定整体状态
        overall_status = HealthStatus.HEALTHY
        for result in check_results:
            if result.status == HealthStatus.UNHEALTHY:
                overall_status = HealthStatus.UNHEALTHY
                break
            elif result.status == HealthStatus.DEGRADED:
                overall_status = HealthStatus.DEGRADED
        
        return HealthReport(
            overall_status=overall_status,
            checks=check_results
        )
    
    def get_last_report(self) -> Optional[HealthReport]:
        """
        获取最后一次的健康报告
        
        Returns:
            HealthReport: 健康报告（如果没有检查过则返回 None）
        """
        with self._lock:
            if not self._last_results:
                return None
            
            # 确定整体状态
            overall_status = HealthStatus.HEALTHY
            for result in self._last_results.values():
                if result.status == HealthStatus.UNHEALTHY:
                    overall_status = HealthStatus.UNHEALTHY
                    break
                elif result.status == HealthStatus.DEGRADED:
                    overall_status = HealthStatus.DEGRADED
            
            return HealthReport(
                overall_status=overall_status,
                checks=list(self._last_results.values())
            )


# 全局健康检查器实例
_global_health_checker: Optional[HealthChecker] = None
_global_lock = threading.Lock()


def get_health_checker() -> HealthChecker:
    """
    获取全局健康检查器实例
    
    Returns:
        HealthChecker: 全局健康检查器
    """
    global _global_health_checker
    
    if _global_health_checker is None:
        with _global_lock:
            if _global_health_checker is None:
                _global_health_checker = HealthChecker()
    
    return _global_health_checker


def register_health_check(name: str, check_func: Callable) -> None:
    """
    注册健康检查函数（便捷方法）
    
    Args:
        name: 检查名称
        check_func: 检查函数
    """
    checker = get_health_checker()
    checker.register_check(name, check_func)


def unregister_health_check(name: str) -> None:
    """
    取消注册健康检查函数（便捷方法）
    
    Args:
        name: 检查名称
    """
    checker = get_health_checker()
    checker.unregister_check(name)


async def run_health_checks() -> HealthReport:
    """
    运行所有健康检查（便捷方法）
    
    Returns:
        HealthReport: 健康报告
    """
    checker = get_health_checker()
    return await checker.run_all_checks()


def get_last_health_report() -> Optional[HealthReport]:
    """
    获取最后一次的健康报告（便捷方法）
    
    Returns:
        HealthReport: 健康报告（如果没有检查过则返回 None）
    """
    checker = get_health_checker()
    return checker.get_last_report()
