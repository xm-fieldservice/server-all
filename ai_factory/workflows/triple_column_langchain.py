from __future__ import annotations

"""三栏业务 LANGCHAIN 链路（实验性）。

设计目标：
- 不改动现有三节点链路（RAG / NOTE / WEB 的 Node1/2/3）；
- 在本模块中，使用 LangChain 的 Runnable 链来编排 Node1/2/3；
- 作为“三栏业务 LANGCHAIN 链路”的后端落点，后续可由 integrations 层新增入口调用。

当前版本：
- 先实现一个最小的 Web QA 工作流示例：
  payload -> QueryIntent(mode="WEB") -> WebSearchExecutor -> web_results_to_evidences -> synthesize_answer_from_evidences
- 对外暴露 run_triple_column_web_qa(payload) 供上层调用；
- 若运行环境未安装 langchain-core，则在调用时给出明确错误提示。
"""

from typing import Any, Dict, List, Optional

from ai_factory.agents.answer_synthesis_agent import synthesize_answer_from_evidences
from ai_factory.agents.query_executors import WebSearchExecutor
from ai_factory.agents.query_intent_agent import build_query_intent
from ai_factory.agents.query_types import Evidence, QueryIntent
from ai_factory.web.evidence_adapter import web_results_to_evidences

try:  # LangChain 为可选依赖
    from langchain_core.runnables import RunnableLambda

    HAS_LANGCHAIN = True
except Exception:  # noqa: BLE001
    RunnableLambda = None  # type: ignore[assignment]
    HAS_LANGCHAIN = False


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


def _node1_build_intent(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Node1：基于 payload 构造 Web 模式的 QueryIntent，并附带守护结果。"""

    if not isinstance(payload, dict):
        raise TypeError("run_triple_column_web_qa: payload must be a dict")

    question_text = str(payload.get("question_text", "")).strip()
    if not question_text:
        raise ValueError(
            "run_triple_column_web_qa: 'question_text' is required and cannot be empty",
        )

    user_id = payload.get("user_id")
    project_code = payload.get("project_code")

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

    context: Dict[str, Any] = {}
    if project_code is not None:
        context["project_code"] = project_code
    if user_id is not None:
        context["user_id"] = user_id
    context["top_k"] = top_k
    context["options"] = options

    guard_ok = True
    guard_reason = "valid_question"
    guard_message = ""

    heuristic_result = _heuristic_is_question(question_text)
    if heuristic_result is False:
        guard_ok = False
        guard_reason = "not_a_question_keyword_rule"
        guard_message = "当前内容更像是笔记或记录，而不是一个具体的问题，请改写为提问再提交。"

    intent: Optional[QueryIntent]
    if guard_ok:
        intent = build_query_intent(question_text, mode="WEB", context=context)
        if getattr(intent, "is_question", None) is None and heuristic_result is not None:
            intent.is_question = heuristic_result
    else:
        intent = None

    guard = {
        "ok": guard_ok,
        "reason": guard_reason,
        "message": guard_message,
        "original_input": question_text,
    }

    return {
        "question_text": question_text,
        "intent": intent,
        "_guard": guard,
    }


def _node2_web_search(state: Dict[str, Any]) -> Dict[str, Any]:
    """Node2：执行 Web 搜索并返回 Evidence 列表。"""

    intent: Optional[QueryIntent] = state.get("intent")
    question_text: str = state["question_text"]

    guard = state.get("_guard") or {}
    if isinstance(guard, dict) and not guard.get("ok", True):
        return {
            "question_text": question_text,
            "intent": intent,
            "evidences": [],
            "_guard": guard,
        }

    executor = WebSearchExecutor()
    raw_results: List[Dict[str, Any]] = executor.execute(intent) if intent is not None else []
    evidences: List[Evidence] = web_results_to_evidences(raw_results)

    return {
        "question_text": question_text,
        "intent": intent,
        "evidences": evidences,
        "_guard": guard,
    }


def _node3_synthesize(state: Dict[str, Any]) -> Dict[str, Any]:
    """Node3：基于 evidences 生成回答，并做统一对外投影。"""

    question_text: str = state["question_text"]
    intent: Optional[QueryIntent] = state.get("intent")
    evidences: List[Evidence] = state.get("evidences") or []

    guard = state.get("_guard") or {}

    if isinstance(guard, dict) and not guard.get("ok", True):
        answer_text = guard.get("message") or "当前内容更像是笔记或记录，而不是一个具体的问题，请改写为提问再提交。"

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
            "answer": answer_text,
            "sources": [_evidence_to_dict(ev) for ev in evidences],
            "_intent": {
                "intent_type": getattr(intent, "intent_type", None) if intent is not None else None,
                "mode": getattr(intent, "mode", "WEB") if intent is not None else "WEB",
                "need_rag": getattr(intent, "need_rag", False) if intent is not None else False,
                "need_web": getattr(intent, "need_web", False) if intent is not None else False,
                "filters": getattr(intent, "filters", {}) if intent is not None else {},
                "answer_style": getattr(intent, "answer_style", None) if intent is not None else None,
                "intent_analysis": getattr(intent, "intent_analysis", None) if intent is not None else None,
                "sub_queries": getattr(intent, "sub_queries", [] ) if intent is not None else [],
            },
            "_structure": None,
            "_guard": guard,
        }

        return out

    answer_with_sources = synthesize_answer_from_evidences(
        question_text=question_text,
        intent=intent,
        evidences=evidences,
    )

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


def build_web_qa_chain():
    """构建一条基于 LangChain Runnable 的 Web QA 工作流链。

    返回值：一个 Runnable，可通过 .invoke(payload) 直接得到最终回答 dict。
    """

    if not HAS_LANGCHAIN:
        raise RuntimeError(
            "LangChain (langchain-core) 未安装，无法构建 Web QA 工作流链；"
            "请先在当前环境安装 langchain-core / langchain 再调用此函数。",
        )

    step1 = RunnableLambda(_node1_build_intent)
    step2 = RunnableLambda(_node2_web_search)
    step3 = RunnableLambda(_node3_synthesize)

    # 简单串联：payload -> state1 -> state2 -> 最终输出
    chain = step1 | step2 | step3
    return chain


def run_triple_column_web_qa(payload: Dict[str, Any]) -> Dict[str, Any]:
    """三栏业务 LANGCHAIN 链路：Web QA 示例入口。

    - 输入：与 qa_answer_web 相同的 payload 结构；
    - 输出：与 qa_answer_web 基本一致的 dict（question/answer/sources/_intent/_structure）。

    注意：
    - 本函数不会修改现有三节点实现，只是通过 LangChain 对其进行编排；
    - 若当前环境未安装 LangChain，则会抛出 RuntimeError 提示缺少依赖。
    """

    chain = build_web_qa_chain()
    result = chain.invoke(payload)
    if not isinstance(result, dict):
        raise TypeError("run_triple_column_web_qa: chain result must be a dict")
    return result
