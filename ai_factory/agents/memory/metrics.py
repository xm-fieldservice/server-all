"""
性能指标收集模块

提供性能指标收集、聚合和报告功能
"""

import time
import threading
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict
import statistics


@dataclass
class MetricDataPoint:
    """指标数据点"""
    value: float
    timestamp: datetime
    tags: Dict[str, str] = field(default_factory=dict)


@dataclass
class MetricStats:
    """指标统计信息"""
    count: int
    sum_value: float
    min_value: float
    max_value: float
    avg_value: float
    p50: float
    p95: float
    p99: float


class MetricsCollector:
    """
    性能指标收集器
    
    收集、聚合和报告性能指标
    """
    
    def __init__(self, max_data_points: int = 10000):
        """
        初始化指标收集器
        
        Args:
            max_data_points: 每个指标保留的最大数据点数
        """
        self.max_data_points = max_data_points
        self._metrics: Dict[str, List[MetricDataPoint]] = defaultdict(list)
        self._counters: Dict[str, int] = defaultdict(int)
        self._gauges: Dict[str, float] = {}
        self._lock = threading.Lock()
    
    def record_timing(
        self,
        name: str,
        duration: float,
        tags: Optional[Dict[str, str]] = None
    ) -> None:
        """
        记录一个时间指标（毫秒）
        
        Args:
            name: 指标名称
            duration: 持续时间（毫秒）
            tags: 标签字典
        """
        with self._lock:
            self._metrics[name].append(MetricDataPoint(
                value=duration,
                timestamp=datetime.utcnow(),
                tags=tags or {}
            ))
            
            # 限制数据点数量
            if len(self._metrics[name]) > self.max_data_points:
                self._metrics[name] = self._metrics[name][-self.max_data_points:]
    
    def increment_counter(
        self,
        name: str,
        value: int = 1,
        tags: Optional[Dict[str, str]] = None
    ) -> None:
        """
        增加计数器
        
        Args:
            name: 指标名称
            value: 增加值
            tags: 标签字典（忽略，计数器不支持标签）
        """
        with self._lock:
            counter_key = name
            self._counters[counter_key] += value
    
    def set_gauge(
        self,
        name: str,
        value: float,
        tags: Optional[Dict[str, str]] = None
    ) -> None:
        """
        设置仪表盘值
        
        Args:
            name: 指标名称
            value: 值
            tags: 标签字典（忽略，仪表盘不支持标签）
        """
        with self._lock:
            gauge_key = name
            self._gauges[gauge_key] = value
    
    def get_metric_stats(
        self,
        name: str,
        time_window: Optional[timedelta] = None
    ) -> Optional[MetricStats]:
        """
        获取指标统计信息
        
        Args:
            name: 指标名称
            time_window: 时间窗口（None 表示所有数据）
        
        Returns:
            MetricStats: 统计信息（如果没有数据则返回 None）
        """
        with self._lock:
            if name not in self._metrics:
                return None
            
            data_points = self._metrics[name]
            
            # 过滤时间窗口
            if time_window:
                cutoff_time = datetime.utcnow() - time_window
                data_points = [
                    dp for dp in data_points
                    if dp.timestamp >= cutoff_time
                ]
            
            if not data_points:
                return None
            
            values = [dp.value for dp in data_points]
            
            sorted_values = sorted(values)
            n = len(sorted_values)
            
            return MetricStats(
                count=n,
                sum_value=sum(values),
                min_value=min(values),
                max_value=max(values),
                avg_value=statistics.mean(values) if n > 0 else 0.0,
                p50=sorted_values[int(n * 0.5)] if n > 0 else 0.0,
                p95=sorted_values[int(n * 0.95)] if n > 0 else 0.0,
                p99=sorted_values[int(n * 0.99)] if n > 0 else 0.0
            )
    
    def get_counter(self, name: str) -> int:
        """
        获取计数器值
        
        Args:
            name: 指标名称
        
        Returns:
            int: 计数器值（如果不存在则返回 0）
        """
        with self._lock:
            return self._counters.get(name, 0)
    
    def get_gauge(self, name: str) -> Optional[float]:
        """
        获取仪表盘值
        
        Args:
            name: 指标名称
        
        Returns:
            float: 仪表盘值（如果不存在则返回 None）
        """
        with self._lock:
            return self._gauges.get(name)
    
    def get_all_metrics(self) -> Dict[str, Any]:
        """
        获取所有指标的摘要
        
        Returns:
            Dict: 所有指标的摘要
        """
        with self._lock:
            result = {
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
                "timings": {}
            }
            
            # 为每个 timing 指标生成统计
            for name in self._metrics.keys():
                stats = self.get_metric_stats(name)
                if stats:
                    result["timings"][name] = {
                        "count": stats.count,
                        "sum_ms": round(stats.sum_value, 2),
                        "min_ms": round(stats.min_value, 2),
                        "max_ms": round(stats.max_value, 2),
                        "avg_ms": round(stats.avg_value, 2),
                        "p50_ms": round(stats.p50, 2),
                        "p95_ms": round(stats.p95, 2),
                        "p99_ms": round(stats.p99, 2)
                    }
            
            return result
    
    def reset_metrics(self) -> None:
        """重置所有指标"""
        with self._lock:
            self._metrics.clear()
            self._counters.clear()
            self._gauges.clear()


# 全局指标收集器实例
_global_metrics_collector: Optional[MetricsCollector] = None
_global_lock = threading.Lock()


def get_metrics_collector() -> MetricsCollector:
    """
    获取全局指标收集器实例
    
    Returns:
        MetricsCollector: 全局指标收集器
    """
    global _global_metrics_collector
    
    if _global_metrics_collector is None:
        with _global_lock:
            if _global_metrics_collector is None:
                _global_metrics_collector = MetricsCollector()
    
    return _global_metrics_collector


class TimedContext:
    """
    计时上下文管理器
    
    用法：
    with TimedContext("operation_name", tags={"service": "memory"}):
        do_something()
    """
    
    def __init__(
        self,
        name: str,
        tags: Optional[Dict[str, str]] = None,
        collector: Optional[MetricsCollector] = None
    ):
        """
        初始化计时上下文
        
        Args:
            name: 指标名称
            tags: 标签字典
            collector: 指标收集器（默认使用全局实例）
        """
        self.name = name
        self.tags = tags
        self.collector = collector or get_metrics_collector()
        self.start_time: Optional[float] = None
    
    def __enter__(self) -> 'TimedContext':
        """进入上下文"""
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """退出上下文"""
        if self.start_time is not None:
            duration = (time.time() - self.start_time) * 1000  # 转换为毫秒
            self.collector.record_timing(self.name, duration, self.tags)


def record_timing(name: str, duration_ms: float, tags: Optional[Dict[str, str]] = None) -> None:
    """
    记录一个时间指标
    
    Args:
        name: 指标名称
        duration_ms: 持续时间（毫秒）
        tags: 标签字典
    """
    collector = get_metrics_collector()
    collector.record_timing(name, duration_ms, tags)


def increment_counter(name: str, value: int = 1) -> None:
    """
    增加计数器
    
    Args:
        name: 指标名称
        value: 增加值
    """
    collector = get_metrics_collector()
    collector.increment_counter(name, value)


def set_gauge(name: str, value: float) -> None:
    """
    设置仪表盘值
    
    Args:
        name: 指标名称
        value: 值
    """
    collector = get_metrics_collector()
    collector.set_gauge(name, value)
