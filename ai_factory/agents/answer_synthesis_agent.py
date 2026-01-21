from __future__ import annotations

"""AnswerSynthesisAgent: Node #3 of the unified query pipeline.

当前版本：
- 通过 Evidence 列表还原 RAG citations 结构；
- 复用 rag_answer_agent.generate_answer_via_deepseek 调用 DeepSeek 模型；
- 主要面向 RAG 场景（kind="rag"），对 Web 证据暂不做特殊处理。

后续可以：
- 根据 QueryIntent.answer_style 等信息细化提示词策略（任务清单/总结/对比等）；
- 同时兼容 RAG / Web / 混合证据，并显式输出 sources。
"""

import json
import os
from typing import Any, Dict, List, Optional

import requests

from ai_factory.agents.query_types import AnswerWithSources, Evidence, QueryIntent


def synthesize_answer_from_evidences(
    question_text: str,
    intent: QueryIntent,
    evidences: List[Evidence],
) -> AnswerWithSources:
    """基于 evidences 调用 DeepSeek 生成结构化回答（含可供 Mindmap 使用的结构）。

    当前策略：
    - 仅使用 kind="rag" 的证据作为节点 3 的主要输入；
    - 通过一个专门的提示词，请 DeepSeek 输出 JSON 结构：
      {summary, themes, transitions, meta}，其中 themes 下再包含 topics/items；
    - 在本函数中根据该 JSON 结构渲染自然语言回答文本；
    - 将原始 evidences 作为 sources 返回，并把 JSON 结构挂在 AnswerWithSources.structure 上，
      便于后续 Mindmap / 前端消费。
    """

    if not evidences:
        return AnswerWithSources(
            answer="暂时没有找到与该问题相关的记录，因此无法给出有依据的回答。",
            sources=[],
        )

    # 按来源类型拆分 evidences
    rag_evidences = [e for e in evidences if e.kind == "rag"]
    web_evidences = [e for e in evidences if e.kind == "web"]

    # 仅 Web 证据时：走专门的 Web 新闻综述整理逻辑
    if not rag_evidences and web_evidences:
        web_answer = _generate_web_answer_from_evidences(
            question_text=question_text,
            intent=intent,
            web_evidences=web_evidences,
        )

        return AnswerWithSources(
            answer=web_answer,
            sources=evidences,
            structure=None,
        )

    # 准备结构化整理所需的精简 evidence 文本
    def _ev_to_brief_dict(ev: Evidence) -> Dict[str, Any]:
        meta = ev.source_meta or {}
        return {
            "entry_id": meta.get("entry_id") or ev.id,
            "title": ev.title,
            "snippet": ev.snippet,
            "created_at": meta.get("created_at"),
        }

    rag_briefs: List[Dict[str, Any]] = [_ev_to_brief_dict(e) for e in rag_evidences]
    
    # 根据意图类型选择回答策略：
    # - 对于 summary/总结 类意图，仍使用结构化时间线 JSON + 渲染；
    # - 其他一般问答场景，直接调用面向任务型回答的助手提示词。

    intent_type = getattr(intent, "intent_type", "") or ""
    intent_analysis = getattr(intent, "intent_analysis", "") or ""

    def _is_summary_intent() -> bool:
        """判断是否应走“总结/时间线”结构化回答路径。

        收紧策略：
        - 主要依据“用户问题本身”是否在要求总结/复盘/周报；
        - 以及 LLM 显式给出的 intent_type == "summary"；
        - 不再因为 intent_analysis 里随口提到“总结”二字就触发，避免查脚本/查配置类问题被误判。
        """

        q = (question_text or "").strip()

        # 1) 问题文本里明确提到总结/复盘/周报/阶段性汇总
        summary_keywords_zh = ("总结", "复盘", "周报", "阶段性", "阶段性工作", "汇报", "报告")
        if any(kw in q for kw in summary_keywords_zh):
            return True

        q_lower = q.lower()
        summary_keywords_en = ("summary", "report", "recap")
        if any(kw in q_lower for kw in summary_keywords_en):
            return True

        # 2) LLM 显式标记为 summary 类型，且在分析中也强调了总结/复盘
        if intent_type == "summary" and any(
            kw in intent_analysis for kw in ("总结", "复盘", "timeline", "时间线")
        ):
            return True

        return False

    if _is_summary_intent():
        # 调用 DeepSeek 让其输出结构化 JSON
        structure = _generate_structured_timeline(
            question_text=question_text,
            intent=intent,
            rag_briefs=rag_briefs,
        )

        # 基于结构 JSON 渲染自然语言回答。如果结构生成失败，则给出降级回答。
        if not structure:
            fallback_answer = (
                "已检索到相关工作记录，但在生成结构化分析时出现问题，"
                "请稍后重试或改用摘要类问题。"
            )
            return AnswerWithSources(
                answer=fallback_answer,
                sources=evidences,
                structure=None,
            )

        answer_text = _render_answer_from_structure(structure)

        return AnswerWithSources(
            answer=answer_text,
            sources=evidences,
            structure=structure,
        )

    # 一般问答场景：直接生成面向任务的自然语言回答，不强制结构化时间线。
    direct_answer = _generate_direct_answer_from_evidences(
        question_text=question_text,
        intent=intent,
        rag_briefs=rag_briefs,
    )

    return AnswerWithSources(
        answer=direct_answer,
        sources=evidences,
        structure=None,
    )


def _generate_structured_timeline(
    *,
    question_text: str,
    intent: QueryIntent,
    rag_briefs: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """调用 DeepSeek 生成结构化的主题/议题/子节点树。

    输出期望结构示例：

    {
      "summary": "...整体总结...",
      "themes": [
        {
          "id": "theme_1",
          "title": "主题一：...",
          "time_range": "2024-12-11",
          "kind": "feature_dev",
          "description": "...",
          "topics": [
            {
              "id": "topic_1_1",
              "title": "...",
              "description": "...",
              "items": [
                {
                  "id": "item_1_1_1",
                  "title": "...",
                  "entries": ["ent_xxx", "ent_yyy"]
                }
              ]
            }
          ]
        }
      ],
      "transitions": [
        {"from": "theme_1", "to": "theme_2", "type": "progression", "relation": "...", "is_jump": false}
      ],
      "meta": {"time_window": "...", "theme_count": 3}
    }
    """

    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("[AnswerSynthesis] DEEPSEEK_API_KEY 未设置，无法生成结构化回答")
        return None

    model_name = os.getenv(
        "ANSWER_MODEL_NAME",
        os.getenv("INGEST_MODEL_NAME", "deepseek-chat"),
    )
    base_url = os.getenv(
        "ANSWER_MODEL_BASE_URL",
        os.getenv("INGEST_MODEL_BASE_URL", "https://api.deepseek.com"),
    ).rstrip("/")

    intent_analysis = getattr(intent, "intent_analysis", "") or ""
    sub_queries = getattr(intent, "sub_queries", []) or []

    system_prompt = (
        "你是一名中文项目时间线与主题分析助手。\n"
        "根据给定的工作记录摘录，识别 1~N 个主题（一级节点），每个主题下包含 0~N 个议题/子主题（二级节点），"
        "议题下再包含 1~N 个具体事项（三级/四级节点）。\n"
        "请严格输出 JSON，不要输出多余文字。"
    )

    user_payload: Dict[str, Any] = {
        "question": question_text,
        "intent_analysis": intent_analysis,
        "sub_queries": sub_queries,
        "rag_entries": rag_briefs,
        "output_schema_hint": {
            "summary": "string",
            "themes": [
                {
                    "id": "string",
                    "title": "string",
                    "time_range": "string",
                    "kind": "string",
                    "description": "string",
                    "topics": [
                        {
                            "id": "string",
                            "title": "string",
                            "description": "string",
                            "items": [
                                {
                                    "id": "string",
                                    "title": "string",
                                    "entries": ["entry_id", "..."]
                                }
                            ],
                        }
                    ],
                }
            ],
            "transitions": [
                {
                    "from": "string",
                    "to": "string",
                    "type": "progression|branch|merge",
                    "relation": "string",
                    "is_jump": False,
                }
            ],
            "meta": {
                "time_window": "string",
                "theme_count": 0,
            },
        },
    }

    user_prompt = (
        "请基于下列工作记录，输出一个 JSON 结构，描述 12-14 日（或问题指定时间窗口）内的工作主题、议题以及主题切换关系。\n"
        "要求：\n"
        "1. JSON 顶层必须包含 summary、themes、transitions、meta 四个字段。\n"
        "2. themes 为数组，表示一级主题，每个主题下的 topics 数量不限，可以为 0。\n"
        "3. 每个 topic 下的 items 一般为 1~2 条，遇到议题特别多的情况可多于 2 条。\n"
        "4. transitions 用于描述主题之间的切换关系，包括是否跳跃式（is_jump 字段）。\n"
        "5. 严格输出合法 JSON，不要在 JSON 前后添加说明文字。\n\n"
        f"下面是输入数据（JSON 格式）：\n{json.dumps(user_payload, ensure_ascii=False)}"
    )

    http_resp = None
    try:
        http_resp = requests.post(
            f"{base_url}/v1/chat/completions",
            json={
                "model": model_name,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "stream": False,
            },
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=600,
        )
        http_resp.raise_for_status()
    except Exception as e:  # noqa: BLE001
        status = http_resp.status_code if http_resp is not None else "<no http>"
        text_preview = http_resp.text[:400] if http_resp is not None else "<no body>"
        print(f"[AnswerSynthesis] 调用 deepseek-chat 生成结构化回答失败: {e}; status={status}; body={text_preview}")
        return None

    try:
        data = http_resp.json()  # type: ignore[union-attr]
    except Exception as e:  # noqa: BLE001
        body_preview = http_resp.text[:800] if http_resp is not None else "<no response>"  # type: ignore[union-attr]
        print(f"[AnswerSynthesis] 解析 deepseek-chat JSON 失败: {e}; body={body_preview}")
        return None

    choices = data.get("choices") or []
    if not choices:
        print("[AnswerSynthesis] deepseek-chat 返回结果中不包含 choices 字段")
        return None

    message = (choices[0] or {}).get("message") or {}
    text = str(message.get("content") or "").strip()
    if not text:
        print("[AnswerSynthesis] deepseek-chat 返回的 message.content 为空")
        return None

    # 有些模型会在 JSON 外层包一段解释文字，尝试从中提取 JSON 段落
    json_str = text
    if "{" in text and "}" in text:
        first = text.find("{")
        last = text.rfind("}")
        json_str = text[first : last + 1]

    try:
        parsed = json.loads(json_str)
    except Exception as e:  # noqa: BLE001
        print(f"[AnswerSynthesis] 解析模型输出为 JSON 失败: {e}; raw_text={text[:400]}")
        return None

    if not isinstance(parsed, dict):
        print("[AnswerSynthesis] 结构化输出不是 JSON 对象，忽略")
        return None

    return parsed


def _render_answer_from_structure(structure: Dict[str, Any]) -> str:
    """根据结构 JSON 渲染人类可读的 Markdown 文本回答。"""

    lines: List[str] = []

    summary = str(structure.get("summary") or "").strip()
    if summary:
        lines.append(summary)
        lines.append("")

    themes = structure.get("themes") or []
    if isinstance(themes, list) and themes:
        for idx, theme in enumerate(themes, start=1):
            if not isinstance(theme, dict):
                continue
            title = str(theme.get("title") or "主题").strip()
            desc = str(theme.get("description") or "").strip()
            lines.append(f"**{idx}. {title}**")
            if desc:
                lines.append(desc)

            topics = theme.get("topics") or []
            if isinstance(topics, list) and topics:
                for t in topics:
                    if not isinstance(t, dict):
                        continue
                    t_title = str(t.get("title") or "").strip()
                    t_desc = str(t.get("description") or "").strip()
                    if t_title or t_desc:
                        bullet = f"- {t_title}" if t_title else "- 子议题"
                        if t_desc:
                            bullet += f"：{t_desc}"
                        lines.append(bullet)

            lines.append("")

    transitions = structure.get("transitions") or []
    if isinstance(transitions, list) and transitions:
        lines.append("**主题切换关系概览：**")
        for tr in transitions:
            if not isinstance(tr, dict):
                continue
            rel = str(tr.get("relation") or "").strip()
            from_id = str(tr.get("from") or "").strip()
            to_id = str(tr.get("to") or "").strip()
            is_jump = tr.get("is_jump")
            tag = "跳跃式" if is_jump else "关联式"
            if rel:
                lines.append(f"- ({tag}) {rel}")
            elif from_id or to_id:
                lines.append(f"- ({tag}) {from_id} → {to_id}")

    if not lines:
        return "未能根据当前结构生成清晰的回答。"

    return "\n".join(lines).strip()


def _generate_direct_answer_from_evidences(
    *,
    question_text: str,
    intent: QueryIntent,
    rag_briefs: List[Dict[str, Any]],
) -> str:
    """调用 DeepSeek 基于 evidences 直接生成任务导向的自然语言回答。"""

    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("[AnswerSynthesis] DEEPSEEK_API_KEY 未设置，无法生成直接回答")
        return "暂时无法生成回答：后端未配置 DeepSeek API Key。"

    model_name = os.getenv(
        "ANSWER_MODEL_NAME",
        os.getenv("INGEST_MODEL_NAME", "deepseek-chat"),
    )
    base_url = os.getenv(
        "ANSWER_MODEL_BASE_URL",
        os.getenv("INGEST_MODEL_BASE_URL", "https://api.deepseek.com"),
    ).rstrip("/")

    system_prompt = (
        "你是面向工程团队的中文 RAG 知识助手。\n"
        "- 信息来源是给定的内部工作记录/文档摘录。\n"
        "- 你的目标是基于这些摘录，给出直接、可执行的回答，优先帮用户完成当前任务。\n"
        "- 回答必须基于引用内容和常识推理，不要编造脚本名、路径或配置项。\n"
        "- 先正面回答问题本身（例如有/没有、如何操作），再补充必要说明。\n"
        "- 当问题涉及脚本/工具/配置/操作步骤时，优先给出名称、位置、命令示例和注意事项。\n"
        "- 如果信息不足，请明确说明不确定之处，并给出合理的下一步建议。\n"
        "- 使用简体中文，回答尽量简洁、有条理，可以使用列表。\n"
        "- 为了便于调试，请在回答的第一行先输出标记 [[RAG_DIRECT_V2]]，然后换行再给出正式回答内容。"
    )

    # 组装 user 提示词：包含原始问题和若干条精简的工作记录摘录
    lines: List[str] = []
    lines.append("【用户问题】")
    lines.append(question_text)
    lines.append("")
    lines.append("【相关工作记录摘录】")

    for idx, brief in enumerate(rag_briefs, start=1):
        entry_id = str(brief.get("entry_id") or "").strip()
        title = str(brief.get("title") or "").strip()
        created_at = str(brief.get("created_at") or "").strip()
        snippet = str(brief.get("snippet") or "").strip()

        lines.append(f"[记录#{idx}]")
        if entry_id:
            lines.append(f"ID: {entry_id}")
        if title:
            lines.append(f"标题: {title}")
        if created_at:
            lines.append(f"时间: {created_at}")
        if snippet:
            lines.append(f"内容摘录: {snippet}")
        lines.append("")

    user_prompt = "\n".join(lines)

    http_resp = None
    try:
        http_resp = requests.post(
            f"{base_url}/v1/chat/completions",
            json={
                "model": model_name,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "stream": False,
            },
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=600,
        )
        http_resp.raise_for_status()
    except Exception as e:  # noqa: BLE001
        status = http_resp.status_code if http_resp is not None else "<no http>"
        text_preview = http_resp.text[:400] if http_resp is not None else "<no body>"
        print(
            f"[AnswerSynthesis] 调用 deepseek-chat 生成直接回答失败: {e}; "
            f"status={status}; body={text_preview}"
        )
        return "暂时无法生成回答，请稍后重试。"

    try:
        data = http_resp.json()  # type: ignore[union-attr]
    except Exception as e:  # noqa: BLE001
        body_preview = http_resp.text[:800] if http_resp is not None else "<no response>"  # type: ignore[union-attr]
        print(
            f"[AnswerSynthesis] 解析 deepseek-chat 返回 JSON 失败: {e}; "
            f"body={body_preview}"
        )
        return "生成回答时出现解析错误，请稍后重试。"

    choices = data.get("choices") or []
    if not choices:
        print("[AnswerSynthesis] deepseek-chat 返回结果中不包含 choices 字段")
        return "未从模型获取到有效回答内容。"

    message = (choices[0] or {}).get("message") or {}
    text = str(message.get("content") or "").strip()

    if not text:
        print("[AnswerSynthesis] deepseek-chat 返回的 message.content 为空")
        return "模型未返回有效文本回答。"

    return text


def _generate_web_answer_from_evidences(
    *,
    question_text: str,
    intent: QueryIntent,
    web_evidences: List[Evidence],
) -> str:
    """基于 Web 证据生成多通讯社报道综述型回答。

    设计目标：
    - 适用于 "WEB" 模式下仅有 kind="web" 证据的场景；
    - 输入通常是一组新闻/通讯社报道（title + snippet + site + published_at）；
    - 输出一段中文综述：先讲清事件本身，再对比不同媒体的报道重点和态度，最后给出综合评价。
    """

    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("[AnswerSynthesis] DEEPSEEK_API_KEY 未设置，无法生成 Web 场景回答")
        return (
            "已检索到若干外部新闻报道，但后端尚未配置 DeepSeek API Key，"
            "因此暂时无法自动整理各家通讯社的观点，请直接查看引用的 sources。"
        )

    model_name = os.getenv(
        "ANSWER_MODEL_NAME",
        os.getenv("INGEST_MODEL_NAME", "deepseek-chat"),
    )
    base_url = os.getenv(
        "ANSWER_MODEL_BASE_URL",
        os.getenv("INGEST_MODEL_BASE_URL", "https://api.deepseek.com"),
    ).rstrip("/")

    intent_analysis = getattr(intent, "intent_analysis", "") or ""
    sub_queries = getattr(intent, "sub_queries", []) or []

    # 将 Web 证据压缩成便于 LLM 消化的结构
    web_briefs: List[Dict[str, Any]] = []
    for ev in web_evidences:
        meta = ev.source_meta or {}
        web_briefs.append(
            {
                "title": ev.title,
                "snippet": ev.snippet,
                "site": meta.get("site") or meta.get("url"),
                "url": meta.get("url"),
                "published_at": meta.get("published_at"),
            }
        )

    system_prompt = (
        "你是一个中文 Web 信息整理助手。\n"
        "\n"
        "【你的任务】\n"
        "- 基于用户的问题和一组来自互联网的网页摘要，对相关信息进行整理；\n"
        "- 尽量扣紧用户问题背后的主要意图来组织回答，而不是泛泛而谈；\n"
        "- 对多条来源中的相似内容做去重和合并，避免重复堆砌；\n"
        "- 将关键信息归纳成结构化、条理清晰的输出，便于阅读和后续使用；\n"
        "- 在不偏离事实素材的前提下，可以根据用户的主要意图以及给定素材，合理补齐你认为有必要的观点和内容。\n"
        "\n"
        "【输入说明】\n"
        "- 用户提出的任意主题问题；\n"
        "- 若干条网页摘要（通常包含标题、摘要、站点、链接、时间等元信息）；\n"
        "- 可选的查询意图分析和子查询列表，仅供你理解用户真实关注点。\n"
        "\n"
        "【输出要求】\n"
        "- 使用简体中文；\n"
        "- 回答内容应围绕用户问题的核心诉求展开；\n"
        "- 结构清晰，可以使用分段或列表使信息更有层次；\n"
        "- 不必强行进行立场分析、风险评估或后续行动建议，除非从用户问题中能明显看出这样的需求。"
    )

    user_payload: Dict[str, Any] = {
        "question": question_text,
        "intent_analysis": intent_analysis,
        "sub_queries": sub_queries,
        "web_evidences": web_briefs,
    }

    user_prompt = (
        "下面是本次查询的详细信息和已检索到的新闻摘要，请基于这些内容完成上面描述的任务。\n\n"
        "【用户问题】\n"
        f"{question_text}\n\n"
        "【查询意图分析（可选）】\n"
        f"{intent_analysis}\n\n"
        "【子查询列表（可选）】\n"
        f"{json.dumps(sub_queries, ensure_ascii=False)}\n\n"
        "【来自不同媒体的新闻摘要】(JSON 数组)\n"
        f"{json.dumps(web_briefs, ensure_ascii=False)}\n\n"
        "请基于上述内容给出综合性的中文分析回答。"
    )

    http_resp = None
    try:
        http_resp = requests.post(
            f"{base_url}/v1/chat/completions",
            json={
                "model": model_name,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "stream": False,
            },
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=600,
        )
        http_resp.raise_for_status()
    except Exception as e:  # noqa: BLE001
        status = http_resp.status_code if http_resp is not None else "<no http>"
        text_preview = http_resp.text[:400] if http_resp is not None else "<no body>"
        print(
            f"[AnswerSynthesis] 调用 deepseek-chat 生成 Web 场景回答失败: {e}; "
            f"status={status}; body={text_preview}"
        )
        return (
            "已检索到若干外部新闻来源，但在生成综合分析回答时出现错误，"
            "请先参考 sources 中列出的具体链接。"
        )

    try:
        data = http_resp.json()  # type: ignore[union-attr]
    except Exception as e:  # noqa: BLE001
        body_preview = http_resp.text[:800] if http_resp is not None else "<no response>"  # type: ignore[union-attr]
        print(
            f"[AnswerSynthesis] 解析 deepseek-chat Web JSON 失败: {e}; "
            f"body={body_preview}"
        )
        return (
            "生成 Web 场景回答时出现解析错误，请稍后重试，"
            "或直接查看 sources 中的具体新闻链接。"
        )

    choices = data.get("choices") or []
    if not choices:
        print("[AnswerSynthesis] deepseek-chat Web 返回中不包含 choices 字段")
        return "未从模型获取到有效的 Web 场景回答内容。"

    message = (choices[0] or {}).get("message") or {}
    text = str(message.get("content") or "").strip()

    if not text:
        print("[AnswerSynthesis] deepseek-chat Web 返回的 message.content 为空")
        return "模型未返回有效的 Web 场景回答文本。"

    return text
