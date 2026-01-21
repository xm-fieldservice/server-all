"""测试批量操作接口。

测试 EntryService、VectorClient、SessionService 的批量操作功能。
"""

import sys
import os
import time

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../..')))

from ai_factory.agents.memory.entry_service import EntryService
from ai_factory.agents.memory.vector_client import VectorClient
from ai_factory.agents.memory.session_service import SessionService
from ai_factory.agents.memory.llm_client import get_llm_client


def test_entry_service_batch_operations():
    """测试 EntryService 批量操作"""
    print("\n" + "=" * 60)
    print("测试 EntryService 批量操作")
    print("=" * 60)

    entry_service = EntryService()

    # 1. 批量创建条目
    print("\n[1] 批量创建条目...")
    batch_entries = [
        {
            "title": "批量测试 1",
            "content": "这是第一个批量创建的条目。",
            "agent_id": "test_agent_batch",
            "space_type": "test"
        },
        {
            "title": "批量测试 2",
            "content": "这是第二个批量创建的条目。",
            "agent_id": "test_agent_batch",
            "space_type": "test"
        },
        {
            "title": "批量测试 3",
            "content": "这是第三个批量创建的条目。",
            "agent_id": "test_agent_batch",
            "space_type": "test"
        }
    ]

    entry_ids = entry_service.batch_create_entries(batch_entries)
    print(f"✅ 批量创建成功: {len(entry_ids)} 个条目")
    print(f"   Entry IDs: {entry_ids}")

    # 2. 批量获取条目
    print("\n[2] 批量获取条目...")
    entries = entry_service.batch_get_entries(entry_ids)
    print(f"✅ 批量获取成功: {len(entries)} 个条目")
    for entry_id, entry_data in entries.items():
        print(f"   - {entry_id}: {entry_data.get('title')}")

    # 3. 批量更新条目
    print("\n[3] 批量更新条目...")
    updates = [
        {
            "entry_id": entry_ids[0],
            "title": "批量测试 1 (已更新)",
            "importance": 8
        },
        {
            "entry_id": entry_ids[1],
            "title": "批量测试 2 (已更新)",
            "importance": 9
        }
    ]

    update_results = entry_service.batch_update_entries(updates)
    print(f"✅ 批量更新成功: {sum(1 for v in update_results.values() if v)} / {len(update_results)}")

    # 验证更新
    updated_entries = entry_service.batch_get_entries([entry_ids[0], entry_ids[1]])
    for entry_id, entry_data in updated_entries.items():
        print(f"   - {entry_id}: {entry_data.get('title')}, importance={entry_data.get('importance')}")

    # 4. 清理
    print("\n[4] 清理测试数据...")
    for entry_id in entry_ids:
        entry_service.delete_entry(entry_id)
    print(f"✅ 清理完成")

    return True


def test_vector_client_batch_operations():
    """测试 VectorClient 批量操作"""
    print("\n" + "=" * 60)
    print("测试 VectorClient 批量操作")
    print("=" * 60)

    vector_client = VectorClient()
    llm_client = get_llm_client()

    # 1. 准备测试向量
    print("\n[1] 准备测试向量...")
    texts = [
        "人工智能技术正在快速发展",
        "机器学习是人工智能的重要分支",
        "深度学习基于神经网络",
        "自然语言处理应用广泛",
        "计算机视觉识别图像"
    ]

    print("生成 embeddings...")
    embeddings = []
    for text in texts:
        embedding = llm_client.generate_embedding_sync(text)
        embeddings.append(embedding)

    print(f"✅ 生成 {len(embeddings)} 个向量，维度: {len(embeddings[0])}")

    # 2. 批量创建条目并添加向量
    print("\n[2] 批量创建条目并添加向量...")
    entry_service = EntryService()

    entries = []
    entry_ids = []

    for i, (text, embedding) in enumerate(zip(texts, embeddings)):
        entry = {
            "entry_id": f"batch_vec_test_{i}_{int(time.time())}",
            "title": f"向量测试 {i}",
            "content": text,
            "agent_id": "test_vector_batch",
            "space_type": "test"
        }
        entry_service.create_entry(entry)
        entry_ids.append(entry["entry_id"])

        entries.append({
            "entry_id": entry["entry_id"],
            "embedding": embedding,
            "project_code": "test_project"
        })

    # 批量 upsert 向量
    upsert_results = vector_client.batch_upsert_embeddings(entries)
    print(f"✅ 批量 upsert 成功: {sum(1 for v in upsert_results.values() if v)} / {len(upsert_results)}")

    # 3. 批量获取向量
    print("\n[3] 批量获取向量...")
    fetched_embeddings = vector_client.batch_get_embeddings(entry_ids)
    print(f"✅ 批量获取成功: {len(fetched_embeddings)} 个向量")
    for entry_id, embedding in fetched_embeddings.items():
        if embedding:
            print(f"   - {entry_id}: 维度={len(embedding)}")

    # 4. 批量检索
    print("\n[4] 批量检索...")
    query_texts = ["AI 技术发展", "神经网络应用"]
    query_embeddings = [llm_client.generate_embedding_sync(text) for text in query_texts]

    search_results = vector_client.batch_search_entries(
        query_embeddings=query_embeddings,
        filters={"agent_id": "test_vector_batch"},
        top_k=3
    )

    for idx, (query_text, results) in enumerate(zip(query_texts, search_results.values())):
        print(f"\n查询 '{query_text}' 的结果:")
        for result in results[:3]:
            print(f"   - {result['title']}: 相似度={result['similarity']:.3f}")

    # 5. 清理
    print("\n[5] 清理测试数据...")
    for entry_id in entry_ids:
        entry_service.delete_entry(entry_id)
    print(f"✅ 清理完成")

    return True


def test_session_service_batch_operations():
    """测试 SessionService 批量操作"""
    print("\n" + "=" * 60)
    print("测试 SessionService 批量操作")
    print("=" * 60)

    session_service = SessionService()

    # 1. 创建测试会话
    print("\n[1] 创建测试会话...")
    session_id = session_service.create_session(
        user_id="test_user_batch",
        assistant_id="test_assistant_batch",
        title="批量测试会话"
    )
    print(f"✅ 创建会话成功: {session_id}")

    # 2. 批量添加消息
    print("\n[2] 批量添加消息...")
    messages = [
        {
            "session_id": session_id,
            "role": "user",
            "content": "你好，这是第一条消息"
        },
        {
            "session_id": session_id,
            "role": "assistant",
            "content": "你好！这是第一条回复"
        },
        {
            "session_id": session_id,
            "role": "user",
            "content": "这是第二条消息"
        },
        {
            "session_id": session_id,
            "role": "assistant",
            "content": "这是第二条回复"
        },
        {
            "session_id": session_id,
            "role": "user",
            "content": "这是第三条消息"
        }
    ]

    message_ids = session_service.batch_append_messages(messages)
    print(f"✅ 批量添加成功: {len(message_ids)} 条消息")

    # 3. 验证消息
    print("\n[3] 验证消息...")
    recent_messages = session_service.get_recent_messages(session_id, limit=10)
    print(f"✅ 获取到 {len(recent_messages)} 条消息:")
    for msg in recent_messages:
        print(f"   - {msg.role}: {msg.content[:30]}...")

    # 4. 批量获取多个会话的消息
    print("\n[4] 创建多个会话并批量获取消息...")
    session_ids = [session_id]

    for i in range(2):
        sid = session_service.create_session(
            user_id="test_user_batch",
            assistant_id="test_assistant_batch",
            title=f"批量测试会话 {i+2}"
        )
        session_ids.append(sid)

        # 添加一些消息
        msgs = [
            {
                "session_id": sid,
                "role": "user",
                "content": f"会话 {i+2} 的消息"
            },
            {
                "session_id": sid,
                "role": "assistant",
                "content": f"会话 {i+2} 的回复"
            }
        ]
        session_service.batch_append_messages(msgs)

    # 批量获取消息
    batch_messages = session_service.batch_get_recent_messages(session_ids, limit=5)
    print(f"✅ 批量获取成功: {len(batch_messages)} 个会话")
    for sid, msgs in batch_messages.items():
        print(f"   - 会话 {sid[-8:]}: {len(msgs)} 条消息")

    # 5. 清理
    print("\n[5] 清理测试数据...")
    for sid in session_ids:
        session_service.delete_session(sid)
    print(f"✅ 清理完成")

    return True


def main():
    """主测试函数"""
    print("\n" + "=" * 60)
    print("开始批量操作测试")
    print("=" * 60)

    try:
        # 测试 EntryService
        test_entry_service_batch_operations()

        # 测试 VectorClient
        test_vector_client_batch_operations()

        # 测试 SessionService
        test_session_service_batch_operations()

        print("\n" + "=" * 60)
        print("✅ 所有批量操作测试通过！")
        print("=" * 60)

        return 0

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
