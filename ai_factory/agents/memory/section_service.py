"""SectionService implementation.

Responsible for section cutting, summarization, and producing candidate knowledge
entries before they are governed by Memory0.
Follows `Agent记忆系统详细设计与施工文档.md`.
"""

from __future__ import annotations

import uuid
import json
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from ai_factory.db.pgvector_client import connection_scope
from psycopg2.extras import Json
from .entry_service import EntryService
from .vector_client import VectorClient
from .llm_client import get_llm_client
from .task_queue import TaskQueue, Memory0Task, TaskType, get_task_queue


class SectionTrigger(str, Enum):
    """Section整理触发方式
    
    对应 chat_sections.trigger_type 字段，取值为：
    - auto: 自动触发（包括消息数量、时间间隔等）
    - manual: 手动触发
    - timeout: 超时触发
    """
    AUTO = "auto"
    MANUAL = "manual"
    TIMEOUT = "timeout"


@dataclass
class SectionSummary:
    """Section总结结果"""
    section_id: str
    entry_id: str
    section_version: int
    content: str
    scene_tags: Dict[str, List[str]]
    agent_id: str
    metadata: Dict[str, Any]


@dataclass
class SectionInfo:
    """Section信息"""
    section_id: str
    session_id: str
    title: Optional[str]
    status: str
    trigger_type: str
    message_count: int
    summary_content: Optional[str]
    summary_entry_id: Optional[str]
    agent_id: str
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime]


class SectionService:
    """Handle section detection, summarization, and first-stage write to entries."""

    def __init__(
        self,
        entry_service: EntryService,
        vector_client: Optional[VectorClient] = None,
        task_queue: Optional[TaskQueue] = None,
        enable_async_memory0: bool = False
    ):
        """初始化 SectionService。

        Args:
            entry_service: EntryService 实例，用于写入 entries 表
            vector_client: 可选的 VectorClient 实例，用于向量检索
            task_queue: 可选的任务队列实例，用于异步 Memory0 处理
            enable_async_memory0: 是否启用异步 Memory0 处理
        """
        self.entry_service = entry_service
        self.vector_client = vector_client or VectorClient()
        self.llm_client = get_llm_client()
        self.task_queue = task_queue or get_task_queue()
        self.enable_async_memory0 = enable_async_memory0

    def summarize_section(
        self,
        session_id: str,
        section_id: Optional[str] = None,
        agent_id: str = "default",
        trigger_type: str = "auto",
        manual_section_title: Optional[str] = None
    ) -> SectionSummary:
        """整理section并写入entries大库。

        Args:
            session_id: 会话ID
            section_id: 可选，手动指定的section_id。如果为None，则生成新的
            agent_id: Agent ID，标识该section属于哪个Agent
            trigger_type: 触发类型（auto/manual/timeout）
            manual_section_title: 可选，手动指定的section标题

        Returns:
            SectionSummary: 整理结果
        """
        # 1. 获取会话的最近消息
        messages = self._get_session_messages(session_id, limit=50)

        if not messages:
            raise ValueError(f"Session {session_id} has no messages to summarize")

        # 2. 如果没有手动指定section_id，生成新的
        if section_id is None:
            section_id = f"sec_{uuid.uuid4().hex[:16]}"
            section_title = manual_section_title or self._generate_section_title(messages)
        else:
            section_title = manual_section_title or f"Section {section_id}"

        # 3. 调用LLM进行整理总结
        summary_content = self._summarize_with_llm(messages, section_title)

        # 4. 生成scene_tags
        scene_tags = self._generate_scene_tags(summary_content, agent_id)

        # 5. 获取当前section的版本号
        section_version = self._get_next_section_version(section_id)

        # 6. 将旧版本标记为非最新
        self._mark_old_versions_as_not_latest(section_id)

        # 7. 写入entries表（通过EntryService）
        entry_id = self.entry_service.create_entry({
            "entry_id": f"ent_{uuid.uuid4().hex}",
            "title": section_title,
            "content": summary_content,
            "scene_tags": scene_tags,
            "section_id": section_id,
            "section_version": section_version,
            "is_latest": True,
            "agent_id": agent_id,
            "source_session_id": session_id,
            "space_type": "note",  # 默认为笔记类型
        })

        # 8. 生成embedding并写入entry_embeddings表
        try:
            embedding = self.llm_client.generate_embedding_sync(summary_content)
            self.vector_client.upsert_embedding(entry_id, embedding)
        except Exception as e:
            # embedding生成失败不影响主流程
            print(f"[SectionService] Warning: Failed to generate embedding for {entry_id}: {e}")

        # 9. 创建或更新section记录
        self._create_or_update_section(
            section_id=section_id,
            session_id=session_id,
            title=section_title,
            status="completed",
            trigger_type=trigger_type,
            message_count=len(messages),
            summary_content=summary_content,
            summary_entry_id=entry_id,
            agent_id=agent_id
        )

        # 10. 提交 Memory0 任务（如果启用异步处理）
        if self.enable_async_memory0:
            self._enqueue_memory0_task(entry_id, agent_id)

        return SectionSummary(
            section_id=section_id,
            entry_id=entry_id,
            section_version=section_version,
            content=summary_content,
            scene_tags=scene_tags,
            agent_id=agent_id,
            metadata={
                "trigger_type": trigger_type,
                "message_count": len(messages),
                "section_title": section_title
            }
        )

    def get_section_history(
        self,
        section_id: str,
        agent_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """获取section的所有版本历史。

        Args:
            section_id: Section ID
            agent_id: 可选，过滤特定Agent的条目

        Returns:
            List[Dict[str, Any]]: 版本历史列表
        """
        with connection_scope() as conn:
            with conn.cursor() as cur:
                conditions = ["section_id = %s"]
                params = [section_id]

                if agent_id:
                    conditions.append("agent_id = %s")
                    params.append(agent_id)

                cur.execute(f"""
                    SELECT entry_id, section_id, section_version, is_latest,
                           content, scene_tags, agent_id, created_at
                    FROM entries
                    WHERE {" AND ".join(conditions)}
                    ORDER BY section_version DESC
                """, params)

                rows = cur.fetchall()
                return [
                    {
                        "entry_id": row[0],
                        "section_id": row[1],
                        "section_version": row[2],
                        "is_latest": row[3],
                        "content": row[4],
                        "scene_tags": json.loads(row[5]) if row[5] else {},
                        "agent_id": row[6],
                        "created_at": row[7]
                    }
                    for row in rows
                ]

    def merge_sections(
        self,
        source_section_ids: List[str],
        target_section_id: str,
        agent_id: str
    ) -> SectionSummary:
        """合并多个section为一个。

        Args:
            source_section_ids: 源section ID列表
            target_section_id: 目标section ID
            agent_id: Agent ID

        Returns:
            SectionSummary: 合并后的section总结
        """
        # 1. 获取所有源section的最新版本
        all_content = []
        for sec_id in source_section_ids:
            history = self.get_section_history(sec_id, agent_id)
            if history:
                all_content.append(history[0]["content"])

        if not all_content:
            raise ValueError(f"No content found in source sections: {source_section_ids}")

        # 2. 合并内容
        merged_content = self._merge_content_with_llm(all_content, target_section_id)

        # 3. 生成scene_tags
        scene_tags = self._generate_scene_tags(merged_content, agent_id)

        # 4. 获取目标section的版本号
        section_version = self._get_next_section_version(target_section_id)

        # 5. 将旧版本标记为非最新
        self._mark_old_versions_as_not_latest(target_section_id)

        # 6. 写入entries表
        entry_id = self.entry_service.create_entry({
            "entry_id": f"ent_{uuid.uuid4().hex}",
            "title": f"Merged Section {target_section_id}",
            "content": merged_content,
            "scene_tags": scene_tags,
            "section_id": target_section_id,
            "section_version": section_version,
            "is_latest": True,
            "agent_id": agent_id,
            "space_type": "note",
        })

        # 7. 生成embedding
        try:
            embedding = self.llm_client.generate_embedding_sync(merged_content)
            self.vector_client.upsert_embedding(entry_id, embedding)
        except Exception as e:
            print(f"[SectionService] Warning: Failed to generate embedding for {entry_id}: {e}")

        # 8. 提交 Memory0 任务（如果启用异步处理）
        if self.enable_async_memory0:
            self._enqueue_memory0_task(entry_id, agent_id)
 
        return SectionSummary(
            section_id=target_section_id,
            entry_id=entry_id,
            section_version=section_version,
            content=merged_content,
            scene_tags=scene_tags,
            agent_id=agent_id,
            metadata={
                "operation": "merge",
                "source_sections": source_section_ids,
                "merged_at": datetime.now().isoformat()
            }
        )

    def get_section_info(self, section_id: str) -> Optional[SectionInfo]:
        """获取section信息。

        Args:
            section_id: Section ID

        Returns:
            SectionInfo: Section信息，如果不存在则返回None
        """
        with connection_scope() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT section_id, session_id, title, status, trigger_type, message_count,
                           summary_content, summary_entry_id, agent_id, created_at, updated_at, completed_at
                    FROM chat_sections
                    WHERE section_id = %s
                """, (section_id,))

                row = cur.fetchone()
                if row:
                    return SectionInfo(
                        section_id=row[0],
                        session_id=row[1],
                        title=row[2],
                        status=row[3],
                        trigger_type=row[4],
                        message_count=row[5],
                        summary_content=row[6],
                        summary_entry_id=row[7],
                        agent_id=row[8],
                        created_at=row[9],
                        updated_at=row[10],
                        completed_at=row[11]
                    )
        return None

    def _get_session_messages(
        self,
        session_id: str,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """获取会话的消息。

        Args:
            session_id: 会话ID
            limit: 返回消息数量限制

        Returns:
            List[Dict[str, Any]]: 消息列表
        """
        with connection_scope() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT message_id, role, msg_type, content, created_at
                    FROM chat_messages
                    WHERE session_id = %s
                    ORDER BY created_at ASC
                    LIMIT %s
                """, (session_id, limit))

                rows = cur.fetchall()
                return [
                    {
                        "message_id": row[0],
                        "role": row[1],
                        "msg_type": row[2],
                        "content": row[3],
                        "created_at": row[4]
                    }
                    for row in rows
                ]

    def _generate_section_title(
        self,
        messages: List[Dict[str, Any]]
    ) -> str:
        """生成section标题。

        Args:
            messages: 消息列表

        Returns:
            str: 标题
        """
        if not messages:
            return "Untitled Section"

        try:
            # 调用 LLM 生成标题
            return self.llm_client.generate_section_title_sync(messages)
        except Exception as e:
            # LLM 调用失败，使用简化逻辑
            print(f"[SectionService] Warning: Failed to generate title with LLM: {e}")
            first_content = messages[0]["content"]
            return first_content[:50] + "..." if len(first_content) > 50 else first_content

    def _summarize_with_llm(
        self,
        messages: List[Dict[str, Any]],
        section_title: str
    ) -> str:
        """调用LLM进行整理总结。

        Args:
            messages: 消息列表
            section_title: Section标题

        Returns:
            str: 总结内容
        """
        try:
            # 调用 LLM 生成总结
            return self.llm_client.summarize_messages_sync(messages, section_title)
        except Exception as e:
            # LLM 调用失败，使用简化逻辑
            print(f"[SectionService] Warning: Failed to summarize with LLM: {e}")
            summary_parts = [f"## {section_title}"]
            for msg in messages:
                role_label = "用户" if msg['role'] == 'user' else "助手"
                summary_parts.append(f"**{role_label}**: {msg['content']}")
            return "\n\n".join(summary_parts)

    def _generate_scene_tags(
        self,
        content: str,
        agent_id: str
    ) -> Dict[str, List[str]]:
        """生成scene_tags。

        Args:
            content: 内容
            agent_id: Agent ID

        Returns:
            Dict[str, List[str]]: scene_tags字典
        """
        try:
            # 调用 LLM 生成标签
            return self.llm_client.generate_scene_tags_sync(content, agent_id)
        except Exception as e:
            # LLM 调用失败，使用简化逻辑
            print(f"[SectionService] Warning: Failed to generate tags with LLM: {e}")
            scene_tags = {
                "execution": ["笔记"],
                "planning": ["项目"]
            }

            # 根据agent_id添加特定标签
            if "project" in agent_id.lower():
                scene_tags["department"] = ["软件"]
            elif "work" in agent_id.lower():
                scene_tags["department"] = ["总部"]

            return scene_tags

    def _get_next_section_version(self, section_id: str) -> int:
        """获取section的下一个版本号。

        Args:
            section_id: Section ID

        Returns:
            int: 下一个版本号
        """
        with connection_scope() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COALESCE(MAX(section_version), 0)
                    FROM entries
                    WHERE section_id = %s
                """, (section_id,))

                result = cur.fetchone()
                return (result[0] if result else 0) + 1

    def _mark_old_versions_as_not_latest(self, section_id: str) -> None:
        """将section的旧版本标记为非最新。

        Args:
            section_id: Section ID
        """
        with connection_scope() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE entries
                    SET is_latest = FALSE
                    WHERE section_id = %s AND is_latest = TRUE
                """, (section_id,))

    def _create_or_update_section(
        self,
        section_id: str,
        session_id: str,
        title: str,
        status: str,
        trigger_type: str,
        message_count: int,
        summary_content: Optional[str],
        summary_entry_id: Optional[str],
        agent_id: str
    ) -> None:
        """创建或更新section记录。

        Args:
            section_id: Section ID
            session_id: 会话ID
            title: 标题
            status: 状态
            trigger_type: 触发类型
            message_count: 消息数量
            summary_content: 摘要内容
            summary_entry_id: 摘要条目ID
            agent_id: Agent ID
        """
        with connection_scope() as conn:
            with conn.cursor() as cur:
                # 检查section是否存在
                cur.execute("""
                    SELECT section_id FROM chat_sections
                    WHERE section_id = %s
                """, (section_id,))

                exists = cur.fetchone() is not None

                if exists:
                    # 更新
                    cur.execute("""
                        UPDATE chat_sections
                        SET title = %s, status = %s, message_count = %s,
                            summary_content = %s, summary_entry_id = %s,
                            updated_at = CURRENT_TIMESTAMP,
                            completed_at = CASE WHEN %s = %s THEN CURRENT_TIMESTAMP ELSE completed_at END
                        WHERE section_id = %s
                    """, (title, status, message_count, summary_content,
                           summary_entry_id, status, "completed", section_id))
                else:
                    # 创建
                    cur.execute("""
                        INSERT INTO chat_sections
                        (section_id, session_id, title, status, trigger_type, message_count,
                         summary_content, summary_entry_id, agent_id, created_at, updated_at, completed_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP,
                                CASE WHEN %s = %s THEN CURRENT_TIMESTAMP ELSE NULL END)
                    """, (section_id, session_id, title, status, trigger_type,
                           message_count, summary_content, summary_entry_id, agent_id,
                           status, "completed"))

    def _merge_content_with_llm(
        self,
        contents: List[str],
        target_section_id: str
    ) -> str:
        """调用LLM合并多个内容。

        Args:
            contents: 内容列表
            target_section_id: 目标section ID

        Returns:
            str: 合并后的内容
        """
        try:
            # 调用 LLM 合并内容
            return self.llm_client.merge_contents_sync(contents, target_section_id)
        except Exception as e:
            # LLM 调用失败，使用简化逻辑
            print(f"[SectionService] Warning: Failed to merge with LLM: {e}")
            return "\n\n---\n\n".join(contents)

    def _enqueue_memory0_task(self, entry_id: str, agent_id: str) -> None:
        """提交 Memory0 任务到队列。

        Args:
            entry_id: 要处理的 entry_id
            agent_id: Agent ID
        """
        try:
            task = Memory0Task.create(
                entry_id=entry_id,
                task_type=TaskType.MEMORY0_PROCESS_ENTRY.value,
                payload={"agent_id": agent_id},
                priority=0
            )
            self.task_queue.enqueue(task)
            print(f"[SectionService] Memory0 task enqueued: {task.task_id} for entry {entry_id}")
        except Exception as e:
            # 任务提交失败不影响主流程
            print(f"[SectionService] Warning: Failed to enqueue Memory0 task for {entry_id}: {e}")
