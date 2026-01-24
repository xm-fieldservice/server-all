import asyncio
import logging
import random
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ai_factory.agents.memory.api.client import MemoryClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


@dataclass
class CallRecord:
    user_id: str
    agent_type: Optional[str]
    agent_instance_id: Optional[str]
    content: str


class FakeMemoryService:
    """轻量级假实现，用于验证 MemoryClient 的 ContextVar 隔离。

    这里不访问数据库，只记录调用中传入的上下文参数，确保并发场景下不会串号。
    """

    def __init__(self) -> None:
        self.calls: List[CallRecord] = []

    # 签名与 MemoryService.remember_explicitly 保持一致，便于替换
    def remember_explicitly(
        self,
        agent_id: str,
        user_id: str,
        content: str,
        agent_type: Optional[str] = None,
        agent_instance_id: Optional[str] = None,
        extra_meta: Optional[Dict[str, Any]] = None,
    ) -> str:
        self.calls.append(
            CallRecord(
                user_id=user_id,
                agent_type=agent_type,
                agent_instance_id=agent_instance_id,
                content=content,
            )
        )
        return f"ent_{user_id}_{len(self.calls)}"


async def run_user(client: MemoryClient, user_id: str, agent_type: str, agent_instance_id: str, iterations: int = 50):
    async with client.async_context(user_id=user_id, agent_type=agent_type, agent_instance_id=agent_instance_id):
        for i in range(iterations):
            # 随机 sleep 模拟异步调度，放大串号风险
            await asyncio.sleep(random.uniform(0.0, 0.01))
            content = f"content_{user_id}_{i}"
            # MemoryClient 是同步方法，这里用 to_thread 避免阻塞事件循环
            await asyncio.to_thread(
                client.remember_explicitly,
                "agent_default",
                content,
                {"iteration": i},
            )


def verify_calls(fake_service: FakeMemoryService, users: List[Dict[str, str]], iterations: int):
    expected_total = len(users) * iterations
    assert len(fake_service.calls) == expected_total, f"expected {expected_total} calls, got {len(fake_service.calls)}"

    # 检查每个用户的记录是否只包含自身上下文
    for user in users:
        uid = user["user_id"]
        atype = user["agent_type"]
        ainst = user["agent_instance_id"]
        user_calls = [c for c in fake_service.calls if c.user_id == uid]
        assert len(user_calls) == iterations, f"user {uid} call count mismatch: {len(user_calls)}"
        for c in user_calls:
            assert c.agent_type == atype, f"agent_type mismatch for {uid}: {c.agent_type} != {atype}"
            assert c.agent_instance_id == ainst, f"agent_instance_id mismatch for {uid}: {c.agent_instance_id} != {ainst}"

    logger.info("Async ContextVar isolation test PASSED: no cross-contamination detected.")


async def main():
    users = [
        {"user_id": f"user_{i}", "agent_type": f"type_{i%3}", "agent_instance_id": f"inst_{i}"}
        for i in range(8)
    ]
    iterations = 40

    fake_service = FakeMemoryService()
    client = MemoryClient(fake_service)

    tasks = [
        asyncio.create_task(
            run_user(
                client,
                user["user_id"],
                user["agent_type"],
                user["agent_instance_id"],
                iterations=iterations,
            )
        )
        for user in users
    ]

    await asyncio.gather(*tasks)
    verify_calls(fake_service, users, iterations)


if __name__ == "__main__":
    asyncio.run(main())
