from __future__ import annotations

"""Experimental RAG QA API v2 based on the unified 1/2/3-node pipeline.

注意：
- 本模块为实验版本，不影响现有 qa_answer_rag 接口；
- 仅在 AI 工厂内部用于验证 QueryIntent / Executors / Evidence / AnswerSynthesis
  等组件的配合是否合理；
- 当前仅实现基于本地 entries 的 RAG 流程，不包含 Web 联网路径。
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from ai_factory.agents.answer_synthesis_agent import synthesize_answer_from_evidences
from ai_factory.agents.query_executors import RagSearchExecutor
from ai_factory.agents.query_intent_agent import build_query_intent
from ai_factory.agents.query_types import AnswerWithSources, Evidence
from ai_factory.rag.evidence_adapter import citations_to_evidences


def _heuristic_is_question(text: str) -> Optional[bool]:
    q = text.strip()
    if not q:
        return None

    lowered = q.lower()

    question_marks = ("?" in q) or ("？" in q)

    question_keywords = [
        "如何",
        "怎么",
        "为何",
        "为什么",
        "是否",
        "吗",
        "是什么",
        "how",
        "why",
        "what",
        "can you",
        "could you",
        "查",
        "找",
        "搜索",
        "检索",
        "search",
        "lookup",
    ]

    note_like_keywords = [
        "会议纪要",
        "纪要",
        "今日工作",
        "今天主要工作",
        "备忘",
        "笔记",
        "实现计划",
        "需求说明",
        "开发记录",
        "日志",
        "TODO",
        "todo",
        "待办",
        "总结",
        "回顾",
    ]

    has_question_keyword = any(kw in q or kw in lowered for kw in question_keywords)
    has_note_keyword = any(kw in q or kw in lowered for kw in note_like_keywords)

    if has_note_keyword and not (question_marks or has_question_keyword):
        return False

    if question_marks or has_question_keyword:
        return True

    return None


def qa_answer_rag_v2(payload: Dict[str, Any]) -> Dict[str, Any]:
    """RAG 问答接口 v2（实验版）：

    - 使用 QueryIntent + RagSearchExecutor + EvidenceAdapter + AnswerSynthesis；
    - 当前仅走本地 RAG 检索路径（不含 Web）；
    - 返回结构与 v1 尽量保持兼容，但内部 answer 由 AnswerWithSources 提供。

    预期输入 payload：
    - question_text: str
    - project_code: Optional[str]
    - user_id: Optional[str]
    - top_k: Optional[int]
    - since: Optional[str 或 datetime]  # ISO 格式字符串或 datetime 对象（当前 v2 暂未使用）
    """

    question_text = str(payload.get("question_text", "")).strip()
    if not question_text:
        raise ValueError("qa_answer_rag_v2: 'question_text' is required and cannot be empty")

    guard_ok = True
    guard_reason = "valid_question"
    guard_message = ""

    heuristic_result = _heuristic_is_question(question_text)
    if heuristic_result is False:
        guard_ok = False
        guard_reason = "not_a_question_keyword_rule"
        guard_message = "当前内容更像是笔记或记录，而不是一个具体的问题，请改写为提问再提交。"

    project_code = payload.get("project_code")
    user_id = payload.get("user_id")

    top_k_raw = payload.get("top_k", 10)
    try:
        top_k = int(top_k_raw)
    except Exception:  # noqa: BLE001
        top_k = 10
    if top_k <= 0:
        top_k = 10

    # since 字段目前在 v2 中尚未接入 QueryIntent / Executor，可后续扩展
    since_val = payload.get("since")
    if isinstance(since_val, datetime):
        _ = since_val
    elif isinstance(since_val, str) and since_val.strip():
        try:
            _ = datetime.fromisoformat(since_val.strip())
        except Exception:  # noqa: BLE001
            _ = None

    guard = {
        "ok": guard_ok,
        "reason": guard_reason,
        "message": guard_message,
        "original_input": question_text,
    }

    if not guard_ok:
        return {
            "question": question_text,
            "answer": guard_message,
            "citations": [],
            "_sources": [],
            "_intent": {
                "intent_type": None,
                "mode": "RAG",
                "need_rag": False,
                "need_web": False,
                "filters": {},
                "answer_style": None,
                "intent_analysis": None,
                "sub_queries": [],
            },
            "_structure": None,
            "_guard": guard,
        }

    # Node #1: 构造意图
    context: Dict[str, Any] = {}
    if project_code is not None:
        context["project_code"] = project_code
    if user_id is not None:
        context["user_id"] = user_id
    context["top_k"] = top_k

    intent = build_query_intent(question_text, mode="RAG", context=context)

    if getattr(intent, "is_question", None) is False:
        guard["ok"] = False
        guard["reason"] = "not_a_question_intent_agent"
        guard["message"] = (
            "当前内容在语义上更像是说明/记录，而不是一个明确的问题，请改写为提问再提交。"
        )

        return {
            "question": question_text,
            "answer": guard["message"],
            "citations": [],
            "_sources": [],
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
            "_structure": None,
            "_guard": guard,
        }

    # Node #2: 执行 RAG 检索
    executor = RagSearchExecutor(default_top_k=top_k)
    raw_results: List[Dict[str, Any]] = executor.execute(intent)

    # 将原始 RAG 结果视为 citations，并转换为 Evidence 列表
    citations_like = raw_results
    evidences: List[Evidence] = citations_to_evidences(citations_like)

    # Node #3: 基于 evidences 生成回答
    answer_with_sources: AnswerWithSources = synthesize_answer_from_evidences(
        question_text, intent, evidences
    )

    # 尽量与 v1 对齐的返回结构：
    # - question: 原始问题
    # - answer: 文本回答（来自 AnswerWithSources.answer）
    # - citations: 仍保持为 RAG 风格的 citations 列表
    #   （当前直接复用 raw_results，后续如有需要可增加更多字段）

    return {
        "question": question_text,
        "answer": answer_with_sources.answer,
        "citations": citations_like,
        # 额外返回 sources 供调试/检查（不强依赖于三栏前端）
        "_sources": [
            {
                "kind": ev.kind,
                "id": ev.id,
                "title": ev.title,
                "snippet": ev.snippet,
                "source_meta": ev.source_meta,
            }
            for ev in answer_with_sources.sources
        ],
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
        # 结构化回答树，供三栏 MINDMAP 等前端消费（实验字段）。
        "_structure": answer_with_sources.structure,
        "_guard": guard,
    }
