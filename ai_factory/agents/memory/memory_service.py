"""MemoryService facade implementation.

High-level interface used by agents to get context for a turn and to
explicitly store memories. Composes SessionService, SectionService,
EntryService and Memory0Service.
Follows `Agent记忆系统详细设计与施工文档.md`.
"""

from __future__ import annotations

from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from datetime import datetime

from .session_service import SessionService
from .section_service import SectionService
from .entry_service import EntryService
from .memory0_service import Memory0Service, MemoryCandidate
from .llm_client import get_llm_client


@dataclass
class ContextSnippet:
    """上下文片段"""
    role: str
    content: str
    weight: float = 1.0
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class ContextForTurn:
    """单轮对话的上下文"""
    system_prompt: str
    history_messages: List[Dict[str, Any]]
    rag_snippets: List[Dict[str, Any]]
    metadata: Dict[str, Any]


class MemoryService:
    """Facade that agents call to interact with the memory stack."""

    # 默认配置
    DEFAULT_MAX_TOKENS = 2048
    DEFAULT_RAG_TOP_K = 5
    DEFAULT_RECENT_MESSAGES = 10

    def __init__(
        self,
        session_service: SessionService,
        section_service: SectionService,
        entry_service: EntryService,
        memory0_service: Memory0Service,
    ) -> None:
        """初始化 MemoryService。

        Args:
            session_service: SessionService 实例
            section_service: SectionService 实例
            entry_service: EntryService 实例
            memory0_service: Memory0Service 实例
        """
        self.session_service = session_service
        self.section_service = section_service
        self.entry_service = entry_service
        self.memory0_service = memory0_service
        self.llm_client = get_llm_client()

    def get_context_for_turn(
        self,
        session_id: str,
        agent_id: str,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        rag_top_k: int = DEFAULT_RAG_TOP_K,
        recent_messages_limit: int = DEFAULT_RECENT_MESSAGES
    ) -> ContextForTurn:
        """为当前轮次组装上下文。

        组装内容：
        1. 短期记忆：从 SessionService 取最近消息
        2. 长期记忆：从 EntryService 取相关条目（按 agent_id/scene_tags 过滤）
        3. （可选）外部 RAG（世界知识）
        4. 组合成上下文包

        Args:
            session_id: 会话ID
            agent_id: Agent ID
            max_tokens: 最大token数
            rag_top_k: RAG检索返回数量
            recent_messages_limit: 最近消息数量

        Returns:
            ContextForTurn: 上下文对象
        """
        # 1. 获取静态提示词（简化版）
        system_prompt = self._get_static_prompt(agent_id)

        # 2. 获取短期记忆（最近消息）
        recent_messages = self.session_service.get_recent_messages(
            session_id=session_id,
            limit=recent_messages_limit
        )
        # 转换为字典列表
        history_messages = [
            {
                "message_id": msg.message_id,
                "role": msg.role,
                "content": msg.content,
                "created_at": msg.created_at.isoformat() if msg.created_at else None
            }
            for msg in recent_messages
        ]

        # 3. 获取长期记忆（从entries大库）
        rag_snippets = []
        if rag_top_k > 0:
            # 从最近消息中提取查询文本
            query_text = self._extract_query_from_messages(recent_messages)
            if query_text:
                try:
                    # 生成查询embedding
                        query_embedding = self.llm_client.generate_embedding_sync(query_text)
                        # 检索相关条目
                        rag_results = self.entry_service.search_similar(
                            query_embedding=query_embedding,
                            filters={"agent_id": agent_id},
                            top_k=rag_top_k
                        )
                        # 转换为字典列表
                        rag_snippets = [
                            {
                                "entry_id": result.get("entry_id"),
                                "title": result.get("title"),
                                "content": result.get("content"),
                                "similarity": result.get("similarity") if result.get("similarity") is not None else None,
                                "scene_tags": result.get("scene_tags"),
                            }
                            for result in rag_results
                        ]
                except Exception as e:
                    print(f"[MemoryService] Warning: Failed to retrieve RAG snippets: {e}")

        # 4. 组装上下文
        return ContextForTurn(
            system_prompt=system_prompt,
            history_messages=history_messages,
            rag_snippets=rag_snippets,
            metadata={
                "token_budget": max_tokens,
                "recent_messages_count": len(history_messages),
                "rag_snippets_count": len(rag_snippets),
                "generated_at": datetime.now().isoformat()
            }
        )

    def remember_explicitly(
        self,
        agent_id: str,
        user_id: str,
        content: str,
        extra_meta: Optional[Dict[str, Any]] = None
    ) -> str:
        """显式存储一条信息作为长期记忆。

        通过 Memory0Service 进行记忆治理，自动判定 NEW/UPDATE/OVERRIDE/DUPLICATE。

        Args:
            agent_id: Agent ID
            user_id: 用户ID
            content: 要记住的内容
            extra_meta: 额外元数据

        Returns:
            str: entry_id
        """
        # 构造记忆候选
        candidate = MemoryCandidate(
            content=content,
            user_id=user_id,
            agent_id=agent_id,
            scene_tags=extra_meta.get("scene_tags", {}) if extra_meta else {},
            space_type=extra_meta.get("space_type", "note") if extra_meta else "note",
            metadata=extra_meta or {}
        )

        # 调用 Memory0Service 进行记忆治理
        result = self.memory0_service.upsert_memory(candidate)

        return result.entry_id

    def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """添加消息到会话。

        Args:
            session_id: 会话ID
            role: 消息角色（user/assistant/system/tool）
            content: 消息内容
            metadata: 元数据

        Returns:
            str: message_id
        """
        return self.session_service.append_message(
            session_id=session_id,
            role=role,
            content=content,
            metadata=metadata
        )

    def summarize_section(
        self,
        session_id: str,
        agent_id: str = "default",
        trigger_type: str = "mcp_tool",
        manual_section_title: Optional[str] = None
    ) -> Dict[str, Any]:
        """整理section并写入entries大库。

        Args:
            session_id: 会话ID
            agent_id: Agent ID
            trigger_type: 触发类型
            manual_section_title: 手动指定的section标题

        Returns:
            Dict[str, Any]: 整理结果
        """
        summary = self.section_service.summarize_section(
            session_id=session_id,
            agent_id=agent_id,
            trigger_type=trigger_type,
            manual_section_title=manual_section_title
        )

        return {
            "section_id": summary.section_id,
            "entry_id": summary.entry_id,
            "section_version": summary.section_version,
            "scene_tags": summary.scene_tags,
            "agent_id": summary.agent_id,
            "metadata": summary.metadata
        }

    def _get_static_prompt(self, agent_id: str) -> str:
        """获取静态提示词（简化版）。

        Args:
            agent_id: Agent ID

        Returns:
            str: 静态提示词
        """
        # TODO: 实际应从agent配置或数据库中获取
        return f"你是一个有帮助的助手（Agent ID: {agent_id}）。请根据上下文回答问题。"

    def _extract_query_from_messages(
        self,
        messages: List[Any]
    ) -> str:
        """从消息中提取检索查询文本（简化版）。

        Args:
            messages: 消息列表

        Returns:
            str: 查询文本
        """
        # TODO: 实现更智能的查询提取逻辑
        # 这里简化处理：使用最后一条用户消息
        for msg in reversed(messages):
            if hasattr(msg, 'role') and msg.role == 'user':
                return msg.content
        return ""

    def _truncate_to_token_budget(
        self,
        snippets: List[ContextSnippet],
        max_tokens: int
    ) -> List[ContextSnippet]:
        """简化版的token截断（实际应使用tokenizer）。

        Args:
            snippets: 上下文片段列表
            max_tokens: 最大token数

        Returns:
            List[ContextSnippet]: 截断后的片段列表
        """
        selected = []
        total_tokens = 0
        for snippet in snippets:
            # 估算token数（按字符数/4粗略估算）
            est_tokens = len(snippet.content) // 4
            if total_tokens + est_tokens <= max_tokens:
                selected.append(snippet)
                total_tokens += est_tokens
            else:
                break
        return selected
