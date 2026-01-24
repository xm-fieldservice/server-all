"""MemoryClient implementation.

Provides a high-level, context-aware interface for interacting with the memory stack.
Handles multi-tenant isolation through context management.
"""

from __future__ import annotations

import logging
from typing import Dict, Any, List, Optional, Union
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar, Token

from ..memory_service import MemoryService, ContextForTurn

logger = logging.getLogger(__name__)


class MemoryClient:
    """记忆系统客户端。

    封装 MemoryService，通过上下文管理器自动处理四层隔离（user_id, agent_type, agent_instance_id）。
    """

    # 协程/线程隔离的上下文存储，避免并发串号
    _context_var: ContextVar[Optional[Dict[str, Any]]] = ContextVar("memory_context", default=None)

    def __init__(self, memory_service: MemoryService):
        """初始化 MemoryClient。

        Args:
            memory_service: MemoryService 实例
        """
        self.service = memory_service

    @contextmanager
    def context(
        self,
        user_id: str,
        agent_type: Optional[str] = None,
        agent_instance_id: Optional[str] = None
    ):
        """同步上下文管理器。

        Args:
            user_id: 用户ID
            agent_type: Agent类型
            agent_instance_id: Agent实例ID
        """
        token: Token = self._context_var.set(
            {
                "user_id": user_id,
                "agent_type": agent_type,
                "agent_instance_id": agent_instance_id,
            }
        )
        try:
            yield self
        finally:
            self._context_var.reset(token)

    @asynccontextmanager
    async def async_context(
        self,
        user_id: str,
        agent_type: Optional[str] = None,
        agent_instance_id: Optional[str] = None
    ):
        """异步上下文管理器。

        Args:
            user_id: 用户ID
            agent_type: Agent类型
            agent_instance_id: Agent实例ID
        """
        token: Token = self._context_var.set(
            {
                "user_id": user_id,
                "agent_type": agent_type,
                "agent_instance_id": agent_instance_id,
            }
        )
        try:
            yield self
        finally:
            self._context_var.reset(token)

    def _get_context_params(self) -> Dict[str, Any]:
        """获取当前上下文参数。"""
        ctx = self._context_var.get()
        if not ctx:
            raise RuntimeError("MemoryClient context is not set. Use 'with client.context(...):' or 'async with client.async_context(...):'")
        return ctx

    def get_context_for_turn(
        self,
        session_id: str,
        agent_id: str,
        max_tokens: int = 2048,
        rag_top_k: int = 5,
        recent_messages_limit: int = 10
    ) -> ContextForTurn:
        """为当前轮次组装上下文（自动应用隔离）。"""
        ctx = self._get_context_params()
        return self.service.get_context_for_turn(
            session_id=session_id,
            agent_id=agent_id,
            user_id=ctx["user_id"],
            agent_type=ctx["agent_type"],
            agent_instance_id=ctx["agent_instance_id"],
            max_tokens=max_tokens,
            rag_top_k=rag_top_k,
            recent_messages_limit=recent_messages_limit
        )

    def remember_explicitly(
        self,
        agent_id: str,
        content: str,
        extra_meta: Optional[Dict[str, Any]] = None
    ) -> str:
        """显式存储一条信息作为长期记忆（自动应用隔离）。"""
        ctx = self._get_context_params()
        return self.service.remember_explicitly(
            agent_id=agent_id,
            user_id=ctx["user_id"],
            content=content,
            agent_type=ctx["agent_type"],
            agent_instance_id=ctx["agent_instance_id"],
            extra_meta=extra_meta
        )

    def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """添加消息到会话（自动应用隔离）。"""
        ctx = self._get_context_params()
        return self.service.append_message(
            session_id=session_id,
            role=role,
            content=content,
            user_id=ctx["user_id"],
            agent_type=ctx["agent_type"],
            agent_instance_id=ctx["agent_instance_id"],
            metadata=metadata
        )

    def summarize_section(
        self,
        session_id: str,
        agent_id: str = "default",
        trigger_type: str = "mcp_tool",
        manual_section_title: Optional[str] = None
    ) -> Dict[str, Any]:
        """整理section并写入entries大库（自动应用隔离）。"""
        ctx = self._get_context_params()
        return self.service.summarize_section(
            session_id=session_id,
            agent_id=agent_id,
            user_id=ctx["user_id"],
            agent_type=ctx["agent_type"],
            agent_instance_id=ctx["agent_instance_id"],
            trigger_type=trigger_type,
            manual_section_title=manual_section_title
        )
