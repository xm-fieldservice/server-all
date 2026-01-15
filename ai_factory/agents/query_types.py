from __future__ import annotations

"""Common type definitions for query & answer pipelines (RAG / Web / Hybrid).

本模块只定义数据结构，不包含具体模型调用逻辑，
用于在 AI 工厂内部统一意图、检索计划与证据表示，
便于后续将查询 Team 迁移到 AI 工厂内。
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional


QueryMode = Literal["RAG", "WEB", "HYBRID"]
EvidenceKind = Literal["rag", "web"]


@dataclass
class QueryIntent:
    """意图与检索规划结果（Node #1 输出）。"""

    # 原始问题
    question_text: str

    # 三栏/调用方显式指定的模式（RAG / WEB / HYBRID 等）
    mode: QueryMode = "RAG"

    # 简要意图类型标记，例如："task_list" / "summary" / "compare" / "debug" 等
    intent_type: Optional[str] = None

    # 是否倾向/允许使用本地 RAG 检索
    need_rag: bool = True

    # 是否倾向/允许使用联网搜索
    need_web: bool = False

    # 过滤条件（project / tag / time range 等），由意图区分与组合
    filters: Dict[str, Any] = field(default_factory=dict)

    # 期望回答风格：如 "list", "summary", "step_by_step" 等
    answer_style: Optional[str] = None

    # （调试/分析用）1 号节点对本次查询的自然语言意图拆解说明
    intent_analysis: Optional[str] = None

    # （可选）从意图拆解得到的一组具体查询问题，用于后续多步 RAG 规划
    sub_queries: List[str] = field(default_factory=list)

    # （可选）1 号节点对“当前内容是否为提问”的综合判断结果
    # - True: 认为是提问
    # - False: 认为不是提问（更像笔记/陈述等）
    # - None: 未显式判断
    is_question: Optional[bool] = None


@dataclass
class Evidence:
    """统一的证据条目表示，供整理节点（Node #3）消费。

    - kind = "rag": 来自本地 entries / RAG 检索
    - kind = "web": 来自 Web 搜索 / 网页抓取结果
    """

    kind: EvidenceKind

    # 统一的 ID，用于在回答中引用和调试
    id: str

    # 标题：RAG 场景对应 entry.title，Web 场景对应网页标题
    title: Optional[str] = None

    # 供 LLM 直接阅读的文本片段（已去 HTML / 已做摘要）
    snippet: Optional[str] = None

    # 结构化元信息：
    # - RAG: {"entry_id", "created_at", "score", "project_code", "user_id"}
    # - Web: {"url", "site", "published_at", ...}
    source_meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AnswerWithSources:
    """最终回答 + 引用源统一表示（Node #3 输出）。"""

    # 自然语言回答文本（markdown/text）
    answer: str

    # 统一的证据列表，内部可以按 kind=rag/web 区分
    sources: List[Evidence] = field(default_factory=list)

    # 可选：用于 Mindmap / 前端消费的结构化表示（如主题/议题树）。
    structure: Optional[Dict[str, Any]] = None
