"""AgentInstanceRegistry implementation.

Manages the lifecycle and status of Agent instances in a multi-tenant environment.
Supports 300+ concurrent instances with status machine and TTL-based cleanup.
"""

from __future__ import annotations

import time
import logging
import asyncio
from enum import Enum
from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class AgentInstanceStatus(str, Enum):
    """Agent 实例状态"""
    ACTIVE = "active"    # 活跃中（正在处理请求）
    IDLE = "idle"        # 闲置中（等待请求，可被回收）
    STOPPED = "stopped"  # 已停止（不可用，等待销毁）


@dataclass
class AgentInstanceMetadata:
    """Agent 实例元数据"""
    instance_id: str
    agent_type: str
    user_id: str
    status: AgentInstanceStatus = AgentInstanceStatus.IDLE
    created_at: float = field(default_factory=time.time)
    last_active_at: float = field(default_factory=time.time)
    config: Dict[str, Any] = field(default_factory=dict)
    metrics: Dict[str, Any] = field(default_factory=dict)


class AgentInstanceRegistry:
    """Agent 实例注册表。

    负责管理大规模 Agent 实例的生命周期、状态切换和自动回收。
    """

    def __init__(
        self,
        idle_ttl: int = 3600,      # 闲置超时回收时间（秒，默认1小时）
        cleanup_interval: int = 300 # 清理任务间隔（秒，默认5分钟）
    ):
        """初始化注册表。

        Args:
            idle_ttl: 闲置超时时间
            cleanup_interval: 清理间隔
        """
        self._instances: Dict[str, AgentInstanceMetadata] = {}
        self._idle_ttl = idle_ttl
        self._cleanup_interval = cleanup_interval
        # 读多写少场景：读操作无锁，写操作用细粒度锁
        self._lock = asyncio.Lock()
        self._cleanup_task: Optional[asyncio.Task] = None

    async def start(self):
        """启动注册表清理任务。"""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            logger.info("AgentInstanceRegistry cleanup task started")

    async def stop(self):
        """停止注册表。"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
            logger.info("AgentInstanceRegistry cleanup task stopped")

    async def register(
        self,
        instance_id: str,
        agent_type: str,
        user_id: str,
        config: Optional[Dict[str, Any]] = None
    ) -> AgentInstanceMetadata:
        """注册一个新实例。"""
        async with self._lock:
            meta = AgentInstanceMetadata(
                instance_id=instance_id,
                agent_type=agent_type,
                user_id=user_id,
                status=AgentInstanceStatus.ACTIVE,
                config=config or {}
            )
            self._instances[instance_id] = meta
            logger.info(f"Registered Agent instance: {instance_id} (type={agent_type}, user={user_id})")
            return meta

    async def get_instance(self, instance_id: str) -> Optional[AgentInstanceMetadata]:
        """获取实例元数据并更新活跃时间。

        读路径无锁，只有在状态更新时才获取锁，避免高频读的串行化。
        """
        meta = self._instances.get(instance_id)
        if meta and meta.status != AgentInstanceStatus.STOPPED:
            async with self._lock:
                # 双检，防止并发删除
                meta = self._instances.get(instance_id)
                if meta and meta.status != AgentInstanceStatus.STOPPED:
                    meta.last_active_at = time.time()
                    meta.status = AgentInstanceStatus.ACTIVE
                    return meta
        return None

    async def set_status(self, instance_id: str, status: AgentInstanceStatus):
        """显式设置实例状态。"""
        async with self._lock:
            meta = self._instances.get(instance_id)
            if meta:
                meta.status = status
                meta.last_active_at = time.time()
                logger.debug(f"Instance {instance_id} status changed to {status}")

    async def remove_instance(self, instance_id: str):
        """移除并销毁实例。"""
        async with self._lock:
            if instance_id in self._instances:
                self._instances[instance_id].status = AgentInstanceStatus.STOPPED
                del self._instances[instance_id]
                logger.info(f"Removed Agent instance: {instance_id}")

    async def list_instances(
        self,
        user_id: Optional[str] = None,
        agent_type: Optional[str] = None
    ) -> List[AgentInstanceMetadata]:
        """列表查询实例（读路径无锁，复制后过滤）。"""
        instances_snapshot = list(self._instances.values())
        if user_id:
            instances_snapshot = [m for m in instances_snapshot if m.user_id == user_id]
        if agent_type:
            instances_snapshot = [m for m in instances_snapshot if m.agent_type == agent_type]
        return instances_snapshot

    async def get_stats(self) -> Dict[str, Any]:
        """获取注册表统计信息（读路径无锁，快照统计）。"""
        instances_snapshot = list(self._instances.values())
        counts = {
            AgentInstanceStatus.ACTIVE: 0,
            AgentInstanceStatus.IDLE: 0,
            AgentInstanceStatus.STOPPED: 0,
        }
        for meta in instances_snapshot:
            counts[meta.status] += 1

        return {
            "total_instances": len(instances_snapshot),
            "status_counts": counts,
            "idle_ttl": self._idle_ttl,
        }

    async def _cleanup_loop(self):
        """定期清理超时闲置实例。"""
        while True:
            try:
                await asyncio.sleep(self._cleanup_interval)
                await self._cleanup_expired()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in AgentInstanceRegistry cleanup loop: {e}")

    async def _cleanup_expired(self):
        """执行过期清理逻辑。写路径上锁，读阶段无锁快照。"""
        now = time.time()
        # 快照读取，避免长时间持锁
        instances_snapshot = list(self._instances.items())
        to_remove: List[str] = []

        for instance_id, meta in instances_snapshot:
            if meta.status == AgentInstanceStatus.IDLE and now - meta.last_active_at > self._idle_ttl:
                to_remove.append(instance_id)
            elif meta.status == AgentInstanceStatus.ACTIVE and now - meta.last_active_at > self._idle_ttl / 2:
                # 延迟状态变更到锁内
                to_remove.append((instance_id, "to_idle"))

        async with self._lock:
            # 再次检查，防止并发删除
            for item in to_remove:
                if isinstance(item, tuple):
                    instance_id, action = item
                    meta = self._instances.get(instance_id)
                    if meta and meta.status == AgentInstanceStatus.ACTIVE and now - meta.last_active_at > self._idle_ttl / 2:
                        meta.status = AgentInstanceStatus.IDLE
                        logger.debug(f"Instance {instance_id} auto-switched to IDLE due to inactivity")
                else:
                    instance_id = item
                    meta = self._instances.get(instance_id)
                    if meta and meta.status == AgentInstanceStatus.IDLE and now - meta.last_active_at > self._idle_ttl:
                        del self._instances[instance_id]
                        logger.info(f"Auto-removed expired Agent instance: {instance_id}")
