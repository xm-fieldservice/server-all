"""
任务类型枚举定义
"""

from enum import Enum


class TaskType(Enum):
    """任务类型枚举"""

    NOTE = "note"  # 笔记整理入库
    RAG = "rag"    # RAG查询
    WEB = "web"    # Web查询
