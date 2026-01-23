"""Memory0Service implementation.

Implements long-term memory governance on top of entries and embeddings.
Follows the design in section 1.10/3.6 of `Agent记忆系统详细设计与施工文档.md`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Any, List, Optional
from datetime import datetime

from ai_factory.db.pgvector_client import connection_scope
from psycopg2.extras import Json
from .entry_service import EntryService
from .vector_client import VectorClient
from .llm_client import get_llm_client
from .config import get_config_manager, Memory0Config


class MemoryRelation(str, Enum):
    """记忆关系类型"""
    NEW = "new"
    UPDATE = "update"
    OVERRIDE = "override"
    DUPLICATE = "duplicate"


@dataclass
class MemoryCandidate:
    """记忆候选"""
    content: str
    user_id: str
    agent_id: str
    scene_tags: Dict[str, List[str]]
    space_type: str
    metadata: Dict[str, Any]


@dataclass
class MemoryResult:
    """记忆治理结果"""
    relation: MemoryRelation
    entry_id: str
    overridden_entry_ids: List[str]
    metadata: Dict[str, Any]


class Memory0Service:
    """长期记忆治理服务（Memory0）。"""

    def __init__(
        self,
        entry_service: EntryService,
        vector_client: Optional[VectorClient] = None,
        config: Optional[Memory0Config] = None,
        agent_id: str = "default",
        enable_llm_judgment: bool = False
    ):
        """初始化 Memory0Service。

        Args:
            entry_service: EntryService 实例
            vector_client: 可选的 VectorClient 实例
            config: 可选的 Memory0Config 配置
            agent_id: Agent ID，用于获取特定配置
            enable_llm_judgment: 是否启用 LLM-based 关系判定（默认 False，使用规则判定）
        """
        self.entry_service = entry_service
        self.vector_client = vector_client or VectorClient()
        self.llm_client = get_llm_client()
        self.agent_id = agent_id
        self.enable_llm_judgment = enable_llm_judgment
        
        # 获取配置
        config_manager = get_config_manager()
        agent_config = config_manager.get_agent_config(agent_id)
        self.config = config or agent_config.memory0_config

    @property
    def SIM_THRESHOLD_LOW(self) -> float:
        """低相似度阈值"""
        return self.config.sim_threshold_low

    @property
    def SIM_THRESHOLD_HIGH(self) -> float:
        """高相似度阈值"""
        return self.config.sim_threshold_high

    @property
    def TOP_K_CANDIDATES(self) -> int:
        """检索候选数量"""
        return self.config.top_k_candidates

    @property
    def CONFLICT_KEYWORDS(self) -> List[str]:
        """冲突信号词列表"""
        return self.config.conflict_keywords

    @property
    def UPDATE_MODE(self) -> str:
        """UPDATE 模式"""
        return self.config.update_mode

    @property
    def IMPORTANCE_NEW(self) -> float:
        """NEW 条目的初始 importance"""
        return self.config.importance_new

    @property
    def IMPORTANCE_UPDATE(self) -> float:
        """UPDATE 时提升 importance 的因子"""
        return self.config.importance_update

    @property
    def IMPORTANCE_OVERRIDE(self) -> float:
        """OVERRIDE 时新条目的 importance"""
        return self.config.importance_override

    @property
    def DUPLICATE_LENGTH_RATIO(self) -> float:
        """内容长度差异阈值"""
        return self.config.duplicate_length_ratio

    @property
    def DUPLICATE_PREFIX_LEN(self) -> int:
        """前缀比较长度"""
        return self.config.duplicate_prefix_len

    @property
    def ENABLE_AUTO_MERGE(self) -> bool:
        """是否允许自动内容合并"""
        return self.config.enable_auto_merge

    @property
    def ENABLE_CONFLICT_MARKING(self) -> bool:
        """是否在 extra_meta 中记录冲突标记"""
        return self.config.enable_conflict_marking

    def upsert_memory(self, candidate: MemoryCandidate) -> MemoryResult:
        """将候选知识写入长期记忆视图（可能是新增/强化/覆盖）。

        步骤：
        1. 基于 candidate.content 生成向量，检索相似条目；
        2. 对比相似条目的 content / metadata，判定关系；
        3. 通过 entry_service 调用，将结果写回 entries。

        Args:
            candidate: 记忆候选

        Returns:
            MemoryResult: 治理结果
        """
        # 1. 生成候选内容的embedding
        try:
            candidate_embedding = self.llm_client.generate_embedding_sync(candidate.content)
        except Exception as e:
            print(f"[Memory0Service] Warning: Failed to generate embedding: {e}")
            # 如果embedding生成失败，直接作为NEW处理
            return self._handle_new(candidate, None)

        # 2. 检索相似条目
        filters = {
            "user_id": candidate.user_id,
            "agent_id": candidate.agent_id,
            "space_type": candidate.space_type,
        }
        similar_entries = self.entry_service.search_similar(
            query_embedding=candidate_embedding,
            filters=filters,
            top_k=self.TOP_K_CANDIDATES
        )

        # 3. 如果没有相似条目，直接判定为NEW
        if not similar_entries:
            return self._handle_new(candidate, candidate_embedding)

        # 4. 找到最相似的条目
        best_match = similar_entries[0]
        similarity = best_match.get("similarity", 0)

        # 5. 根据相似度判定关系
        if similarity < self.SIM_THRESHOLD_LOW:
            # 相似度低，判定为NEW
            return self._handle_new(candidate, candidate_embedding)
        elif similarity >= self.SIM_THRESHOLD_HIGH:
            # 高相似度，判定为DUPLICATE或UPDATE/OVERRIDE
            return self._handle_high_similarity(candidate, candidate_embedding, best_match)
        else:
            # 中等相似度，需要进一步判断
            return self._handle_medium_similarity(candidate, candidate_embedding, best_match)

    def process_entry(self, entry_id: str) -> MemoryResult:
        """针对已存在的 entries 记录执行记忆治理（用于异步任务消费）。

        通常由后台 Worker 在接收到 Memory0 任务后调用。

        Args:
            entry_id: 条目ID

        Returns:
            MemoryResult: 治理结果
        """
        # 1. 获取条目信息
        entry = self.entry_service.get_entry(entry_id)
        if entry is None:
            raise ValueError(f"Entry {entry_id} not found")

        # 2. 构造候选对象
        candidate = MemoryCandidate(
            content=entry.get("content", ""),
            user_id=entry.get("user_id", "default"),
            agent_id=entry.get("agent_id", "default"),
            scene_tags=entry.get("scene_tags", {}),
            space_type=entry.get("space_type", "note"),
            metadata=entry.get("metadata", {})
        )

        # 3. 调用 upsert_memory 进行治理
        result = self.upsert_memory(candidate)

        # 4. 如果是NEW，更新原条目的importance和last_seen_at
        if result.relation == MemoryRelation.NEW:
            self._update_entry_importance(entry_id, 1.0)
        # 如果是UPDATE或DUPLICATE，更新原条目的usage_count和last_seen_at
        elif result.relation in (MemoryRelation.UPDATE, MemoryRelation.DUPLICATE):
            self._update_entry_usage(entry_id)

        return result

    def _handle_new(
        self,
        candidate: MemoryCandidate,
        embedding: Optional[List[float]]
    ) -> MemoryResult:
        """处理NEW关系：新增条目。

        Args:
            candidate: 记忆候选
            embedding: 向量（可选）

        Returns:
            MemoryResult: 治理结果
        """
        entry_id = self.entry_service.create_entry({
            "entry_id": f"ent_{uuid.uuid4().hex}",
            "title": candidate.metadata.get("title", "Memory Entry"),
            "content": candidate.content,
            "scene_tags": candidate.scene_tags,
            "agent_id": candidate.agent_id,
            "space_type": candidate.space_type,
            "importance": 1.0,
            "usage_count": 0,
            "last_seen_at": datetime.now(),
        })

        # 生成embedding
        if embedding is not None:
            try:
                self.vector_client.upsert_embedding(entry_id, embedding)
            except Exception as e:
                print(f"[Memory0Service] Warning: Failed to upsert embedding: {e}")

        return MemoryResult(
            relation=MemoryRelation.NEW,
            entry_id=entry_id,
            overridden_entry_ids=[],
            metadata=candidate.metadata
        )

    def _handle_high_similarity(
        self,
        candidate: MemoryCandidate,
        embedding: Optional[List[float]],
        best_match: Dict[str, Any]
    ) -> MemoryResult:
        """处理高相似度情况：DUPLICATE/UPDATE/OVERRIDE。

        Args:
            candidate: 记忆候选
            embedding: 向量（可选）
            best_match: 最佳匹配条目

        Returns:
            MemoryResult: 治理结果
        """
        existing_content = best_match.get("content", "")
        existing_entry_id = best_match.get("entry_id")

        # 如果启用了 LLM-based 判定，使用 LLM 判定关系
        if self.enable_llm_judgment:
            return self._handle_with_llm_judgment(candidate, embedding, existing_entry_id, existing_content)

        # 否则使用规则判定
        # 1. 检查是否有冲突信号
        has_conflict = self._detect_conflict(candidate.content, existing_content)

        if has_conflict:
            # 有冲突，判定为OVERRIDE
            return self._handle_override(candidate, embedding, existing_entry_id)

        # 2. 检查是否几乎完全重复
        is_duplicate = self._is_duplicate(candidate.content, existing_content)

        if is_duplicate:
            # 判定为DUPLICATE
            self._update_entry_usage(existing_entry_id)
            return MemoryResult(
                relation=MemoryRelation.DUPLICATE,
                entry_id=existing_entry_id,
                overridden_entry_ids=[],
                metadata={"duplicate_of": existing_entry_id}
            )

        # 3. 否则判定为UPDATE
        return self._handle_update(candidate, embedding, existing_entry_id)

    def _handle_medium_similarity(
        self,
        candidate: MemoryCandidate,
        embedding: Optional[List[float]],
        best_match: Dict[str, Any]
    ) -> MemoryResult:
        """处理中等相似度情况：UPDATE/OVERRIDE。

        Args:
            candidate: 记忆候选
            embedding: 向量（可选）
            best_match: 最佳匹配条目

        Returns:
            MemoryResult: 治理结果
        """
        existing_content = best_match.get("content", "")
        existing_entry_id = best_match.get("entry_id")

        # 如果启用了 LLM-based 判定，使用 LLM 判定关系
        if self.enable_llm_judgment:
            return self._handle_with_llm_judgment(candidate, embedding, existing_entry_id, existing_content)

        # 否则使用规则判定
        # 检查是否有冲突信号
        has_conflict = self._detect_conflict(candidate.content, existing_content)

        if has_conflict:
            # 有冲突，判定为OVERRIDE
            return self._handle_override(candidate, embedding, existing_entry_id)
        else:
            # 无冲突，判定为UPDATE
            return self._handle_update(candidate, embedding, existing_entry_id)

    def _handle_update(
        self,
        candidate: MemoryCandidate,
        embedding: Optional[List[float]],
        existing_entry_id: str
    ) -> MemoryResult:
        """处理UPDATE关系：更新原条目的权重和时间戳。

        Args:
            candidate: 记忆候选
            embedding: 向量（可选）
            existing_entry_id: 现有条目ID

        Returns:
            MemoryResult: 治理结果
        """
        # 更新原条目的importance、last_seen_at、usage_count
        self._update_entry_importance(existing_entry_id, self.IMPORTANCE_UPDATE)  # 提升importance
        self._update_entry_usage(existing_entry_id)

        return MemoryResult(
            relation=MemoryRelation.UPDATE,
            entry_id=existing_entry_id,
            overridden_entry_ids=[],
            metadata={"updated_at": datetime.now().isoformat()}
        )

    def _handle_override(
        self,
        candidate: MemoryCandidate,
        embedding: Optional[List[float]],
        existing_entry_id: str
    ) -> MemoryResult:
        """处理OVERRIDE关系：新增新条目，标记旧条目为deprecated。

        Args:
            candidate: 记忆候选
            embedding: 向量（可选）
            existing_entry_id: 现有条目ID

        Returns:
            MemoryResult: 治理结果
        """
        # 1. 标记旧条目为deprecated
        self._mark_entry_as_deprecated(existing_entry_id)

        # 2. 创建新条目
        new_entry_id = self.entry_service.create_entry({
            "entry_id": f"ent_{uuid.uuid4().hex}",
            "title": candidate.metadata.get("title", "Memory Entry"),
            "content": candidate.content,
            "scene_tags": candidate.scene_tags,
            "agent_id": candidate.agent_id,
            "space_type": candidate.space_type,
            "importance": 1.5,  # OVERRIDE的新条目importance更高
            "usage_count": 0,
            "last_seen_at": datetime.now(),
            "overridden_entry_ids": [existing_entry_id],
        })

        # 3. 生成embedding
        if embedding is not None:
            try:
                self.vector_client.upsert_embedding(new_entry_id, embedding)
            except Exception as e:
                print(f"[Memory0Service] Warning: Failed to upsert embedding: {e}")

        return MemoryResult(
            relation=MemoryRelation.OVERRIDE,
            entry_id=new_entry_id,
            overridden_entry_ids=[existing_entry_id],
            metadata={"overridden_at": datetime.now().isoformat()}
        )

    def _detect_conflict(self, new_content: str, old_content: str) -> bool:
        """检测是否有冲突信号。

        Args:
            new_content: 新内容
            old_content: 旧内容

        Returns:
            bool: 是否有冲突
        """
        # 检查新内容中是否包含冲突信号词
        for keyword in self.CONFLICT_KEYWORDS:
            if keyword in new_content:
                return True
        return False

    def _is_duplicate(self, new_content: str, old_content: str) -> bool:
        """判断是否几乎完全重复。

        Args:
            new_content: 新内容
            old_content: 旧内容

        Returns:
            bool: 是否重复
        """
        # 使用配置中的参数
        if len(new_content) == 0 or len(old_content) == 0:
            return False

        length_ratio = min(len(new_content), len(old_content)) / max(len(new_content), len(old_content))
        if length_ratio < self.DUPLICATE_LENGTH_RATIO:
            return False

        # 比较前缀
        prefix_len = min(self.DUPLICATE_PREFIX_LEN, len(new_content), len(old_content))
        return new_content[:prefix_len] == old_content[:prefix_len]

    def _update_entry_importance(self, entry_id: str, factor: float) -> None:
        """更新条目的importance。

        Args:
            entry_id: 条目ID
            factor: 乘数因子
        """
        with connection_scope() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE entries
                    SET importance = importance * %s,
                        last_seen_at = CURRENT_TIMESTAMP
                    WHERE entry_id = %s
                """, (factor, entry_id))

    def _update_entry_usage(self, entry_id: str) -> None:
        """更新条目的usage_count和last_seen_at。

        Args:
            entry_id: 条目ID
        """
        with connection_scope() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE entries
                    SET usage_count = usage_count + 1,
                        last_seen_at = CURRENT_TIMESTAMP
                    WHERE entry_id = %s
                """, (entry_id,))

    def _handle_with_llm_judgment(
        self,
        candidate: MemoryCandidate,
        embedding: Optional[List[float]],
        existing_entry_id: str,
        existing_content: str
    ) -> MemoryResult:
        """使用 LLM 判定关系并处理。

        Args:
            candidate: 记忆候选
            embedding: 向量（可选）
            existing_entry_id: 现有条目ID
            existing_content: 现有条目内容

        Returns:
            MemoryResult: 治理结果
        """
        try:
            # 调用 LLM 判定关系
            judgment = self.llm_client.determine_memory_relation_sync(
                new_content=candidate.content,
                old_content=existing_content
            )

            relation = judgment.get("relation", "new")
            reason = judgment.get("reason", "")
            confidence = judgment.get("confidence", 0.5)

            print(f"[Memory0Service] LLM judgment: relation={relation}, reason={reason}, confidence={confidence}")

            # 根据判定结果处理
            if relation == "new":
                return self._handle_new(candidate, embedding)
            elif relation == "duplicate":
                self._update_entry_usage(existing_entry_id)
                return MemoryResult(
                    relation=MemoryRelation.DUPLICATE,
                    entry_id=existing_entry_id,
                    overridden_entry_ids=[],
                    metadata={"duplicate_of": existing_entry_id, "llm_reason": reason, "llm_confidence": confidence}
                )
            elif relation == "update":
                return self._handle_update(candidate, embedding, existing_entry_id)
            elif relation == "override":
                return self._handle_override(candidate, embedding, existing_entry_id)
            else:
                # 未知关系类型，默认为 NEW
                print(f"[Memory0Service] Warning: Unknown relation type '{relation}', defaulting to NEW")
                return self._handle_new(candidate, embedding)

        except Exception as e:
            # LLM 判定失败，回退到规则判定
            print(f"[Memory0Service] Warning: LLM judgment failed: {e}, falling back to rule-based judgment")
            
            # 检查是否有冲突信号
            has_conflict = self._detect_conflict(candidate.content, existing_content)

            if has_conflict:
                return self._handle_override(candidate, embedding, existing_entry_id)
            else:
                return self._handle_update(candidate, embedding, existing_entry_id)

    def _mark_entry_as_deprecated(self, entry_id: str) -> None:
        """标记条目为deprecated。

        Args:
            entry_id: 条目ID
        """
        with connection_scope() as conn:
            with conn.cursor() as cur:
                # 将is_latest标记为FALSE
                cur.execute("""
                    UPDATE entries
                    SET is_latest = FALSE,
                        last_seen_at = CURRENT_TIMESTAMP
                    WHERE entry_id = %s
                """, (entry_id,))

                # 在extra_meta中添加deprecated标记
                cur.execute("""
                    UPDATE entries
                    SET extra_meta = COALESCE(extra_meta, '{}'::jsonb) || '{"deprecated": true}'::jsonb
                    WHERE entry_id = %s
                """, (entry_id,))
