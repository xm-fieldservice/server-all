from __future__ import annotations

"""本地长任务执行器（实验版）。

- 提供固定数量的执行位（worker），用于串行执行耗时的 RAG / WEB 查询；
- 支持提交任务、查询任务状态与结果；
- 仅在单机本地场景使用，不涉及跨进程通信或持久化。

三栏页面可以在前端维护排队器，将 RAG / WEB 请求映射为任务：
- submit_task(kind="RAG"|"WEB", payload) -> task_id
- get_task(task_id) -> {status, result, error}

AI 工厂现有的 qa_answer_rag_v2 / qa_answer_web 作为实际执行函数被调用。
"""

import queue
import threading
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Literal, Optional


TaskKind = Literal["RAG", "WEB"]
TaskStatus = Literal["queued", "running", "succeeded", "failed"]


@dataclass
class Task:
    id: str
    kind: TaskKind
    payload: Dict[str, Any]
    status: TaskStatus = "queued"
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class TaskExecutor:
    """固定 worker 数量的简单任务执行器（线程版）。"""

    def __init__(self, *, num_workers: int = 2) -> None:
        self._num_workers = max(1, num_workers)
        self._tasks: Dict[str, Task] = {}
        self._queue: "queue.Queue[str]" = queue.Queue()
        self._lock = threading.Lock()
        self._workers: list[threading.Thread] = []

        # 执行函数表：按 kind 调用具体实现
        from ai_factory.integrations.rag_pipeline_api_v2 import qa_answer_rag_v2
        from ai_factory.integrations.web_api import qa_answer_web

        self._handlers: Dict[TaskKind, Callable[[Dict[str, Any]], Dict[str, Any]]] = {
            "RAG": qa_answer_rag_v2,
            "WEB": qa_answer_web,
        }

        self._start_workers()

    # ------------------------------------------------------------------
    # 对外接口
    # ------------------------------------------------------------------

    def submit_task(self, kind: TaskKind, payload: Dict[str, Any]) -> str:
        """提交一个任务，返回 task_id。"""

        task_id = uuid.uuid4().hex[:16]
        task = Task(id=task_id, kind=kind, payload=dict(payload or {}))

        with self._lock:
            self._tasks[task_id] = task

        self._queue.put(task_id)
        return task_id

    def get_task(self, task_id: str) -> Optional[Task]:
        """查询任务当前状态。"""

        with self._lock:
            return self._tasks.get(task_id)

    # ------------------------------------------------------------------
    # 内部实现
    # ------------------------------------------------------------------

    def _start_workers(self) -> None:
        for i in range(self._num_workers):
            t = threading.Thread(target=self._worker_loop, name=f"TaskWorker-{i}", daemon=True)
            t.start()
            self._workers.append(t)

    def _worker_loop(self) -> None:
        while True:
            task_id = self._queue.get()
            task: Optional[Task]
            with self._lock:
                task = self._tasks.get(task_id)
                if task is None:
                    # 任务可能已被取消或不存在，直接跳过
                    self._queue.task_done()
                    continue
                task.status = "running"

            try:
                handler = self._handlers.get(task.kind)
                if handler is None:
                    raise RuntimeError(f"no handler for task kind {task.kind!r}")

                result = handler(task.payload)

                with self._lock:
                    task.status = "succeeded"
                    # 只保存 dict 结果，避免意外的不可序列化对象
                    task.result = dict(result or {})
            except Exception as exc:  # noqa: BLE001
                with self._lock:
                    task.status = "failed"
                    task.error = repr(exc)
            finally:
                self._queue.task_done()


# 单例执行器（本地场景足够使用一份）
_executor: Optional[TaskExecutor] = None


def get_executor() -> TaskExecutor:
    global _executor
    if _executor is None:
        _executor = TaskExecutor(num_workers=2)
    return _executor


def submit_task(kind: TaskKind, payload: Dict[str, Any]) -> str:
    """快捷函数：提交任务，返回 task_id。"""

    return get_executor().submit_task(kind, payload)


def get_task(task_id: str) -> Optional[Dict[str, Any]]:
    """快捷函数：查询任务状态与结果，返回投影 dict。

    返回示例：
    {
      "id": "...",
      "kind": "RAG" | "WEB",
      "status": "queued" | "running" | "succeeded" | "failed",
      "result": { ... } | None,
      "error": "..." | None,
    }
    """

    task = get_executor().get_task(task_id)
    if task is None:
        return None

    return {
        "id": task.id,
        "kind": task.kind,
        "status": task.status,
        "result": task.result,
        "error": task.error,
    }
