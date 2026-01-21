from __future__ import annotations

"""QueryIntentAgent: Node #1 of the unified query pipeline.

当前版本：
- 优先调用 DeepSeek 模型进行通用意图分析，生成 QueryIntent；
- 若未配置 DEEPSEEK_API_KEY 或调用失败，则回退到简单规则推断。

提示词基于原有“查询路由分析专家”的设定做了适配：
- 不直接决定是否联网，而是在给定 mode/allow_web 约束下，
  输出 need_rag/need_web/answer_style 等规划信息。
"""

import json
import os
from typing import Any, Dict, Optional

import requests

from ai_factory.agents.query_types import QueryIntent, QueryMode


def _infer_intent_type(question_text: str) -> Optional[str]:
    q = question_text.strip()
    if not q:
        return None

    lowered = q.lower()
    if "任务清单" in q or "todo" in lowered or "待办" in q:
        return "task_list"
    if "总结" in q or "概述" in q or "回顾" in q:
        return "summary"
    if "对比" in q or "比较" in q:
        return "compare"
    return None


def _default_answer_style(intent_type: Optional[str]) -> Optional[str]:
    if intent_type == "task_list":
        return "list"
    if intent_type == "summary":
        return "summary"
    if intent_type == "compare":
        return "step_by_step"
    return None


def _build_intent_fallback(
    q: str,
    *,
    mode: QueryMode,
    context: Dict[str, Any],
) -> QueryIntent:
    """基于简单规则的兜底实现。"""

    intent_type = _infer_intent_type(q)
    answer_style = _default_answer_style(intent_type)

    if mode == "WEB":
        need_rag = False
        need_web = True
    elif mode == "HYBRID":
        need_rag = True
        need_web = True
    else:  # "RAG"
        need_rag = True
        need_web = False

    filters: Dict[str, Any] = {}
    if "project_code" in context:
        filters["project_code"] = context["project_code"]
    if "user_id" in context:
        filters["user_id"] = context["user_id"]
    if "top_k" in context:
        filters["top_k"] = context["top_k"]

    return QueryIntent(
        question_text=q,
        mode=mode,
        intent_type=intent_type,
        need_rag=need_rag,
        need_web=need_web,
        filters=filters,
        answer_style=answer_style,
    )


def _build_intent_via_deepseek(
    q: str,
    *,
    mode: QueryMode,
    context: Dict[str, Any],
) -> Optional[QueryIntent]:
    """使用 DeepSeek 模型进行通用意图分析。

    如调用失败或配置缺失，则返回 None，由上层回退到规则实现。
    """

    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        return None

    model_name = os.getenv("INTENT_MODEL_NAME", os.getenv("INGEST_MODEL_NAME", "deepseek-chat"))
    base_url = os.getenv("INTENT_MODEL_BASE_URL", os.getenv("INGEST_MODEL_BASE_URL", "https://api.deepseek.com")).rstrip("/")

    # allow_web 由上游/模式决定，这里只按约定使用
    allow_web = bool(context.get("allow_web", mode == "WEB"))

    system_prompt = (
        "你是查询路由分析专家，负责分析用户查询意图并制定查询策略。\n"
        "\n"
        "【调用约定】\n"
        "- 已知当前模式 mode = 'RAG' | 'WEB' | 'HYBRID'。\n"
        "- 已知是否允许联网 allow_web = true | false。\n"
        "- 当 allow_web = false 时，你不能要求使用外部网络，只能使用本地知识库/本地上下文。\n"
        "\n"
        "【核心职责】\n"
        "1. 分析查询意图与复杂度（用户在问什么、想达到什么目标）。\n"
        "2. 在给定约束下，判断需要使用哪些信息源：本地 RAG / 外部 Web。\n"
        "3. 确定查询策略（basic/advanced），以及可能的过滤条件。\n"
        "4. 生成结构化的查询路由计划，包括必要时将问题拆解为若干子问题，供后续执行节点使用。\n"
        "5. 明确判断当前输入是否是在向系统提出问题、请求答案/建议（而不是仅仅做笔记或陈述），并通过 is_question 字段给出布尔结果。\n"
        "\n"
        "【输出要求】\n"
        "只输出一个 JSON 对象，不要添加任何解释性文字。字段示例：\n"
        "{\n"
        "  \"analysis\": \"查询分析结果\",\n"
        "  \"strategy\": \"basic|advanced\",\n"
        "  \"need_rag\": true,\n"
        "  \"need_web\": false,\n"
        "  \"filters\": {\"project_code\": null, \"time_range\": null, \"other\": null},\n"
        "  \"answer_style\": \"list|summary|step_by_step|other\",\n"
        "  \"sub_queries\": [\"子问题1\", \"子问题2\"],\n"
        "  \"instructions\": \"给后续执行节点的具体操作建议\",\n"
        "  \"is_question\": true\n"
        "}\n"
    )

    user_prompt = {
        "question": q,
        "mode": mode,
        "allow_web": allow_web,
        "context": {k: v for k, v in context.items() if k not in {"allow_web"}},
    }

    provider = os.getenv("INTENT_MODEL_PROVIDER", "deepseek").lower()

    try:
        if provider == "ollama":
            # 使用本地 Ollama 服务进行推理，走 /api/chat 接口，不需要 Authorization 头。
            resp = requests.post(
                f"{base_url}/api/chat",
                json={
                    "model": model_name,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": json.dumps(user_prompt, ensure_ascii=False)},
                    ],
                    "stream": False,
                },
                timeout=60,
            )
        else:
            # 默认走 DeepSeek 官方 OpenAI 风格接口
            resp = requests.post(
                f"{base_url}/v1/chat/completions",
                json={
                    "model": model_name,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": json.dumps(user_prompt, ensure_ascii=False)},
                    ],
                    "stream": False,
                },
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                timeout=60,
            )

        resp.raise_for_status()
    except Exception as e:  # noqa: BLE001
        print(f"[QueryIntentAgent] DeepSeek/Ollama 调用失败: {e!r}")
        return None

    try:
        data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            print("[QueryIntentAgent] DeepSeek 返回中无 choices 字段")
            return None
        message = (choices[0] or {}).get("message") or {}
        content = str(message.get("content") or "").strip()
    except Exception as e:  # noqa: BLE001
        print(f"[QueryIntentAgent] 解析 DeepSeek JSON 失败: {e!r}")
        return None

    # 去掉可能的 ``` 包裹
    if content.startswith("```"):
        content = content.split("\n", 1)[-1]
    if content.endswith("```"):
        content = content.rsplit("```", 1)[0]

    try:
        obj = json.loads(content)
    except Exception as e:  # noqa: BLE001
        print(f"[QueryIntentAgent] LLM 输出无法解析为 JSON: {e!r}; raw={content[:300]}")
        return None

    # 映射到 QueryIntent
    intent_type = None
    answer_style = None
    is_question: Optional[bool] = None

    strategy = str(obj.get("strategy") or "").lower()
    if strategy in {"basic", "advanced"}:
        # 可按需利用 strategy，但当前先不映射到字段
        pass

    answer_style_raw = str(obj.get("answer_style") or "").lower()
    if answer_style_raw in {"list", "summary", "step_by_step"}:
        answer_style = answer_style_raw

    # 从 analysis 中粗略推 intent_type（可后续细化）
    analysis = str(obj.get("analysis") or "")
    if "任务清单" in analysis or "清单" in analysis:
        intent_type = "task_list"
    elif "总结" in analysis:
        intent_type = "summary"

    # is_question: LLM 对“是否为问题”的显式判断
    is_question_raw = obj.get("is_question")
    if isinstance(is_question_raw, bool):
        is_question = is_question_raw
    elif isinstance(is_question_raw, str):
        lowered_flag = is_question_raw.strip().lower()
        if lowered_flag in {"true", "yes", "y", "1"}:
            is_question = True
        elif lowered_flag in {"false", "no", "n", "0"}:
            is_question = False

    need_rag = bool(obj.get("need_rag", True))
    need_web = bool(obj.get("need_web", False))
    # 强制遵守 allow_web 约束
    if not allow_web:
        need_web = False

    filters_obj = obj.get("filters") or {}
    filters: Dict[str, Any] = {}
    if isinstance(filters_obj, dict):
        filters.update(filters_obj)

    # 把上游 context 中的 project_code/user_id/top_k 合并进 filters，
    # 并且强制以上游 context 为准，避免 LLM 乱写这三个字段导致误过滤。
    for key in ("project_code", "user_id", "top_k"):
        if key in context:
            filters[key] = context[key]

    # 子问题列表：用于调试和后续多步查询规划
    sub_queries_raw = obj.get("sub_queries") or []
    sub_queries: list[str] = []
    if isinstance(sub_queries_raw, list):
        for item in sub_queries_raw:
            if isinstance(item, str) and item.strip():
                sub_queries.append(item.strip())

    return QueryIntent(
        question_text=q,
        mode=mode,
        intent_type=intent_type,
        need_rag=need_rag,
        need_web=need_web,
        filters=filters,
        answer_style=answer_style,
        intent_analysis=analysis or None,
        sub_queries=sub_queries,
        is_question=is_question,
    )


def build_query_intent(
    question_text: str,
    *,
    mode: QueryMode = "RAG",
    context: Optional[Dict[str, Any]] = None,
) -> QueryIntent:
    """构造 QueryIntent：优先使用 LLM，失败时回退到规则实现。"""

    context = context or {}
    q = question_text.strip()

    # 先尝试使用 DeepSeek 进行通用意图分析
    intent_llm = _build_intent_via_deepseek(q, mode=mode, context=context)
    if intent_llm is not None:
        return intent_llm

    # 回退到简单规则
    return _build_intent_fallback(q, mode=mode, context=context)
