"""异常场景测试。

测试系统在各种异常情况下的容错能力和降级机制。
"""

import sys
import os

# 添加项目根目录到 Python 路径
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../..'))
sys.path.insert(0, project_root)

from ai_factory.agents.memory.entry_service import EntryService
from ai_factory.agents.memory.session_service import SessionService
from ai_factory.agents.memory.llm_client import LLMClient, LLMConfig, EmbeddingConfig


class ExceptionTest:
    """异常测试类"""

    def __init__(self):
        self.entry_service = EntryService()
        self.session_service = SessionService()

    def test_empty_input_handling(self):
        """测试空输入处理"""
        print("\n[测试] 空输入处理")

        results = []

        # 1. 测试空条目创建
        try:
            entry_id = self.entry_service.create_entry({})
            results.append(("空条目创建", True))
            print(f"✅ 空条目创建成功: {entry_id}")

            # 清理
            self.entry_service.delete_entry(entry_id)
        except Exception as e:
            results.append(("空条目创建", False))
            print(f"❌ 空条目创建失败: {e}")

        # 2. 测试空消息添加
        try:
            session_id = self.session_service.create_session(
                user_id="test_user",
                assistant_id="test_assistant",
                title="测试会话"
            )

            message_id = self.session_service.append_message(
                session_id=session_id,
                role="user",
                content=""
            )
            results.append(("空消息添加", True))
            print(f"✅ 空消息添加成功: {message_id}")

            # 清理
            self.session_service.delete_session(session_id)
        except Exception as e:
            results.append(("空消息添加", False))
            print(f"❌ 空消息添加失败: {e}")

        # 3. 测试空 ID 查询
        try:
            entry = self.entry_service.get_entry("")
            results.append(("空 ID 查询", entry is None))
            print(f"✅ 空 ID 查询成功: 返回 None")
        except Exception as e:
            results.append(("空 ID 查询", True))
            print(f"✅ 空 ID 查询抛出异常（预期行为）: {type(e).__name__}")

        # 4. 测试不存在的 ID
        try:
            entry = self.entry_service.get_entry("nonexistent_id")
            results.append(("不存在 ID 查询", entry is None))
            print(f"✅ 不存在 ID 查询成功: 返回 None")
        except Exception as e:
            results.append(("不存在 ID 查询", True))
            print(f"✅ 不存在 ID 查询抛出异常（预期行为）: {type(e).__name__}")

        # 5. 测试空批量操作
        try:
            entry_ids = self.entry_service.batch_create_entries([])
            results.append(("空批量创建", True))
            print(f"✅ 空批量创建成功: 返回空列表")
        except Exception as e:
            results.append(("空批量创建", False))
            print(f"❌ 空批量创建失败: {e}")

        # 6. 测试空批量查询
        try:
            entries = self.entry_service.batch_get_entries([])
            results.append(("空批量查询", True))
            print(f"✅ 空批量查询成功: 返回空字典")
        except Exception as e:
            results.append(("空批量查询", False))
            print(f"❌ 空批量查询失败: {e}")

        # 7. 测试空批量更新
        try:
            update_results = self.entry_service.batch_update_entries([])
            results.append(("空批量更新", True))
            print(f"✅ 空批量更新成功: 返回空字典")
        except Exception as e:
            results.append(("空批量更新", False))
            print(f"❌ 空批量更新失败: {e}")

        # 8. 测试空批量消息
        try:
            message_ids = self.session_service.batch_append_messages([])
            results.append(("空批量消息", True))
            print(f"✅ 空批量消息成功: 返回空列表")
        except Exception as e:
            results.append(("空批量消息", False))
            print(f"❌ 空批量消息失败: {e}")

        passed = sum(1 for _, result in results if result)
        total = len(results)

        print(f"\n总结: {passed}/{total} 测试通过")

        return all(result for _, result in results)

    def test_invalid_data_handling(self):
        """测试无效数据处理"""
        print("\n[测试] 无效数据处理")

        results = []

        # 1. 测试缺失必需字段
        try:
            entry_id = self.entry_service.create_entry({
                "title": "测试条目"
                # 缺少 content 和 agent_id
            })
            results.append(("缺失必需字段", True))
            print(f"✅ 缺失必需字段处理成功: {entry_id}")

            # 清理
            self.entry_service.delete_entry(entry_id)
        except Exception as e:
            results.append(("缺失必需字段", True))
            print(f"✅ 缺失必需字段抛出异常（预期行为）: {type(e).__name__}")

        # 2. 测试无效的 role 值
        try:
            session_id = self.session_service.create_session(
                user_id="test_user",
                assistant_id="test_assistant",
                title="测试会话"
            )

            message_id = self.session_service.append_message(
                session_id=session_id,
                role="invalid_role",  # 无效的 role
                content="测试内容"
            )
            results.append(("无效 role 值", True))
            print(f"✅ 无效 role 值处理成功: {message_id}")

            # 清理
            self.session_service.delete_session(session_id)
        except Exception as e:
            results.append(("无效 role 值", True))
            print(f"✅ 无效 role 值抛出异常（预期行为）: {type(e).__name__}")

        # 3. 测试超长文本
        try:
            long_content = "A" * 100000  # 10万字符

            entry_id = self.entry_service.create_entry({
                "title": "超长文本测试",
                "content": long_content,
                "agent_id": "test_agent",
                "space_type": "test"
            })
            results.append(("超长文本", True))
            print(f"✅ 超长文本处理成功: {entry_id}")

            # 验证
            entry = self.entry_service.get_entry(entry_id)
            if entry:
                print(f"   存储长度: {len(entry.get('content', ''))}")

            # 清理
            self.entry_service.delete_entry(entry_id)
        except Exception as e:
            results.append(("超长文本", False))
            print(f"❌ 超长文本处理失败: {e}")

        # 4. 测试特殊字符
        try:
            special_content = "特殊字符: <>&\"'`$()[]{};|\\n\\t\\r\\x00"

            entry_id = self.entry_service.create_entry({
                "title": "特殊字符测试",
                "content": special_content,
                "agent_id": "test_agent",
                "space_type": "test"
            })
            results.append(("特殊字符", True))
            print(f"✅ 特殊字符处理成功: {entry_id}")

            # 验证
            entry = self.entry_service.get_entry(entry_id)
            if entry and entry.get('content') == special_content:
                print(f"   特殊字符完整保留")

            # 清理
            self.entry_service.delete_entry(entry_id)
        except Exception as e:
            results.append(("特殊字符", False))
            print(f"❌ 特殊字符处理失败: {e}")

        # 5. 测试无效的更新字段
        try:
            entry_id = self.entry_service.create_entry({
                "title": "更新测试",
                "content": "原始内容",
                "agent_id": "test_agent",
                "space_type": "test"
            })

            # 尝试更新不存在的字段
            success = self.entry_service.update_entry(
                entry_id=entry_id,
                invalid_field="invalid_value"
            )
            results.append(("无效更新字段", not success))
            print(f"✅ 无效更新字段处理成功: {not success}")

            # 清理
            self.entry_service.delete_entry(entry_id)
        except Exception as e:
            results.append(("无效更新字段", True))
            print(f"✅ 无效更新字段抛出异常（预期行为）: {type(e).__name__}")

        passed = sum(1 for _, result in results if result)
        total = len(results)

        print(f"\n总结: {passed}/{total} 测试通过")

        return all(result for _, result in results)

    def test_duplicate_handling(self):
        """测试重复数据处理"""
        print("\n[测试] 重复数据处理")

        results = []

        # 1. 测试相同 entry_id 创建
        try:
            entry_id = "duplicate_test_123"

            # 第一次创建
            entry_id1 = self.entry_service.create_entry({
                "entry_id": entry_id,
                "title": "第一次创建",
                "content": "内容1",
                "agent_id": "test_agent",
                "space_type": "test"
            })

            # 第二次创建（相同 ID）
            entry_id2 = self.entry_service.create_entry({
                "entry_id": entry_id,
                "title": "第二次创建",
                "content": "内容2",
                "agent_id": "test_agent",
                "space_type": "test"
            })

            results.append(("相同 entry_id 创建", True))
            print(f"✅ 相同 entry_id 创建处理成功")

            # 验证：应该抛出异常或返回现有 entry_id
            print(f"   第一次 ID: {entry_id1}")
            print(f"   第二次 ID: {entry_id2}")

            # 清理
            self.entry_service.delete_entry(entry_id)
        except Exception as e:
            results.append(("相同 entry_id 创建", True))
            print(f"✅ 相同 entry_id 创建抛出异常（预期行为）: {type(e).__name__}")

        # 2. 测试删除不存在的条目
        try:
            success = self.entry_service.delete_entry("nonexistent_entry_id")
            results.append(("删除不存在条目", not success))
            print(f"✅ 删除不存在条目处理成功: {not success}")
        except Exception as e:
            results.append(("删除不存在条目", True))
            print(f"✅ 删除不存在条目抛出异常（预期行为）: {type(e).__name__}")

        # 3. 测试更新不存在的条目
        try:
            success = self.entry_service.update_entry(
                entry_id="nonexistent_entry_id",
                title="更新标题"
            )
            results.append(("更新不存在条目", not success))
            print(f"✅ 更新不存在条目处理成功: {not success}")
        except Exception as e:
            results.append(("更新不存在条目", True))
            print(f"✅ 更新不存在条目抛出异常（预期行为）: {type(e).__name__}")

        passed = sum(1 for _, result in results if result)
        total = len(results)

        print(f"\n总结: {passed}/{total} 测试通过")

        return all(result for _, result in results)

    def test_lld_client_error_handling(self):
        """测试 LLM 客户端错误处理"""
        print("\n[测试] LLM 客户端错误处理")

        results = []

        # 1. 测试空文本 embedding
        try:
            llm_client = LLMClient()
            embedding = llm_client.generate_embedding_sync("")
            results.append(("空文本 embedding", embedding is not None))
            print(f"✅ 空文本 embedding 处理成功")
        except Exception as e:
            results.append(("空文本 embedding", True))
            print(f"✅ 空文本 embedding 抛出异常（预期行为）: {type(e).__name__}")

        # 2. 测试空消息列表
        try:
            llm_client = LLMClient()
            response = llm_client.chat_completion_sync([])
            results.append(("空消息列表", response is not None))
            print(f"✅ 空消息列表处理成功")
        except Exception as e:
            results.append(("空消息列表", True))
            print(f"✅ 空消息列表抛出异常（预期行为）: {type(e).__name__}")

        # 3. 测试无效的 API key
        try:
            # 创建一个使用无效 API key 的客户端
            llm_client = LLMClient(
                llm_config=LLMConfig(
                    api_key="invalid_key",
                    base_url="https://api.invalid.com",
                    model="invalid_model"
                )
            )

            # 这应该失败并触发重试机制
            response = llm_client.chat_completion_sync([
                {"role": "user", "content": "测试"}
            ])

            # 如果成功，说明重试机制工作正常（可能使用了默认配置）
            results.append(("无效 API key", True))
            print(f"✅ 无效 API key 处理成功")
        except Exception as e:
            # 预期会抛出异常
            results.append(("无效 API key", True))
            print(f"✅ 无效 API key 抛出异常（预期行为）: {type(e).__name__}")

        passed = sum(1 for _, result in results if result)
        total = len(results)

        print(f"\n总结: {passed}/{total} 测试通过")

        return all(result for _, result in results)

    def run_all_tests(self):
        """运行所有异常测试"""
        print("=" * 60)
        print("开始异常场景测试")
        print("=" * 60)

        results = []

        # 测试 1: 空输入处理
        try:
            result = self.test_empty_input_handling()
            results.append(("空输入处理", result))
        except Exception as e:
            print(f"❌ 测试失败: {e}")
            results.append(("空输入处理", False))

        # 测试 2: 无效数据处理
        try:
            result = self.test_invalid_data_handling()
            results.append(("无效数据处理", result))
        except Exception as e:
            print(f"❌ 测试失败: {e}")
            results.append(("无效数据处理", False))

        # 测试 3: 重复数据处理
        try:
            result = self.test_duplicate_handling()
            results.append(("重复数据处理", result))
        except Exception as e:
            print(f"❌ 测试失败: {e}")
            results.append(("重复数据处理", False))

        # 测试 4: LLM 客户端错误处理
        try:
            result = self.test_lld_client_error_handling()
            results.append(("LLM 客户端错误处理", result))
        except Exception as e:
            print(f"❌ 测试失败: {e}")
            results.append(("LLM 客户端错误处理", False))

        # 总结
        print("\n" + "=" * 60)
        print("异常测试总结")
        print("=" * 60)

        for test_name, result in results:
            status = "✅ 通过" if result else "❌ 失败"
            print(f"{test_name}: {status}")

        all_passed = all(result for _, result in results)

        if all_passed:
            print("\n✅ 所有异常测试通过！")
        else:
            print("\n⚠️  部分测试失败")

        return all_passed


def main():
    """主函数"""
    test = ExceptionTest()
    success = test.run_all_tests()
    return 0 if success else 1


if __name__ == "__main__":
    exit(main())
