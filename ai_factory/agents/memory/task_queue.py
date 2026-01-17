"""任务队列抽象和 PostgreSQL 实现。

提供 Memory0 任务队列功能，支持：
- 任务提交（enqueue）
- 任务消费（dequeue）
- 任务状态更新
- 错误处理和重试
- 死信队列

基于 PostgreSQL 表实现，避免引入额外依赖。
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum

from ai_factory.db.pgvector_client import connection_scope


class TaskStatus(str, Enum):
    """任务状态枚举"""
    PENDING = "pending"        # 待处理
    PROCESSING = "processing"  # 处理中
    COMPLETED = "completed"    # 已完成
    FAILED = "failed"          # 失败
    DEAD = "dead"              # 死信（多次失败后）


class TaskType(str, Enum):
    """任务类型枚举"""
    MEMORY0_PROCESS_ENTRY = "memory0_process_entry"  # Memory0 处理 entry


@dataclass
class Memory0Task:
    """Memory0 任务数据结构"""
    task_id: str
    entry_id: str
    task_type: str
    payload: Optional[Dict[str, Any]] = None
    status: str = TaskStatus.PENDING.value
    attempts: int = 0
    max_attempts: int = 3
    created_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    failed_at: Optional[str] = None
    dead_at: Optional[str] = None
    last_error: Optional[str] = None
    priority: int = 0
    scheduled_at: Optional[str] = None
    worker_id: Optional[str] = None
    worker_info: Optional[Dict[str, Any]] = None

    @classmethod
    def create(
        cls,
        entry_id: str,
        task_type: str = TaskType.MEMORY0_PROCESS_ENTRY.value,
        payload: Optional[Dict[str, Any]] = None,
        priority: int = 0,
        max_attempts: int = 3
    ) -> "Memory0Task":
        """创建新任务

        Args:
            entry_id: 要处理的 entry_id
            task_type: 任务类型
            payload: 任务负载
            priority: 优先级（数字越小优先级越高）
            max_attempts: 最大尝试次数

        Returns:
            Memory0Task: 新任务实例
        """
        return cls(
            task_id=str(uuid.uuid4()),
            entry_id=entry_id,
            task_type=task_type,
            payload=payload,
            status=TaskStatus.PENDING.value,
            attempts=0,
            max_attempts=max_attempts,
            created_at=datetime.now().isoformat(),
            scheduled_at=datetime.now().isoformat(),
            priority=priority
        )

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Memory0Task":
        """从字典创建"""
        return cls(**data)

    def to_json(self) -> str:
        """转换为 JSON 字符串"""
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> "Memory0Task":
        """从 JSON 字符串创建"""
        return cls.from_dict(json.loads(json_str))


class TaskQueue:
    """任务队列抽象接口

    提供任务提交、消费、状态更新等核心功能。
    """

    def enqueue(self, task: Memory0Task) -> None:
        """提交任务到队列

        Args:
            task: 要提交的任务
        """
        raise NotImplementedError

    def dequeue(
        self,
        block: bool = True,
        timeout: Optional[float] = None
    ) -> Optional[Memory0Task]:
        """从队列中取出一个任务

        Args:
            block: 是否阻塞等待
            timeout: 超时时间（秒）

        Returns:
            Optional[Memory0Task]: 取出的任务，如果没有任务则返回 None
        """
        raise NotImplementedError

    def update_status(
        self,
        task_id: str,
        status: TaskStatus,
        worker_id: Optional[str] = None,
        worker_info: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None
    ) -> None:
        """更新任务状态

        Args:
            task_id: 任务 ID
            status: 新状态
            worker_id: Worker ID
            worker_info: Worker 元信息
            error: 错误信息
        """
        raise NotImplementedError

    def requeue(
        self,
        task_id: str,
        delay_seconds: int = 60
    ) -> None:
        """重新排队任务（用于延迟重试）

        Args:
            task_id: 任务 ID
            delay_seconds: 延迟时间（秒）
        """
        raise NotImplementedError

    def mark_as_dead(self, task_id: str, error: str) -> None:
        """标记任务为死信

        Args:
            task_id: 任务 ID
            error: 错误信息
        """
        raise NotImplementedError

    def get_task(self, task_id: str) -> Optional[Memory0Task]:
        """获取任务详情

        Args:
            task_id: 任务 ID

        Returns:
            Optional[Memory0Task]: 任务详情，不存在则返回 None
        """
        raise NotImplementedError

    def get_pending_tasks(
        self,
        limit: int = 100
    ) -> List[Memory0Task]:
        """获取待处理任务列表

        Args:
            limit: 返回数量限制

        Returns:
            List[Memory0Task]: 待处理任务列表
        """
        raise NotImplementedError

    def get_dead_tasks(
        self,
        limit: int = 100
    ) -> List[Memory0Task]:
        """获取死信任务列表

        Args:
            limit: 返回数量限制

        Returns:
            List[Memory0Task]: 死信任务列表
        """
        raise NotImplementedError

    def cleanup_old_tasks(
        self,
        days_to_keep: int = 7
    ) -> int:
        """清理旧任务

        Args:
            days_to_keep: 保留天数

        Returns:
            int: 删除的任务数量
        """
        raise NotImplementedError


class PostgresTaskQueue(TaskQueue):
    """基于 PostgreSQL 的任务队列实现

    使用 memory_tasks 表作为队列存储，支持：
    - 原子性的任务消费（SELECT FOR UPDATE SKIP LOCKED）
    - 优先级调度
    - 延迟重试
    - 死信队列
    """

    def __init__(self):
        """初始化 PostgreSQL 任务队列"""
        pass

    def enqueue(self, task: Memory0Task) -> None:
        """提交任务到队列

        Args:
            task: 要提交的任务
        """
        with connection_scope() as conn:
            with conn.cursor() as cursor:
                sql = """
                    INSERT INTO memory_tasks (
                        task_id, entry_id, task_type, payload,
                        status, attempts, max_attempts,
                        created_at, scheduled_at, priority
                    ) VALUES (
                        %(task_id)s, %(entry_id)s, %(task_type)s, %(payload)s,
                        %(status)s, %(attempts)s, %(max_attempts)s,
                        %(created_at)s, %(scheduled_at)s, %(priority)s
                    )
                """
                cursor.execute(sql, {
                    "task_id": task.task_id,
                    "entry_id": task.entry_id,
                    "task_type": task.task_type,
                    "payload": json.dumps(task.payload) if task.payload else None,
                    "status": task.status,
                    "attempts": task.attempts,
                    "max_attempts": task.max_attempts,
                    "created_at": task.created_at,
                    "scheduled_at": task.scheduled_at,
                    "priority": task.priority
                })

    def dequeue(
        self,
        block: bool = True,
        timeout: Optional[float] = None
    ) -> Optional[Memory0Task]:
        """从队列中取出一个任务

        使用 SELECT FOR UPDATE SKIP LOCKED 实现并发安全的任务消费。

        Args:
            block: 是否阻塞等待
            timeout: 超时时间（秒）

        Returns:
            Optional[Memory0Task]: 取出的任务，如果没有任务则返回 None
        """
        start_time = time.time()
        max_wait = timeout if timeout is not None else 30.0  # 默认等待 30 秒

        while True:
            with connection_scope() as conn:
                with conn.cursor() as cursor:
                    # 查找并锁定一个待处理的任务
                    sql = """
                        SELECT
                            task_id, entry_id, task_type, payload,
                            status, attempts, max_attempts,
                            created_at, started_at, completed_at, failed_at, dead_at,
                            last_error, priority, scheduled_at, worker_id, worker_info
                        FROM memory_tasks
                        WHERE status = 'pending'
                          AND scheduled_at <= NOW()
                        ORDER BY priority ASC, created_at ASC
                        LIMIT 1
                        FOR UPDATE SKIP LOCKED
                    """
                    cursor.execute(sql)
                    row = cursor.fetchone()

                    if row:
                        # 找到任务，更新状态为 processing
                        task = self._row_to_task(row)
                        update_sql = """
                            UPDATE memory_tasks
                            SET status = 'processing',
                                started_at = NOW(),
                                attempts = attempts + 1
                            WHERE task_id = %(task_id)s
                        """
                        cursor.execute(update_sql, {"task_id": task.task_id})

                        # 重新查询获取更新后的数据
                        cursor.execute(
                            "SELECT * FROM memory_tasks WHERE task_id = %(task_id)s",
                            {"task_id": task.task_id}
                        )
                        updated_row = cursor.fetchone()
                        return self._row_to_task(updated_row)

                    # 没有找到任务
                    if not block:
                        return None

                    # 检查是否超时
                    elapsed = time.time() - start_time
                    if elapsed >= max_wait:
                        return None

                    # 等待一段时间后重试
                    time.sleep(1.0)

    def update_status(
        self,
        task_id: str,
        status: TaskStatus,
        worker_id: Optional[str] = None,
        worker_info: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None
    ) -> None:
        """更新任务状态

        Args:
            task_id: 任务 ID
            status: 新状态
            worker_id: Worker ID
            worker_info: Worker 元信息
            error: 错误信息
        """
        with connection_scope() as conn:
            with conn.cursor() as cursor:
                updates = {
                    "status": status.value,
                    "task_id": task_id
                }

                # 根据状态设置相应的时间戳
                if status == TaskStatus.COMPLETED:
                    updates["completed_at"] = "NOW()"
                elif status == TaskStatus.FAILED:
                    updates["failed_at"] = "NOW()"
                elif status == TaskStatus.DEAD:
                    updates["dead_at"] = "NOW()"

                if worker_id:
                    updates["worker_id"] = worker_id

                if worker_info:
                    updates["worker_info"] = json.dumps(worker_info)

                if error:
                    updates["last_error"] = error

                # 构建 SQL
                set_clauses = []
                params = {"task_id": task_id}

                for key, value in updates.items():
                    if key == "task_id":
                        continue
                    if isinstance(value, str) and value == "NOW()":
                        set_clauses.append(f"{key} = NOW()")
                    elif isinstance(value, str) and value == status.value:
                        set_clauses.append(f"{key} = %({key})s")
                        params[key] = value
                    else:
                        set_clauses.append(f"{key} = %({key})s")
                        params[key] = value

                sql = f"""
                    UPDATE memory_tasks
                    SET {', '.join(set_clauses)}
                    WHERE task_id = %(task_id)s
                """
                cursor.execute(sql, params)

    def requeue(
        self,
        task_id: str,
        delay_seconds: int = 60
    ) -> None:
        """重新排队任务（用于延迟重试）

        Args:
            task_id: 任务 ID
            delay_seconds: 延迟时间（秒）
        """
        with connection_scope() as conn:
            with conn.cursor() as cursor:
                sql = """
                    UPDATE memory_tasks
                    SET status = 'pending',
                        scheduled_at = NOW() + make_interval(secs => %(delay)s),
                        last_error = NULL
                    WHERE task_id = %(task_id)s
                """
                cursor.execute(sql, {"task_id": task_id, "delay": delay_seconds})

    def mark_as_dead(self, task_id: str, error: str) -> None:
        """标记任务为死信

        Args:
            task_id: 任务 ID
            error: 错误信息
        """
        with connection_scope() as conn:
            with conn.cursor() as cursor:
                sql = """
                    UPDATE memory_tasks
                    SET status = 'dead',
                        dead_at = NOW(),
                        last_error = %(error)s
                    WHERE task_id = %(task_id)s
                """
                cursor.execute(sql, {"task_id": task_id, "error": error})

    def get_task(self, task_id: str) -> Optional[Memory0Task]:
        """获取任务详情

        Args:
            task_id: 任务 ID

        Returns:
            Optional[Memory0Task]: 任务详情，不存在则返回 None
        """
        with connection_scope() as conn:
            with conn.cursor() as cursor:
                sql = """
                    SELECT * FROM memory_tasks WHERE task_id = %(task_id)s
                """
                cursor.execute(sql, {"task_id": task_id})
                row = cursor.fetchone()
                return self._row_to_task(row) if row else None

    def get_pending_tasks(
        self,
        limit: int = 100
    ) -> List[Memory0Task]:
        """获取待处理任务列表

        Args:
            limit: 返回数量限制

        Returns:
            List[Memory0Task]: 待处理任务列表
        """
        with connection_scope() as conn:
            with conn.cursor() as cursor:
                sql = """
                    SELECT * FROM memory_tasks
                    WHERE status = 'pending'
                      AND scheduled_at <= NOW()
                    ORDER BY priority ASC, created_at ASC
                    LIMIT %(limit)s
                """
                cursor.execute(sql, {"limit": limit})
                rows = cursor.fetchall()
                return [self._row_to_task(row) for row in rows]

    def get_dead_tasks(
        self,
        limit: int = 100
    ) -> List[Memory0Task]:
        """获取死信任务列表

        Args:
            limit: 返回数量限制

        Returns:
            List[Memory0Task]: 死信任务列表
        """
        with connection_scope() as conn:
            with conn.cursor() as cursor:
                sql = """
                    SELECT * FROM memory_tasks
                    WHERE status = 'dead'
                    ORDER BY dead_at DESC
                    LIMIT %(limit)s
                """
                cursor.execute(sql, {"limit": limit})
                rows = cursor.fetchall()
                return [self._row_to_task(row) for row in rows]

    def cleanup_old_tasks(
        self,
        days_to_keep: int = 7
    ) -> int:
        """清理旧任务

        Args:
            days_to_keep: 保留天数

        Returns:
            int: 删除的任务数量
        """
        with connection_scope() as conn:
            with conn.cursor() as cursor:
                sql = """
                    DELETE FROM memory_tasks
                    WHERE status IN ('completed', 'failed', 'dead')
                      AND created_at < NOW() - make_interval(days => %(days)s)
                    RETURNING task_id
                """
                cursor.execute(sql, {"days": days_to_keep})
                deleted_count = cursor.rowcount
                return deleted_count

    def _row_to_task(self, row) -> Memory0Task:
        """将数据库行转换为 Memory0Task
        
        Args:
            row: 数据库行（psycopg2 返回的元组）
        
        Returns:
            Memory0Task: 任务对象
        """
        # 处理时间戳字段
        datetime_fields = [
            'created_at', 'started_at', 'completed_at',
            'failed_at', 'dead_at', 'scheduled_at'
        ]
        
        # 从 cursor.description 获取列名（需要传入 cursor）
        # 这里假设 row 是一个元组，列名按顺序排列
        # 列顺序：task_id, entry_id, task_type, payload, status, attempts, max_attempts,
        #          created_at, started_at, completed_at, failed_at, dead_at,
        #          last_error, priority, scheduled_at, worker_id, worker_info
        column_names = [
            'task_id', 'entry_id', 'task_type', 'payload', 'status',
            'attempts', 'max_attempts', 'created_at', 'started_at',
            'completed_at', 'failed_at', 'dead_at', 'last_error',
            'priority', 'scheduled_at', 'worker_id', 'worker_info'
        ]
        
        row_dict = {}
        for i, value in enumerate(row):
            if i < len(column_names):
                row_dict[column_names[i]] = value
        
        for field in datetime_fields:
            if row_dict.get(field) and hasattr(row_dict[field], 'isoformat'):
                row_dict[field] = row_dict[field].isoformat()
        
        # 处理 JSONB 字段
        if row_dict.get('payload') and isinstance(row_dict['payload'], dict):
            row_dict['payload'] = row_dict['payload']
        
        if row_dict.get('worker_info') and isinstance(row_dict['worker_info'], dict):
            row_dict['worker_info'] = row_dict['worker_info']
        
        return Memory0Task(**row_dict)


# 便捷函数：创建任务队列实例
def get_task_queue() -> TaskQueue:
    """获取任务队列实例

    Returns:
        TaskQueue: 任务队列实例
    """
    return PostgresTaskQueue()
