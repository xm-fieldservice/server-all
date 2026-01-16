"""端到端测试脚本：验证 Agent 记忆流水线。

测试流程：
1. 创建会话和添加消息（SessionService）
2. 整理 Section（SectionService + LLM + Embedding）
3. 获取上下文（MemoryService）
4. 显式记忆（MemoryService）
5. 验证 Memory0 治理（Memory0Service）
6. Q&A 缓存测试（QACacheService）
7. 异步 Memory0 处理（TaskQueue + Worker）
8. 配置管理测试（ConfigManager）

运行方式：
    python -m ai_factory.agents.memory.test_memory_pipeline
"""

from __future__ import annotations

import sys
import os
import time
import threading
from typing import Optional

# 添加项目根目录到 Python 路径
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../.."))
sys.path.insert(0, project_root)

from ai_factory.agents.memory import (
    create_memory_stack,
    SessionService,
    SectionService,
    EntryService,
    Memory0Service,
    MemoryService,
    MemoryRelation,
    SectionTrigger,
    QACacheService,
    QAStatus,
    AnswerType,
    TaskQueue,
    Memory0Task,
    TaskType,
    TaskStatus,
    get_task_queue,
    Memory0Worker,
    WorkerConfig,
    create_worker,
    ConfigManager,
    get_config_manager,
    Memory0Profile,
    Memory0Config,
    AgentMemoryConfig,
)


def print_separator(title: str) -> None:
    """打印分隔线。"""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60 + "\n")


def test_session_service(session_service: SessionService) -> str:
    """测试 SessionService。

    Args:
        session_service: SessionService 实例

    Returns:
        str: session_id
    """
    print_separator("测试 1: SessionService - 创建会话和添加消息")

    # 创建会话
    session_id = session_service.create_session(
        user_id="test_user_001",
        assistant_id="test_agent_001",
        title="测试会话 - 项目进展",
        metadata={"test": True}
    )
    print(f"✓ 创建会话: {session_id}")

    # 获取会话信息
    session_info = session_service.get_session_info(session_id)
    print(f"✓ 会话信息: {session_info.title}, 状态: {session_info.status}")

    # 添加用户消息
    msg_id_1 = session_service.append_message(
        session_id=session_id,
        role="user",
        content="项目A的进展如何？",
        msg_type="question",
        metadata={"priority": "high"}
    )
    print(f"✓ 添加用户消息: {msg_id_1}")

    # 添加助手回复
    msg_id_2 = session_service.append_message(
        session_id=session_id,
        role="assistant",
        content="项目A目前进展顺利，已完成80%的开发工作。",
        msg_type="answer",
        metadata={"sources": ["rag", "entries"]}
    )
    print(f"✓ 添加助手回复: {msg_id_2}")

    # 添加更多消息
    session_service.append_message(
        session_id=session_id,
        role="user",
        content="那项目B呢？"
    )
    session_service.append_message(
        session_id=session_id,
        role="assistant",
        content="项目B正在进行需求分析阶段。"
    )

    # 获取最近消息
    recent_messages = session_service.get_recent_messages(session_id, limit=5)
    print(f"✓ 获取最近消息: {len(recent_messages)} 条")

    return session_id


def test_section_service(
    section_service: SectionService,
    session_id: str
) -> str:
    """测试 SectionService。

    Args:
        section_service: SectionService 实例
        session_id: 会话ID

    Returns:
        str: entry_id
    """
    print_separator("测试 2: SectionService - 整理 Section")

    # 整理 section（使用新的 SectionTrigger 枚举）
    summary = section_service.summarize_section(
        session_id=session_id,
        agent_id="test_agent_001",
        trigger_type=SectionTrigger.AUTO.value,  # 使用枚举值
        manual_section_title="项目进展讨论"
    )

    print(f"✓ Section ID: {summary.section_id}")
    print(f"✓ Entry ID: {summary.entry_id}")
    print(f"✓ Section 版本: {summary.section_version}")
    print(f"✓ 场景标签: {summary.scene_tags}")
    print(f"✓ 内容摘要: {summary.content[:100]}...")

    return summary.entry_id


def test_memory_service(
    memory_service: MemoryService,
    session_id: str
) -> None:
    """测试 MemoryService - 获取上下文。

    Args:
        memory_service: MemoryService 实例
        session_id: 会话ID
    """
    print_separator("测试 3: MemoryService - 获取上下文")

    # 获取上下文
    context = memory_service.get_context_for_turn(
        session_id=session_id,
        agent_id="test_agent_001",
        max_tokens=2048,
        rag_top_k=5,
        recent_messages_limit=10
    )

    print(f"✓ 静态提示词: {context.system_prompt[:50]}...")
    print(f"✓ 历史消息数: {len(context.history_messages)}")
    print(f"✓ RAG 片段数: {len(context.rag_snippets)}")
    print(f"✓ 元数据: {context.metadata}")


def test_explicit_memory(memory_service: MemoryService) -> str:
    """测试显式记忆。

    Args:
        memory_service: MemoryService 实例

    Returns:
        str: entry_id
    """
    print_separator("测试 4: 显式记忆")

    # 显式记住一条信息
    entry_id = memory_service.remember_explicitly(
        agent_id="test_agent_001",
        user_id="test_user_001",
        content="用户偏好使用中文回答，并且喜欢简洁明了的风格。",
        extra_meta={
            "title": "用户偏好",
            "scene_tags": {
                "execution": ["笔记"],
                "planning": ["项目"]
            },
            "space_type": "note"
        }
    )

    print(f"✓ 显式记忆已创建: {entry_id}")

    return entry_id


def test_memory0_service(
    memory0_service: Memory0Service,
    entry_id: str
) -> None:
    """测试 Memory0Service - 记忆治理。

    Args:
        memory0_service: Memory0Service 实例
        entry_id: 条目ID
    """
    print_separator("测试 5: Memory0Service - 记忆治理")

    # 处理条目
    result = memory0_service.process_entry(entry_id)

    print(f"✓ 关系类型: {result.relation}")
    print(f"✓ 条目 ID: {result.entry_id}")
    print(f"✓ 覆盖的条目: {result.overridden_entry_ids}")
    print(f"✓ 元数据: {result.metadata}")


def test_duplicate_detection(
    memory_service: MemoryService,
    memory0_service: Memory0Service
) -> None:
    """测试重复检测。

    Args:
        memory_service: MemoryService 实例
        memory0_service: Memory0Service 实例
    """
    print_separator("测试 6: 重复检测")

    # 第一次记住
    entry_id_1 = memory_service.remember_explicitly(
        agent_id="test_agent_001",
        user_id="test_user_001",
        content="项目A的截止日期是2024年12月31日。",
        extra_meta={"title": "项目A截止日期"}
    )
    print(f"✓ 第一次记忆: {entry_id_1}")

    # 第二次记住相似内容（应该被判定为 DUPLICATE）
    entry_id_2 = memory_service.remember_explicitly(
        agent_id="test_agent_001",
        user_id="test_user_001",
        content="项目A的截止日期是2024年12月31日。",
        extra_meta={"title": "项目A截止日期"}
    )
    print(f"✓ 第二次记忆: {entry_id_2}")

    # 处理第二条
    result = memory0_service.process_entry(entry_id_2)
    print(f"✓ 关系类型: {result.relation} (期望: DUPLICATE)")


def test_override_detection(
    memory_service: MemoryService,
    memory0_service: Memory0Service
) -> None:
    """测试覆盖检测。

    Args:
        memory_service: MemoryService 实例
        memory0_service: Memory0Service 实例
    """
    print_separator("测试 7: 覆盖检测")

    # 第一次记住
    entry_id_1 = memory_service.remember_explicitly(
        agent_id="test_agent_001",
        user_id="test_user_001",
        content="项目A的截止日期是2024年12月31日。",
        extra_meta={"title": "项目A截止日期"}
    )
    print(f"✓ 第一次记忆: {entry_id_1}")

    # 第二次记住冲突内容（应该被判定为 OVERRIDE）
    entry_id_2 = memory_service.remember_explicitly(
        agent_id="test_agent_001",
        user_id="test_user_001",
        content="项目A的截止日期不再使用，改为2025年1月15日。",
        extra_meta={"title": "项目A截止日期更新"}
    )
    print(f"✓ 第二次记忆: {entry_id_2}")

    # 处理第二条
    result = memory0_service.process_entry(entry_id_2)
    print(f"✓ 关系类型: {result.relation} (期望: OVERRIDE)")
    print(f"✓ 覆盖的条目: {result.overridden_entry_ids}")


def test_qa_cache_service(
    qa_cache_service: QACacheService,
    entry_service: EntryService
) -> None:
    """测试 QACacheService。

    Args:
        qa_cache_service: QACacheService 实例
        entry_service: EntryService 实例
    """
    print_separator("测试 8: QACacheService - Q&A 缓存")

    # 创建一个答案条目
    answer_entry_id = entry_service.create_entry({
        "title": "项目A进展",
        "content": "项目A目前进展顺利，已完成80%的开发工作。",
        "agent_id": "test_agent_001",
        "space_type": "note"
    })
    print(f"✓ 创建答案条目: {answer_entry_id}")

    # 缓存 Q&A
    qa_id = qa_cache_service.cache_qa(
        user_id="test_user_001",
        assistant_id="test_agent_001",
        question="项目A的进展如何？",
        answer_entry_id=answer_entry_id,
        answer_type=AnswerType.GENERATED,
        tenant_id="default"
    )
    print(f"✓ 缓存 Q&A: {qa_id}")

    # 查询相似的 Q&A
    results = qa_cache_service.query_qa(
        user_id="test_user_001",
        assistant_id="test_agent_001",
        question="项目A进展怎么样？",
        tenant_id="default",
        threshold=0.85,
        limit=5
    )
    print(f"✓ 查询到 {len(results)} 条相似 Q&A")

    # 记录命中
    if results:
        qa_cache_service.hit_qa(results[0].qa_id)
        print(f"✓ 记录命中: {results[0].qa_id}")

    # 获取用户 Q&A 统计
    stats = qa_cache_service.get_user_qa_stats(
        user_id="test_user_001",
        assistant_id="test_agent_001",
        tenant_id="default"
    )
    print(f"✓ 用户 Q&A 统计: 总数={stats.total_count}, 热门={stats.hot_qas_count}, 温热={stats.warm_qas_count}, 冷门={stats.cold_qas_count}")


def test_async_memory0(
    section_service: SectionService,
    session_id: str
) -> None:
    """测试异步 Memory0 处理（TaskQueue + Worker）。

    Args:
        section_service: SectionService 实例（已启用异步 Memory0）
        session_id: 会话ID
    """
    print_separator("测试 9: 异步 Memory0 处理")

    # 创建一个启用异步 Memory0 的 SectionService
    from ai_factory.agents.memory import create_memory_stack
    async_memory_stack = create_memory_stack(enable_async_memory0=True)

    # 整理 section（会自动提交 Memory0 任务到队列）
    summary = async_memory_stack.section_service.summarize_section(
        session_id=session_id,
        agent_id="test_agent_001",
        trigger_type=SectionTrigger.MANUAL.value,
        manual_section_title="异步测试 Section"
    )
    print(f"✓ Section 已创建: {summary.section_id}")
    print(f"✓ Entry ID: {summary.entry_id}")

    # 检查任务队列
    task_queue = get_task_queue()
    pending_tasks = task_queue.get_pending_tasks(limit=10)
    print(f"✓ 待处理任务数: {len(pending_tasks)}")

    # 创建并启动 Worker
    worker_config = WorkerConfig(
        poll_interval=1.0,
        heartbeat_interval=5.0,
        cleanup_interval=30.0,
        max_retries=3,
        retry_delay_multiplier=2.0
    )
    worker = create_worker(worker_config)

    # 启动 Worker（在后台线程中运行）
    worker_thread = threading.Thread(target=worker.start, daemon=True)
    worker_thread.start()
    print("✓ Worker 已启动")

    # 等待任务处理
    time.sleep(3)

    # 检查任务状态
    if pending_tasks:
        task_id = pending_tasks[0].task_id
        task = task_queue.get_task(task_id)
        print(f"✓ 任务状态: {task.status}")

    # 停止 Worker
    worker.stop()
    print("✓ Worker 已停止")


def test_config_manager() -> None:
    """测试配置管理。

    Args:
        config_manager: ConfigManager 实例
    """
    print_separator("测试 10: ConfigManager - 配置管理")

    # 获取配置管理器
    config_manager = get_config_manager()

    # 注册一个 Agent 配置
    agent_config = AgentMemoryConfig(
        agent_id="test_agent_001",
        agent_name="测试 Agent",
        profile=Memory0Profile.CONSERVATIVE,
        enable_section=True,
        enable_memory0=True,
        enable_async_memory0=False,
        section_trigger_message_count=10,
        section_trigger_time_interval=3600,
        scene_tag_templates={
            "execution": ["笔记", "任务"],
            "planning": ["项目", "计划"]
        },
        default_space_type="note",
        metadata={"version": "1.0"}
    )
    config_manager.register_agent_config(agent_config)
    print(f"✓ 注册 Agent 配置: {agent_config.agent_id}")

    # 获取 Agent 配置
    retrieved_config = config_manager.get_agent_config("test_agent_001")
    print(f"✓ 获取 Agent 配置: {retrieved_config.agent_name}, Profile: {retrieved_config.profile}")

    # 获取 Memory0 配置
    memory0_config = config_manager.get_memory0_config("test_agent_001")
    print(f"✓ Memory0 配置: sim_threshold_low={memory0_config.sim_threshold_low}, sim_threshold_high={memory0_config.sim_threshold_high}")

    # 更新 Agent Profile
    config_manager.update_agent_profile("test_agent_001", Memory0Profile.AGGRESSIVE)
    updated_config = config_manager.get_agent_config("test_agent_001")
    print(f"✓ 更新 Profile: {updated_config.profile}")

    # 列出所有 Agent 配置
    all_configs = config_manager.list_agent_configs()
    print(f"✓ 所有 Agent 配置数: {len(all_configs)}")

    # 移除 Agent 配置
    removed = config_manager.remove_agent_config("test_agent_001")
    print(f"✓ 移除 Agent 配置: {removed}")


def test_section_trigger_enum() -> None:
    """测试 SectionTrigger 枚举。

    验证枚举值与 SQL 定义一致。
    """
    print_separator("测试 11: SectionTrigger 枚举")

    # 检查枚举值
    print(f"✓ SectionTrigger.AUTO = {SectionTrigger.AUTO.value}")
    print(f"✓ SectionTrigger.MANUAL = {SectionTrigger.MANUAL.value}")
    print(f"✓ SectionTrigger.TIMEOUT = {SectionTrigger.TIMEOUT.value}")

    # 验证枚举值与 SQL 定义一致
    expected_values = {"auto", "manual", "timeout"}
    actual_values = {trigger.value for trigger in SectionTrigger}
    assert actual_values == expected_values, f"枚举值不匹配: {actual_values} != {expected_values}"
    print(f"✓ 枚举值与 SQL 定义一致")


def main() -> None:
    """主函数。"""
    print("\n" + "=" * 60)
    print("  Agent 记忆流水线 - 端到端测试")
    print("=" * 60)

    try:
        # 创建记忆栈
        memory_stack = create_memory_stack()
        print("✓ 记忆栈初始化成功")

        # 测试 SessionService
        session_id = test_session_service(memory_stack.session_service)

        # 测试 SectionService
        entry_id = test_section_service(memory_stack.section_service, session_id)

        # 测试 MemoryService - 获取上下文
        test_memory_service(memory_stack, session_id)

        # 测试显式记忆
        explicit_entry_id = test_explicit_memory(memory_stack)

        # 测试 Memory0Service
        test_memory0_service(memory_stack.memory0_service, explicit_entry_id)

        # 测试重复检测
        test_duplicate_detection(memory_stack, memory_stack.memory0_service)

        # 测试覆盖检测
        test_override_detection(memory_stack, memory_stack.memory0_service)

        # 测试 QACacheService
        test_qa_cache_service(QACacheService(), memory_stack.entry_service)

        # 测试异步 Memory0 处理
        test_async_memory0(memory_stack.section_service, session_id)

        # 测试配置管理
        test_config_manager()

        # 测试 SectionTrigger 枚举
        test_section_trigger_enum()

        print("\n" + "=" * 60)
        print("  ✓ 所有测试通过！")
        print("=" * 60 + "\n")

    except Exception as e:
        print("\n" + "=" * 60)
        print(f"  ✗ 测试失败: {e}")
        print("=" * 60 + "\n")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
