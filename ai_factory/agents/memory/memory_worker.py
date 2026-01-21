"""Memory0 后台 Worker。

负责消费任务队列中的 Memory0 任务，调用 Memory0Service 进行记忆治理。

功能：
- 持续从队列中取出任务
- 调用 Memory0Service.process_entry() 处理任务
- 调用 SectionService.summarize_section() 处理 Section 整理任务
- 错误处理和重试机制（指数退避）
- 死信队列处理
- 健康检查和监控
- 优雅关闭
"""

from __future__ import annotations

import threading
import time
import signal
import logging
import uuid
from typing import Optional, Dict, Any
from datetime import datetime

from .task_queue import TaskQueue, Memory0Task, TaskStatus, get_task_queue, TaskType
from .memory0_service import Memory0Service
from .entry_service import EntryService
from .section_service import SectionService

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class WorkerConfig:
    """Worker 配置"""

    def __init__(
        self,
        poll_interval: float = 1.0,           # 轮询间隔（秒）
        max_retries: int = 3,                  # 最大重试次数
        retry_delay_base: float = 60.0,         # 基础重试延迟（秒）
        retry_delay_multiplier: float = 2.0,     # 重试延迟倍数
        heartbeat_interval: float = 30.0,       # 心跳间隔（秒）
        shutdown_timeout: float = 30.0,          # 关闭超时（秒）
        enable_auto_cleanup: bool = True,        # 是否启用自动清理
        cleanup_interval: float = 3600.0,       # 清理间隔（秒）
        cleanup_days_to_keep: int = 7            # 清理保留天数
    ):
        self.poll_interval = poll_interval
        self.max_retries = max_retries
        self.retry_delay_base = retry_delay_base
        self.retry_delay_multiplier = retry_delay_multiplier
        self.heartbeat_interval = heartbeat_interval
        self.shutdown_timeout = shutdown_timeout
        self.enable_auto_cleanup = enable_auto_cleanup
        self.cleanup_interval = cleanup_interval
        self.cleanup_days_to_keep = cleanup_days_to_keep


class Memory0Worker:
    """Memory0 后台 Worker

    消费任务队列，调用 Memory0Service 进行记忆治理。
    支持优雅关闭、错误重试、死信队列等功能。
    """

    def __init__(
        self,
        memory0_service: Memory0Service,
        task_queue: Optional[TaskQueue] = None,
        config: Optional[WorkerConfig] = None,
        section_service: Optional[SectionService] = None
    ):
        """初始化 Worker

        Args:
            memory0_service: Memory0Service 实例
            task_queue: 任务队列实例（默认使用 get_task_queue()）
            config: Worker 配置（默认使用默认配置）
            section_service: 可选的 SectionService 实例，用于处理 Section 整理任务
        """
        self.memory0_service = memory0_service
        self.section_service = section_service
        self.task_queue = task_queue or get_task_queue()
        self.config = config or WorkerConfig()

        # Worker 标识
        self.worker_id = f"worker-{uuid.uuid4().hex[:8]}"
        self.worker_info = {
            "worker_id": self.worker_id,
            "started_at": datetime.now().isoformat(),
            "pid": None,  # 将在启动时设置
        }

        # 运行状态
        self._running = False
        self._shutdown_event = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._cleanup_thread: Optional[threading.Thread] = None

        # 统计信息
        self.stats = {
            "tasks_processed": 0,
            "tasks_succeeded": 0,
            "tasks_failed": 0,
            "tasks_dead": 0,
            "total_retries": 0,
            "last_heartbeat": None,
            "uptime_seconds": 0,
        }

        # 注册信号处理
        self._setup_signal_handlers()

    def _setup_signal_handlers(self):
        """设置信号处理器，支持优雅关闭"""
        try:
            signal.signal(signal.SIGINT, self._handle_signal)
            signal.signal(signal.SIGTERM, self._handle_signal)
        except ValueError:
            # 在非主线程中无法设置信号处理器
            pass

    def _handle_signal(self, signum, frame):
        """处理关闭信号"""
        logger.info(f"Worker {self.worker_id} 收到关闭信号 {signum}")
        self.stop()

    def start(self):
        """启动 Worker"""
        if self._running:
            logger.warning(f"Worker {self.worker_id} 已经在运行中")
            return

        logger.info(f"启动 Worker {self.worker_id}")
        self._running = True
        self._shutdown_event.clear()
        self.worker_info["pid"] = __import__("os").getpid()

        # 启动工作线程
        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            name=f"Memory0Worker-{self.worker_id}",
            daemon=True
        )
        self._worker_thread.start()

        # 启动心跳线程
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            name=f"Memory0Worker-Heartbeat-{self.worker_id}",
            daemon=True
        )
        self._heartbeat_thread.start()

        # 启动清理线程（如果启用）
        if self.config.enable_auto_cleanup:
            self._cleanup_thread = threading.Thread(
                target=self._cleanup_loop,
                name=f"Memory0Worker-Cleanup-{self.worker_id}",
                daemon=True
            )
            self._cleanup_thread.start()

        logger.info(f"Worker {self.worker_id} 启动成功")

    def stop(self, timeout: Optional[float] = None):
        """停止 Worker

        Args:
            timeout: 超时时间（秒），默认使用配置中的 shutdown_timeout
        """
        if not self._running:
            logger.warning(f"Worker {self.worker_id} 未在运行")
            return

        timeout = timeout or self.config.shutdown_timeout
        logger.info(f"停止 Worker {self.worker_id}（超时 {timeout} 秒）")

        self._running = False
        self._shutdown_event.set()

        # 等待线程结束
        threads = [
            self._worker_thread,
            self._heartbeat_thread,
            self._cleanup_thread
        ]
        for thread in threads:
            if thread and thread.is_alive():
                thread.join(timeout=timeout / len(threads))

        logger.info(f"Worker {self.worker_id} 已停止")

    def _worker_loop(self):
        """Worker 主循环"""
        logger.info(f"Worker {self.worker_id} 主循环开始")

        while self._running:
            try:
                # 从队列中取出任务
                task = self.task_queue.dequeue(
                    block=True,
                    timeout=self.config.poll_interval
                )

                if task is None:
                    continue

                logger.info(
                    f"Worker {self.worker_id} 取到任务: {task.task_id}, "
                    f"entry_id={task.entry_id}, attempts={task.attempts}"
                )

                # 处理任务
                self._process_task(task)

            except Exception as e:
                logger.error(
                    f"Worker {self.worker_id} 主循环异常: {e}",
                    exc_info=True
                )
                # 短暂等待后继续
                time.sleep(1.0)

        logger.info(f"Worker {self.worker_id} 主循环结束")

    def _process_task(self, task: Memory0Task):
        """处理单个任务

        Args:
            task: 要处理的任务
        """
        try:
            # 根据任务类型选择处理逻辑
            if task.task_type == TaskType.SECTION_SUMMARIZE.value:
                # 处理 Section 整理任务
                self._process_section_task(task)
            else:
                # 处理 Memory0 任务（默认）
                self._process_memory0_task(task)

            # 更新统计
            self.stats["tasks_processed"] += 1
            self.stats["tasks_succeeded"] += 1

            # 标记任务为完成
            self.task_queue.update_status(
                task_id=task.task_id,
                status=TaskStatus.COMPLETED,
                worker_id=self.worker_id,
                worker_info=self.worker_info
            )

        except Exception as e:
            logger.error(
                f"Worker {self.worker_id} 任务 {task.task_id} 处理失败: {e}",
                exc_info=True
            )

            # 更新统计
            self.stats["tasks_failed"] += 1

            # 判断是否重试
            if task.attempts < self.config.max_retries:
                # 计算重试延迟（指数退避）
                retry_delay = self._calculate_retry_delay(task.attempts)
                self.stats["total_retries"] += 1

                # 重新排队
                self.task_queue.requeue(
                    task_id=task.task_id,
                    delay_seconds=int(retry_delay)
                )

                logger.info(
                    f"Worker {self.worker_id} 任务 {task.task_id} "
                    f"将重试（第 {task.attempts + 1} 次），延迟 {retry_delay} 秒"
                )

            else:
                # 超过最大重试次数，标记为死信
                self.stats["tasks_dead"] += 1
                self.task_queue.mark_as_dead(
                    task_id=task.task_id,
                    error=str(e)
                )

                logger.warning(
                    f"Worker {self.worker_id} 任务 {task.task_id} "
                    f"超过最大重试次数，标记为死信"
                )

    def _process_memory0_task(self, task: Memory0Task):
        """处理 Memory0 任务

        Args:
            task: 要处理的任务
        """
        # 调用 Memory0Service 处理 entry
        result = self.memory0_service.process_entry(task.entry_id)

        logger.info(
            f"Worker {self.worker_id} Memory0 任务 {task.task_id} 处理成功: "
            f"relation={result.relation}"
        )

    def _process_section_task(self, task: Memory0Task):
        """处理 Section 整理任务

        Args:
            task: 要处理的任务
        """
        if not self.section_service:
            raise RuntimeError("SectionService 未配置，无法处理 Section 整理任务")

        # 从 payload 中获取参数
        payload = task.payload or {}
        session_id = payload.get("session_id", task.entry_id)  # 兼容：使用 session_id 或 entry_id
        agent_id = payload.get("agent_id", "default")
        trigger_type = payload.get("trigger_type", "auto")

        # 调用 SectionService 进行整理
        result = self.section_service.summarize_section(
            session_id=session_id,
            agent_id=agent_id,
            trigger_type=trigger_type
        )

        logger.info(
            f"Worker {self.worker_id} Section 任务 {task.task_id} 处理成功: "
            f"section_id={result.section_id}, entry_id={result.entry_id}"
        )

    def _calculate_retry_delay(self, attempt: int) -> float:
        """计算重试延迟（指数退避）

        Args:
            attempt: 当前尝试次数

        Returns:
            float: 延迟时间（秒）
        """
        return self.config.retry_delay_base * (
            self.config.retry_delay_multiplier ** (attempt - 1)
        )

    def _heartbeat_loop(self):
        """心跳循环"""
        logger.info(f"Worker {self.worker_id} 心跳循环开始")

        while self._running:
            try:
                # 更新心跳时间
                self.stats["last_heartbeat"] = datetime.now().isoformat()

                # 更新运行时间
                if self.worker_info.get("started_at"):
                    started = datetime.fromisoformat(self.worker_info["started_at"])
                    self.stats["uptime_seconds"] = (
                        datetime.now() - started
                    ).total_seconds()

                # 记录统计信息
                logger.info(
                    f"Worker {self.worker_id} 心跳: "
                    f"processed={self.stats['tasks_processed']}, "
                    f"succeeded={self.stats['tasks_succeeded']}, "
                    f"failed={self.stats['tasks_failed']}, "
                    f"dead={self.stats['tasks_dead']}, "
                    f"uptime={self.stats['uptime_seconds']:.0f}s"
                )

                # 等待下次心跳
                self._shutdown_event.wait(self.config.heartbeat_interval)

            except Exception as e:
                logger.error(
                    f"Worker {self.worker_id} 心跳循环异常: {e}",
                    exc_info=True
                )

        logger.info(f"Worker {self.worker_id} 心跳循环结束")

    def _cleanup_loop(self):
        """清理循环"""
        logger.info(f"Worker {self.worker_id} 清理循环开始")

        while self._running:
            try:
                # 等待清理间隔
                self._shutdown_event.wait(self.config.cleanup_interval)

                if not self._running:
                    break

                # 执行清理
                deleted_count = self.task_queue.cleanup_old_tasks(
                    days_to_keep=self.config.cleanup_days_to_keep
                )

                if deleted_count > 0:
                    logger.info(
                        f"Worker {self.worker_id} 清理了 {deleted_count} 个旧任务"
                    )

            except Exception as e:
                logger.error(
                    f"Worker {self.worker_id} 清理循环异常: {e}",
                    exc_info=True
                )

        logger.info(f"Worker {self.worker_id} 清理循环结束")

    def get_stats(self) -> Dict[str, Any]:
        """获取 Worker 统计信息

        Returns:
            Dict[str, Any]: 统计信息
        """
        return {
            "worker_id": self.worker_id,
            "running": self._running,
            "stats": self.stats.copy(),
            "config": {
                "poll_interval": self.config.poll_interval,
                "max_retries": self.config.max_retries,
                "retry_delay_base": self.config.retry_delay_base,
                "retry_delay_multiplier": self.config.retry_delay_multiplier,
            }
        }

    def is_running(self) -> bool:
        """检查 Worker 是否在运行

        Returns:
            bool: 是否在运行
        """
        return self._running

    def __enter__(self):
        """上下文管理器入口"""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.stop()


def create_worker(
    entry_service: EntryService,
    task_queue: Optional[TaskQueue] = None,
    config: Optional[WorkerConfig] = None,
    section_service: Optional[SectionService] = None
) -> Memory0Worker:
    """创建 Memory0 Worker 实例

    Args:
        entry_service: EntryService 实例
        task_queue: 任务队列实例（默认使用 get_task_queue()）
        config: Worker 配置（默认使用默认配置）
        section_service: 可选的 SectionService 实例，用于处理 Section 整理任务

    Returns:
        Memory0Worker: Worker 实例
    """
    memory0_service = Memory0Service(entry_service=entry_service)
    return Memory0Worker(
        memory0_service=memory0_service,
        task_queue=task_queue,
        config=config,
        section_service=section_service
    )
