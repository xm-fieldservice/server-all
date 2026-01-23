from __future__ import annotations

"""RAG 问答对外接口（v0）。

对三栏 / 其他客户端暴露一个稳定的高层接口：qa_answer_rag(payload)。

v0 约定：
- 只做检索，不做 answer 生成，answer 字段为 None；
- 返回 citations 列表，每条包含 entry 的基本信息和相似度得分；
- 后续可以在不破坏外层契约的前提下，增加 RagQueryAgent / AnswerAgent 等内部步骤。
"""

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from ai_factory.rag.entries_rag import RetrievedEntry, search_entries
from ai_factory.agents.rag_answer_agent import generate_answer_via_deepseek
from ai_factory.integrations.rag_pipeline_api_v2 import qa_answer_rag_v2


@dataclass
class QaRagRequest:
    question_text: str
    project_code: Optional[str] = None
    user_id: Optional[str] = None
    top_k: int = 10
    since: Optional[datetime] = None


def _entry_to_citation(entry: RetrievedEntry) -> Dict[str, Any]:
    """将 RetrievedEntry 映射为对外暴露的 citation 结构。"""

    return {
        "entry_id": entry.entry_id,
        "title": entry.title,
        "summary_ai": entry.summary_ai,
        # content 暂不直接暴露全文，视需求可再加
        "project_code": entry.project_code,
        "user_id": entry.user_id,
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
        "score": entry.score,
    }


def qa_answer_rag_legacy(payload: Dict[str, Any]) -> Dict[str, Any]:
    """RAG 问答接口（legacy 实现）：直接检索 entries 并调用旧版 Answer Agent。

    预期输入 payload：
    - question_text: str
    - project_code: Optional[str]
    - user_id: Optional[str]
    - top_k: Optional[int]
    - since: Optional[str 或 datetime]  # ISO 格式字符串或 datetime 对象

    返回结构：
    {
      "question": str,
      "answer": None,
      "citations": [
        {
          "entry_id": str,
          "title": str | None,
          "summary_ai": str | None,
          "project_code": str | None,
          "user_id": str | None,
          "created_at": str | None,  # ISO8601
          "score": float,
        },
        ...
      ],
    }
    """

    question_text = str(payload.get("question_text", "")).strip()
    if not question_text:
        raise ValueError("qa_answer_rag: 'question_text' is required and cannot be empty")

    project_code = payload.get("project_code")
    user_id = payload.get("user_id")

    top_k_raw = payload.get("top_k", 10)
    try:
        top_k = int(top_k_raw)
    except Exception:  # noqa: BLE001
        top_k = 10
    if top_k <= 0:
        top_k = 10

    since_val = payload.get("since")
    since_dt: Optional[datetime] = None
    if isinstance(since_val, datetime):
        since_dt = since_val
    elif isinstance(since_val, str) and since_val.strip():
        try:
            since_dt = datetime.fromisoformat(since_val.strip())
        except Exception:  # noqa: BLE001
            since_dt = None

    retrieved: List[RetrievedEntry] = search_entries(
        question_text,
        top_k=top_k,
        project_code=project_code,
        user_id=user_id,
        since=since_dt,
    )

    citations = [_entry_to_citation(e) for e in retrieved]

    answer_text: Optional[str] = None
    if citations:
        try:
            answer_text = generate_answer_via_deepseek(question_text, citations)
        except Exception as e:  # noqa: BLE001
            # 生成回答失败时不阻断检索主流程，仅记录错误并返回空回答
            print(f"[RAG-answer] generate_answer_via_deepseek 失败: {e!r}")
            answer_text = None

    return {
        "question": question_text,
        "answer": answer_text,
        "citations": citations,
    }


def qa_answer_rag(payload: Dict[str, Any]) -> Dict[str, Any]:
    """RAG 问答接口（当前默认实现）：转发到 v2 流水线。

    对三栏等调用方保持原有契约：
    - question: str
    - answer: str | None
    - citations: List[dict]

    同时保留 v2 额外返回的调试字段（如 _intent / _sources / _structure），
    以便前端按需消费，但不做强依赖。
    """

    # 基于历史契约，对入参做最小预处理，然后直接调用 v2。
    if not isinstance(payload, dict):
        raise TypeError("qa_answer_rag: payload must be a dict")

    result_v2 = qa_answer_rag_v2(dict(payload))

    # 向后兼容的基础字段
    out: Dict[str, Any] = {
        "question": result_v2.get("question"),
        "answer": result_v2.get("answer"),
        "citations": result_v2.get("citations") or [],
    }

    # 额外挂载 v2 的内部结构，供前端/调试使用（不破坏旧契约）。
    for key in ("_intent", "_sources", "_structure", "_guard"):
        if key in result_v2:
            out[key] = result_v2[key]

    return out
