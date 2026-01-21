"""MemoryService facade implementation.

High-level interface used by agents to get context for a turn and to
explicitly store memories. Composes SessionService, SectionService,
EntryService and Memory0Service.
Follows `Agent记忆系统详细设计与施工文档.md`.
"""

from __future__ import annotations

from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from datetime import datetime
import re

from .session_service import SessionService
from .section_service import SectionService
from .entry_service import EntryService
from .memory0_service import Memory0Service, MemoryCandidate
from .llm_client import get_llm_client

# 尝试导入 tiktoken，如果失败则使用简化版的 token 计算器
try:
    import tiktoken
    HAS_TIKTOKEN = True
except ImportError:
    HAS_TIKTOKEN = False


@dataclass
class ContextSnippet:
    """上下文片段"""
    role: str
    content: str
    weight: float = 1.0
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class ContextForTurn:
    """单轮对话的上下文"""
    system_prompt: str
    history_messages: List[Dict[str, Any]]
    rag_snippets: List[Dict[str, Any]]
    metadata: Dict[str, Any]


class TokenCalculator:
    """Token 计算器"""

    def __init__(self, model: str = "gpt-3.5-turbo"):
        """初始化 Token 计算器

        Args:
            model: 模型名称，用于选择正确的 tokenizer
        """
        self.model = model
        self._tokenizer = None
        self._init_tokenizer()

    def _init_tokenizer(self):
        """初始化 tokenizer"""
        if HAS_TIKTOKEN:
            try:
                # 使用 cl100k_base 编码器（适用于 GPT-3.5, GPT-4 等）
                self._tokenizer = tiktoken.get_encoding("cl100k_base")
            except Exception as e:
                print(f"[TokenCalculator] Warning: Failed to initialize tiktoken: {e}")
                self._tokenizer = None
        else:
            self._tokenizer = None

    def count_tokens(self, text: str) -> int:
        """计算文本的 token 数量

        Args:
            text: 输入文本

        Returns:
            int: token 数量
        """
        if not text:
            return 0

        if self._tokenizer is not None:
            try:
                tokens = self._tokenizer.encode(text)
                return len(tokens)
            except Exception as e:
                print(f"[TokenCalculator] Warning: Failed to count tokens with tiktoken: {e}")

        # 降级方案：按字符数粗略估算（中文 1 字符 ≈ 0.7 token，英文 1 词 ≈ 1.3 token）
        # 使用简化公式：token 数 ≈ 字符数 / 3
        return len(text) // 3

    def count_messages_tokens(self, messages: List[Dict[str, str]]) -> int:
        """计算消息列表的 token 数量（考虑消息格式开销）

        Args:
            messages: 消息列表

        Returns:
            int: token 数量
        """
        total_tokens = 0
        for msg in messages:
            # 消息格式开销（每个消息约 4 tokens）
            total_tokens += 4
            # 角色和内容的 token 数
            total_tokens += self.count_tokens(msg.get("role", ""))
            total_tokens += self.count_tokens(msg.get("content", ""))
        # 整体格式开销（约 3 tokens）
        total_tokens += 3
        return total_tokens


class QueryExtractor:
    """智能查询提取器"""

    def __init__(self):
        """初始化查询提取器"""
        # 停用词列表（需要过滤的词）
        self._stop_words = {
            "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一",
            "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着", "没有",
            "看", "好", "自己", "这", "那", "这个", "那个", "什么", "怎么", "为什么"
        }

        # 疑问词列表（优先提取）
        self._question_words = {
            "什么", "怎么", "如何", "为什么", "哪里", "哪个", "多少", "何时", "能否",
            "是否", "怎么样", "怎么样", "哪些", "谁", "怎样", "如何", "干嘛"
        }

        # 关键词提取权重
        self._keyword_weights = {
            "动词": 2.0,
            "名词": 1.5,
            "疑问词": 2.5,
            "数字": 1.2,
            "专业术语": 1.8
        }

    def extract_from_messages(
        self,
        messages: List[Any],
        max_length: int = 200
    ) -> str:
        """从消息列表中提取查询文本

        Args:
            messages: 消息列表
            max_length: 最大长度（字符数）

        Returns:
            str: 查询文本
        """
        # 1. 提取最近的消息片段
        recent_messages = self._get_recent_messages(messages, limit=5)

        # 2. 从消息中提取关键词
        keywords = []
        for msg in reversed(recent_messages):  # 从最新的消息开始
            if hasattr(msg, 'role') and msg.role == 'user':
                msg_keywords = self._extract_keywords(msg.content)
                keywords.extend(msg_keywords)
                # 如果已经提取到足够的关键词，就停止
                if len(keywords) >= 10:
                    break

        # 3. 过滤和排序关键词
        filtered_keywords = self._filter_and_rank_keywords(keywords)

        # 4. 组合成查询文本
        query = " ".join(filtered_keywords[:8])  # 最多取 8 个关键词
        query = query[:max_length]  # 截断到最大长度

        return query

    def _get_recent_messages(self, messages: List[Any], limit: int = 5) -> List[Any]:
        """获取最近的消息

        Args:
            messages: 消息列表
            limit: 数量限制

        Returns:
            List[Any]: 最近的消息
        """
        return messages[-limit:] if messages else []

    def _extract_keywords(self, text: str) -> List[str]:
        """从文本中提取关键词

        Args:
            text: 输入文本

        Returns:
            List[str]: 关键词列表
        """
        if not text or not text.strip():
            return []

        keywords = []

        # 1. 提取疑问词
        question_matches = []
        for qword in self._question_words:
            if qword in text:
                question_matches.append(qword)
        keywords.extend(question_matches)

        # 2. 提取数字（如 100, 3.5, 2024）
        number_pattern = r'\b\d+\.?\d*\b'
        numbers = re.findall(number_pattern, text)
        keywords.extend(numbers)

        # 3. 提取专业术语（连续 2-4 个中文字符，包含特定的专业词汇）
        # 提取中文词汇（2-4 个字符）
        chinese_pattern = r'[\u4e00-\u9fa5]{2,4}'
        chinese_words = re.findall(chinese_pattern, text)
        keywords.extend(chinese_words)

        # 4. 提取英文单词（2 个字符以上）
        english_pattern = r'\b[a-zA-Z]{2,}\b'
        english_words = re.findall(english_pattern, text)
        keywords.extend(english_words)

        # 5. 去除停用词
        filtered = [kw for kw in keywords if kw not in self._stop_words and len(kw) > 1]

        return filtered

    def _filter_and_rank_keywords(self, keywords: List[str]) -> List[str]:
        """过滤和排序关键词

        Args:
            keywords: 关键词列表

        Returns:
            List[str]: 排序后的关键词
        """
        # 1. 去重
        unique_keywords = list(dict.fromkeys(keywords))

        # 2. 计算权重
        keyword_weights = []
        for kw in unique_keywords:
            weight = 1.0

            # 疑问词权重高
            if kw in self._question_words:
                weight *= self._keyword_weights["疑问词"]

            # 数字权重较高
            if re.match(r'^\d+\.?\d*$', kw):
                weight *= self._keyword_weights["数字"]

            # 英文单词权重中等
            if re.match(r'^[a-zA-Z]+$', kw):
                weight *= self._keyword_weights["名词"]

            # 中文字数越多，权重越高
            if re.match(r'^[\u4e00-\u9fa5]+$', kw):
                length_weight = min(len(kw) / 2.0, 2.0)
                weight *= length_weight

            keyword_weights.append((kw, weight))

        # 3. 按权重排序
        keyword_weights.sort(key=lambda x: x[1], reverse=True)

        # 4. 返回关键词
        return [kw for kw, _ in keyword_weights]


class MemoryService:
    """Facade that agents call to interact with the memory stack."""

    # 默认配置
    DEFAULT_MAX_TOKENS = 2048
    DEFAULT_RAG_TOP_K = 5
    DEFAULT_RECENT_MESSAGES = 10

    def __init__(
        self,
        session_service: SessionService,
        section_service: SectionService,
        entry_service: EntryService,
        memory0_service: Memory0Service,
        model: str = "gpt-3.5-turbo"
    ) -> None:
        """初始化 MemoryService。

        Args:
            session_service: SessionService 实例
            section_service: SectionService 实例
            entry_service: EntryService 实例
            memory0_service: Memory0Service 实例
            model: 模型名称，用于 token 计算
        """
        self.session_service = session_service
        self.section_service = section_service
        self.entry_service = entry_service
        self.memory0_service = memory0_service
        self.llm_client = get_llm_client()

        # 初始化 TokenCalculator 和 QueryExtractor
        self.token_calculator = TokenCalculator(model=model)
        self.query_extractor = QueryExtractor()

    def get_context_for_turn(
        self,
        session_id: str,
        agent_id: str,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        rag_top_k: int = DEFAULT_RAG_TOP_K,
        recent_messages_limit: int = DEFAULT_RECENT_MESSAGES
    ) -> ContextForTurn:
        """为当前轮次组装上下文。

        组装内容：
        1. 短期记忆：从 SessionService 取最近消息
        2. 长期记忆：从 EntryService 取相关条目（按 agent_id/scene_tags 过滤）
        3. （可选）外部 RAG（世界知识）
        4. 组合成上下文包，按 token 预算截断

        Args:
            session_id: 会话ID
            agent_id: Agent ID
            max_tokens: 最大token数
            rag_top_k: RAG检索返回数量
            recent_messages_limit: 最近消息数量

        Returns:
            ContextForTurn: 上下文对象
        """
        # 1. 获取静态提示词（简化版）
        system_prompt = self._get_static_prompt(agent_id)

        # 2. 获取短期记忆（最近消息）
        recent_messages = self.session_service.get_recent_messages(
            session_id=session_id,
            limit=recent_messages_limit
        )
        # 转换为字典列表
        history_messages = [
            {
                "message_id": msg.message_id,
                "role": msg.role,
                "content": msg.content,
                "created_at": msg.created_at.isoformat() if msg.created_at else None
            }
            for msg in recent_messages
        ]

        # 3. 获取长期记忆（从entries大库）
        rag_snippets = []
        if rag_top_k > 0:
            # 使用智能查询提取器
            query_text = self.query_extractor.extract_from_messages(recent_messages)
            if query_text:
                try:
                    # 生成查询embedding
                    query_embedding = self.llm_client.generate_embedding_sync(query_text)
                    # 检索相关条目
                    rag_results = self.entry_service.search_similar(
                        query_embedding=query_embedding,
                        filters={"agent_id": agent_id},
                        top_k=rag_top_k
                    )
                    # 转换为字典列表
                    rag_snippets = [
                        {
                            "entry_id": result.get("entry_id"),
                            "title": result.get("title"),
                            "content": result.get("content"),
                            "similarity": result.get("similarity") if result.get("similarity") is not None else None,
                            "scene_tags": result.get("scene_tags"),
                        }
                        for result in rag_results
                    ]
                except Exception as e:
                    print(f"[MemoryService] Warning: Failed to retrieve RAG snippets: {e}")

        # 4. 计算 token 预算
        # system_prompt 占用 tokens
        system_tokens = self.token_calculator.count_tokens(system_prompt)

        # 5. 按权重和 token 预算截断上下文
        # RAG 片段优先级较高（权重 1.5）
        # 历史消息优先级较低（权重 1.0）
        remaining_tokens = max_tokens - system_tokens

        # 先截断 RAG 片段
        selected_rag_snippets = self._truncate_rag_snippets(rag_snippets, remaining_tokens * 0.4)

        # 再截断历史消息
        rag_tokens = sum(
            self.token_calculator.count_tokens(snippet.get("content", "")) +
            self.token_calculator.count_tokens(snippet.get("title", ""))
            for snippet in selected_rag_snippets
        )
        remaining_tokens -= rag_tokens
        selected_history_messages = self._truncate_history_messages(history_messages, remaining_tokens)

        # 6. 组装上下文
        return ContextForTurn(
            system_prompt=system_prompt,
            history_messages=selected_history_messages,
            rag_snippets=selected_rag_snippets,
            metadata={
                "token_budget": max_tokens,
                "system_tokens": system_tokens,
                "rag_tokens": rag_tokens,
                "history_tokens": self.token_calculator.count_messages_tokens(selected_history_messages),
                "recent_messages_count": len(history_messages),
                "selected_messages_count": len(selected_history_messages),
                "rag_snippets_count": len(rag_snippets),
                "selected_rag_count": len(selected_rag_snippets),
                "generated_at": datetime.now().isoformat()
            }
        )

    def remember_explicitly(
        self,
        agent_id: str,
        user_id: str,
        content: str,
        extra_meta: Optional[Dict[str, Any]] = None
    ) -> str:
        """显式存储一条信息作为长期记忆。

        通过 Memory0Service 进行记忆治理，自动判定 NEW/UPDATE/OVERRIDE/DUPLICATE。

        Args:
            agent_id: Agent ID
            user_id: 用户ID
            content: 要记住的内容
            extra_meta: 额外元数据

        Returns:
            str: entry_id
        """
        # 构造记忆候选
        candidate = MemoryCandidate(
            content=content,
            user_id=user_id,
            agent_id=agent_id,
            scene_tags=extra_meta.get("scene_tags", {}) if extra_meta else {},
            space_type=extra_meta.get("space_type", "note") if extra_meta else "note",
            metadata=extra_meta or {}
        )

        # 调用 Memory0Service 进行记忆治理
        result = self.memory0_service.upsert_memory(candidate)

        return result.entry_id

    def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """添加消息到会话。

        Args:
            session_id: 会话ID
            role: 消息角色（user/assistant/system/tool）
            content: 消息内容
            metadata: 元数据

        Returns:
            str: message_id
        """
        return self.session_service.append_message(
            session_id=session_id,
            role=role,
            content=content,
            metadata=metadata
        )

    def summarize_section(
        self,
        session_id: str,
        agent_id: str = "default",
        trigger_type: str = "mcp_tool",
        manual_section_title: Optional[str] = None
    ) -> Dict[str, Any]:
        """整理section并写入entries大库。

        Args:
            session_id: 会话ID
            agent_id: Agent ID
            trigger_type: 触发类型
            manual_section_title: 手动指定的section标题

        Returns:
            Dict[str, Any]: 整理结果
        """
        summary = self.section_service.summarize_section(
            session_id=session_id,
            agent_id=agent_id,
            trigger_type=trigger_type,
            manual_section_title=manual_section_title
        )

        return {
            "section_id": summary.section_id,
            "entry_id": summary.entry_id,
            "section_version": summary.section_version,
            "scene_tags": summary.scene_tags,
            "agent_id": summary.agent_id,
            "metadata": summary.metadata
        }

    def _get_static_prompt(self, agent_id: str) -> str:
        """获取静态提示词（简化版）。

        Args:
            agent_id: Agent ID

        Returns:
            str: 静态提示词
        """
        # TODO: 实际应从agent配置或数据库中获取
        return f"你是一个有帮助的助手（Agent ID: {agent_id}）。请根据上下文回答问题。"

    def _extract_query_from_messages(
        self,
        messages: List[Any]
    ) -> str:
        """从消息中提取检索查询文本（智能版）。

        使用 QueryExtractor 智能提取关键词和查询文本。

        Args:
            messages: 消息列表

        Returns:
            str: 查询文本
        """
        # 使用智能查询提取器
        return self.query_extractor.extract_from_messages(messages, max_length=200)

    def _truncate_rag_snippets(
        self,
        rag_snippets: List[Dict[str, Any]],
        max_tokens: int
    ) -> List[Dict[str, Any]]:
        """按 token 预算截断 RAG 片段。

        优先保留相似度高的片段，并按 token 预算截断。

        Args:
            rag_snippets: RAG 片段列表
            max_tokens: 最大 token 数

        Returns:
            List[Dict[str, Any]]: 截断后的 RAG 片段列表
        """
        if not rag_snippets:
            return []

        # 按相似度排序
        sorted_snippets = sorted(
            rag_snippets,
            key=lambda x: x.get("similarity", 0) or 0,
            reverse=True
        )

        selected = []
        total_tokens = 0

        for snippet in sorted_snippets:
            # 计算 snippet 的 token 数
            title = snippet.get("title", "")
            content = snippet.get("content", "")
            snippet_tokens = (
                self.token_calculator.count_tokens(title) +
                self.token_calculator.count_tokens(content)
            )

            # 检查是否超过预算
            if total_tokens + snippet_tokens <= max_tokens:
                selected.append(snippet)
                total_tokens += snippet_tokens
            else:
                # 如果片段超过预算，尝试截断内容
                remaining = max_tokens - total_tokens
                if remaining > 50:  # 至少保留 50 tokens
                    # 计算可保留的内容长度
                    max_content_length = int(remaining * 3)  # 估算字符数
                    if len(content) > max_content_length:
                        # 截断内容
                        snippet["content"] = content[:max_content_length] + "..."
                        selected.append(snippet)
                break

        return selected

    def _truncate_history_messages(
        self,
        history_messages: List[Dict[str, Any]],
        max_tokens: int
    ) -> List[Dict[str, Any]]:
        """按 token 预算截断历史消息。

        优先保留最新的消息，并按 token 预算截断。

        Args:
            history_messages: 历史消息列表
            max_tokens: 最大 token 数

        Returns:
            List[Dict[str, Any]]: 截断后的历史消息列表
        """
        if not history_messages:
            return []

        # 历史消息已经是按时间排序的（从旧到新）
        # 我们需要从最新的消息开始保留
        selected = []
        total_tokens = 0

        # 从最新的消息开始（倒序遍历）
        for msg in reversed(history_messages):
            # 计算消息的 token 数
            msg_tokens = self.token_calculator.count_tokens(msg.get("content", ""))

            # 检查是否超过预算
            if total_tokens + msg_tokens <= max_tokens:
                selected.insert(0, msg)  # 插入到开头，保持顺序
                total_tokens += msg_tokens
            else:
                # 如果消息超过预算，尝试截断
                remaining = max_tokens - total_tokens
                if remaining > 50:  # 至少保留 50 tokens
                    max_content_length = int(remaining * 3)  # 估算字符数
                    content = msg.get("content", "")
                    if len(content) > max_content_length:
                        # 截断内容
                        msg_copy = msg.copy()
                        msg_copy["content"] = content[:max_content_length] + "..."
                        selected.insert(0, msg_copy)
                break

        return selected

    def _truncate_to_token_budget(
        self,
        snippets: List[ContextSnippet],
        max_tokens: int
    ) -> List[ContextSnippet]:
        """简化版的token截断（实际应使用tokenizer）。

        Args:
            snippets: 上下文片段列表
            max_tokens: 最大token数

        Returns:
            List[ContextSnippet]: 截断后的片段列表
        """
        selected = []
        total_tokens = 0
        for snippet in snippets:
            # 估算token数（按字符数/4粗略估算）
            est_tokens = len(snippet.content) // 4
            if total_tokens + est_tokens <= max_tokens:
                selected.append(snippet)
                total_tokens += est_tokens
            else:
                break
        return selected
