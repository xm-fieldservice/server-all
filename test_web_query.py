from __future__ import annotations

"""最小 Web 查询通道测试脚本。

运行前请确认环境变量已配置：
- GOOGLE_SEARCH_API_KEY
- GOOGLE_SEARCH_ENGINE_ID
- （可选）DEEPSEEK_API_KEY，用于答案整理；若未配置，Web 场景可能仅返回占位回答。

用法：
    python test_web_query.py
"""

from typing import Any, Dict

from ai_factory.integrations.web_api import qa_answer_web


def run_single_web_query() -> None:
    """使用一个示例问题测试 qa_answer_web 通道。"""

    question = (
        "2025年迄今为止中国的对外贸易顺差达到10,000亿美元，我想知道世界各大主要通讯社对这件事的报道和评价？"
    )

    payload: Dict[str, Any] = {
        "question_text": question,
        # 视需要可填 project_code / user_id
        "project_code": "proj-ai-factory",
        "user_id": "test-user-web", 
        "top_k": 5,
        "options": {
            # 这里可以后续扩展语言/地区/站点偏好等
            "max_results": 5,
        },
    }

    print("=== 请求 payload ===")
    print(payload)

    print("\n=== 调用 qa_answer_web(...) ===")
    result = qa_answer_web(payload)

    print("\n=== 返回 answer ===")
    print(result.get("answer"))

    print("\n=== 返回 sources（最多前 5 条）===")
    sources = result.get("sources") or []
    for i, src in enumerate(sources[:5], start=1):
        print(f"[Source #{i}]")
        print(f"  title : {src.get('title')}")
        print(f"  url   : {src.get('source_meta', {}).get('url') or src.get('url')}")
        print(f"  site  : {src.get('source_meta', {}).get('site')}")
        print(f"  snippet: {src.get('snippet')}")
        print()

    print("\n=== 调试字段 _intent ===")
    intent = result.get("_intent") or {}
    print(intent)


if __name__ == "__main__":
    run_single_web_query()
