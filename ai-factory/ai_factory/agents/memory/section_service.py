"""SectionService implementation.

Responsible for section cutting, summarization, and producing candidate knowledge
entries before they are governed by Memory0.
Follows `Agent记忆系统详细设计与施工文档.md`.

V3升级说明:
- 添加四层隔离支持（user_id, agent_type, agent_instance_id）
- 添加RLS上下文管理（set_rls_context, clear_rls_context）
- 对齐chat_sections表完整结构（status, trigger_type等）
- 完整错误处理和日志记录
"""

from __future__ import annotations

import uuid
import json
import logging
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

# 配置日志
logger = logging.getLogger(__name__)


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
    """Section信息（V3升级：包含四层隔离字段）"""
    section_id: str
    session_id: str
    title: Optional[str]
    status: str
    trigger_type: str
    message_count: int
    summary_content: Optional[str]
    summary_entry_id: Optional[str]
    agent_id: str
    user_id: Optional[str]  # V3新增：四层隔离 - 第1层
    agent_type: Optional[str]  # V3新增：四层隔离 - 第2层
    agent_instance_id: Optional[str]  # V3新增：四层隔离 - 第3层
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime]


class SectionService:
    """Handle section detection, summarization, and first-stage write to entries."""

    def set_rls_context(
        self,
        user_id: str,
        agent_type: Optional[str] = None,
        agent_instance_id: Optional[str] = None,
        conn = None
    ) -> None:
        """设置RLS上下文（V3新增）

        Args:
            user_id: 用户ID
            agent_type: Agent类型（可选）
            agent_instance_id: Agent实例ID（可选）
            conn: 数据库连接（可选）
        """
        try:
            if conn is None:
                with connection_scope() as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT set_config('app.current_user_id', %s, true)", (user_id,))
                        cur.execute("SELECT set_config('app.current_agent_type', %s, true)", (agent_type or "",))
                        cur.execute("SELECT set_config('app.current_agent_instance_id', %s, true)", (agent_instance_id or "",))
            else:
                with conn.cursor() as cur:
                    cur.execute("SET LOCAL app.current_user_id = %s", (user_id,))
                    if agent_type:
                        cur.execute("SET LOCAL app.current_agent_type = %s", (agent_type,))
                    else:
                        cur.execute("SET LOCAL app.current_agent_type = %s", ("",))
                    
                    if agent_instance_id:
                        cur.execute("SET LOCAL app.current_agent_instance_id = %s", (agent_instance_id,))
                    else:
                        cur.execute("SET LOCAL app.current_agent_instance_id = %s", ("",))

            logger.debug(f"RLS context set: user_id={user_id}, agent_type={agent_type}, agent_instance_id={agent_instance_id}")
        except Exception as e:
            logger.error(f"Failed to set RLS context: {e}")
            # 不抛出异常，继续执行

    def clear_rls_context(self, conn=None) -> None:
        """清除RLS上下文（V3新增）

        Args:
            conn: 数据库连接（可选）
        """
        # 暂时禁用RLS上下文清除
        logger.debug("RLS context cleared (disabled)")

    def __init__(
        self,
        entry_service: EntryService,
        vector_client: Optional[VectorClient] = None,
        task_queue: Optional[TaskQueue] = None,
        enable_async_memory0: bool = False,
        section_trigger_message_count: int = 10,
        section_trigger_time_interval: int = 3600,
        section_trigger_cooldown: int = 300,
        section_trigger_keywords: Optional[List[str]] = None,
        enable_async_section_summarize: bool = False
    ):
        """初始化 SectionService。

        Args:
            entry_service: EntryService 实例，用于写入 entries 表
            vector_client: 可选的 VectorClient 实例，用于向量检索
            task_queue: 可选的任务队列实例，用于异步 Memory0 处理
            enable_async_memory0: 是否启用异步 Memory0 处理
            section_trigger_message_count: 消息数量触发阈值（默认10条）
            section_trigger_time_interval: 时间间隔触发阈值（秒，默认3600秒=1小时）
            section_trigger_cooldown: 触发冷却时间窗（秒，默认300秒=5分钟）
            section_trigger_keywords: 语义触发关键词列表（默认包含"先到这里"、"换个话题"、"总结一下"等）
            enable_async_section_summarize: 是否启用异步 Section 整理（默认 False）
        """
        self.entry_service = entry_service
        self.vector_client = vector_client or VectorClient()
        self.llm_client = get_llm_client()
        self.task_queue = task_queue or get_task_queue()
        self.enable_async_memory0 = enable_async_memory0
        self.section_trigger_message_count = section_trigger_message_count
        self.section_trigger_time_interval = section_trigger_time_interval
        self.section_trigger_cooldown = section_trigger_cooldown
        self.section_trigger_keywords = section_trigger_keywords or [
            "先到这里",
            "换个话题",
            "总结一下",
            "暂停",
            "结束",
            "完成",
            "就这样",
            "好了"
        ]
        self.enable_async_section_summarize = enable_async_section_summarize

    def summarize_section(
        self,
        session_id: str,
        section_id: Optional[str] = None,
        agent_id: str = "default",
        agent_type: Optional[str] = None,  # V3新增
        agent_instance_id: Optional[str] = None,  # V3新增
        user_id: Optional[str] = None,  # V3新增
        trigger_type: str = "auto",
        manual_section_title: Optional[str] = None
    ) -> SectionSummary:
        """整理section并写入entries大库。

        Args:
            session_id: 会话ID
            section_id: 可选，手动指定的section_id。如果为None，则生成新的
            agent_id: Agent ID，标识该section属于哪个Agent
            agent_type: Agent类型（V3新增：四层隔离）
            agent_instance_id: Agent实例ID（V3新增：四层隔离）
            user_id: 用户ID（V3新增：四层隔离）
            trigger_type: 触发类型（auto/manual/timeout）
            manual_section_title: 可选，手动指定的section标题

        Returns:
            SectionSummary: 整理结果
        """
        if user_id is None:
            raise ValueError("user_id is required for creating entry")

        with connection_scope() as conn:
            # 0. 设置 RLS 上下文 (V3.1.2 加固)
            self.set_rls_context(user_id, agent_type, agent_instance_id, conn=conn)
            
            try:
                # 1. 获取会话的最近消息
                messages = self._get_session_messages(
                    session_id,
                    limit=50,
                    conn=conn,
                    user_id=user_id,
                    agent_type=agent_type,
                    agent_instance_id=agent_instance_id
                )

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
                section_version = self._get_next_section_version(section_id, conn=conn)

                # 6. 将旧版本标记为非最新
                self._mark_old_versions_as_not_latest(section_id, conn=conn)

                # 7. 写入entries表（通过EntryService，V3升级：传递四层隔离参数）
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
                }, user_id=user_id, agent_type=agent_type, agent_instance_id=agent_instance_id)

                # 8. 生成embedding并写入entry_embeddings表
                try:
                    embedding = self.llm_client.generate_embedding_sync(summary_content)
                    self.vector_client.upsert_embedding(entry_id, embedding)
                except Exception as e:
                    # embedding生成失败不影响主流程
                    logger.warning(f"Failed to generate embedding for {entry_id}: {e}")

                # 9. 创建或更新section记录（V3升级：包含四层隔离字段）
                self._create_or_update_section(
                    section_id=section_id,
                    session_id=session_id,
                    title=section_title,
                    status="completed",
                    trigger_type=trigger_type,
                    message_count=len(messages),
                    summary_content=summary_content,
                    summary_entry_id=entry_id,
                    agent_id=agent_id,
                    user_id=user_id,  # V3新增
                    agent_type=agent_type,  # V3新增
                    agent_instance_id=agent_instance_id,  # V3新增
                    conn=conn
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
            finally:
                self.clear_rls_context(conn=conn)

    def check_and_trigger_section(
        self,
        session_id: str,
        agent_id: str = "default",
        agent_type: Optional[str] = None,  # V3新增
        agent_instance_id: Optional[str] = None,  # V3新增
        user_id: Optional[str] = None,  # V3新增
        user_message: Optional[str] = None
    ) -> Optional[SectionSummary]:
        """检查是否需要触发 Section 整理，并在满足条件时自动触发。

        Args:
            session_id: 会话ID
            agent_id: Agent ID
            agent_type: Agent类型（V3新增：四层隔离）
            agent_instance_id: Agent实例ID（V3新增：四层隔离）
            user_id: 用户ID（V3新增：四层隔离）
            user_message: 可选的用户消息内容，用于语义触发检测

        Returns:
            Optional[SectionSummary]: 如果触发了整理，返回整理结果；否则返回 None

        注意：此方法已实现幂等性/防抖逻辑：
        - 消息数量触发：基于"上次整理时间之后新增的消息数"判断
        - 时间间隔触发：基于"距离上次整理的时间"判断
        - 语义触发：每次调用都会检查（因为语义触发是显式用户意图）
        - 冷却时间窗：触发后会有一段时间的冷却期（默认5分钟），防止重复触发
        - 异步处理：如果启用异步整理，则入队任务而非同步执行
        """
        if user_id is None:
            raise ValueError("user_id is required for check_and_trigger_section")

        with connection_scope() as conn:
            # 设置 RLS 上下文
            self.set_rls_context(user_id, agent_type, agent_instance_id, conn=conn)
            
            try:
                # 1. 检查冷却时间窗
                last_triggered_at = self._get_last_section_triggered_at(
                    session_id,
                    conn=conn,
                    user_id=user_id,
                    agent_type=agent_type,
                    agent_instance_id=agent_instance_id
                )
                if last_triggered_at:
                    now = datetime.now(last_triggered_at.tzinfo) if last_triggered_at.tzinfo else datetime.now()
                    time_since_trigger = (now - last_triggered_at).total_seconds()
                    if time_since_trigger < self.section_trigger_cooldown:
                        logger.debug(f"Cooldown active: {time_since_trigger}s < {self.section_trigger_cooldown}s, skipping trigger check")
                        return None

                # 2. 获取会话的消息总数和上次整理时间
                message_count = self._get_session_message_count(
                    session_id,
                    conn=conn,
                    user_id=user_id,
                    agent_type=agent_type,
                    agent_instance_id=agent_instance_id
                )
                last_section_time = self._get_last_section_time(
                    session_id,
                    conn=conn,
                    user_id=user_id,
                    agent_type=agent_type,
                    agent_instance_id=agent_instance_id
                )

                # 3. 消息数量触发：基于"上次整理时间之后新增的消息数"判断
                trigger_type = None
                if message_count >= self.section_trigger_message_count:
                    if last_section_time:
                        # 获取上次整理时间之后新增的消息数
                        new_message_count = self._get_session_message_count_since(
                            session_id,
                            last_section_time,
                            conn=conn,
                            user_id=user_id,
                            agent_type=agent_type,
                            agent_instance_id=agent_instance_id
                        )
                        if new_message_count >= self.section_trigger_message_count:
                            logger.info(f"Message count trigger: {new_message_count} new messages >= {self.section_trigger_message_count}")
                            trigger_type = SectionTrigger.AUTO.value
                    else:
                        # 首次整理：直接检查消息总数
                        logger.info(f"Message count trigger (first time): {message_count} messages >= {self.section_trigger_message_count}")
                        trigger_type = SectionTrigger.AUTO.value

                # 4. 检查时间间隔触发
                if not trigger_type and last_section_time:
                    # 处理时区问题：确保 datetime.now() 和 last_section_time 有相同的时区信息
                    now = datetime.now(last_section_time.tzinfo) if last_section_time.tzinfo else datetime.now()
                    time_since_last = (now - last_section_time).total_seconds()
                    if time_since_last >= self.section_trigger_time_interval:
                        logger.info(f"Time interval trigger: {time_since_last}s >= {self.section_trigger_time_interval}s")
                        trigger_type = SectionTrigger.TIMEOUT.value

                # 5. 检查语义触发（如果有用户消息）
                if not trigger_type and user_message and self._check_semantic_trigger(user_message):
                    logger.info(f"Semantic trigger detected in message: {user_message[:50]}...")
                    trigger_type = SectionTrigger.AUTO.value

                # 6. 如果满足触发条件，执行整理
                if trigger_type:
                    # 更新触发时间（用于冷却时间窗）
                    self._update_last_section_triggered_at(
                        session_id,
                        conn=conn,
                        user_id=user_id,
                        agent_type=agent_type,
                        agent_instance_id=agent_instance_id
                    )

                    # 如果启用异步整理，则入队任务
                    if self.enable_async_section_summarize:
                        self._enqueue_section_summarize_task(session_id, agent_id, agent_type, agent_instance_id, user_id, trigger_type)
                        return None  # 异步处理，不返回结果
                    else:
                        # 同步执行整理（V3升级：传递四层隔离字段）
                        return self.summarize_section(
                            session_id=session_id,
                            agent_id=agent_id,
                            agent_type=agent_type,  # V3新增
                            agent_instance_id=agent_instance_id,  # V3新增
                            user_id=user_id,  # V3新增
                            trigger_type=trigger_type
                        )
            finally:
                self.clear_rls_context(conn=conn)

        # 没有触发条件满足
        return None

    def get_section_history(
        self,
        section_id: str,
        agent_id: Optional[str] = None,
        agent_type: Optional[str] = None,  # V3新增
        agent_instance_id: Optional[str] = None,  # V3新增
        user_id: Optional[str] = None  # V3新增
    ) -> List[Dict[str, Any]]:
        """获取section的所有版本历史。

        Args:
            section_id: Section ID
            agent_id: 可选，过滤特定Agent的条目
            agent_type: Agent类型（V3新增：四层隔离过滤）
            agent_instance_id: Agent实例ID（V3新增：四层隔离过滤）
            user_id: 用户ID（V3新增：四层隔离过滤）

        Returns:
            List[Dict[str, Any]]: 版本历史列表
        """
        with connection_scope() as conn:
            if user_id:
                self.set_rls_context(user_id, agent_type, agent_instance_id, conn=conn)
            try:
                with conn.cursor() as cur:
                    conditions = ["section_id = %s"]
                    params = [section_id]

                    if agent_id:
                        conditions.append("agent_id = %s")
                        params.append(agent_id)

                    # V3新增：四层隔离过滤
                    if user_id:
                        conditions.append("user_id = %s")
                        params.append(user_id)

                    if agent_type:
                        conditions.append("agent_type = %s")
                        params.append(agent_type)

                    if agent_instance_id:
                        conditions.append("agent_instance_id = %s")
                        params.append(agent_instance_id)

                    cur.execute(f"""
                        SELECT entry_id, section_id, section_version, is_latest,
                               content, scene_tags, agent_id, user_id, agent_type, agent_instance_id, created_at
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
                            "user_id": row[7],  # V3新增
                            "agent_type": row[8],  # V3新增
                            "agent_instance_id": row[9],  # V3新增
                            "created_at": row[10]
                        }
                        for row in rows
                    ]
            finally:
                if user_id:
                    self.clear_rls_context(conn=conn)

    def merge_sections(
        self,
        source_section_ids: List[str],
        target_section_id: str,
        agent_id: str,
        agent_type: Optional[str] = None,  # V3新增
        agent_instance_id: Optional[str] = None,  # V3新增
        user_id: Optional[str] = None  # V3新增
    ) -> SectionSummary:
        """合并多个section为一个。

        Args:
            source_section_ids: 源section ID列表
            target_section_id: 目标section ID
            agent_id: Agent ID
            agent_type: Agent类型（V3新增：四层隔离）
            agent_instance_id: Agent实例ID（V3新增：四层隔离）
            user_id: 用户ID（V3新增：四层隔离）

        Returns:
            SectionSummary: 合并后的section总结
        """
        if user_id is None:
            raise ValueError("user_id is required for merging sections")

        with connection_scope() as conn:
            self.set_rls_context(user_id, agent_type, agent_instance_id, conn=conn)
            try:
                # 1. 获取所有源section的最新版本
                all_content = []
                for sec_id in source_section_ids:
                    history = self.get_section_history(sec_id, agent_id, agent_type, agent_instance_id, user_id)
                    if history:
                        all_content.append(history[0]["content"])

                if not all_content:
                    raise ValueError(f"No content found in source sections: {source_section_ids}")

                # 2. 合并内容
                merged_content = self._merge_content_with_llm(all_content, target_section_id)

                # 3. 生成scene_tags
                scene_tags = self._generate_scene_tags(merged_content, agent_id)

                # 4. 获取目标section的版本号
                section_version = self._get_next_section_version(target_section_id, conn=conn)

                # 5. 将旧版本标记为非最新
                self._mark_old_versions_as_not_latest(target_section_id, conn=conn)

                # 6. 写入entries表（V3升级：传递四层隔离参数）
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
                }, user_id=user_id, agent_type=agent_type, agent_instance_id=agent_instance_id)

                # 7. 生成embedding
                try:
                    embedding = self.llm_client.generate_embedding_sync(merged_content)
                    self.vector_client.upsert_embedding(entry_id, embedding)
                except Exception as e:
                    logger.warning(f"Failed to generate embedding for {entry_id}: {e}")

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
            finally:
                self.clear_rls_context(conn=conn)

    def get_section_info(
        self,
        section_id: str,
        user_id: Optional[str] = None,
        agent_type: Optional[str] = None,
        agent_instance_id: Optional[str] = None
    ) -> Optional[SectionInfo]:
        """获取section信息。

        Args:
            section_id: Section ID
            user_id: 用户ID（可选，用于RLS）
            agent_type: Agent类型（可选，用于RLS）
            agent_instance_id: Agent实例ID（可选，用于RLS）

        Returns:
            SectionInfo: Section信息，如果不存在则返回None
        """
        with connection_scope() as conn:
            if user_id:
                self.set_rls_context(user_id, agent_type, agent_instance_id, conn=conn)
            try:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT section_id, session_id, title, status, trigger_type, message_count,
                               summary_content, summary_entry_id, agent_id,
                               user_id, agent_type, agent_instance_id,
                               created_at, updated_at, completed_at
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
                            user_id=row[9],  # V3新增
                            agent_type=row[10],  # V3新增
                            agent_instance_id=row[11],  # V3新增
                            created_at=row[12],
                            updated_at=row[13],
                            completed_at=row[14]
                        )
            finally:
                if user_id:
                    self.clear_rls_context(conn=conn)
        return None

    def _get_session_messages(
        self,
        session_id: str,
        limit: int = 50,
        conn = None,
        user_id: Optional[str] = None,
        agent_type: Optional[str] = None,
        agent_instance_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """获取会话的消息。

        Args:
            session_id: 会话ID
            limit: 返回消息数量限制
            conn: 数据库连接（可选）
            user_id: 用户ID（可选，用于RLS）
            agent_type: Agent类型（可选）
            agent_instance_id: Agent实例ID（可选）

        Returns:
            List[Dict[str, Any]]: 消息列表
        """
        def execute_query(connection):
            if user_id:
                self.set_rls_context(user_id, agent_type, agent_instance_id, conn=connection)
            with connection.cursor() as cur:
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

        if conn:
            return execute_query(conn)
        else:
            with connection_scope() as conn:
                return execute_query(conn)

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
            logger.warning(f"Failed to generate title with LLM: {e}")
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
            logger.warning(f"Failed to summarize with LLM: {e}")
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
            logger.warning(f"Failed to generate tags with LLM: {e}")
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

    def _get_next_section_version(self, section_id: str, conn=None) -> int:
        """获取section的下一个版本号。

        Args:
            section_id: Section ID
            conn: 数据库连接（可选）

        Returns:
            int: 下一个版本号
        """
        def execute_query(connection):
            with connection.cursor() as cur:
                cur.execute("""
                    SELECT COALESCE(MAX(section_version), 0)
                    FROM entries
                    WHERE section_id = %s
                """, (section_id,))

                result = cur.fetchone()
                return (result[0] if result else 0) + 1

        if conn:
            return execute_query(conn)
        else:
            with connection_scope() as conn:
                return execute_query(conn)

    def _mark_old_versions_as_not_latest(self, section_id: str, conn=None) -> None:
        """将section的旧版本标记为非最新。

        Args:
            section_id: Section ID
            conn: 数据库连接（可选）
        """
        def execute_query(connection):
            with connection.cursor() as cur:
                cur.execute("""
                    UPDATE entries
                    SET is_latest = FALSE
                    WHERE section_id = %s AND is_latest = TRUE
                """, (section_id,))

        if conn:
            execute_query(conn)
        else:
            with connection_scope() as conn:
                execute_query(conn)

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
        agent_id: str,
        user_id: Optional[str] = None,  # V3新增
        agent_type: Optional[str] = None,  # V3新增
        agent_instance_id: Optional[str] = None,  # V3新增
        conn=None
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
            user_id: 用户ID（V3新增）
            agent_type: Agent类型（V3新增）
            agent_instance_id: Agent实例ID（V3新增）
            conn: 数据库连接（可选）
        """
        def execute_query(connection):
            if user_id:
                self.set_rls_context(user_id, agent_type, agent_instance_id, conn=connection)
            with connection.cursor() as cur:
                # 检查section是否存在
                cur.execute("""
                    SELECT section_id FROM chat_sections
                    WHERE section_id = %s
                """, (section_id,))

                exists = cur.fetchone() is not None

                if exists:
                    # 更新（V3升级：包含四层隔离字段）
                    cur.execute("""
                        UPDATE chat_sections
                        SET title = %s, status = %s, message_count = %s,
                            summary_content = %s, summary_entry_id = %s,
                            user_id = %s, agent_type = %s, agent_instance_id = %s,
                            updated_at = CURRENT_TIMESTAMP,
                            completed_at = CASE WHEN %s = %s THEN CURRENT_TIMESTAMP ELSE completed_at END
                        WHERE section_id = %s
                    """, (title, status, message_count, summary_content,
                           summary_entry_id, user_id, agent_type, agent_instance_id,
                           status, "completed", section_id))
                else:
                    # 创建（V3升级：包含四层隔离字段）
                    cur.execute("""
                        INSERT INTO chat_sections
                        (section_id, session_id, title, status, trigger_type, message_count,
                         summary_content, summary_entry_id, agent_id, user_id, agent_type, agent_instance_id,
                         created_at, updated_at, completed_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP,
                                CASE WHEN %s = %s THEN CURRENT_TIMESTAMP ELSE NULL END)
                    """, (section_id, session_id, title, status, trigger_type,
                           message_count, summary_content, summary_entry_id, agent_id,
                           user_id, agent_type, agent_instance_id,
                           status, "completed"))

        if conn:
            execute_query(conn)
        else:
            with connection_scope() as conn:
                execute_query(conn)

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
            logger.warning(f"Failed to merge with LLM: {e}")
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
            logger.info(f"Memory0 task enqueued: {task.task_id} for entry {entry_id}")
        except Exception as e:
            # 任务提交失败不影响主流程
            logger.warning(f"Failed to enqueue Memory0 task for {entry_id}: {e}")

    def _get_session_message_count(
        self,
        session_id: str,
        conn=None,
        user_id=None,
        agent_type=None,
        agent_instance_id=None
    ) -> int:
        """获取会话的消息数量。

        Args:
            session_id: 会话ID
            conn: 数据库连接（可选）
            user_id: 用户ID（可选，用于RLS）
            agent_type: Agent类型（可选）
            agent_instance_id: Agent实例ID（可选）

        Returns:
            int: 消息数量
        """
        def execute_query(connection):
            if user_id:
                self.set_rls_context(user_id, agent_type, agent_instance_id, conn=connection)
            with connection.cursor() as cur:
                cur.execute("""
                    SELECT COUNT(*)
                    FROM chat_messages
                    WHERE session_id = %s
                """, (session_id,))

                result = cur.fetchone()
                return result[0] if result else 0

        if conn:
            return execute_query(conn)
        else:
            with connection_scope() as conn:
                return execute_query(conn)

    def _get_session_message_count_since(
        self,
        session_id: str,
        since_time: datetime,
        conn=None,
        user_id=None,
        agent_type=None,
        agent_instance_id=None
    ) -> int:
        """获取会话在指定时间之后新增的消息数量。

        Args:
            session_id: 会话ID
            since_time: 起始时间
            conn: 数据库连接（可选）
            user_id: 用户ID（可选，用于RLS）
            agent_type: Agent类型（可选）
            agent_instance_id: Agent实例ID（可选）

        Returns:
            int: 新增的消息数量
        """
        def execute_query(connection):
            if user_id:
                self.set_rls_context(user_id, agent_type, agent_instance_id, conn=connection)
            with connection.cursor() as cur:
                cur.execute("""
                    SELECT COUNT(*)
                    FROM chat_messages
                    WHERE session_id = %s AND created_at > %s
                """, (session_id, since_time))

                result = cur.fetchone()
                return result[0] if result else 0

        if conn:
            return execute_query(conn)
        else:
            with connection_scope() as conn:
                return execute_query(conn)

    def _get_last_section_time(
        self,
        session_id: str,
        conn=None,
        user_id=None,
        agent_type=None,
        agent_instance_id=None
    ) -> Optional[datetime]:
        """获取会话上次 Section 整理的时间。

        Args:
            session_id: 会话ID
            conn: 数据库连接（可选）
            user_id: 用户ID（可选，用于RLS）
            agent_type: Agent类型（可选）
            agent_instance_id: Agent实例ID（可选）

        Returns:
            Optional[datetime]: 上次整理时间，如果没有则返回 None
        """
        def execute_query(connection):
            if user_id:
                self.set_rls_context(user_id, agent_type, agent_instance_id, conn=connection)
            with connection.cursor() as cur:
                cur.execute("""
                    SELECT MAX(updated_at)
                    FROM chat_sections
                    WHERE session_id = %s AND status = 'completed'
                """, (session_id,))

                result = cur.fetchone()
                return result[0] if result and result[0] else None

        if conn:
            return execute_query(conn)
        else:
            with connection_scope() as conn:
                return execute_query(conn)

    def _get_last_section_triggered_at(
        self,
        session_id: str,
        conn=None,
        user_id=None,
        agent_type=None,
        agent_instance_id=None
    ) -> Optional[datetime]:
        """获取会话上次触发 Section 整理的时间（用于冷却时间窗控制）。

        Args:
            session_id: 会话ID
            conn: 数据库连接（可选）
            user_id: 用户ID（可选，用于RLS）
            agent_type: Agent类型（可选）
            agent_instance_id: Agent实例ID（可选）

        Returns:
            Optional[datetime]: 上次触发时间，如果没有则返回 None
        """
        def execute_query(connection):
            if user_id:
                self.set_rls_context(user_id, agent_type, agent_instance_id, conn=connection)
            with connection.cursor() as cur:
                cur.execute("""
                    SELECT last_section_triggered_at
                    FROM chat_sessions
                    WHERE session_id = %s
                """, (session_id,))

                result = cur.fetchone()
                return result[0] if result and result[0] else None

        if conn:
            return execute_query(conn)
        else:
            with connection_scope() as conn:
                return execute_query(conn)

    def _update_last_section_triggered_at(
        self,
        session_id: str,
        conn=None,
        user_id=None,
        agent_type=None,
        agent_instance_id=None
    ) -> None:
        """更新会话的 Section 触发时间（用于冷却时间窗控制）。

        Args:
            session_id: 会话ID
            conn: 数据库连接（可选）
            user_id: 用户ID（可选，用于RLS）
            agent_type: Agent类型（可选）
            agent_instance_id: Agent实例ID（可选）
        """
        def execute_query(connection):
            if user_id:
                self.set_rls_context(user_id, agent_type, agent_instance_id, conn=connection)
            with connection.cursor() as cur:
                cur.execute("""
                    UPDATE chat_sessions
                    SET last_section_triggered_at = CURRENT_TIMESTAMP
                    WHERE session_id = %s
                """, (session_id,))

        if conn:
            execute_query(conn)
        else:
            with connection_scope() as conn:
                execute_query(conn)

    def _enqueue_section_summarize_task(
        self,
        session_id: str,
        agent_id: str,
        agent_type: Optional[str] = None,  # V3新增
        agent_instance_id: Optional[str] = None,  # V3新增
        user_id: Optional[str] = None,  # V3新增
        trigger_type: str = "auto"
    ) -> None:
        """提交 Section 整理任务到队列。

        Args:
            session_id: 会话ID
            agent_id: Agent ID
            agent_type: Agent类型（V3新增）
            agent_instance_id: Agent实例ID（V3新增）
            user_id: 用户ID（V3新增）
            trigger_type: 触发类型
        """
        try:
            task = Memory0Task.create(
                entry_id=session_id,  # 使用 session_id 作为 entry_id（因为 Section 整理任务需要 session_id）
                task_type=TaskType.SECTION_SUMMARIZE.value,
                payload={
                    "session_id": session_id,
                    "agent_id": agent_id,
                    "agent_type": agent_type,  # V3新增
                    "agent_instance_id": agent_instance_id,  # V3新增
                    "user_id": user_id,  # V3新增
                    "trigger_type": trigger_type
                },
                priority=0
            )
            self.task_queue.enqueue(task)
            logger.info(f"Section summarize task enqueued: {task.task_id} for session {session_id}")
        except Exception as e:
            # 任务提交失败不影响主流程
            logger.warning(f"Failed to enqueue Section summarize task for {session_id}: {e}")

    def _check_semantic_trigger(self, message: str) -> bool:
        """检查消息是否包含语义触发关键词。

        Args:
            message: 用户消息内容

        Returns:
            bool: 是否触发
        """
        if not message:
            return False

        # 检查是否包含任何触发关键词
        for keyword in self.section_trigger_keywords:
            if keyword in message:
                return True

        return False
