"""
日志配置模块

提供结构化日志配置和日志记录器
"""

import logging
import sys
from typing import Optional
from datetime import datetime
import json
from pathlib import Path


class StructuredFormatter(logging.Formatter):
    """
    结构化日志格式化器
    
    将日志记录格式化为 JSON 格式，便于解析和分析
    """
    
    def format(self, record: logging.LogRecord) -> str:
        """
        格式化日志记录
        
        Args:
            record: 日志记录
        
        Returns:
            str: JSON 格式的日志字符串
        """
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # 添加异常信息（如果有）
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        # 添加自定义字段（如果有）
        if hasattr(record, 'extra_data'):
            log_data["extra"] = record.extra_data
        
        # 添加性能指标（如果有）
        if hasattr(record, 'metrics'):
            log_data["metrics"] = record.metrics
        
        return json.dumps(log_data, ensure_ascii=False)


class TextFormatter(logging.Formatter):
    """
    文本日志格式化器
    
    将日志记录格式化为人类可读的文本格式
    """
    
    def __init__(self):
        super().__init__(
            fmt='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    
    def format(self, record: logging.LogRecord) -> str:
        result = super().format(record)
        
        # 添加性能指标（如果有）
        if hasattr(record, 'metrics'):
            metrics_str = " | " + " ".join([f"{k}={v}" for k, v in record.metrics.items()])
            result += metrics_str
        
        return result


def setup_logging(
    level: str = "INFO",
    log_format: str = "text",  # "text" or "json"
    log_file: Optional[str] = None
) -> logging.Logger:
    """
    配置日志系统
    
    Args:
        level: 日志级别（DEBUG, INFO, WARNING, ERROR, CRITICAL）
        log_format: 日志格式（text 或 json）
        log_file: 日志文件路径（可选）
    
    Returns:
        logging.Logger: 配置好的根日志记录器
    """
    # 清除现有的 handlers
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    
    # 设置日志级别
    log_level = getattr(logging, level.upper(), logging.INFO)
    root_logger.setLevel(log_level)
    
    # 选择格式化器
    if log_format == "json":
        formatter = StructuredFormatter()
    else:
        formatter = TextFormatter()
    
    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # 文件处理器（如果指定了文件路径）
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    
    # 设置第三方库的日志级别（避免过多日志）
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    
    return root_logger


def get_logger(name: str) -> logging.Logger:
    """
    获取指定名称的日志记录器
    
    Args:
        name: 日志记录器名称
    
    Returns:
        logging.Logger: 日志记录器
    """
    return logging.getLogger(name)


def add_extra_data(record: logging.LogRecord, extra_data: dict) -> None:
    """
    为日志记录添加额外数据
    
    Args:
        record: 日志记录
        extra_data: 额外数据字典
    """
    if not hasattr(record, 'extra_data'):
        record.extra_data = {}
    record.extra_data.update(extra_data)


def add_metrics(record: logging.LogRecord, metrics: dict) -> None:
    """
    为日志记录添加性能指标
    
    Args:
        record: 日志记录
        metrics: 性能指标字典
    """
    if not hasattr(record, 'metrics'):
        record.metrics = {}
    record.metrics.update(metrics)
