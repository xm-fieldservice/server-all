"""性能基准测试。

测试系统的吞吐量、延迟和资源使用情况。
"""

import sys
import os
import time
import statistics
from typing import List, Dict, Any, Tuple

# 添加项目根目录到 Python 路径
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../..'))
sys.path.insert(0, project_root)

from ai_factory.agents.memory.entry_service import EntryService
from ai_factory.agents.memory.session_service import SessionService
from ai_factory.agents.memory.vector_client import VectorClient
from ai_factory.agents.memory.llm_client import get_llm_client


class PerformanceTest:
    """性能测试类"""

    def __init__(self):
        self.entry_service = EntryService()
        self.session_service = SessionService()
        self.vector_client = VectorClient()
        self.llm_client = get_llm_client()

    def _measure_time(self, func, *args, **kwargs) -> Tuple[Any, float]:
        """测量函数执行时间

        Args:
            func: 要测量的函数
            *args: 位置参数
            **kwargs: 关键字参数

        Returns:
            Tuple[Any, float]: (返回值, 执行时间)
        """
        start_time = time.time()
        result = func(*args, **kwargs)
        elapsed_time = time.time() - start_time
        return result, elapsed_time

    def test_entry_create_performance(self, num_entries: int = 100):
        """测试条目创建性能

        Args:
            num_entries: 创建的条目数量
        """
        print(f"\n[性能测试] 条目创建: {num_entries} 条")

        entry_ids = []
        latencies = []

        for i in range(num_entries):
            entry_data = {
                "title": f"性能测试条目 {i}",
                "content": f"这是第 {i} 条性能测试数据，用于测试系统的写入性能和吞吐量。" * 5,
                "agent_id": "perf_test_agent",
                "space_type": "performance_test"
            }

            _, latency = self._measure_time(self.entry_service.create_entry, entry_data)
            latencies.append(latency)

            # 收集 ID 用于清理
            entry_id = self.entry_service.get_agent_entries(
                agent_id="perf_test_agent",
                space_type="performance_test",
                limit=1000
            )
            if entry_id:
                entry_ids.extend([e["entry_id"] for e in entry_id])
                entry_ids = list(dict.fromkeys(entry_ids))[-num_entries:]  # 去重并保留最新的

        # 统计
        total_time = sum(latencies)
        avg_latency = statistics.mean(latencies)
        min_latency = min(latencies)
        max_latency = max(latencies)
        median_latency = statistics.median(latencies)
        p95_latency = statistics.quantiles(latencies, n=20)[18] if len(latencies) > 20 else max(latencies)
        throughput = num_entries / total_time

        print(f"✅ 创建完成")
        print(f"   总耗时: {total_time:.3f} 秒")
        print(f"   平均延迟: {avg_latency*1000:.2f} ms")
        print(f"   最小延迟: {min_latency*1000:.2f} ms")
        print(f"   最大延迟: {max_latency*1000:.2f} ms")
        print(f"   中位数延迟: {median_latency*1000:.2f} ms")
        print(f"   P95 延迟: {p95_latency*1000:.2f} ms")
        print(f"   吞吐量: {throughput:.2f} 条/秒")

        # 清理
        print("   清理测试数据...")
        for entry_id in entry_ids:
            try:
                self.entry_service.delete_entry(entry_id)
            except Exception:
                pass

        return throughput, avg_latency

    def test_entry_read_performance(self, num_entries: int = 100):
        """测试条目读取性能

        Args:
            num_entries: 读取的条目数量
        """
        print(f"\n[性能测试] 条目读取: {num_entries} 条")

        # 先创建测试数据
        entry_ids = []
        for i in range(num_entries):
            entry_id = self.entry_service.create_entry({
                "title": f"读取性能测试 {i}",
                "content": f"测试内容 {i}" * 10,
                "agent_id": "read_perf_test",
                "space_type": "test"
            })
            entry_ids.append(entry_id)

        # 测试单条读取性能
        latencies = []
        for entry_id in entry_ids:
            _, latency = self._measure_time(self.entry_service.get_entry, entry_id)
            latencies.append(latency)

        # 统计
        avg_latency = statistics.mean(latencies)
        min_latency = min(latencies)
        max_latency = max(latencies)
        median_latency = statistics.median(latencies)
        p95_latency = statistics.quantiles(latencies, n=20)[18] if len(latencies) > 20 else max(latencies)
        throughput = num_entries / sum(latencies)

        print(f"✅ 单条读取完成")
        print(f"   平均延迟: {avg_latency*1000:.2f} ms")
        print(f"   最小延迟: {min_latency*1000:.2f} ms")
        print(f"   最大延迟: {max_latency*1000:.2f} ms")
        print(f"   中位数延迟: {median_latency*1000:.2f} ms")
        print(f"   P95 延迟: {p95_latency*1000:.2f} ms")
        print(f"   吞吐量: {throughput:.2f} 条/秒")

        # 测试批量读取性能
        batch_size = 10
        batch_latencies = []
        for i in range(0, num_entries, batch_size):
            batch_ids = entry_ids[i:i+batch_size]
            _, latency = self._measure_time(self.entry_service.batch_get_entries, batch_ids)
            batch_latencies.append(latency)

        batch_avg_latency = statistics.mean(batch_latencies)
        batch_throughput = (num_entries / batch_size) / sum(batch_latencies)

        print(f"\n✅ 批量读取完成 (批量大小: {batch_size})")
        print(f"   平均延迟: {batch_avg_latency*1000:.2f} ms")
        print(f"   吞吐量: {batch_throughput:.2f} 批次/秒")

        # 清理
        print("   清理测试数据...")
        for entry_id in entry_ids:
            self.entry_service.delete_entry(entry_id)

        return throughput, avg_latency

    def test_vector_search_performance(self, num_queries: int = 50):
        """测试向量检索性能

        Args:
            num_queries: 查询次数
        """
        print(f"\n[性能测试] 向量检索: {num_queries} 次查询")

        # 准备测试数据
        print("   准备测试数据...")
        entry_ids = []
        for i in range(100):
            entry_id = self.entry_service.create_entry({
                "title": f"向量测试 {i}",
                "content": f"向量检索性能测试数据 {i}，用于测试向量搜索的性能。" * 3,
                "agent_id": "vector_perf_test",
                "space_type": "test"
            })
            entry_ids.append(entry_id)

            # 生成并存储向量
            embedding = self.llm_client.generate_embedding_sync(f"测试文本 {i}")
            self.vector_client.upsert_embedding(entry_id, embedding)

        print(f"   准备了 {len(entry_ids)} 条测试数据")

        # 测试检索性能
        latencies = []
        query_embedding = self.llm_client.generate_embedding_sync("查询测试")

        for _ in range(num_queries):
            _, latency = self._measure_time(
                self.vector_client.search_entries,
                query_embedding=query_embedding,
                filters={"agent_id": "vector_perf_test"},
                top_k=10
            )
            latencies.append(latency)

        # 统计
        avg_latency = statistics.mean(latencies)
        min_latency = min(latencies)
        max_latency = max(latencies)
        median_latency = statistics.median(latencies)
        p95_latency = statistics.quantiles(latencies, n=20)[18] if len(latencies) > 20 else max(latencies)
        throughput = num_queries / sum(latencies)

        print(f"✅ 检索完成")
        print(f"   平均延迟: {avg_latency*1000:.2f} ms")
        print(f"   最小延迟: {min_latency*1000:.2f} ms")
        print(f"   最大延迟: {max_latency*1000:.2f} ms")
        print(f"   中位数延迟: {median_latency*1000:.2f} ms")
        print(f"   P95 延迟: {p95_latency*1000:.2f} ms")
        print(f"   吞吐量: {throughput:.2f} 次/秒")

        # 清理
        print("   清理测试数据...")
        for entry_id in entry_ids:
            self.entry_service.delete_entry(entry_id)

        return throughput, avg_latency

    def test_message_append_performance(self, num_messages: int = 500):
        """测试消息添加性能

        Args:
            num_messages: 添加的消息数量
        """
        print(f"\n[性能测试] 消息添加: {num_messages} 条")

        # 创建测试会话
        session_id = self.session_service.create_session(
            user_id="perf_test_user",
            assistant_id="perf_test_assistant",
            title="性能测试会话"
        )

        latencies = []

        for i in range(num_messages):
            role = "user" if i % 2 == 0 else "assistant"
            _, latency = self._measure_time(
                self.session_service.append_message,
                session_id=session_id,
                role=role,
                content=f"性能测试消息 {i}: 这是一条用于测试系统消息添加性能的数据。" * 3
            )
            latencies.append(latency)

        # 统计
        total_time = sum(latencies)
        avg_latency = statistics.mean(latencies)
        min_latency = min(latencies)
        max_latency = max(latencies)
        median_latency = statistics.median(latencies)
        p95_latency = statistics.quantiles(latencies, n=20)[18] if len(latencies) > 20 else max(latencies)
        throughput = num_messages / total_time

        print(f"✅ 添加完成")
        print(f"   总耗时: {total_time:.3f} 秒")
        print(f"   平均延迟: {avg_latency*1000:.2f} ms")
        print(f"   最小延迟: {min_latency*1000:.2f} ms")
        print(f"   最大延迟: {max_latency*1000:.2f} ms")
        print(f"   中位数延迟: {median_latency*1000:.2f} ms")
        print(f"   P95 延迟: {p95_latency*1000:.2f} ms")
        print(f"   吞吐量: {throughput:.2f} 条/秒")

        # 清理
        print("   清理测试数据...")
        self.session_service.delete_session(session_id)

        return throughput, avg_latency

    def test_batch_operation_performance(self):
        """测试批量操作性能"""
        print(f"\n[性能测试] 批量操作性能对比")

        # 准备测试数据
        num_entries = 100

        # 测试单条创建 vs 批量创建
        print("\n   [单条创建 vs 批量创建]")

        # 单条创建
        single_latencies = []
        single_ids = []
        for i in range(num_entries):
            entry_data = {
                "title": f"单条创建 {i}",
                "content": f"测试内容 {i}",
                "agent_id": "batch_test_single",
                "space_type": "test"
            }
            _, latency = self._measure_time(self.entry_service.create_entry, entry_data)
            single_latencies.append(latency)

        single_total = sum(single_latencies)

        # 批量创建
        batch_entries = [
            {
                "title": f"批量创建 {i}",
                "content": f"测试内容 {i}",
                "agent_id": "batch_test_batch",
                "space_type": "test"
            }
            for i in range(num_entries)
        ]

        _, batch_latency = self._measure_time(self.entry_service.batch_create_entries, batch_entries)

        # 对比
        speedup = single_total / batch_latency

        print(f"   单条创建: {single_total:.3f} 秒 ({num_entries/single_total:.2f} 条/秒)")
        print(f"   批量创建: {batch_latency:.3f} 秒 ({num_entries/batch_latency:.2f} 条/秒)")
        print(f"   加速比: {speedup:.2f}x")

        # 清理
        print("   清理测试数据...")
        single_entries = self.entry_service.get_agent_entries(
            agent_id="batch_test_single",
            space_type="test",
            limit=1000
        )
        for entry in single_entries:
            self.entry_service.delete_entry(entry["entry_id"])

        batch_entries_data = self.entry_service.get_agent_entries(
            agent_id="batch_test_batch",
            space_type="test",
            limit=1000
        )
        for entry in batch_entries_data:
            self.entry_service.delete_entry(entry["entry_id"])

        return speedup

    def test_embedding_generation_performance(self, num_texts: int = 50):
        """测试向量生成性能

        Args:
            num_texts: 生成的文本数量
        """
        print(f"\n[性能测试] 向量生成: {num_texts} 个文本")

        texts = [f"性能测试文本 {i}，用于测试向量生成的性能。" * 5 for i in range(num_texts)]

        latencies = []

        for text in texts:
            _, latency = self._measure_time(self.llm_client.generate_embedding_sync, text)
            latencies.append(latency)

        # 统计
        total_time = sum(latencies)
        avg_latency = statistics.mean(latencies)
        min_latency = min(latencies)
        max_latency = max(latencies)
        median_latency = statistics.median(latencies)
        p95_latency = statistics.quantiles(latencies, n=20)[18] if len(latencies) > 20 else max(latencies)
        throughput = num_texts / total_time

        print(f"✅ 生成完成")
        print(f"   总耗时: {total_time:.3f} 秒")
        print(f"   平均延迟: {avg_latency*1000:.2f} ms")
        print(f"   最小延迟: {min_latency*1000:.2f} ms")
        print(f"   最大延迟: {max_latency*1000:.2f} ms")
        print(f"   中位数延迟: {median_latency*1000:.2f} ms")
        print(f"   P95 延迟: {p95_latency*1000:.2f} ms")
        print(f"   吞吐量: {throughput:.2f} 个/秒")

        return throughput, avg_latency

    def run_all_tests(self):
        """运行所有性能测试"""
        print("=" * 60)
        print("开始性能基准测试")
        print("=" * 60)

        results = []

        # 测试 1: 条目创建性能
        try:
            throughput, latency = self.test_entry_create_performance(num_entries=100)
            results.append(("条目创建性能", throughput, latency))
        except Exception as e:
            print(f"❌ 测试失败: {e}")
            results.append(("条目创建性能", 0, 0))

        # 测试 2: 条目读取性能
        try:
            throughput, latency = self.test_entry_read_performance(num_entries=100)
            results.append(("条目读取性能", throughput, latency))
        except Exception as e:
            print(f"❌ 测试失败: {e}")
            results.append(("条目读取性能", 0, 0))

        # 测试 3: 向量检索性能
        try:
            throughput, latency = self.test_vector_search_performance(num_queries=50)
            results.append(("向量检索性能", throughput, latency))
        except Exception as e:
            print(f"❌ 测试失败: {e}")
            results.append(("向量检索性能", 0, 0))

        # 测试 4: 消息添加性能
        try:
            throughput, latency = self.test_message_append_performance(num_messages=200)
            results.append(("消息添加性能", throughput, latency))
        except Exception as e:
            print(f"❌ 测试失败: {e}")
            results.append(("消息添加性能", 0, 0))

        # 测试 5: 批量操作性能
        try:
            speedup = self.test_batch_operation_performance()
            results.append(("批量操作加速比", speedup, 0))
        except Exception as e:
            print(f"❌ 测试失败: {e}")
            results.append(("批量操作加速比", 0, 0))

        # 测试 6: 向量生成性能
        try:
            throughput, latency = self.test_embedding_generation_performance(num_texts=30)
            results.append(("向量生成性能", throughput, latency))
        except Exception as e:
            print(f"❌ 测试失败: {e}")
            results.append(("向量生成性能", 0, 0))

        # 总结
        print("\n" + "=" * 60)
        print("性能测试总结")
        print("=" * 60)

        print(f"\n{'测试项目':<20} {'吞吐量':<20} {'平均延迟 (ms)':<20}")
        print("-" * 60)

        for test_name, throughput, latency in results:
            throughput_str = f"{throughput:.2f} 次/秒" if throughput > 0 else "N/A"
            latency_str = f"{latency*1000:.2f} ms" if latency > 0 else "N/A"

            if test_name == "批量操作加速比":
                print(f"{test_name:<20} {f'{throughput:.2f}x':<20} {'N/A':<20}")
            else:
                print(f"{test_name:<20} {throughput_str:<20} {latency_str:<20}")

        print("\n" + "=" * 60)
        print("✅ 性能测试完成！")
        print("=" * 60)

        return True


def main():
    """主函数"""
    test = PerformanceTest()
    success = test.run_all_tests()
    return 0 if success else 1


if __name__ == "__main__":
    exit(main())
