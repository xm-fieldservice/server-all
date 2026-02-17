#!/usr/bin/env python3
"""Web 查询工具使用示例。

展示如何使用标准化封装的 Web 查询工具。
"""

from ai_factory.integrations.web_query_tool import (
    get_web_query_tool,
    WebQueryConfig,
    QueryMode
)


def example_1_basic_usage():
    """示例 1: 基本用法"""
    print("=" * 60)
    print("示例 1: 基本用法")
    print("=" * 60)

    # 获取工具实例（使用默认配置）
    tool = get_web_query_tool()

    # 执行查询
    result = tool.query(
        question_text="Python 如何实现装饰器？",
        user_id="test-user-001",
        project_code="proj-ai-factory",
        top_k=3
    )

    print(f"\n问题: {result['question']}")
    print(f"回答: {result['answer'][:100]}...")
    print(f"来源数量: {len(result['sources'])}")


def example_2_with_guard():
    """示例 2: 使用带保护的查询"""
    print("\n" + "=" * 60)
    print("示例 2: 使用带保护的查询")
    print("=" * 60)

    tool = get_web_query_tool()

    # 测试非问题输入
    result = tool.query_with_guard("今天会议的记录如下...")
    if not result.get("_guard", {}).get("ok"):
        print(f"被拒绝: {result['answer']}")
        print(f"原因: {result['_guard']['reason']}")

    # 测试问题输入
    result = tool.query_with_guard("如何使用 Python 装饰器？")
    if result.get("_guard", {}).get("ok"):
        print(f"接受: {result['answer'][:100]}...")


def example_3_custom_config():
    """示例 3: 使用自定义配置"""
    print("\n" + "=" * 60)
    print("示例 3: 使用自定义配置")
    print("=" * 60)

    # 创建自定义配置
    config = WebQueryConfig(
        max_results=10,
        top_k=5,
        enable_result_filter=True,
        enable_guard=True
    )

    # 使用自定义配置创建工具
    tool = get_web_query_tool(config)

    result = tool.query(
        question_text="什么是机器学习？",
        project_code="proj-ml"
    )

    print(f"\n问题: {result['question']}")
    print(f"回答: {result['answer'][:100]}...")
    print(f"来源数量: {len(result['sources'])}")


def example_4_multiple_queries():
    """示例 4: 执行多个查询"""
    print("\n" + "=" * 60)
    print("示例 4: 执行多个查询")
    print("=" * 60)

    tool = get_web_query_tool()

    questions = [
        "什么是 GraphQL？",
        "如何优化 Python 代码性能？",
        "Docker 如何使用？"
    ]

    for i, question in enumerate(questions, 1):
        print(f"\n[{i}/{len(questions)}] {question}")
        try:
            result = tool.query(question_text=question, top_k=3)
            print(f"  简短回答: {result['answer'][:80]}...")
            print(f"  来源: {len(result['sources'])}")
        except Exception as e:
            print(f"  错误: {e}")


def main():
    """主函数"""
    print("Web 查询工具使用示例\n")

    try:
        # 注意：这些示例需要有效的 API 密钥配置
        # 在运行前确保已设置 GOOGLE_SEARCH_API_KEY 和 GOOGLE_SEARCH_ENGINE_ID

        # example_1_basic_usage()
        # example_2_with_guard()
        # example_3_custom_config()
        example_4_multiple_queries()

    except Exception as e:
        print(f"运行示例时出错: {e}")
        print("\n提示:")
        print("- 确保已设置环境变量: GOOGLE_SEARCH_API_KEY 和 GOOGLE_SEARCH_ENGINE_ID")
        print("- 检查网络连接是否正常")
        print("- 确认 API 密钥有效且具有足够的配额")


if __name__ == "__main__":
    main()
