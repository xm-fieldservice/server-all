from __future__ import annotations

import os
from typing import Any, Dict, List

import requests


def generate_answer_via_deepseek(question: str, citations: List[Dict[str, Any]]) -> str:
    question = (question or "").strip()
    if not question:
        return ""

    if not citations:
        return "暂无可用参考记录，无法生成回答。"

    lines: List[str] = []
    lines.append("你是一名中文知识助手，任务是基于给定的工作记录摘录来回答用户的问题。")
    lines.append("\n【回答规则】")
    lines.append("1. 必须使用简体中文回答。")
    lines.append("2. 面向终端用户，用自然语言连贯地回答，不要罗列 JSON。")
    lines.append("3. 允许引用、总结、归纳给定的工作记录内容，但不要编造明显与记录无关的事实。")
    lines.append("4. 如果记录中信息不足以准确回答，请明确说明不确定之处，并给出你能推断的部分。")
    lines.append("5. 不要在回答中提到“检索”“向量”“entries 表”等内部实现细节。")

    lines.append("\n【用户问题】")
    lines.append(question)

    lines.append("\n【可用参考工作记录】")
    for idx, c in enumerate(citations, start=1):
        title = str(c.get("title") or "").strip()
        summary_ai = str(c.get("summary_ai") or "").strip()
        created_at = str(c.get("created_at") or "").strip()
        lines.append(f"[记录#{idx}]")
        if title:
            lines.append(f"标题: {title}")
        if created_at:
            lines.append(f"时间: {created_at}")
        if summary_ai:
            lines.append(f"概要: {summary_ai}")
        lines.append("")

    lines.append("请根据以上工作记录，为用户的问题生成一个完整、清晰、结构化的中文回答。")

    prompt = "\n".join(lines)

    model_name = os.getenv("ANSWER_MODEL_NAME", os.getenv("INGEST_MODEL_NAME", "deepseek-chat"))
    base_url = os.getenv("ANSWER_MODEL_BASE_URL", os.getenv("INGEST_MODEL_BASE_URL", "https://api.deepseek.com")).rstrip("/")

    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("[RAG-answer] DEEPSEEK_API_KEY 未设置，无法调用 deepseek-chat API")
        return "暂时无法生成回答：后端未配置 DeepSeek API Key。"

    http_resp = None
    try:
        http_resp = requests.post(
            f"{base_url}/v1/chat/completions",
            json={
                "model": model_name,
                "messages": [
                    {"role": "user", "content": prompt},
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
        print(f"[RAG-answer] 调用 deepseek-chat 失败: {e}; status={status}; body={text_preview}")
        return "暂时无法生成 RAG 回答，请稍后重试。"

    try:
        data = http_resp.json()  # type: ignore[union-attr]
    except Exception as e:  # noqa: BLE001
        body_preview = http_resp.text[:800] if http_resp is not None else "<no response>"  # type: ignore[union-attr]
        print(f"[RAG-answer] 解析 deepseek-chat 返回 JSON 失败: {e}; body={body_preview}")
        return "生成 RAG 回答时出现解析错误，请稍后重试。"

    choices = data.get("choices") or []
    if not choices:
        print("[RAG-answer] deepseek-chat 返回结果中不包含 choices 字段")
        return "未从模型获取到有效回答内容。"

    message = (choices[0] or {}).get("message") or {}
    text = str(message.get("content") or "").strip()

    if not text:
        print("[RAG-answer] deepseek-chat 返回的 message.content 为空")
        return "模型未返回有效文本回答。"

    return text
