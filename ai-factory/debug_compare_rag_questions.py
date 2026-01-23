from __future__ import annotations

"""对比两个 RAG 问题的检索与回答结果，用于排查“有记录却查不到”的问题。

在 ai-factory 根目录下运行：

    python debug_compare_rag_questions.py

脚本会分别调用 qa_answer_rag，打印：
- question
- answer
- _intent.filters
- citations 条数及前几条 entry_id/title
"""

from typing import Any, Dict

from ai_factory.integrations.rag_api import qa_answer_rag


def _pretty_print_block(title: str) -> None:
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)


def _run_one(question: str) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "question_text": question,
        # 不显式带 project_code/user_id，让行为完全由当前前端约定以外的默认逻辑决定
    }
    result = qa_answer_rag(payload)

    _pretty_print_block(f"[RAG 结果] {question}")
    print("question:", result.get("question"))
    print("answer:\n", result.get("answer"), "\n")

    intent = (result.get("_intent") or {})
    print("_intent.filters:", intent.get("filters"))
    print("_intent.intent_type:", intent.get("intent_type"))
    print("_intent.intent_analysis:\n", intent.get("intent_analysis"), "\n")

    citations = result.get("citations") or []
    print("citations count:", len(citations))
    for c in citations[:5]:
        print(
            " - entry_id=",
            c.get("entry_id"),
            " title=",
            repr(c.get("title")),
            " score=",
            c.get("score"),
        )

    return result


def main() -> None:
    q1 = "你帮我检查一下，是否能找到： 检查DB内容与向量库内容是否对齐的脚本。"
    q2 = "给我查一下，我们在防爬原则下，通过屏幕截屏获取数据的计划，做了哪些工作，取得哪些成果？"

    _run_one(q1)
    _run_one(q2)


if __name__ == "__main__":
    main()
