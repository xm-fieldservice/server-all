"""Agent Memory Module.

Provides a complete memory stack for agents, including:
- SessionService: Short-term conversation memory
- SectionService: Section summarization and organization
- EntryService: Unified entries storage and retrieval
- Memory0Service: Long-term memory governance
- MemoryService: Facade for all memory operations
- QACacheService: Q&A cache for fast response to repeated questions
- SectionAgent: Multi-agent semantic segmentation for section boundary detection
- VectorClient: Vector search abstraction
- LLMClient: LLM and Embedding service client for remote APIs
- TaskQueue: Task queue for asynchronous Memory0 processing
- Memory0Worker: Background worker for consuming Memory0 tasks

Based on `Agent记忆系统详细设计与施工文档.md`.
"""

from __future__ import annotations

from typing import Optional, List

from .session_service import SessionService, SessionInfo, MessageInfo
from .section_service import SectionService, SectionSummary, SectionInfo, SectionTrigger
# SectionService 的 check_and_trigger_section 方法通过 SectionService 类直接使用
from .entry_service import EntryService
from .memory0_service import (
    Memory0Service,
    MemoryRelation,
    MemoryCandidate,
    MemoryResult,
)
from .memory_service import (
    MemoryService,
    ContextSnippet,
    ContextForTurn,
)
from .api.client import MemoryClient
from .registry import AgentInstanceRegistry, AgentInstanceStatus, AgentInstanceMetadata
from .vector_client import VectorClient
from .llm_client import LLMClient, get_llm_client, LLMConfig, EmbeddingConfig
from .task_queue import TaskQueue, Memory0Task, TaskStatus, TaskType, get_task_queue
from .memory_worker import Memory0Worker, WorkerConfig, create_worker
from .qa_cache_service import QACacheService, QAStatus, AnswerType, QAInfo, QAStats
from .section_agent import (
    SectionAgent,
    SectionDecision,
    SectionBoundary,
    SectionProposal,
    SectionReview
)
from .config import (
    Memory0Profile,
    Memory0Config,
    AgentMemoryConfig,
    ConfigManager,
    get_config_manager,
    register_default_agents,
    DEFAULT_CONFIG,
    MEMORY0_PROFILES
)
from .metrics import (
    MetricsCollector,
    TimedContext,
    get_metrics_collector,
    record_timing,
    increment_counter,
    set_gauge
)
from .health_check import (
    HealthStatus,
    HealthCheckResult,
    HealthReport,
    HealthChecker,
    get_health_checker,
    register_health_check,
    unregister_health_check,
    run_health_checks,
    get_last_health_report
)
from .logging_config import (
    setup_logging,
    get_logger,
    StructuredFormatter,
    TextFormatter
)
from .monitoring import (
    MonitoringManager,
    get_monitoring_manager,
    initialize_monitoring,
    monitored
)

__all__ = [
    # SessionService
    "SessionService",
    "SessionInfo",
    "MessageInfo",
    # SectionService
    "SectionService",
    "SectionSummary",
    "SectionInfo",
    "SectionTrigger",
    # EntryService
    "EntryService",
    # Memory0Service
    "Memory0Service",
    "MemoryRelation",
    "MemoryCandidate",
    "MemoryResult",
    # MemoryService
    "MemoryService",
    "ContextSnippet",
    "ContextForTurn",
    # MemoryClient
    "MemoryClient",
    # AgentInstanceRegistry
    "AgentInstanceRegistry",
    "AgentInstanceStatus",
    "AgentInstanceMetadata",
    # QACacheService
    "QACacheService",
    "QAStatus",
    "AnswerType",
    "QAInfo",
    "QAStats",
    # SectionAgent
    "SectionAgent",
    "SectionDecision",
    "SectionBoundary",
    "SectionProposal",
    "SectionReview",
    # VectorClient
    "VectorClient",
    # LLMClient
    "LLMClient",
    "LLMConfig",
    "EmbeddingConfig",
    "get_llm_client",
    # TaskQueue
    "TaskQueue",
    "Memory0Task",
    "TaskStatus",
    "TaskType",
    "get_task_queue",
    # Memory0Worker
    "Memory0Worker",
    "WorkerConfig",
    "create_worker",
    # Config
    "Memory0Profile",
    "Memory0Config",
    "AgentMemoryConfig",
    "ConfigManager",
    "get_config_manager",
    "register_default_agents",
    "DEFAULT_CONFIG",
    "MEMORY0_PROFILES",
    # Metrics
    "MetricsCollector",
    "TimedContext",
    "get_metrics_collector",
    "record_timing",
    "increment_counter",
    "set_gauge",
    # HealthCheck
    "HealthStatus",
    "HealthCheckResult",
    "HealthReport",
    "HealthChecker",
    "get_health_checker",
    "register_health_check",
    "unregister_health_check",
    "run_health_checks",
    "get_last_health_report",
    # Logging
    "setup_logging",
    "get_logger",
    "StructuredFormatter",
    "TextFormatter",
    # Monitoring
    "MonitoringManager",
    "get_monitoring_manager",
    "initialize_monitoring",
    "monitored",
]


def create_memory_stack(
    enable_async_memory0: bool = False,
    task_queue: Optional[TaskQueue] = None,
    section_trigger_message_count: int = 10,
    section_trigger_time_interval: int = 3600,
    section_trigger_cooldown: int = 300,
    section_trigger_keywords: Optional[List[str]] = None,
    enable_async_section_summarize: bool = False,
    enable_llm_judgment: bool = False
) -> MemoryService:
    """创建完整的记忆栈。

    这是一个便捷函数，用于快速初始化所有记忆服务。
    所有服务共享同一个 VectorClient 实例，避免连接管理混乱。

    Args:
        enable_async_memory0: 是否启用异步 Memory0 处理（默认 False）
        task_queue: 可选的任务队列实例（默认使用 get_task_queue()）
        section_trigger_message_count: 消息数量触发阈值（默认10条）
        section_trigger_time_interval: 时间间隔触发阈值（秒，默认3600秒=1小时）
        section_trigger_cooldown: 触发冷却时间窗（秒，默认300秒=5分钟）
        section_trigger_keywords: 语义触发关键词列表（默认包含"先到这里"、"换个话题"、"总结一下"等）
        enable_async_section_summarize: 是否启用异步 Section 整理（默认 False）
        enable_llm_judgment: 是否启用 LLM-based 关系判定（默认 False，使用规则判定）

    Returns:
        MemoryService: 配置好的 MemoryService 实例
    """
    vector_client = VectorClient()
    entry_service = EntryService(vector_client=vector_client)
    session_service = SessionService()
    task_queue = task_queue or get_task_queue()
    section_service = SectionService(
        entry_service=entry_service,
        vector_client=vector_client,  # 注入共享的 VectorClient
        task_queue=task_queue,      # 注入任务队列
        enable_async_memory0=enable_async_memory0,  # 启用异步 Memory0
        section_trigger_message_count=section_trigger_message_count,
        section_trigger_time_interval=section_trigger_time_interval,
        section_trigger_cooldown=section_trigger_cooldown,  # 添加冷却时间窗
        section_trigger_keywords=section_trigger_keywords,
        enable_async_section_summarize=enable_async_section_summarize  # 启用异步 Section 整理
    )
    memory0_service = Memory0Service(
        entry_service=entry_service,
        vector_client=vector_client,  # 注入共享的 VectorClient
        enable_llm_judgment=enable_llm_judgment  # 启用 LLM-based 关系判定
    )

    memory_service = MemoryService(
        session_service=session_service,
        section_service=section_service,
        entry_service=entry_service,
        memory0_service=memory0_service,
    )

    return memory_service


def create_worker_with_section(
    entry_service: EntryService,
    section_service: SectionService,
    task_queue: Optional[TaskQueue] = None,
    config: Optional[WorkerConfig] = None
) -> Memory0Worker:
    """创建支持 Section 整理任务的 Worker 实例

    Args:
        entry_service: EntryService 实例
        section_service: SectionService 实例，用于处理 Section 整理任务
        task_queue: 任务队列实例（默认使用 get_task_queue()）
        config: Worker 配置（默认使用默认配置）

    Returns:
        Memory0Worker: Worker 实例
    """
    from .memory_worker import create_worker
    return create_worker(
        entry_service=entry_service,
        section_service=section_service,
        task_queue=task_queue,
        config=config
    )


# 更新 __all__ 导出
__all__.append("create_worker_with_section")
