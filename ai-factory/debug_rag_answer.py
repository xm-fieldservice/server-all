from __future__ import annotations

"""本地调试脚本：调用 qa_answer_rag，验证 rag-整理agent 输出。

用法（在 ai-factory 根目录下）：

    python debug_rag_answer.py

在运行前请确保：
- 已配置并可以访问 PG / 向量库；
- .env 中已配置好 DEEPSEEK_API_KEY（以及可选的 INGEST_/ANSWER_ 模型配置）。
"""

import json
from pathlib import Path
from typing import Any, Dict


def _load_dotenv_if_available() -> None:
    """尽量加载全局 D:\AI\.env + 项目级 .env（如果存在且安装了 python-dotenv）。"""

    try:
        from dotenv import load_dotenv  # type: ignore
    except Exception:
        return

    current = Path(__file__).resolve()
    project_root = current.parent      # .../ai-factory
    ai_root = project_root.parent      # .../AI

    # 1) 全局 D:\AI\.env
    global_env = ai_root / ".env"
    if global_env.is_file():
        load_dotenv(global_env, override=False)

    # 2) 项目级 D:\AI\ai-factory\.env（可选覆盖）
    local_env = project_root / ".env"
    if local_env.is_file():
        load_dotenv(local_env, override=True)


def _pretty_print_result(result: Dict[str, Any]) -> None:
    print("=== RAG 调试结果 ===")
    print("[question]")
    print(result.get("question"))
    print()

    print("[answer]")
    print(result.get("answer"))
    print()

    print("[citations]")
    citations = result.get("citations") or []
    print(f"共 {len(citations)} 条")
    for idx, c in enumerate(citations, start=1):
        print("--- citation #", idx)
        print("entry_id  :", c.get("entry_id"))
        print("title     :", c.get("title"))
        print("created_at:", c.get("created_at"))
        print("score     :", c.get("score"))
        print("summary_ai:")
        print((c.get("summary_ai") or "").strip()[:300], "...")
        print()

    print("=== 结果原始 JSON ===")
    try:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception:
        print(result)


def main() -> None:
    _load_dotenv_if_available()

    # 为方便调试，这里直接在代码中写一个问题；你可以按需修改。
    question_text = "今天 AI 工厂开发进展如何？帮我总结一下最近的工作重点。"

    # 如果你想限定 project_code / user_id，可以在这里填上；否则留空即可。
    payload: Dict[str, Any] = {
        "question_text": question_text,
        # "project_code": "demo_project",
        # "user_id": "u_demo",
        # "top_k": 5,
    }

    from ai_factory.integrations.rag_api import qa_answer_rag

    print("调用 qa_answer_rag，中...\n")
    result = qa_answer_rag(payload)

    _pretty_print_result(result)


if __name__ == "__main__":
    main()
