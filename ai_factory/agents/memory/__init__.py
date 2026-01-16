"""Agent Memory Module.

Provides a complete memory stack for agents, including:
- SessionService: Short-term conversation memory
- SectionService: Section summarization and organization
- EntryService: Unified entries storage and retrieval
- Memory0Service: Long-term memory governance
- MemoryService: Facade for all memory operations
- QACacheService: Q&A cache for fast response to repeated questions
- VectorClient: Vector search abstraction
- LLMClient: LLM and Embedding service client for remote APIs
- TaskQueue: Task queue for asynchronous Memory0 processing
- Memory0Worker: Background worker for consuming Memory0 tasks

Based on `Agent记忆系统详细设计与施工文档.md`.
"""

from __future__ import annotations

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
from .vector_client import VectorClient
from .llm_client import LLMClient, get_llm_client, LLMConfig, EmbeddingConfig
from .task_queue import TaskQueue, Memory0Task, TaskStatus, TaskType, get_task_queue
from .memory_worker import Memory0Worker, WorkerConfig, create_worker
from .qa_cache_service import QACacheService, QAStatus, AnswerType, QAInfo, QAStats
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
    # QACacheService
    "QACacheService",
    "QAStatus",
    "AnswerType",
    "QAInfo",
    "QAStats",
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
]


def create_memory_stack(
    enable_async_memory0: bool = False,
    task_queue: Optional[TaskQueue] = None,
    section_trigger_message_count: int = 10,
    section_trigger_time_interval: int = 3600,
    section_trigger_keywords: Optional[List[str]] = None
) -> MemoryService:
    """创建完整的记忆栈。

    这是一个便捷函数，用于快速初始化所有记忆服务。
    所有服务共享同一个 VectorClient 实例，避免连接管理混乱。

    Args:
        enable_async_memory0: 是否启用异步 Memory0 处理（默认 False）
        task_queue: 可选的任务队列实例（默认使用 get_task_queue()）
        section_trigger_message_count: 消息数量触发阈值（默认10条）
        section_trigger_time_interval: 时间间隔触发阈值（秒，默认3600秒=1小时）
        section_trigger_keywords: 语义触发关键词列表（默认包含"先到这里"、"换个话题"、"总结一下"等）

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
        section_trigger_keywords=section_trigger_keywords
    )
    memory0_service = Memory0Service(
        entry_service=entry_service,
        vector_client=vector_client  # 注入共享的 VectorClient
    )

    memory_service = MemoryService(
        session_service=session_service,
        section_service=section_service,
        entry_service=entry_service,
        memory0_service=memory0_service,
    )

    return memory_service
