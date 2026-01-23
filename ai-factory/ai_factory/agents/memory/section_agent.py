"""
Section 语义切分 Agent（Section Agent）
负责多 Agent 协同的语义切分策略

根据设计文档 3.4 节，实现三个协同 Agent：
1. Agent1：局部 Section 识别 Agent
2. Agent2：宏观复核 + 话题标签 Agent
3. Agent3（可选）：多视角关联重构 Agent
"""

from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass
from enum import Enum
from datetime import datetime
import json


class SectionDecision(str, Enum):
    """Section 决策类型"""
    CONTINUE = "continue"           # 继续当前 section
    END_SECTION = "end_section"   # 结束当前 section，开启新 section
    MERGE_PREVIOUS = "merge_previous"  # 与前一个 section 合并


@dataclass
class SectionBoundary:
    """Section 边界建议"""
    message_index: int              # 边界消息索引
    decision: SectionDecision     # 决策类型
    reason: str                   # 决策理由
    confidence: float              # 置信度（0.0-1.0）
    suggested_title: Optional[str] = None  # 建议的 section 标题


@dataclass
class SectionProposal:
    """Section 提议（Agent1 输出）"""
    boundaries: List[SectionBoundary]  # 边界建议列表
    overall_summary: str          # 整体总结
    confidence: float              # 整体置信度


@dataclass
class SectionReview:
    """Section 复核结果（Agent2 输出）"""
    approved_boundaries: List[SectionBoundary]  # 批准的边界
    scene_tags: Dict[str, List[str]]    # 场景标签
    related_entries: List[str]        # 相关的 entries ID
    review_notes: str              # 复核说明


class SectionAgent:
    """Section 语义切分 Agent"""
    
    def __init__(
        self,
        llm_client,
        vector_client=None,
        config: Optional[Dict[str, Any]] = None
    ):
        """
        初始化 Section Agent
        
        Args:
            llm_client: LLM 客户端
            vector_client: 向量客户端（可选）
            config: 配置参数
        """
        self.llm_client = llm_client
        self.vector_client = vector_client
        self.config = config or {}
        
        # 配置参数
        self.semantic_threshold = config.get("semantic_threshold", 0.7)
        self.min_section_length = config.get("min_section_length", 3)
        self.max_section_length = config.get("max_section_length", 20)
        self.enable_llm_judgment = config.get("enable_llm_judgment", True)
        
        # 显式结束语关键词
        self.explicit_end_keywords = config.get("explicit_end_keywords", [
            "先到这儿",
            "换个话题",
            "换个方向",
            "新话题",
            "开始新的",
            "结束这个话题",
            "这个话题就到这里"
        ])
    
    # ==================== Agent1：局部 Section 识别 ====================
    
    async def analyze_local_context(
        self,
        messages: List[Dict[str, Any]],
        current_section_id: Optional[str] = None
    ) -> SectionProposal:
        """
        Agent1：局部 Section 识别
        
        基于局部语境，判断当前是否应结束当前 section 或开启新 section
        
        Args:
            messages: 消息列表
            current_section_id: 当前 section ID（如果有）
        
        Returns:
            SectionProposal: Section 提议
        """
        if not messages:
            return SectionProposal(
                boundaries=[],
                overall_summary="没有消息可分析",
                confidence=0.0
            )
        
        # 1. 检查显式结束语
        explicit_end = self._check_explicit_end(messages)
        if explicit_end:
            boundary = SectionBoundary(
                message_index=explicit_end["index"],
                decision=SectionDecision.END_SECTION,
                reason=f"检测到显式结束语：{explicit_end['keyword']}",
                confidence=0.9,
                suggested_title=explicit_end.get("suggested_title")
            )
            return SectionProposal(
                boundaries=[boundary],
                overall_summary=f"检测到显式结束语，建议结束当前 section",
                confidence=0.9
            )
        
        # 2. 基于语义连续性判断（使用 LLM）
        if self.enable_llm_judgment:
            llm_proposal = await self._analyze_with_llm(messages, current_section_id)
            return llm_proposal
        
        # 3. 基于规则判断（降级方案）
        return self._analyze_with_rules(messages, current_section_id)
    
    def _check_explicit_end(
        self,
        messages: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """
        检查显式结束语
        
        Args:
            messages: 消息列表
        
        Returns:
            Dict: 检测结果，包含 index, keyword, suggested_title
        """
        for i, msg in enumerate(messages):
            content = msg.get("content", "").lower()
            
            for keyword in self.explicit_end_keywords:
                if keyword in content:
                    # 尝试提取建议的标题
                    suggested_title = self._extract_suggested_title(content, keyword)
                    
                    return {
                        "index": i,
                        "keyword": keyword,
                        "suggested_title": suggested_title
                    }
        
        return None
    
    def _extract_suggested_title(self, content: str, keyword: str) -> Optional[str]:
        """
        从消息中提取建议的标题
        
        Args:
            content: 消息内容
            keyword: 关键词
        
        Returns:
            str: 建议的标题
        """
        # 简化实现：提取关键词后面的文本
        parts = content.split(keyword)
        if len(parts) > 1:
            title_part = parts[1].strip()
            if title_part:
                # 移除标点符号
                title_part = title_part.rstrip("。！？，")
                if title_part:
                    return title_part[:50]  # 限制长度
        return None
    
    async def _analyze_with_llm(
        self,
        messages: List[Dict[str, Any]],
        current_section_id: Optional[str] = None
    ) -> SectionProposal:
        """
        使用 LLM 分析语义连续性
        
        Args:
            messages: 消息列表
            current_section_id: 当前 section ID
        
        Returns:
            SectionProposal: Section 提议
        """
        # 构建提示词
        messages_text = "\n".join([
            f"[{msg.get('role', 'user')}]: {msg.get('content', '')}"
            for msg in messages
        ])
        
        prompt = f"""你是一个对话分析专家，负责判断对话是否应该切分为不同的 section（话题片段）。

当前对话内容：
{messages_text}

请分析这段对话，判断是否应该：
1. 继续当前 section（所有消息属于同一个话题）
2. 结束当前 section，开启新 section（检测到话题转换）

请以 JSON 格式返回结果：
{{
    "decision": "continue" 或 "end_section",
    "reason": "决策理由",
    "confidence": 0.0-1.0 的置信度,
    "suggested_title": "建议的 section 标题（如果需要）"
}}

只返回 JSON，不要有其他内容。"""
        
        try:
            # 调用 LLM
            response = await self.llm_client.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3
            )
            
            # 解析响应
            result = json.loads(response)
            
            decision = SectionDecision.CONTINUE if result.get("decision") == "continue" else SectionDecision.END_SECTION
            
            boundary = SectionBoundary(
                message_index=len(messages) - 1,
                decision=decision,
                reason=result.get("reason", ""),
                confidence=result.get("confidence", 0.7),
                suggested_title=result.get("suggested_title")
            )
            
            return SectionProposal(
                boundaries=[boundary],
                overall_summary=f"LLM 分析结果：{result.get('reason', '')}",
                confidence=result.get("confidence", 0.7)
            )
            
        except Exception as e:
            print(f"[SectionAgent] LLM 分析失败: {e}")
            # 降级到规则判断
            return self._analyze_with_rules(messages, current_section_id)
    
    def _analyze_with_rules(
        self,
        messages: List[Dict[str, Any]],
        current_section_id: Optional[str] = None
    ) -> SectionProposal:
        """
        基于规则分析语义连续性
        
        Args:
            messages: 消息列表
            current_section_id: 当前 section ID
        
        Returns:
            SectionProposal: Section 提议
        """
        if len(messages) < self.min_section_length:
            # 消息太少，继续当前 section
            return SectionProposal(
                boundaries=[],
                overall_summary=f"消息数量不足（{len(messages)} < {self.min_section_length}），继续当前 section",
                confidence=0.8
            )
        
        if len(messages) >= self.max_section_length:
            # 消息太多，建议结束当前 section
            return SectionProposal(
                boundaries=[
                    SectionBoundary(
                        message_index=len(messages) - 1,
                        decision=SectionDecision.END_SECTION,
                        reason=f"消息数量达到上限（{len(messages)} >= {self.max_section_length}）",
                        confidence=0.7,
                        suggested_title=self._extract_title_from_messages(messages)
                    )
                ],
                overall_summary=f"消息数量达到上限，建议结束当前 section",
                confidence=0.7
            )
        
        # 基于消息长度和关键词判断
        return SectionProposal(
            boundaries=[],
            overall_summary="基于规则判断：继续当前 section",
            confidence=0.6
        )
    
    def _extract_title_from_messages(self, messages: List[Dict[str, Any]]) -> str:
        """
        从消息中提取标题
        
        Args:
            messages: 消息列表
        
        Returns:
            str: 提取的标题
        """
        if not messages:
            return "Untitled Section"
        
        # 使用第一条用户消息的前 50 个字符
        for msg in messages:
            if msg.get("role") == "user":
                content = msg.get("content", "")
                title = content[:50].replace("\n", " ").strip()
                if not title:
                    title = "Untitled Section"
                return title
        
        return "Untitled Section"
    
    # ==================== Agent2：宏观复核 + 话题标签 ====================
    
    async def review_and_tag_sections(
        self,
        messages: List[Dict[str, Any]],
        proposal: SectionProposal,
        existing_entries: List[Dict[str, Any]] = None
    ) -> SectionReview:
        """
        Agent2：宏观复核 + 话题标签
        
        Args:
            messages: 消息列表
            proposal: Agent1 的提案
            existing_entries: 现有的 entries（用于关联分析）
        
        Returns:
            SectionReview: Section 复核结果
        """
        if not proposal.boundaries:
            return SectionReview(
                approved_boundaries=[],
                scene_tags={},
                related_entries=[],
                review_notes="没有边界建议，无需复核"
            )
        
        # 使用 LLM 进行复核和标签生成
        if self.enable_llm_judgment:
            llm_review = await self._review_with_llm(messages, proposal, existing_entries)
            return llm_review
        
        # 降级到规则复核
        return self._review_with_rules(proposal)
    
    async def _review_with_llm(
        self,
        messages: List[Dict[str, Any]],
        proposal: SectionProposal,
        existing_entries: List[Dict[str, Any]]
    ) -> SectionReview:
        """
        使用 LLM 进行复核和标签生成
        
        Args:
            messages: 消息列表
            proposal: Agent1 的提案
            existing_entries: 现有的 entries
        
        Returns:
            SectionReview: Section 复核结果
        """
        # 构建提示词
        messages_text = "\n".join([
            f"[{msg.get('role', 'user')}]: {msg.get('content', '')}"
            for msg in messages
        ])
        
        proposal_summary = proposal.overall_summary
        if proposal.boundaries:
            boundary_info = proposal.boundaries[0]
            proposal_summary += f"\n- 边界决策: {boundary_info.decision.value}\n- 理由: {boundary_info.reason}\n- 置信度: {boundary_info.confidence}"
            if boundary_info.suggested_title:
                proposal_summary += f"\n- 建议标题: {boundary_info.suggested_title}"
        
        prompt = f"""你是一个对话复核专家，负责审核 section 切分建议并生成场景标签。

对话内容：
{messages_text}

Agent1 的切分建议：
{proposal_summary}

请执行以下任务：
1. 审核切分建议是否合理
2. 如果不合理，提出修正建议
3. 为这个 section 生成场景标签（scene_tags），包括：
   - department: 部门（如：总部、软件、软件部、现场、知识库、内务）
   - execution: 执行类型（如：项目、任务、议题、笔记、其他）
   - planning: 规划类型（如：项目、计划、战略、目标、其他）
   - status: 状态（如：待开始、进行中）
   - work: 工作状态（如：in_work）

4. 识别相关的 entries（如果提供了现有 entries）

请以 JSON 格式返回结果：
{{
    "approved_boundaries": [
        {{
            "message_index": 0,
            "decision": "continue" 或 "end_section",
            "reason": "理由",
            "confidence": 0.0-1.0,
            "suggested_title": "标题"
        }}
    ],
    "scene_tags": {{
        "department": ["软件"],
        "execution": ["项目"],
        "planning": ["项目"],
        "status": ["进行中"],
        "work": ["in_work"]
    }},
    "related_entries": ["entry_id1", "entry_id2"],
    "review_notes": "复核说明"
}}

只返回 JSON，不要有其他内容。"""
        
        try:
            # 调用 LLM
            response = await self.llm_client.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3
            )
            
            # 解析响应
            result = json.loads(response)
            
            # 构建边界列表
            approved_boundaries = []
            for b in result.get("approved_boundaries", []):
                decision = SectionDecision.CONTINUE if b.get("decision") == "continue" else SectionDecision.END_SECTION
                boundary = SectionBoundary(
                    message_index=b.get("message_index", 0),
                    decision=decision,
                    reason=b.get("reason", ""),
                    confidence=b.get("confidence", 0.7),
                    suggested_title=b.get("suggested_title")
                )
                approved_boundaries.append(boundary)
            
            return SectionReview(
                approved_boundaries=approved_boundaries,
                scene_tags=result.get("scene_tags", {}),
                related_entries=result.get("related_entries", []),
                review_notes=result.get("review_notes", "")
            )
            
        except Exception as e:
            print(f"[SectionAgent] LLM 复核失败: {e}")
            # 降级到规则复核
            return self._review_with_rules(proposal)
    
    def _review_with_rules(self, proposal: SectionProposal) -> SectionReview:
        """
        基于规则进行复核
        
        Args:
            proposal: Agent1 的提案
        
        Returns:
            SectionReview: Section 复核结果
        """
        if not proposal.boundaries:
            return SectionReview(
                approved_boundaries=[],
                scene_tags={},
                related_entries=[],
                review_notes="没有边界建议，无需复核"
            )
        
        # 批准所有边界
        approved_boundaries = proposal.boundaries.copy()
        
        # 生成默认场景标签
        scene_tags = {
            "execution": ["笔记"],
            "planning": ["项目"]
        }
        
        return SectionReview(
            approved_boundaries=approved_boundaries,
            scene_tags=scene_tags,
            related_entries=[],
            review_notes="基于规则复核：批准所有边界建议"
        )
    
    # ==================== Agent3：多视角关联重构（可选） ====================
    
    async def refactor_associations(
        self,
        section_summaries: List[Dict[str, Any]],
        existing_entries: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Agent3：多视角关联重构（可选）
        
        从不同视角出发，调整话题标签和关联关系
        
        Args:
            section_summaries: Section 总结列表
            existing_entries: 现有的 entries
        
        Returns:
            Dict: 重构结果
        """
        # 这是一个高级功能，暂时返回空结果
        return {
            "status": "not_implemented",
            "message": "Agent3 尚未实现"
        }
    
    # ==================== 协同工作流 ====================
    
    async def analyze_session(
        self,
        messages: List[Dict[str, Any]],
        current_section_id: Optional[str] = None,
        existing_entries: List[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        协同分析会话，生成 section 切分建议
        
        Args:
            messages: 消息列表
            current_section_id: 当前 section ID
            existing_entries: 现有的 entries
        
        Returns:
            Dict: 分析结果，包含：
                - proposal: Agent1 的提案
                - review: Agent2 的复核
                - final_boundaries: 最终边界
                - scene_tags: 场景标签
                - related_entries: 相关 entries
        """
        # Agent1：局部分析
        proposal = await self.analyze_local_context(messages, current_section_id)
        
        # Agent2：宏观复核 + 话题标签
        review = await self.review_and_tag_sections(messages, proposal, existing_entries)
        
        # 最终边界
        final_boundaries = review.approved_boundaries if review.approved_boundaries else proposal.boundaries
        
        return {
            "proposal": {
                "boundaries": [
                    {
                        "message_index": b.message_index,
                        "decision": b.decision.value,
                        "reason": b.reason,
                        "confidence": b.confidence,
                        "suggested_title": b.suggested_title
                    }
                    for b in proposal.boundaries
                ],
                "overall_summary": proposal.overall_summary,
                "confidence": proposal.confidence
            },
            "review": {
                "approved_boundaries": [
                    {
                        "message_index": b.message_index,
                        "decision": b.decision.value,
                        "reason": b.reason,
                        "confidence": b.confidence,
                        "suggested_title": b.suggested_title
                    }
                    for b in review.approved_boundaries
                ],
                "scene_tags": review.scene_tags,
                "related_entries": review.related_entries,
                "review_notes": review.review_notes
            },
            "final_boundaries": [
                {
                    "message_index": b.message_index,
                    "decision": b.decision.value,
                    "reason": b.reason,
                    "confidence": b.confidence,
                    "suggested_title": b.suggested_title
                }
                for b in final_boundaries
            ],
            "scene_tags": review.scene_tags,
            "related_entries": review.related_entries,
            "overall_confidence": (proposal.confidence + 0.5) / 1.5  # 简单平均
        }
