"""
异步任务管理器

管理2号通道的各类异步任务：
- NOTE: 笔记整理入库（整理+写库+向量化）
- RAG: RAG查询
- WEB: Web查询
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
import requests
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from ai_factory.integrations.task_types import TaskType
from ai_factory.integrations.entries_ingest import entries_ingest
from ai_factory.integrations.rag_api import qa_answer_rag
from ai_factory.integrations.web_api import qa_answer_web

logger = logging.getLogger(__name__)

# 默认API基础URL
DEFAULT_API_BASE = "http://localhost:8001"


@dataclass
class TaskResult:
    """任务结果"""

    type: TaskType
    status: str  # queued/running/succeeded/failed
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    entry_id: Optional[str] = None  # NOTE任务返回的entry_id
    result: Optional[Dict[str, Any]] = None  # RAG/Web任务返回的结果


@dataclass
class IngestJob:
    """入库任务记录"""

    job_id: str
    payload_hash: str
    raw_text: Optional[str] = None  # NOTE任务的raw_text
    task_type: TaskType = TaskType.NOTE
    status: str = "queued"
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    entry_id: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "job_id": self.job_id,
            "payload_hash": self.payload_hash,
            "raw_text": self.raw_text,
            "task_type": self.task_type.value,
            "status": self.status,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "entry_id": self.entry_id,
            "result": self.result,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class TaskManager:
    """任务管理器（单例）"""

    _instance: Optional[TaskManager] = None
    _lock = threading.Lock()

    def __new__(cls) -> TaskManager:
        """单例模式"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """初始化"""
        if not hasattr(self, "_initialized"):
            self._initialized = True
            self._jobs: Dict[str, IngestJob] = {}
            self._queue: List[str] = []
            self._running_jobs: set = set()
            self._stop_event = threading.Event()

            # 启动工作线程
            self._worker_thread = threading.Thread(
                target=self._worker_loop, daemon=True
            )
            self._worker_thread.start()

    def _hash_payload(self, payload: Dict[str, Any]) -> str:
        """计算payload的hash"""
        # 只对raw_text和task_type进行hash
        hash_data = {
            "raw_text": payload.get("raw_text", ""),
            "task_type": payload.get("task_type", ""),
        }
        return hashlib.sha256(json.dumps(hash_data, sort_keys=True).encode()).hexdigest()

    def submit_task(
        self, task_type: TaskType, payload: Dict[str, Any], idempotency_key: Optional[str] = None
    ) -> str:
        """
        提交任务到队列

        Args:
            task_type: 任务类型
            payload: 任务参数
            idempotency_key: 幂等键

        Returns:
            job_id: 任务ID
        """
        # 计算payload hash
        payload_hash = self._hash_payload(payload)

        # 幂等性检查：如果相同payload已存在，返回已有的job_id
        if idempotency_key:
            # 从idempotency_key反推payload_hash（简化处理）
            idemp_hash = hashlib.sha256(idempotency_key.encode()).hexdigest()[:32]
            for job_id, job in self._jobs.items():
                if job.payload_hash == idemp_hash and job.task_type == task_type:
                    logger.info(f"Job {job_id} 已存在，返回已有任务")
                    return job_id
        else:
            # 基于payload_hash查找
            for job_id, job in self._jobs.items():
                if job.payload_hash == payload_hash and job.task_type == task_type:
                    logger.info(f"Job {job_id} 已存在，返回已有任务")
                    return job_id

        # 创建新任务
        job_id = f"job_{uuid4().hex[:12]}"
        raw_text = payload.get("raw_text", "")

        job = IngestJob(
            job_id=job_id,
            payload_hash=payload_hash,
            raw_text=raw_text,
            task_type=task_type,
            status="queued",
        )

        self._jobs[job_id] = job
        self._queue.append(job_id)

        logger.info(f"任务已提交: job_id={job_id}, task_type={task_type.value}, raw_text_len={len(raw_text)}")

        return job_id

    def _worker_loop(self):
        """工作线程循环"""
        logger.info("任务工作线程已启动")

        while not self._stop_event.is_set():
            time.sleep(0.1)  # 避免忙等待

            # 从队列中取任务
            while self._queue:
                job_id = self._queue.pop(0)

                # 如果任务已经在运行，跳过
                if job_id in self._running_jobs:
                    continue

                # 获取任务
                job = self._jobs.get(job_id)
                if job is None or job.status in ["succeeded", "failed"]:
                    continue

                # 标记为运行中
                self._running_jobs.add(job_id)
                job.status = "running"
                job.updated_at = datetime.utcnow()

                # 在新线程中执行任务
                threading.Thread(
                    target=self._execute_task,
                    args=(job,),
                    daemon=True,
                ).start()

            # 清理已完成的运行状态
            self._running_jobs = {
                job_id for job_id in self._running_jobs
                if self._jobs.get(job_id, {}).get("status") in ["succeeded", "failed"]
            }

    def _execute_task(self, job: IngestJob):
        """执行任务"""
        try:
            logger.info(f"开始执行任务: job_id={job.job_id}, task_type={job.task_type.value}")

            if job.task_type == TaskType.NOTE:
                self._execute_note_task(job)
            elif job.task_type == TaskType.RAG:
                self._execute_rag_task(job)
            elif job.task_type == TaskType.WEB:
                self._execute_web_task(job)
            else:
                raise ValueError(f"未知任务类型: {job.task_type}")

            job.status = "succeeded"
            job.updated_at = datetime.utcnow()
            logger.info(f"任务执行成功: job_id={job.job_id}")

        except Exception as e:
            logger.error(f"任务执行失败: job_id={job.job_id}, error={e!r}")

            job.status = "failed"
            job.error_code = type(e).__name__
            job.error_message = str(e)
            job.updated_at = datetime.utcnow()

    def _execute_note_task(self, job: IngestJob):
        """执行笔记入库任务"""
        raw_text = job.raw_text
        if not raw_text:
            raise ValueError("raw_text 不能为空")

        # 调用现有的同步入库函数
        result = entries_ingest({"raw_text": raw_text})
        entries = result.get("entries", [])
        if not entries:
            raise RuntimeError("entries_ingest 返回空结果")

        job.entry_id = entries[0].get("entry_id")
        job.result = result

    def _execute_rag_task(self, job: IngestJob):
        """执行RAG查询任务"""
        try:
            # 通过HTTP API调用RAG服务
            api_base = os.getenv("API_BASE", DEFAULT_API_BASE)

            # 由于当前RAG服务不直接暴露HTTP接口，我们暂时直接调用内部函数
            # TODO: 创建RAG服务的HTTP接口
            payload = job.result or {}
            result = qa_answer_rag(payload)
            job.result = result
        except Exception as e:
            job.status = "failed"
            job.error_code = type(e).__name__
            job.error_message = str(e)
            job.updated_at = datetime.utcnow()
            return

    def _execute_web_task(self, job: IngestJob):
        """执行Web查询任务"""
        try:
            # 通过HTTP API调用Web服务
            api_base = os.getenv("API_BASE", DEFAULT_API_BASE)

            # 由于当前Web服务不直接暴露HTTP接口，我们暂时直接调用内部函数
            # TODO: 创建Web服务的HTTP接口
            payload = job.result or {}
            result = qa_answer_web(payload)
            job.result = result
        except Exception as e:
            job.status = "failed"
            job.error_code = type(e).__name__
            job.error_message = str(e)
            job.updated_at = datetime.utcnow()
            return

    def get_job(self, job_id: str) -> Optional[IngestJob]:
        """获取任务"""
        return self._jobs.get(job_id)

    def list_jobs(
        self,
        status: Optional[str] = None,
        task_type: Optional[TaskType] = None,
        limit: int = 100,
    ) -> List[IngestJob]:
        """列出任务"""
        jobs = list(self._jobs.values())

        # 过滤
        if status:
            jobs = [j for j in jobs if j.status == status]
        if task_type:
            jobs = [j for j in jobs if j.task_type == task_type]

        # 按时间倒序
        jobs.sort(key=lambda j: j.updated_at, reverse=True)

        return jobs[:limit]

    def stop(self):
        """停止工作线程"""
        self._stop_event.set()
        if self._worker_thread.is_alive():
            self._worker_thread.join(timeout=5)


# 全局任务管理器实例
task_manager = TaskManager()
