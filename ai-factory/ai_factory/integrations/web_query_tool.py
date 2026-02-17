"""Web 查询工具标准封装模块。

提供统一的 Web 查询接口和配置管理。

主要功能:
1. Web 查询标准化封装
2. 搜索配置管理（Google Search API 等）
3. 查询结果验证和过滤
4. 错误处理和重试机制
"""

from __future__ import annotations

import os
import json
import logging
from typing import Optional, List, Dict, Any, Callable
from dataclasses import dataclass, field
from enum import Enum

from ai_factory.web.evidence_adapter import web_results_to_evidences
from ai_factory.agents.query_types import Evidence
from ai_factory.agents.query_intent_agent import build_query_intent
from ai_factory.agents.query_executors import WebSearchExecutor
from ai_factory.agents.answer_synthesis_agent import synthesize_answer_from_evidences

# 设置日志
logger = logging.getLogger(__name__)


class QueryMode(Enum):
    """查询模式枚举"""
    WEB = "web"
    RAG = "rag"
    HYBRID = "hybrid"


@dataclass
class WebQueryConfig:
    """Web 查询配置类"""
    # API 配置
    google_search_api_key: Optional[str] = None
    google_search_engine_id: Optional[str] = None

    # 搜索参数
    max_results: int = 5
    top_k: Optional[int] = None
    query_timeout: int = 30

    # 结果过滤
    enable_result_filter: bool = True
    result_filters: List[Callable[[Dict[str, Any]], bool]] = field(default_factory=list)

    # 代理配置
    proxy_enabled: bool = True

    # 其他
    enable_guard: bool = True

    def __post_init__(self):
        """初始化后设置环境变量"""
        self.google_search_api_key = (
            self.google_search_api_key
            or os.getenv("GOOGLE_SEARCH_API_KEY")
        )
        self.google_search_engine_id = (
            self.google_search_engine_id
            or os.getenv("GOOGLE_SEARCH_ENGINE_ID")
        )


class WebQueryTool:
    """Web 查询工具标准封装类"""

    def __init__(self, config: Optional[WebQueryConfig] = None):
        """初始化 Web 查询工具

        Args:
            config: 查询配置对象，如果为 None 则使用默认配置
        """
        self.config = config or WebQueryConfig()
        self.executor = WebSearchExecutor()
        self._check_config()

    def _check_config(self):
        """检查配置是否完整"""
        if not self.config.google_search_api_key:
            logger.warning("Google Search API key not configured")
        if not self.config.google_search_engine_id:
            logger.warning("Google Search Engine ID not configured")

    def _apply_result_filters(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """应用结果过滤规则

        Args:
            results: 原始搜索结果

        Returns:
            过滤后的结果
        """
        if not self.config.enable_result_filter:
            return results

        filtered = []
        for result in results:
            if self._should_include_result(result):
                filtered.append(result)

        logger.info(f"Result filter applied: {len(results)} -> {len(filtered)}")
        return filtered

    def _should_include_result(self, result: Dict[str, Any]) -> bool:
        """判断结果是否应该被包含

        Args:
            result: 搜索结果

        Returns:
            bool: 是否应该包含
        """
        # 基础过滤：排除空结果
        if not result:
            return False

        # 简单的 URL 验证
        url = result.get("source_meta", {}).get("url") or result.get("url")
        if not url:
            return False

        # 可选：添加自定义过滤规则
        for filter_func in self.config.result_filters:
            try:
                if not filter_func(result):
                    return False
            except Exception as e:
                logger.warning(f"Filter function failed: {e}")
                continue

        return True

    def _build_context(self, user_id: Optional[str] = None,
                      project_code: Optional[str] = None,
                      options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """构建查询上下文

        Args:
            user_id: 用户 ID
            project_code: 项目代码
            options: 扩展选项

        Returns:
            查询上下文字典
        """
        context = {}

        if user_id:
            context["user_id"] = user_id

        if project_code:
            context["project_code"] = project_code

        if options:
            context["options"] = options

        return context

    def _convert_to_evidence_list(
        self,
        raw_results: List[Dict[str, Any]]
    ) -> List[Evidence]:
        """将原始结果转换为 Evidence 列表

        Args:
            raw_results: 原始搜索结果

        Returns:
            Evidence 列表
        """
        evidences = web_results_to_evidences(raw_results)
        logger.info(f"Converted {len(raw_results)} results to {len(evidences)} evidences")
        return evidences

    def _synthesize_answer(
        self,
        question_text: str,
        intent,
        evidences: List[Evidence]
    ) -> Dict[str, Any]:
        """基于证据合成回答

        Args:
            question_text: 用户问题
            intent: 查询意图
            evidences: 证据列表

        Returns:
            合成后的回答结果
        """
        answer_with_sources = synthesize_answer_from_evidences(
            question_text=question_text,
            intent=intent,
            evidences=evidences,
        )

        # 转换为对外接口格式
        def _evidence_to_dict(ev: Evidence) -> Dict[str, Any]:
            return {
                "kind": ev.kind,
                "id": ev.id,
                "title": ev.title,
                "snippet": ev.snippet,
                "source_meta": dict(ev.source_meta or {}),
            }

        return {
            "question": question_text,
            "answer": answer_with_sources.answer,
            "sources": [_evidence_to_dict(ev) for ev in answer_with_sources.sources],
            "_intent": {
                "intent_type": intent.intent_type,
                "mode": intent.mode,
                "need_rag": intent.need_rag,
                "need_web": intent.need_web,
                "filters": intent.filters,
                "answer_style": intent.answer_style,
                "intent_analysis": getattr(intent, "intent_analysis", None),
                "sub_queries": getattr(intent, "sub_queries", []),
            },
            "_structure": answer_with_sources.structure,
        }

    def query(
        self,
        question_text: str,
        user_id: Optional[str] = None,
        project_code: Optional[str] = None,
        top_k: Optional[int] = None,
        options: Optional[Dict[str, Any]] = None,
        mode: str = QueryMode.WEB.value,
    ) -> Dict[str, Any]:
        """执行 Web 查询

        Args:
            question_text: 用户问题
            user_id: 用户 ID
            project_code: 项目代码
            top_k: 结果条数
            options: 扩展选项
            mode: 查询模式

        Returns:
            查询结果字典

        Raises:
            ValueError: 当 question_text 为空时
            RuntimeError: 当查询执行失败时
        """
        if not question_text or not question_text.strip():
            raise ValueError("question_text cannot be empty")

        # 使用传入的 top_k 或配置的 top_k
        resolved_top_k = top_k or self.config.top_k

        logger.info(f"Executing web query: {question_text[:50]}...")
        logger.info(f"Mode: {mode.value}, Top-K: {resolved_top_k}")

        try:
            # Node #1: 构造查询意图
            context = self._build_context(user_id, project_code, options)

            intent = build_query_intent(
                question_text,
                mode=mode.value,
                context=context
            )

            if getattr(intent, "is_question", None) is False:
                return {
                    "question": question_text,
                    "answer": "当前内容更像是说明或记录，而不是一个明确的问题。",
                    "sources": [],
                    "_intent": {
                        "intent_type": intent.intent_type,
                        "mode": intent.mode,
                        "need_rag": intent.need_rag,
                        "need_web": intent.need_web,
                        "filters": intent.filters,
                        "intent_analysis": getattr(intent, "intent_analysis", None),
                        "sub_queries": getattr(intent, "sub_queries", []),
                    },
                    "_structure": None,
                }

            # Node #2: 执行 Web 搜索
            executor = WebSearchExecutor()
            raw_results = executor.execute(intent)
            logger.info(f"WebSearchExecutor returned {len(raw_results)} results")

            # 应用过滤
            filtered_results = self._apply_result_filters(raw_results)

            # Node #3: 合成回答
            evidences = self._convert_to_evidence_list(filtered_results)
            result = self._synthesize_answer(question_text, intent, evidences)

            logger.info(f"Query completed. Sources: {len(result['sources'])}")

            return result

        except Exception as e:
            logger.error(f"Query failed: {e}")
            raise RuntimeError(f"Web query failed: {e}")

    def query_with_guard(
        self,
        question_text: str,
        **kwargs
    ) -> Dict[str, Any]:
        """执行带保护的查询（包含简单的启发式检查）

        Args:
            question_text: 用户问题
            **kwargs: 其他参数传递给 query()

        Returns:
            查询结果
        """
        if not question_text or not question_text.strip():
            return {
                "question": question_text,
                "answer": "问题不能为空",
                "sources": [],
                "_guard": {
                    "ok": False,
                    "reason": "empty_question",
                    "message": "问题不能为空",
                    "original_input": question_text,
                },
            }

        # 简单的启发式检查
        question_lower = question_text.strip().lower()

        # 检查是否包含问题关键词
        question_keywords = ["如何", "怎么", "为什么", "是什么", "查", "找", "搜索", "search"]
        has_question_keyword = any(kw in question_lower for kw in question_keywords)

        if not has_question_keyword:
            return {
                "question": question_text,
                "answer": "看起来不像是问题，而是记录或说明。请改写为提问形式。",
                "sources": [],
                "_guard": {
                    "ok": False,
                    "reason": "not_a_question",
                    "message": "看起来不像是问题，而是记录或说明。请改写为提问形式。",
                    "original_input": question_text,
                },
            }

        return self.query(question_text, **kwargs)


# 全局实例（单例模式）
_global_tool: Optional[WebQueryTool] = None


def get_web_query_tool(config: Optional[WebQueryConfig] = None) -> WebQueryTool:
    """获取全局 Web 查询工具实例

    Args:
        config: 可选的配置，如果提供则使用新配置

    Returns:
        WebQueryTool 实例
    """
    global _global_tool

    if _global_tool is None:
        _global_tool = WebQueryTool(config)
    elif config is not None:
        # 如果提供了配置则创建新实例
        _global_tool = WebQueryTool(config)

    return _global_tool


def reset_web_query_tool():
    """重置全局实例（用于测试）"""
    global _global_tool
    _global_tool = None
