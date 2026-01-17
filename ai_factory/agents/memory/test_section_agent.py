"""
Section Agent 测试脚本

测试多 Agent 语义切分功能，包括：
1. Agent1：局部 Section 识别
2. Agent2：宏观复核 + 话题标签
3. Agent3：多视角关联重构（可选）
4. 协同工作流
"""

import asyncio
import sys
import os

# 添加项目根目录到 Python 路径
# 测试文件在 ai-factory/ai_factory/agents/memory/test_section_agent.py
# 需要添加 ai-factory/ 到 sys.path，这样 ai_factory 包才能被找到
test_dir = os.path.dirname(os.path.abspath(__file__))
# 向上三级：memory -> agents -> ai_factory -> ai-factory
project_root = os.path.dirname(os.path.dirname(os.path.dirname(test_dir)))  # ai-factory/ai_factory
ai_factory_root = os.path.dirname(project_root)  # ai-factory/
sys.path.insert(0, ai_factory_root)

# 添加 ai_factory/ai_factory/ 到 sys.path
sys.path.insert(0, project_root)

from ai_factory.agents.memory.section_agent import (
    SectionAgent,
    SectionDecision,
    SectionBoundary,
    SectionProposal,
    SectionReview
)
from ai_factory.agents.memory.llm_client import get_llm_client
from ai_factory.agents.memory.llm_client import LLMConfig


async def test_explicit_end_detection():
    """测试显式结束语检测"""
    print("\n=== 测试 1: 显式结束语检测 ===")
    
    # 创建 LLM 客户端
    llm_client = get_llm_client()
    
    # 创建 Section Agent
    section_agent = SectionAgent(
        llm_client=llm_client,
        config={
            "enable_llm_judgment": False,  # 只测试规则检测
            "explicit_end_keywords": ["先到这儿", "换个话题", "结束这个话题"]
        }
    )
    
    # 测试消息（包含显式结束语）
    messages = [
        {"role": "user", "content": "我们讨论一下项目进度"},
        {"role": "assistant", "content": "好的，项目目前进展顺利"},
        {"role": "user", "content": "先到这儿吧，我们换个话题"}
    ]
    
    # 执行分析
    proposal = await section_agent.analyze_local_context(messages)
    
    # 验证结果
    assert proposal.boundaries, "应该检测到边界"
    assert proposal.boundaries[0].decision == SectionDecision.END_SECTION, "应该结束 section"
    assert "显式结束语" in proposal.boundaries[0].reason, "理由应该包含'显式结束语'"
    
    print(f"✓ 检测到显式结束语: {proposal.boundaries[0].reason}")
    print(f"✓ 决策: {proposal.boundaries[0].decision.value}")
    print(f"✓ 置信度: {proposal.boundaries[0].confidence}")


async def test_rule_based_analysis():
    """测试基于规则的分析"""
    print("\n=== 测试 2: 基于规则的分析 ===")
    
    # 创建 LLM 客户端
    llm_client = get_llm_client()
    
    # 创建 Section Agent
    section_agent = SectionAgent(
        llm_client=llm_client,
        config={
            "enable_llm_judgment": False,  # 只使用规则
            "min_section_length": 3,
            "max_section_length": 20
        }
    )
    
    # 测试消息（消息太少）
    messages = [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好！"}
    ]
    
    # 执行分析
    proposal = await section_agent.analyze_local_context(messages)
    
    # 验证结果
    assert not proposal.boundaries, "消息太少，不应该检测到边界"
    assert "消息数量不足" in proposal.overall_summary, "理由应该包含'消息数量不足'"
    
    print(f"✓ 消息太少，继续当前 section: {proposal.overall_summary}")
    
    # 测试消息（消息太多）
    many_messages = [
        {"role": "user", "content": f"消息 {i}"}
        for i in range(25)
    ]
    
    # 执行分析
    proposal = await section_agent.analyze_local_context(many_messages)
    
    # 验证结果
    assert proposal.boundaries, "消息太多，应该检测到边界"
    assert proposal.boundaries[0].decision == SectionDecision.END_SECTION, "应该结束 section"
    assert "消息数量达到上限" in proposal.boundaries[0].reason, "理由应该包含'消息数量达到上限'"
    
    print(f"✓ 消息太多，建议结束 section: {proposal.boundaries[0].reason}")


async def test_llm_based_analysis():
    """测试基于 LLM 的分析"""
    print("\n=== 测试 3: 基于 LLM 的分析 ===")
    
    # 创建 LLM 客户端
    llm_client = get_llm_client()
    
    # 创建 Section Agent
    section_agent = SectionAgent(
        llm_client=llm_client,
        config={
            "enable_llm_judgment": True,  # 使用 LLM
            "min_section_length": 3,
            "max_section_length": 20
        }
    )
    
    # 测试消息（话题转换）
    messages = [
        {"role": "user", "content": "我们讨论一下项目 A 的进度"},
        {"role": "assistant", "content": "项目 A 目前进展顺利，已经完成了 50%"},
        {"role": "user", "content": "好的，那我们换个话题，讨论一下项目 B 的计划"}
    ]
    
    # 执行分析
    proposal = await section_agent.analyze_local_context(messages)
    
    # 验证结果
    assert proposal.boundaries, "应该检测到边界"
    print(f"✓ LLM 分析结果: {proposal.overall_summary}")
    print(f"✓ 决策: {proposal.boundaries[0].decision.value}")
    print(f"✓ 置信度: {proposal.boundaries[0].confidence}")


async def test_review_and_tag_sections():
    """测试 Agent2：宏观复核 + 话题标签"""
    print("\n=== 测试 4: Agent2 宏观复核 + 话题标签 ===")
    
    # 创建 LLM 客户端
    llm_client = get_llm_client()
    
    # 创建 Section Agent
    section_agent = SectionAgent(
        llm_client=llm_client,
        config={
            "enable_llm_judgment": True
        }
    )
    
    # 测试消息
    messages = [
        {"role": "user", "content": "我们讨论一下软件部的项目进度"},
        {"role": "assistant", "content": "好的，软件部目前有几个项目在进行中"},
        {"role": "user", "content": "主要是关于知识库的项目"}
    ]
    
    # 创建提案
    proposal = SectionProposal(
        boundaries=[
            SectionBoundary(
                message_index=2,
                decision=SectionDecision.END_SECTION,
                reason="检测到话题转换",
                confidence=0.8,
                suggested_title="软件部知识库项目"
            )
        ],
        overall_summary="建议结束当前 section",
        confidence=0.8
    )
    
    # 执行复核
    review = await section_agent.review_and_tag_sections(messages, proposal)
    
    # 验证结果
    assert review.approved_boundaries, "应该批准边界"
    assert review.scene_tags, "应该生成场景标签"
    
    print(f"✓ 批准边界: {len(review.approved_boundaries)} 个")
    print(f"✓ 场景标签: {review.scene_tags}")
    print(f"✓ 复核说明: {review.review_notes}")


async def test_rule_based_review():
    """测试基于规则的复核"""
    print("\n=== 测试 5: 基于规则的复核 ===")
    
    # 创建 LLM 客户端
    llm_client = get_llm_client()
    
    # 创建 Section Agent
    section_agent = SectionAgent(
        llm_client=llm_client,
        config={
            "enable_llm_judgment": False  # 只使用规则
        }
    )
    
    # 创建提案
    proposal = SectionProposal(
        boundaries=[
            SectionBoundary(
                message_index=5,
                decision=SectionDecision.END_SECTION,
                reason="消息数量达到上限",
                confidence=0.7,
                suggested_title="Untitled Section"
            )
        ],
        overall_summary="消息数量达到上限，建议结束当前 section",
        confidence=0.7
    )
    
    # 执行复核
    review = await section_agent.review_and_tag_sections([], proposal)
    
    # 验证结果
    assert review.approved_boundaries, "应该批准边界"
    assert review.scene_tags, "应该生成默认场景标签"
    
    print(f"✓ 批准边界: {len(review.approved_boundaries)} 个")
    print(f"✓ 场景标签: {review.scene_tags}")
    print(f"✓ 复核说明: {review.review_notes}")


async def test_collaborative_workflow():
    """测试协同工作流"""
    print("\n=== 测试 6: 协同工作流 ===")
    
    # 创建 LLM 客户端
    llm_client = get_llm_client()
    
    # 创建 Section Agent
    section_agent = SectionAgent(
        llm_client=llm_client,
        config={
            "enable_llm_judgment": True
        }
    )
    
    # 测试消息
    messages = [
        {"role": "user", "content": "我们讨论一下软件部的项目进度"},
        {"role": "assistant", "content": "好的，软件部目前有几个项目在进行中"},
        {"role": "user", "content": "主要是关于知识库的项目"},
        {"role": "assistant", "content": "知识库项目目前进展如何？"},
        {"role": "user", "content": "已经完成了 60%，接下来要换个话题讨论一下其他项目"}
    ]
    
    # 执行协同分析
    result = await section_agent.analyze_session(messages)
    
    # 验证结果
    assert "proposal" in result, "应该包含提案"
    assert "review" in result, "应该包含复核"
    assert "final_boundaries" in result, "应该包含最终边界"
    assert "scene_tags" in result, "应该包含场景标签"
    assert "overall_confidence" in result, "应该包含整体置信度"
    
    print(f"✓ 提案: {result['proposal']['overall_summary']}")
    print(f"✓ 复核: {result['review']['review_notes']}")
    print(f"✓ 最终边界: {len(result['final_boundaries'])} 个")
    print(f"✓ 场景标签: {result['scene_tags']}")
    print(f"✓ 整体置信度: {result['overall_confidence']}")


async def test_agent3_refactor_associations():
    """测试 Agent3：多视角关联重构（可选）"""
    print("\n=== 测试 7: Agent3 多视角关联重构 ===")
    
    # 创建 LLM 客户端
    llm_client = get_llm_client()
    
    # 创建 Section Agent（传递 config 参数）
    section_agent = SectionAgent(
        llm_client=llm_client,
        config={}
    )
    
    # 测试数据
    section_summaries = [
        {"section_id": "1", "title": "软件部项目进度", "summary": "讨论软件部项目进度"},
        {"section_id": "2", "title": "知识库项目", "summary": "讨论知识库项目"}
    ]
    
    existing_entries = [
        {"entry_id": "entry1", "title": "软件部项目", "content": "软件部项目相关内容"}
    ]
    
    # 执行重构
    result = await section_agent.refactor_associations(section_summaries, existing_entries)
    
    # 验证结果
    assert result["status"] == "not_implemented", "Agent3 尚未实现"
    print(f"✓ Agent3 状态: {result['status']}")
    print(f"✓ 消息: {result['message']}")


async def main():
    """主函数"""
    print("=" * 60)
    print("Section Agent 测试开始")
    print("=" * 60)
    
    try:
        # 测试 1: 显式结束语检测
        await test_explicit_end_detection()
        
        # 测试 2: 基于规则的分析
        await test_rule_based_analysis()
        
        # 测试 3: 基于 LLM 的分析
        await test_llm_based_analysis()
        
        # 测试 4: Agent2 宏观复核 + 话题标签
        await test_review_and_tag_sections()
        
        # 测试 5: 基于规则的复核
        await test_rule_based_review()
        
        # 测试 6: 协同工作流
        await test_collaborative_workflow()
        
        # 测试 7: Agent3 多视角关联重构
        await test_agent3_refactor_associations()
        
        print("\n" + "=" * 60)
        print("✓ 所有测试通过！")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
