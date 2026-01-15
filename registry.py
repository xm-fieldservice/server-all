"""
企业微信应用处理器注册表。

提供简单的 `AgentID → Handler` 映射，支持动态注册与自动发现。

使用示例：

    from wecom_gateway.registry import register_handler, get_handler

    @register_handler(agent_id="1000023")
    async def handle_note(userid: str, content: str, msg_type: str, **kwargs):
        # 业务逻辑
        pass

或在模块初始化时显式注册：

    register_handler(agent_id="1000025", handler=handle_qa)
"""
import inspect
import logging
from typing import Any, Awaitable, Callable, Dict, Optional

logger = logging.getLogger(__name__)

# 全局注册表：agent_id -> handler
_HANDLERS: Dict[str, Callable[..., Awaitable[Optional[dict]]]] = {}

# 可选：存储 agent 的元数据（如名称、描述）
_AGENT_META: Dict[str, Dict[str, Any]] = {}


def register_handler(
    agent_id: str,
    handler: Optional[Callable[..., Awaitable[Optional[dict]]]] = None,
    *,
    name: str = "",
    description: str = "",
    **meta,
) -> Callable:
    """注册一个企业微信应用处理器。

    可作为装饰器使用：

        @register_handler(agent_id="1000023", name="笔记助手", description="工作笔记收集器")
        async def handle_note(...):
            ...

    或直接注册函数：

        register_handler(agent_id="1000023", handler=handle_note)

    Args:
        agent_id: 企业微信应用的 AgentID（字符串）
        handler: 处理器函数，接收 (userid, content, msg_type, **kwargs) 并返回可选的 dict
        name: 应用名称（便于监控与日志）
        description: 应用描述
        **meta: 额外的元数据

    Returns:
        装饰器函数或原函数（当作为装饰器时）
    """
    if handler is None:
        # 作为装饰器使用
        def decorator(func: Callable[..., Awaitable[Optional[dict]]]) -> Callable:
            register_handler(agent_id, func, name=name, description=description, **meta)
            return func
        return decorator

    if not inspect.iscoroutinefunction(handler):
        logger.warning(f"Handler for agent {agent_id} is not async, may cause blocking.")

    if agent_id in _HANDLERS:
        logger.warning(f"Agent {agent_id} already registered, overwriting.")

    _HANDLERS[agent_id] = handler
    _AGENT_META[agent_id] = {
        "name": name or handler.__name__,
        "description": description,
        "module": handler.__module__,
        **meta,
    }
    logger.info(f"Registered handler for agent {agent_id} ({name})")
    return handler


def get_handler(agent_id: str) -> Optional[Callable[..., Awaitable[Optional[dict]]]]:
    """根据 AgentID 获取处理器。"""
    return _HANDLERS.get(agent_id)


def list_agents() -> Dict[str, Dict[str, Any]]:
    """返回所有已注册应用的元数据。"""
    return _AGENT_META.copy()


def clear_registry():
    """清空注册表（主要用于测试）。"""
    global _HANDLERS, _AGENT_META
    _HANDLERS.clear()
    _AGENT_META.clear()
    logger.info("Registry cleared.")