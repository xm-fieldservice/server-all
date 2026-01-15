from __future__ import annotations

"""三栏业务 LANGCHAIN 链路对外接口。

当前版本：
- 提供基于 LangChain 编排的 Web QA 示例入口：qa_answer_triple_web_langchain(payload)。
- 不改动现有 RAG / NOTE / WEB 三节点链路，仅作为备用 / 新链路存在。

依赖说明：
- 该接口内部调用 ai_factory.workflows.triple_column_langchain.run_triple_column_web_qa；
- 若当前环境未安装 langchain-core，将在调用时报错并给出明确提示。
"""

from typing import Any, Dict

from ai_factory.workflows.triple_column_langchain import run_triple_column_web_qa


def qa_answer_triple_web_langchain(payload: Dict[str, Any]) -> Dict[str, Any]:
    """三栏业务 LANGCHAIN 链路：Web 问答入口。

    - 输入：与 qa_answer_web 相同结构的 payload：
      {
        "question_text": str,
        "user_id": str | None,
        "project_code": str | None,
        "top_k": int | None,
        "options": dict | None,
      }

    - 输出：与 qa_answer_web 基本一致的结构：
      {
        "question": str,
        "answer": str,
        "sources": List[dict],
        "_intent": dict,
        "_structure": dict | None,
      }

    注意：
    - 该接口仅是对 workflows 层 LangChain 工作流的薄封装；
    - 若运行环境未正确安装 langchain-core，将在内部调用时抛出 RuntimeError。
    """

    if not isinstance(payload, dict):
        raise TypeError("qa_answer_triple_web_langchain: payload must be a dict")

    # 直接转发到 LangChain 工作流实现
    result = run_triple_column_web_qa(dict(payload))
    if not isinstance(result, dict):
        raise TypeError("qa_answer_triple_web_langchain: workflow result must be a dict")
    return result
