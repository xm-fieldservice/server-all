from __future__ import annotations

"""Web 问答对外接口（v0）。

为三栏 / 其他客户端提供统一的联网问答入口：qa_answer_web(payload)。

当前实现基于统一的 1/2/3 节点流水线：
- Node #1: build_query_intent(mode="WEB") 构造 QueryIntent；
- Node #2: WebSearchExecutor 执行实际的 Web 搜索（当前为占位实现，返回空列表）；
- Node #3: synthesize_answer_from_evidences 基于 Evidence 列表生成回答。

注意：
- 目前 WebSearchExecutor 还是占位实现，因此默认不会返回真实的联网结果；
- 接口契约已经固定，后续只需在 WebSearchExecutor 内部接入真实的联网 Team / HTTP 搜索即可。
"""

from typing import Any, Dict, List, Optional

from ai_factory.agents.answer_synthesis_agent import synthesize_answer_from_evidences
from ai_factory.agents.query_executors import WebSearchExecutor
from ai_factory.agents.query_intent_agent import build_query_intent
from ai_factory.agents.query_types import Evidence
from ai_factory.web.evidence_adapter import web_results_to_evidences

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


def qa_answer_web(payload: Dict[str, Any]) -> Dict[str, Any]:
    """联网问答接口（v0）。

    预期输入 payload：
    - question_text: str                       # 必填，用户问题
    - user_id: Optional[str]                   # 可选，调用方用户标识
    - project_code: Optional[str]              # 可选，项目/空间标识
    - top_k: Optional[int]                     # 可选，Web 结果最大条数，默认 5
    - options: Optional[dict]                  # 可选，扩展选项，如语言、站点偏好等

    当前实现要点：
    - 统一通过 QueryIntent(mode="WEB") 描述本次查询；
    - Node #2 使用 WebSearchExecutor 执行 Web 搜索（当前为占位，返回空列表）；
    - 使用 web_results_to_evidences 将原始 Web 结果适配为 Evidence(kind="web")；
    - 使用 synthesize_answer_from_evidences 生成自然语言回答。

    返回结构（v0 约定）：
    {
      "question": str,
      "answer": str,                 # 面向用户的自然语言回答
      "sources": [                   # 统一 Evidence 结构的外层投影
        {
          "kind": "web",           # 目前固定为 "web"
          "id": str,
          "title": str | None,
          "snippet": str | None,
          "source_meta": {          # 典型字段：url/site/published_at
            ...
          },
        },
        ...
      ],
      "_intent": {                   # 调试/分析用，前端可选消费
        "intent_type": str | None,
        "mode": str,
        "need_rag": bool,
        "need_web": bool,
        "filters": dict,
        "answer_style": str | None,
        "intent_analysis": str | None,
        "sub_queries": list[str],
      },
      "_structure": dict | None,     # 结构化回答树（若有），供脑图等使用
    }
    """

    print("[qa_answer_web] payload received:", payload)

    if not isinstance(payload, dict):
        raise TypeError("qa_answer_web: payload must be a dict")

    question_text = str(payload.get("question_text", "")).strip()
    if not question_text:
        raise ValueError("qa_answer_web: 'question_text' is required and cannot be empty")

    print("[qa_answer_web] question_text:", question_text)

    guard_ok = True
    guard_reason = "valid_question"
    guard_message = ""

    heuristic_result = _heuristic_is_question(question_text)
    if heuristic_result is False:
        guard_ok = False
        guard_reason = "not_a_question_keyword_rule"
        guard_message = "当前内容更像是笔记或记录，而不是一个具体的问题，请改写为提问再提交。"

    user_id: Optional[str] = payload.get("user_id")
    project_code: Optional[str] = payload.get("project_code")

    # 结果条数控制：优先使用显式 top_k，其次从 options 中读取，默认 5
    top_k_raw = payload.get("top_k")
    options = payload.get("options") or {}
    if not isinstance(options, dict):
        options = {}

    if top_k_raw is None:
        top_k_raw = options.get("max_results", 5)

    try:
        top_k = int(top_k_raw)
    except Exception:  # noqa: BLE001
        top_k = 5
    if top_k <= 0:
        top_k = 5

    print("[qa_answer_web] resolved top_k =", top_k)

    guard = {
        "ok": guard_ok,
        "reason": guard_reason,
        "message": guard_message,
        "original_input": question_text,
    }

    if not guard_ok:
        out_guard_only: Dict[str, Any] = {
            "question": question_text,
            "answer": guard_message,
            "sources": [],
            "_intent": {
                "intent_type": None,
                "mode": "WEB",
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
        print("[qa_answer_web] guard blocked request:", guard)
        return out_guard_only

    # Node #1: 构造 QueryIntent（mode="WEB"）
    print("[qa_answer_web] building QueryIntent (mode=WEB)...")

    context: Dict[str, Any] = {}
    if project_code is not None:
        context["project_code"] = project_code
    if user_id is not None:
        context["user_id"] = user_id

    # 将 top_k 作为过滤条件的一部分，便于后续在执行器层统一处理
    context["top_k"] = top_k

    # 额外将 options 合并进 filters 上下文，供未来 WebSearchExecutor 使用
    context["options"] = options

    print("[qa_answer_web] context for intent:", context)

    intent = build_query_intent(question_text, mode="WEB", context=context)
    print("[qa_answer_web] intent built:", {
        "mode": intent.mode,
        "need_rag": intent.need_rag,
        "need_web": intent.need_web,
        "filters": intent.filters,
        "intent_type": intent.intent_type,
        "answer_style": intent.answer_style,
        "sub_queries": getattr(intent, "sub_queries", []),
        "is_question": getattr(intent, "is_question", None),
    })

    if getattr(intent, "is_question", None) is False:
        guard["ok"] = False
        guard["reason"] = "not_a_question_intent_agent"
        guard["message"] = (
            "当前内容在语义上更像是说明/记录，而不是一个明确的问题，请改写为提问再提交。"
        )

        out_guard_only_intent: Dict[str, Any] = {
            "question": question_text,
            "answer": guard["message"],
            "sources": [],
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
        print("[qa_answer_web] guard blocked by intent.is_question:", guard)
        return out_guard_only_intent

    # Node #2: 执行 Web 搜索
    print("[qa_answer_web] calling WebSearchExecutor.execute ...")
    executor = WebSearchExecutor()
    raw_results: List[Dict[str, Any]] = executor.execute(intent)
    print("[qa_answer_web] WebSearchExecutor returned", len(raw_results), "raw results")

    # 将原始 Web 结果适配为 Evidence 列表
    evidences: List[Evidence] = web_results_to_evidences(raw_results)
    print("[qa_answer_web] evidences converted, count =", len(evidences))

    # Node #3: 基于 evidences 生成回答
    print("[qa_answer_web] calling synthesize_answer_from_evidences ...")
    answer_with_sources = synthesize_answer_from_evidences(
        question_text=question_text,
        intent=intent,
        evidences=evidences,
    )
    print("[qa_answer_web] answer_with_sources prepared, sources count =",
          len(answer_with_sources.sources))

    # 对 Evidence 做一个稳定的对外投影结构
    def _evidence_to_dict(ev: Evidence) -> Dict[str, Any]:
        return {
            "kind": ev.kind,
            "id": ev.id,
            "title": ev.title,
            "snippet": ev.snippet,
            "source_meta": dict(ev.source_meta or {}),
        }

    out: Dict[str, Any] = {
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
        "_guard": guard,
    }

    return out
