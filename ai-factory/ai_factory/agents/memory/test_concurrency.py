"""并发场景测试。

测试系统在高并发情况下的稳定性和正确性。
"""

import sys
import os
import threading
import time
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any

# 添加项目根目录到 Python 路径
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../..'))
sys.path.insert(0, project_root)

from ai_factory.agents.memory.entry_service import EntryService
from ai_factory.agents.memory.session_service import SessionService
from ai_factory.agents.memory.llm_client import get_llm_client


class ConcurrencyTest:
    """并发测试类"""

    def __init__(self):
        self.entry_service = EntryService()
        self.session_service = SessionService()
        self.llm_client = get_llm_client()
        self.errors = []
        self.lock = threading.Lock()

    def test_concurrent_entry_creation(self, num_threads: int = 10, entries_per_thread: int = 5):
        """测试并发创建条目

        Args:
            num_threads: 线程数
            entries_per_thread: 每个线程创建的条目数
        """
        print(f"\n[测试] 并发创建条目: {num_threads} 线程, 每线程 {entries_per_thread} 条目")

        entry_ids = []
        entry_ids_lock = threading.Lock()

        def create_entries(thread_id: int):
            """线程函数：创建条目"""
            try:
                for i in range(entries_per_thread):
                    entry_data = {
                        "title": f"并发测试条目 T{thread_id}-E{i}",
                        "content": f"线程 {thread_id} 的第 {i} 个条目",
                        "agent_id": f"concurrent_test_thread_{thread_id}",
                        "space_type": "concurrent_test"
                    }

                    entry_id = self.entry_service.create_entry(entry_data)

                    with entry_ids_lock:
                        entry_ids.append(entry_id)

            except Exception as e:
                with self.lock:
                    self.errors.append(f"线程 {thread_id} 创建失败: {e}")

        # 执行并发创建
        start_time = time.time()

        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(create_entries, i) for i in range(num_threads)]
            for future in as_completed(futures):
                future.result()  # 等待所有线程完成

        elapsed_time = time.time() - start_time

        # 验证结果
        expected_count = num_threads * entries_per_thread
        actual_count = len(entry_ids)

        print(f"✅ 完成: 预期 {expected_count} 条，实际 {actual_count} 条")
        print(f"   耗时: {elapsed_time:.2f} 秒")
        print(f"   吞吐量: {actual_count / elapsed_time:.2f} 条/秒")

        if self.errors:
            print(f"   ⚠️  错误数: {len(self.errors)}")
            for error in self.errors[:3]:  # 只显示前3个错误
                print(f"      - {error}")

        # 清理
        print("   清理测试数据...")
        for entry_id in entry_ids:
            try:
                self.entry_service.delete_entry(entry_id)
            except Exception:
                pass

        return actual_count == expected_count and not self.errors

    def test_concurrent_message_append(self, num_threads: int = 10, messages_per_thread: int = 5):
        """测试并发添加消息

        Args:
            num_threads: 线程数
            messages_per_thread: 每个线程添加的消息数
        """
        print(f"\n[测试] 并发添加消息: {num_threads} 线程, 每线程 {messages_per_thread} 条消息")

        # 创建测试会话
        session_id = self.session_service.create_session(
            user_id="concurrent_test_user",
            assistant_id="concurrent_test_assistant",
            title="并发测试会话"
        )

        message_ids = []
        message_ids_lock = threading.Lock()

        def append_messages(thread_id: int):
            """线程函数：添加消息"""
            try:
                for i in range(messages_per_thread):
                    role = "user" if i % 2 == 0 else "assistant"
                    message_id = self.session_service.append_message(
                        session_id=session_id,
                        role=role,
                        content=f"线程 {thread_id} 的第 {i} 条消息"
                    )

                    with message_ids_lock:
                        message_ids.append(message_id)

            except Exception as e:
                with self.lock:
                    self.errors.append(f"线程 {thread_id} 添加消息失败: {e}")

        # 执行并发添加
        start_time = time.time()

        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(append_messages, i) for i in range(num_threads)]
            for future in as_completed(futures):
                future.result()

        elapsed_time = time.time() - start_time

        # 验证结果
        expected_count = num_threads * messages_per_thread
        actual_count = len(message_ids)

        print(f"✅ 完成: 预期 {expected_count} 条，实际 {actual_count} 条")
        print(f"   耗时: {elapsed_time:.2f} 秒")
        print(f"   吞吐量: {actual_count / elapsed_time:.2f} 条/秒")

        if self.errors:
            print(f"   ⚠️  错误数: {len(self.errors)}")

        # 清理
        print("   清理测试数据...")
        self.session_service.delete_session(session_id)

        return actual_count == expected_count and not self.errors

    def test_concurrent_entry_update(self, num_threads: int = 10):
        """测试并发更新条目

        Args:
            num_threads: 线程数
        """
        print(f"\n[测试] 并发更新条目: {num_threads} 线程")

        # 创建测试条目
        entry_id = self.entry_service.create_entry({
            "title": "并发更新测试条目",
            "content": "原始内容",
            "agent_id": "concurrent_update_test",
            "space_type": "test"
        })

        def update_entry(thread_id: int):
            """线程函数：更新条目"""
            try:
                for _ in range(5):  # 每个线程更新5次
                    time.sleep(random.uniform(0.001, 0.01))  # 随机延迟

                    self.entry_service.update_entry(
                        entry_id=entry_id,
                        content=f"线程 {thread_id} 的更新内容 - {time.time()}",
                        importance=random.randint(1, 10)
                    )

            except Exception as e:
                with self.lock:
                    self.errors.append(f"线程 {thread_id} 更新失败: {e}")

        # 执行并发更新
        start_time = time.time()

        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(update_entry, i) for i in range(num_threads)]
            for future in as_completed(futures):
                future.result()

        elapsed_time = time.time() - start_time

        # 验证结果
        entry = self.entry_service.get_entry(entry_id)
        print(f"✅ 完成: {num_threads} 个线程并发更新")
        print(f"   耗时: {elapsed_time:.2f} 秒")
        print(f"   更新后内容: {entry.get('content', '')[:50]}...")
        print(f"   更新后 importance: {entry.get('importance')}")

        if self.errors:
            print(f"   ⚠️  错误数: {len(self.errors)}")

        # 清理
        print("   清理测试数据...")
        self.entry_service.delete_entry(entry_id)

        return entry is not None and not self.errors

    def test_concurrent_embedding_generation(self, num_threads: int = 10, texts_per_thread: int = 3):
        """测试并发生成向量

        Args:
            num_threads: 线程数
            texts_per_thread: 每个线程生成的文本数
        """
        print(f"\n[测试] 并发生成向量: {num_threads} 线程, 每线程 {texts_per_thread} 个文本")

        texts = [f"测试文本 {i}" for i in range(num_threads * texts_per_thread)]
        embeddings = []
        embeddings_lock = threading.Lock()

        def generate_embeddings(thread_id: int):
            """线程函数：生成向量"""
            try:
                for i in range(texts_per_thread):
                    text = texts[thread_id * texts_per_thread + i]
                    embedding = self.llm_client.generate_embedding_sync(text)

                    with embeddings_lock:
                        embeddings.append(embedding)

            except Exception as e:
                with self.lock:
                    self.errors.append(f"线程 {thread_id} 生成向量失败: {e}")

        # 执行并发生成
        start_time = time.time()

        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(generate_embeddings, i) for i in range(num_threads)]
            for future in as_completed(futures):
                future.result()

        elapsed_time = time.time() - start_time

        # 验证结果
        expected_count = num_threads * texts_per_thread
        actual_count = len(embeddings)

        print(f"✅ 完成: 预期 {expected_count} 个，实际 {actual_count} 个")
        print(f"   耗时: {elapsed_time:.2f} 秒")
        print(f"   吞吐量: {actual_count / elapsed_time:.2f} 个/秒")

        if embeddings:
            print(f"   向量维度: {len(embeddings[0])}")

        if self.errors:
            print(f"   ⚠️  错误数: {len(self.errors)}")

        return actual_count == expected_count and not self.errors

    def run_all_tests(self):
        """运行所有并发测试"""
        print("=" * 60)
        print("开始并发场景测试")
        print("=" * 60)

        results = []

        # 测试 1: 并发创建条目
        try:
            result = self.test_concurrent_entry_creation(num_threads=10, entries_per_thread=5)
            results.append(("并发创建条目", result))
        except Exception as e:
            print(f"❌ 测试失败: {e}")
            results.append(("并发创建条目", False))

        # 测试 2: 并发添加消息
        try:
            result = self.test_concurrent_message_append(num_threads=10, messages_per_thread=5)
            results.append(("并发添加消息", result))
        except Exception as e:
            print(f"❌ 测试失败: {e}")
            results.append(("并发添加消息", False))

        # 测试 3: 并发更新条目
        try:
            result = self.test_concurrent_entry_update(num_threads=10)
            results.append(("并发更新条目", result))
        except Exception as e:
            print(f"❌ 测试失败: {e}")
            results.append(("并发更新条目", False))

        # 测试 4: 并发生成向量
        try:
            result = self.test_concurrent_embedding_generation(num_threads=5, texts_per_thread=3)
            results.append(("并发生成向量", result))
        except Exception as e:
            print(f"❌ 测试失败: {e}")
            results.append(("并发生成向量", False))

        # 总结
        print("\n" + "=" * 60)
        print("并发测试总结")
        print("=" * 60)

        for test_name, result in results:
            status = "✅ 通过" if result else "❌ 失败"
            print(f"{test_name}: {status}")

        all_passed = all(result for _, result in results)

        if all_passed:
            print("\n✅ 所有并发测试通过！")
        else:
            print("\n⚠️  部分测试失败")

        return all_passed


def main():
    """主函数"""
    test = ConcurrencyTest()
    success = test.run_all_tests()
    return 0 if success else 1


if __name__ == "__main__":
    exit(main())
