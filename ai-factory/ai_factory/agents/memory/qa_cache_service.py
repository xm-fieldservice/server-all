"""
Q&A缓存服务（QACacheService）
用于快速响应重复问题

基于设计文档：Agent记忆系统详细设计与施工文档.md - 3.7 QACacheService 设计
V3.0 Upgrade: 从 tenant_id 迁移到四层隔离（user_id, agent_type, agent_instance_id）
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
import re
import json
import uuid
import logging

from .llm_client import get_llm_client

logger = logging.getLogger(__name__)


class QAStatus(str, Enum):
    """Q&A状态"""
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    PENDING_REVIEW = "pending_review"


class AnswerType(str, Enum):
    """答案类型"""
    CACHED = "cached"      # 缓存的答案
    GENERATED = "generated"  # 生成的答案


@dataclass
class QAInfo:
    """Q&A信息（V3.0: 支持四层隔离）"""
    qa_id: str
    user_id: str
    assistant_id: str
    tenant_id: str  # V3.0: 保留向后兼容，但优先使用agent_type/agent_instance_id
    agent_type: Optional[str]  # V3.0: 四层隔离 - L2
    agent_instance_id: Optional[str]  # V3.0: 四层隔离 - L3
    normalized_question: str
    answer_entry_id: str
    answer_type: AnswerType
    hit_count: int
    last_hit_at: Optional[datetime]
    status: QAStatus
    quality_score: Optional[float]
    tags: List[str]
    metadata: Dict[str, Any]
    created_at: datetime
    updated_at: datetime


@dataclass
class QAStats:
    """Q&A统计信息"""
    total_count: int
    hot_qas_count: int
    warm_qas_count: int
    cold_qas_count: int
    hot_qas: List[QAInfo]
    warm_qas: List[QAInfo]
    cold_qas: List[QAInfo]


class QACacheService:
    """Q&A缓存服务"""

    def __init__(self):
        self._conn = None
        # 初始化 LLM 客户端用于生成 embedding
        from .llm_client import get_llm_client
        self.llm_client = get_llm_client()

    def set_rls_context(
        self,
        user_id: str,
        agent_type: str,
        agent_instance_id: str,
        conn=None
    ) -> None:
        """设置RLS上下文变量（V3.0）。

        Args:
            user_id: 用户ID
            agent_type: Agent类型
            agent_instance_id: Agent实例ID
            conn: 数据库连接（可选）
        """
        try:
            from ai_factory.db.pgvector_client import connection_scope
            if conn is None:
                with connection_scope() as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT set_config('app.current_user_id', %s, true)", (user_id,))
                        cur.execute("SELECT set_config('app.current_agent_type', %s, true)", (agent_type or "",))
                        cur.execute("SELECT set_config('app.current_agent_instance_id', %s, true)", (agent_instance_id or "",))
            else:
                with conn.cursor() as cur:
                    cur.execute("SET LOCAL app.current_user_id = %s", (user_id,))
                    cur.execute("SET LOCAL app.current_agent_type = %s", (agent_type or "",))
                    cur.execute("SET LOCAL app.current_agent_instance_id = %s", (agent_instance_id or "",))
        except Exception as e:
            logger.error(f"Failed to set RLS context: {e}")
            # 不抛出异常，继续执行

    def _get_connection(self):
        """获取数据库连接"""
        from ai_factory.db.pgvector_client import connection_scope
        return connection_scope()

    def cache_qa(
        self,
        user_id: str,
        assistant_id: str,
        question: str,
        answer_entry_id: str,
        tenant_id: str = "default",  # V3.0: 保留向后兼容
        agent_type: Optional[str] = None,  # V3.0
        agent_instance_id: Optional[str] = None,  # V3.0
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        answer_type: AnswerType = AnswerType.CACHED,
        quality_score: float = 0.8,
        conn=None
    ) -> str:
        """
        缓存Q&A对（V3.0: 支持四层隔离）

        Args:
            user_id: 用户ID
            assistant_id: 助手ID
            question: 问题文本
            answer_entry_id: 答案对应的entries节点ID
            tenant_id: 租户/组织ID，默认为"default"（V3.0: 保留向后兼容）
            agent_type: Agent类型（V3.0）
            agent_instance_id: Agent实例ID（V3.0）
            tags: 可选，标签列表
            metadata: 可选，元数据
            answer_type: 答案类型，默认为 CACHED
            quality_score: 质量分数，默认为 0.8
            conn: 数据库连接（可选）

        Returns:
            str: qa_id
        """
        import uuid

        # 规范化问题
        normalized_question = self._normalize_question(question)

        # 生成问题 embedding
        question_embedding = self._generate_embedding(normalized_question)

        # 生成 qa_id
        qa_id = f"qa_{uuid.uuid4().hex[:16]}"

        # 确保隔离参数不为空
        a_type = agent_type or "default_type"
        a_inst = agent_instance_id or "default_instance"

        from ai_factory.db.pgvector_client import connection_scope
        with (conn.cursor() if conn else connection_scope()) as scope:
            # 如果是 connection_scope，结果是 conn；如果是 conn.cursor()，结果是 cur
            # 为统一逻辑，处理如下：
            if conn:
                cur = scope
                # 设置 RLS 上下文
                self.set_rls_context(user_id, a_type, a_inst, conn=conn)
                
                cur.execute("""
                    INSERT INTO qa_query_index
                    (qa_id, user_id, assistant_id, tenant_id, agent_type, agent_instance_id,
                     normalized_question, question_embedding,
                     answer_entry_id, answer_type,
                     hit_count, last_hit_at, status, quality_score,
                     tags, metadata_json, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    RETURNING qa_id
                """, (qa_id, user_id, assistant_id, tenant_id, a_type, a_inst,
                       normalized_question, question_embedding, answer_entry_id, answer_type.value,
                       0, None, QAStatus.ACTIVE.value, quality_score,
                       tags if tags else None,
                       json.dumps(metadata) if metadata else None))
            else:
                db_conn = scope
                # 设置 RLS 上下文
                self.set_rls_context(user_id, a_type, a_inst, conn=db_conn)
                
                with db_conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO qa_query_index
                        (qa_id, user_id, assistant_id, tenant_id, agent_type, agent_instance_id,
                         normalized_question, question_embedding,
                         answer_entry_id, answer_type,
                         hit_count, last_hit_at, status, quality_score,
                         tags, metadata_json, created_at, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                        RETURNING qa_id
                    """, (qa_id, user_id, assistant_id, tenant_id, a_type, a_inst,
                           normalized_question, question_embedding, answer_entry_id, answer_type.value,
                           0, None, QAStatus.ACTIVE.value, quality_score,
                           tags if tags else None,
                           json.dumps(metadata) if metadata else None))

        logger.debug(f"Cached QA {qa_id} with isolation: user_id={user_id}, agent_type={a_type}, agent_instance_id={a_inst}")
        return qa_id

    def query_qa(
        self,
        user_id: str,
        assistant_id: str,
        question: str,
        tenant_id: str = "default",  # V3.0: 保留向后兼容
        agent_type: Optional[str] = None,  # V3.0
        agent_instance_id: Optional[str] = None,  # V3.0
        threshold: float = 0.85,
        limit: int = 5,
        conn=None
    ) -> List[QAInfo]:
        """
        查询相似的Q&A（V3.0: 支持四层隔离）

        Args:
            user_id: 用户ID
            assistant_id: 助手ID
            question: 问题文本
            tenant_id: 租户/组织ID，默认为"default"（V3.0: 保留向后兼容）
            agent_type: Agent类型（V3.0）
            agent_instance_id: Agent实例ID（V3.0）
            threshold: 相似度阈值，默认为 0.85
            limit: 返回结果数量限制，默认为 5
            conn: 数据库连接（可选）

        Returns:
            List[QAInfo]: 匹配的Q&A列表，按相似度和命中次数排序
        """
        # 规范化问题
        normalized_question = self._normalize_question(question)

        # 生成问题 embedding
        question_embedding = self._generate_embedding(normalized_question)

        # 确保隔离参数不为空
        a_type = agent_type or "default_type"
        a_inst = agent_instance_id or "default_instance"

        from ai_factory.db.pgvector_client import connection_scope
        with (conn.cursor() if conn else connection_scope()) as scope:
            if conn:
                cur = scope
                self.set_rls_context(user_id, a_type, a_inst, conn=conn)
            else:
                db_conn = scope
                self.set_rls_context(user_id, a_type, a_inst, conn=db_conn)
                cur = db_conn.cursor()

            try:
                # V3.0: 构建四层隔离条件 (虽然有 RLS，但 SQL 显式带上过滤条件性能更好，且双重保险)
                conditions = ["user_id = %s", "assistant_id = %s", "status = %s"]
                params = [user_id, assistant_id, QAStatus.ACTIVE.value]

                # RLS 已经强制了 agent_type 和 agent_instance_id，这里显式带上以确保逻辑一致
                conditions.append("agent_type = %s")
                params.append(a_type)
                conditions.append("agent_instance_id = %s")
                params.append(a_inst)

                # 使用 pgvector 的余弦相似度检索
                cur.execute(f"""
                    SELECT qa_id, user_id, assistant_id, tenant_id, agent_type, agent_instance_id,
                           normalized_question, answer_entry_id, answer_type,
                           hit_count, last_hit_at, status, quality_score,
                           tags, metadata_json, created_at, updated_at,
                           1 - (question_embedding <=> %s::vector) AS similarity
                    FROM qa_query_index
                    WHERE {' AND '.join(conditions)}
                      AND 1 - (question_embedding <=> %s::vector) >= %s
                    ORDER BY similarity DESC, hit_count DESC, last_hit_at DESC
                    LIMIT %s
                """, params + [question_embedding, question_embedding, threshold, limit])

                rows = cur.fetchall()
                results = [
                    QAInfo(
                        qa_id=row[0],
                        user_id=row[1],
                        assistant_id=row[2],
                        tenant_id=row[3],
                        agent_type=row[4],  # V3.0
                        agent_instance_id=row[5],  # V3.0
                        normalized_question=row[6],
                        answer_entry_id=row[7],
                        answer_type=AnswerType(row[8]),
                        hit_count=row[9],
                        last_hit_at=row[10],
                        status=QAStatus(row[11]),
                        quality_score=self._parse_quality_score(row[12]),
                        tags=row[13] if row[13] else [],
                        metadata=json.loads(row[14]) if row[14] else {},
                        created_at=row[15],
                        updated_at=row[16]
                    )
                    for row in rows
                ]
                return results
            finally:
                if not conn:
                    cur.close()

    def hit_qa(
        self,
        qa_id: str,
        user_id: str,
        agent_type: str,
        agent_instance_id: str,
        conn=None
    ) -> bool:
        """
        记录Q&A命中（V3.0: 增加隔离参数以支持RLS）

        Args:
            qa_id: Q&A ID
            user_id: 用户ID
            agent_type: Agent类型
            agent_instance_id: Agent实例ID
            conn: 数据库连接（可选）

        Returns:
            bool: 是否成功更新
        """
        from ai_factory.db.pgvector_client import connection_scope
        with (conn.cursor() if conn else connection_scope()) as scope:
            if conn:
                cur = scope
                self.set_rls_context(user_id, agent_type, agent_instance_id, conn=conn)
                cur.execute("""
                    UPDATE qa_query_index
                    SET hit_count = hit_count + 1,
                        last_hit_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE qa_id = %s AND user_id = %s AND agent_type = %s AND agent_instance_id = %s
                """, (qa_id, user_id, agent_type, agent_instance_id))
                return cur.rowcount > 0
            else:
                db_conn = scope
                self.set_rls_context(user_id, agent_type, agent_instance_id, conn=db_conn)
                with db_conn.cursor() as cur:
                    cur.execute("""
                        UPDATE qa_query_index
                        SET hit_count = hit_count + 1,
                            last_hit_at = CURRENT_TIMESTAMP,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE qa_id = %s AND user_id = %s AND agent_type = %s AND agent_instance_id = %s
                    """, (qa_id, user_id, agent_type, agent_instance_id))
                    return cur.rowcount > 0

    def _parse_quality_score(self, quality_score_value):
        """
        解析 quality_score 字段

        Args:
            quality_score_value: 从数据库读取的 quality_score 值（可能是 float 或 dict）

        Returns:
            Optional[float]: 解析后的质量分数
        """
        if quality_score_value is None:
            return None
        try:
            # 尝试直接转换为 float
            return float(quality_score_value)
        except (ValueError, TypeError):
            # 如果转换失败，尝试解析 JSON
            try:
                parsed = json.loads(quality_score_value)
                if isinstance(parsed, dict):
                    # 如果是字典，提取 score 字段
                    return float(parsed.get("score", 0.0))
                else:
                    return 0.0
            except (json.JSONDecodeError, TypeError):
                return 0.0

    def deprecate_qa(
        self,
        qa_id: str,
        user_id: str,
        agent_type: str,
        agent_instance_id: str,
        conn=None
    ) -> bool:
        """
        标记Q&A为已废弃（V3.0: 增加隔离参数以支持RLS）

        Args:
            qa_id: Q&A ID
            user_id: 用户ID
            agent_type: Agent类型
            agent_instance_id: Agent实例ID
            conn: 数据库连接（可选）

        Returns:
            bool: 是否成功更新
        """
        from ai_factory.db.pgvector_client import connection_scope
        with (conn.cursor() if conn else connection_scope()) as scope:
            if conn:
                cur = scope
                self.set_rls_context(user_id, agent_type, agent_instance_id, conn=conn)
                cur.execute("""
                    UPDATE qa_query_index
                    SET status = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE qa_id = %s AND user_id = %s AND agent_type = %s AND agent_instance_id = %s
                """, (QAStatus.DEPRECATED.value, qa_id, user_id, agent_type, agent_instance_id))
                return cur.rowcount > 0
            else:
                db_conn = scope
                self.set_rls_context(user_id, agent_type, agent_instance_id, conn=db_conn)
                with db_conn.cursor() as cur:
                    cur.execute("""
                        UPDATE qa_query_index
                        SET status = %s, updated_at = CURRENT_TIMESTAMP
                        WHERE qa_id = %s AND user_id = %s AND agent_type = %s AND agent_instance_id = %s
                    """, (QAStatus.DEPRECATED.value, qa_id, user_id, agent_type, agent_instance_id))
                    return cur.rowcount > 0

    def get_user_qa_stats(
        self,
        user_id: str,
        assistant_id: Optional[str] = None,
        tenant_id: Optional[str] = None,  # V3.0: 保留向后兼容
        agent_type: Optional[str] = None,  # V3.0
        agent_instance_id: Optional[str] = None,  # V3.0
        limit: int = 100,
        conn=None
    ) -> QAStats:
        """
        获取用户的Q&A统计（V3.0: 支持四层隔离）

        Args:
            user_id: 用户ID
            assistant_id: 可选，助手ID
            tenant_id: 可选，租户ID（V3.0: 保留向后兼容）
            agent_type: Agent类型（V3.0）
            agent_instance_id: Agent实例ID（V3.0）
            limit: 返回结果数量限制，默认为 100
            conn: 数据库连接（可选）

        Returns:
            QAStats: Q&A统计信息
        """
        a_type = agent_type or "default_type"
        a_inst = agent_instance_id or "default_instance"

        from ai_factory.db.pgvector_client import connection_scope
        with (conn.cursor() if conn else connection_scope()) as scope:
            if conn:
                cur = scope
                self.set_rls_context(user_id, a_type, a_inst, conn=conn)
            else:
                db_conn = scope
                self.set_rls_context(user_id, a_type, a_inst, conn=db_conn)
                cur = db_conn.cursor()

            try:
                # V3.0: 构建查询条件
                conditions = ["user_id = %s", "agent_type = %s", "agent_instance_id = %s"]
                params = [user_id, a_type, a_inst]

                if assistant_id:
                    conditions.append("assistant_id = %s")
                    params.append(assistant_id)

                if tenant_id:
                    conditions.append("tenant_id = %s")
                    params.append(tenant_id)

                # 获取用户的所有Q&A
                cur.execute(f"""
                    SELECT qa_id, user_id, assistant_id, tenant_id, agent_type, agent_instance_id,
                           normalized_question, answer_entry_id, answer_type,
                           hit_count, last_hit_at, status, quality_score,
                           tags, metadata_json, created_at, updated_at
                    FROM qa_query_index
                    WHERE {' AND '.join(conditions)}
                    ORDER BY hit_count DESC, last_hit_at DESC
                    LIMIT %s
                """, params + [limit])

                rows = cur.fetchall()
                # 转换为 QAInfo 对象
                all_qas = [
                    QAInfo(
                        qa_id=row[0],
                        user_id=row[1],
                        assistant_id=row[2],
                        tenant_id=row[3],
                        agent_type=row[4],  # V3.0
                        agent_instance_id=row[5],  # V3.0
                        normalized_question=row[6],
                        answer_entry_id=row[7],
                        answer_type=AnswerType(row[8]),
                        hit_count=row[9],
                        last_hit_at=row[10],
                        status=QAStatus(row[11]),
                        quality_score=self._parse_quality_score(row[12]),
                        tags=row[13] if row[13] else [],
                        metadata=json.loads(row[14]) if row[14] else {},
                        created_at=row[15],
                        updated_at=row[16]
                    ) for row in rows
                ]

                # 按命中次数分类
                hot_qas = [qa for qa in all_qas if qa.hit_count >= 5]  # 高频（≥5次）
                warm_qas = [qa for qa in all_qas if 2 <= qa.hit_count < 5]  # 温热（2-4次）
                cold_qas = [qa for qa in all_qas if qa.hit_count < 2]  # 冷门（<2次）

                return QAStats(
                    total_count=len(all_qas),
                    hot_qas_count=len(hot_qas),
                    warm_qas_count=len(warm_qas),
                    cold_qas_count=len(cold_qas),
                    hot_qas=hot_qas[:10],
                    warm_qas=warm_qas[:10],
                    cold_qas=cold_qas[:10]
                )
            finally:
                if not conn:
                    cur.close()

    def cleanup_old_qa(
        self,
        user_id: str,
        assistant_id: Optional[str] = None,
        tenant_id: Optional[str] = None,  # V3.0
        agent_type: Optional[str] = None,  # V3.0
        agent_instance_id: Optional[str] = None,  # V3.0
        days_threshold: int = 180,  # 180天未命中则清理
        keep_top_n: int = 50,  # 每个用户保留N条高频Q&A
        conn=None
    ) -> int:
        """
        清理旧的Q&A（V3.0: 支持四层隔离）

        Args:
            user_id: 用户ID
            assistant_id: 可选，助手ID
            tenant_id: 可选，租户ID（V3.0）
            agent_type: Agent类型（V3.0）
            agent_instance_id: Agent实例ID（V3.0）
            days_threshold: 未命中天数阈值，默认为 180 天
            keep_top_n: 保留的高频Q&A数量，默认为 50
            conn: 数据库连接（可选）

        Returns:
            int: 删除的Q&A数量
        """
        cutoff_date = datetime.now() - timedelta(days=days_threshold)
        a_type = agent_type or "default_type"
        a_inst = agent_instance_id or "default_instance"

        from ai_factory.db.pgvector_client import connection_scope
        with (conn.cursor() if conn else connection_scope()) as scope:
            if conn:
                cur = scope
                self.set_rls_context(user_id, a_type, a_inst, conn=conn)
            else:
                db_conn = scope
                self.set_rls_context(user_id, a_type, a_inst, conn=db_conn)
                cur = db_conn.cursor()

            try:
                # V3.0: 构建查询条件
                conditions = ["user_id = %s", "status = %s", "agent_type = %s", "agent_instance_id = %s"]
                params = [user_id, QAStatus.ACTIVE.value, a_type, a_inst]

                if assistant_id:
                    conditions.append("assistant_id = %s")
                    params.append(assistant_id)

                if tenant_id:
                    conditions.append("tenant_id = %s")
                    params.append(tenant_id)

                # 先删除超过阈值未命中的Q&A
                delete_sql = f"""
                    DELETE FROM qa_query_index
                    WHERE {" AND ".join(conditions)}
                      AND (last_hit_at < %s OR last_hit_at IS NULL)
                      AND hit_count <= 1
                """
                cur.execute(delete_sql, params + [cutoff_date])
                deleted_count = cur.rowcount

                # 然后保留top N条高频Q&A
                if keep_top_n > 0:
                    # 先删除低频Q&A，保留top N
                    conditions_str = " AND ".join(conditions)
                    cur.execute(f"""
                        DELETE FROM qa_query_index
                        WHERE {conditions_str}
                          AND qa_id NOT IN (
                              SELECT qa_id FROM (
                                  SELECT qa_id FROM qa_query_index
                                  WHERE {conditions_str}
                                  ORDER BY hit_count DESC, last_hit_at DESC
                                  LIMIT %s
                              ) AS top_qas
                          )
                    """, params + [keep_top_n])
                    deleted_count += cur.rowcount

                logger.debug(f"Cleaned up {deleted_count} old QAs for user={user_id}, agent_type={a_type}")
                return deleted_count
            finally:
                if not conn:
                    cur.close()

    def get_qa(
        self,
        qa_id: str,
        user_id: str,
        agent_type: str,
        agent_instance_id: str,
        conn=None
    ) -> Optional[QAInfo]:
        """
        获取单个Q&A（V3.0: 支持四层隔离字段，补齐RLS支持）

        Args:
            qa_id: Q&A ID
            user_id: 用户ID
            agent_type: Agent类型
            agent_instance_id: Agent实例ID
            conn: 数据库连接（可选）

        Returns:
            Optional[QAInfo]: Q&A信息，如果不存在则返回 None
        """
        from ai_factory.db.pgvector_client import connection_scope
        with (conn.cursor() if conn else connection_scope()) as scope:
            if conn:
                cur = scope
                self.set_rls_context(user_id, agent_type, agent_instance_id, conn=conn)
            else:
                db_conn = scope
                self.set_rls_context(user_id, agent_type, agent_instance_id, conn=db_conn)
                cur = db_conn.cursor()

            try:
                # V3.0: 查询包含四层隔离字段，且增加 WHERE 条件
                cur.execute("""
                    SELECT qa_id, user_id, assistant_id, tenant_id, agent_type, agent_instance_id,
                           normalized_question, answer_entry_id, answer_type,
                           hit_count, last_hit_at, status, quality_score,
                           tags, metadata_json, created_at, updated_at
                    FROM qa_query_index
                    WHERE qa_id = %s AND user_id = %s AND agent_type = %s AND agent_instance_id = %s
                """, (qa_id, user_id, agent_type, agent_instance_id))

                row = cur.fetchone()
                if row:
                    return QAInfo(
                        qa_id=row[0],
                        user_id=row[1],
                        assistant_id=row[2],
                        tenant_id=row[3],
                        agent_type=row[4],  # V3.0
                        agent_instance_id=row[5],  # V3.0
                        normalized_question=row[6],
                        answer_entry_id=row[7],
                        answer_type=AnswerType(row[8]),
                        hit_count=row[9],
                        last_hit_at=row[10],
                        status=QAStatus(row[11]),
                        quality_score=self._parse_quality_score(row[12]),
                        tags=row[13] if row[13] else [],
                        metadata=json.loads(row[14]) if row[14] else {},
                        created_at=row[15],
                        updated_at=row[16]
                    )
                return None
            finally:
                if not conn:
                    cur.close()

    def update_qa(
        self,
        qa_id: str,
        user_id: str,
        agent_type: str,
        agent_instance_id: str,
        quality_score: Optional[float] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        status: Optional[QAStatus] = None,
        conn=None
    ) -> bool:
        """
        更新Q&A信息（V3.0: 补齐RLS支持）

        Args:
            qa_id: Q&A ID
            user_id: 用户ID
            agent_type: Agent类型
            agent_instance_id: Agent实例ID
            quality_score: 可选，质量分数
            tags: 可选，标签列表
            metadata: 可选，元数据
            status: 可选，状态
            conn: 数据库连接（可选）

        Returns:
            bool: 是否成功更新
        """
        updates = []
        params = []

        if quality_score is not None:
            updates.append("quality_score = %s")
            params.append(quality_score)

        if tags is not None:
            updates.append("tags = %s")
            params.append(tags)

        if metadata is not None:
            updates.append("metadata_json = %s")
            params.append(json.dumps(metadata))

        if status is not None:
            updates.append("status = %s")
            params.append(status.value)

        if not updates:
            return False

        updates.append("updated_at = CURRENT_TIMESTAMP")
        
        from ai_factory.db.pgvector_client import connection_scope
        with (conn.cursor() if conn else connection_scope()) as scope:
            if conn:
                cur = scope
                self.set_rls_context(user_id, agent_type, agent_instance_id, conn=conn)
                
                # 构建完整的参数列表：updates中的参数 + WHERE条件的参数
                full_params = params + [qa_id, user_id, agent_type, agent_instance_id]
                cur.execute(f"""
                    UPDATE qa_query_index
                    SET {", ".join(updates)}
                    WHERE qa_id = %s AND user_id = %s AND agent_type = %s AND agent_instance_id = %s
                """, full_params)
                return cur.rowcount > 0
            else:
                db_conn = scope
                self.set_rls_context(user_id, agent_type, agent_instance_id, conn=db_conn)
                with db_conn.cursor() as cur:
                    full_params = params + [qa_id, user_id, agent_type, agent_instance_id]
                    cur.execute(f"""
                        UPDATE qa_query_index
                        SET {", ".join(updates)}
                        WHERE qa_id = %s AND user_id = %s AND agent_type = %s AND agent_instance_id = %s
                    """, full_params)
                    return cur.rowcount > 0

    def _normalize_question(self, question: str) -> str:
        """
        规范化问题文本

        Args:
            question: 原始问题文本

        Returns:
            str: 规范化后的问题文本
        """
        # 去除多余空格和标点
        question = re.sub(r'\s+', ' ', question)
        question = question.strip()

        # 移除常见标点符号（保留中文标点）
        question = re.sub(r'[!?.,;:]+$', '', question)

        # 转小写
        question = question.lower()

        return question

    def _generate_embedding(self, text: str) -> List[float]:
        """
        生成文本的向量嵌入

        Args:
            text: 文本内容

        Returns:
            List[float]: 向量嵌入
        """
        # 使用 LLMClient 生成 embedding
        return self.llm_client.generate_embedding_sync(text)
