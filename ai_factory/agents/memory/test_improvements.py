#!/usr/bin/env python3
"""
测试脚本：验证 MemoryService 和 LLMClient 的改进

测试内容：
1. TokenCalculator - token 计算精度
2. QueryExtractor - 智能查询提取
3. MemoryService - 上下文组装和 token 截断
4. LLMClient - 重试机制和缓存
"""

import sys
import os
import asyncio

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from ai_factory.agents.memory.memory_service import TokenCalculator, QueryExtractor
from ai_factory.agents.memory.llm_client import LLMClient, RequestCache


def test_token_calculator():
    """测试 TokenCalculator"""
    print("\n" + "="*60)
    print("测试 1: TokenCalculator")
    print("="*60)

    # 初始化 TokenCalculator
    token_calc = TokenCalculator(model="gpt-3.5-turbo")

    # 测试文本
    test_texts = [
        "Hello, world!",
        "你好，世界！",
        "这是一个测试文本，用于验证 token 计算器的准确性。",
        "This is a test text to verify the accuracy of the token calculator.",
    ]

    for text in test_texts:
        tokens = token_calc.count_tokens(text)
        print(f"文本: {text}")
        print(f"Token 数: {tokens}")
        print(f"字符数: {len(text)}")
        print(f"Token/字符比: {tokens/len(text):.2f}")
        print("-" * 40)

    # 测试消息列表
    messages = [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好！有什么可以帮助你的吗？"},
        {"role": "user", "content": "我想了解一下 token 计算器的工作原理。"},
    ]

    total_tokens = token_calc.count_messages_tokens(messages)
    print(f"消息列表总 Token 数: {total_tokens}")
    print("="*60)


def test_query_extractor():
    """测试 QueryExtractor"""
    print("\n" + "="*60)
    print("测试 2: QueryExtractor")
    print("="*60)

    # 初始化 QueryExtractor
    query_extractor = QueryExtractor()

    # 模拟消息对象
    class MockMessage:
        def __init__(self, role, content):
            self.role = role
            self.content = content

    # 测试消息列表
    test_messages = [
        MockMessage("user", "我需要了解如何使用向量数据库"),
        MockMessage("assistant", "向量数据库是一种支持向量相似度检索的数据库。"),
        MockMessage("user", "什么是最合适的向量数据库？"),
        MockMessage("assistant", "有很多选择，比如 pgvector、Milvus 等。"),
        MockMessage("user", "pgvector 的性能如何？"),
    ]

    # 提取查询
    query = query_extractor.extract_from_messages(test_messages, max_length=200)
    print(f"提取的查询文本: {query}")
    print("="*60)


def test_request_cache():
    """测试 RequestCache"""
    print("\n" + "="*60)
    print("测试 3: RequestCache")
    print("="*60)

    # 初始化缓存
    cache = RequestCache(max_size=10, ttl=5)

    # 测试数据
    url = "https://api.example.com/test"
    data1 = {"key": "value1"}
    data2 = {"key": "value2"}

    # 测试缓存 set 和 get
    cache.set(url, data1, "result1")
    cache.set(url, data2, "result2")

    result1 = cache.get(url, data1)
    result2 = cache.get(url, data2)

    print(f"Cache set/get test:")
    print(f"  data1 -> {result1}")
    print(f"  data2 -> {result2}")
    print(f"  Cache size: {cache.size()}")

    # 测试缓存未命中
    result3 = cache.get(url, {"key": "value3"})
    print(f"  data3 (not cached) -> {result3}")

    # 测试缓存过期
    print("\n等待 6 秒...")
    import time
    time.sleep(6)

    result1_expired = cache.get(url, data1)
    print(f"  data1 after 6s -> {result1_expired} (should be None)")

    # 清空缓存
    cache.clear()
    print(f"  Cache size after clear: {cache.size()}")

    print("="*60)


def test_llm_client_basic():
    """测试 LLMClient 基本功能"""
    print("\n" + "="*60)
    print("测试 4: LLMClient 基本功能")
    print("="*60)

    # 初始化 LLMClient（启用缓存和重试）
    client = LLMClient(
        max_retries=3,
        retry_delay=1.0,
        retry_backoff_factor=2.0,
        request_timeout=60.0,
        enable_cache=True,
        cache_ttl=3600
    )

    # 测试 embedding 生成
    print("测试 embedding 生成...")
    try:
        test_text = "这是一个测试文本。"
        embedding = client.generate_embedding_sync(test_text)
        print(f"Embedding 生成成功！")
        print(f"  文本: {test_text}")
        print(f"  Embedding 维度: {len(embedding)}")
        print(f"  前 5 维: {embedding[:5]}")

        # 测试缓存
        print("\n测试 embedding 缓存...")
        embedding2 = client.generate_embedding_sync(test_text)
        print(f"第二次生成成功（应该命中缓存）！")
        print(f"  结果相同: {embedding == embedding2}")

        # 测试聊天补全
        print("\n测试聊天补全...")
        messages = [
            {"role": "user", "content": "你好"}
        ]
        response = client.chat_completion_sync(
            messages=messages,
            temperature=0.7,
            max_tokens=100
        )
        print(f"聊天补全成功！")
        print(f"  回复: {response}")

        # 测试低温度缓存
        print("\n测试聊天补全缓存（低温度）...")
        response2 = client.chat_completion_sync(
            messages=messages,
            temperature=0.2,
            max_tokens=100
        )
        print(f"第二次生成成功（应该命中缓存）！")
        print(f"  结果相同: {response == response2}")

        # 查看缓存大小
        print("\n缓存统计:")
        print(f"  Embedding 缓存大小: {client._embedding_cache.size()}")
        print(f"  LLM 缓存大小: {client._llm_cache.size()}")

    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()

    print("="*60)


def test_memory_service_basic():
    """测试 MemoryService 基本功能"""
    print("\n" + "="*60)
    print("测试 5: MemoryService 基本功能")
    print("="*60)

    # 这个测试需要数据库连接，暂时跳过
    print("注意：此测试需要数据库连接，暂时跳过。")
    print("完整的测试请参考 test_memory_pipeline.py")

    print("="*60)


def main():
    """主测试函数"""
    print("\n" + "="*60)
    print("Agent记忆系统改进测试脚本")
    print("="*60)

    try:
        # 运行所有测试
        test_token_calculator()
        test_query_extractor()
        test_request_cache()
        test_llm_client_basic()
        test_memory_service_basic()

        print("\n" + "="*60)
        print("所有测试完成！✅")
        print("="*60)

    except KeyboardInterrupt:
        print("\n测试被用户中断。")
    except Exception as e:
        print(f"\n测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
