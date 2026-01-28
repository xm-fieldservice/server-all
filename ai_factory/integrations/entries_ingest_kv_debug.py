from __future__ import annotations

"""entries_ingest 的 Key-Value 协议调试链路。

本模块提供 `entries_ingest_kv_debug`：
- 不修改现有 entries_ingest / entries_ingest_debug 的行为；
- 使用“标题: … / 小结: …”两行文本协议替代 JSON 协议；
- 复用相同的模型调用方式和写库逻辑；
- 便于在缺陷笔记场景下对比 JSON 协议与 KV 协议的稳定性。
"""

import os
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

import requests

from ai_factory.agents.entry_agents import ChunkResult
from ai_factory.db.entries_repo import insert_entry
from ai_factory.integrations.entries_ingest_debug import (
    EntryIngestionResult,
    _get_debug_log_path,
    _log_debug_block,
)


def _build_kv_prompt(raw_text: str) -> str:
    """构造 Key-Value 协议的提示词。"""

    return f"""
下面是一条完整的工作记录，请你严格按下面要求输出两行文本，用于生成标题和小结。

输出格式要求（务必逐字遵守）：
1. 第一行：以“标题: ”开头，后面跟上一句中文标题，简短但能准确概括主要内容，不要超过一行。
2. 第二行：以“小结: ”开头，后面跟上一段中文小结，控制在大约 200~300 字内，不够就原样总结，不要为了凑字数重复内容。

重要限制：
- 只输出这两行，不要输出任何多余文字（不要加 markdown 标题、不要加代码块、不要解释、不要空行）。
- “标题: ”和“小结: ”这两个前缀必须是半角冒号和一个空格，不能改成别的写法。

工作记录原文如下：
----------------
{raw_text}
----------------
"""


def _parse_kv_output(text: str) -> Dict[str, str]:
    """解析模型输出的 Key-Value 文本，返回 {title, summary}。

    期望格式：
        标题: ...
        小结: ...
    """

    lines = [ln.strip("\r") for ln in text.splitlines() if ln.strip()]
    if len(lines) < 2:
        raise ValueError("KV 输出行数不足 2")

    line1, line2 = lines[0], lines[1]
    prefix_title = "标题: "
    prefix_summary = "小结: "

    if not line1.startswith(prefix_title):
        raise ValueError(f"首行未以 '标题: ' 开头: {line1!r}")
    if not line2.startswith(prefix_summary):
        raise ValueError(f"第二行未以 '小结: ' 开头: {line2!r}")

    title = line1[len(prefix_title) :].strip()
    summary = line2[len(prefix_summary) :].strip()

    if not title:
        raise ValueError("标题内容为空")
    if not summary or len(summary) < 10:
        raise ValueError("小结内容过短")

    return {"title": title, "summary": summary}


def entries_ingest_kv_debug(
    payload: Dict[str, Any],
    *,
    debug_tag: Optional[str] = None,
    write_db: bool = False,
) -> Dict[str, Any]:
    """使用 Key-Value 协议的调试版入库链路。

    - 与 entries_ingest_debug 类似，但不再依赖 JSON 解析；
    - 仅解析“标题: … / 小结: …”两行文本；
    - 默认 write_db=False，作为调试/对比用途，需要时可显式开启写库。
    """

    raw_text = str(payload.get("raw_text", "")).strip()
    if not raw_text:
        raise ValueError("payload.raw_text 不能为空")

    base_meta: Dict[str, Any] = {}
    for key in ("project_code", "user_id", "note_datetime"):
        if key in payload:
            base_meta[key] = payload[key]

    extra_ctx = payload.get("extra_context") or {}
    if isinstance(extra_ctx, dict):
        base_meta.update(extra_ctx)

    # 默认使用 DeepSeek 官方 API 的 deepseek-chat 模型
    model_name = os.getenv("INGEST_MODEL_NAME", "deepseek-chat")
    base_url = os.getenv("INGEST_MODEL_BASE_URL", "https://api.deepseek.com").rstrip("/")

    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY 未设置，无法调用 deepseek-chat API")

    prompt = _build_kv_prompt(raw_text)

    debug_lines: List[str] = []
    debug_lines.append(f"debug_tag = {debug_tag!r}")
    debug_lines.append(f"model_name = {model_name!r}")
    debug_lines.append(f"base_url = {base_url!r}")
    debug_lines.append(f"raw_text_len = {len(raw_text)}")
    debug_lines.append(f"raw_text_preview = {raw_text[:400].replace(chr(10), ' ')}...")
    debug_lines.append("--- prompt preview (first 400 chars) ---")
    debug_lines.append(prompt[:400].replace("\n", " ") + "...")

    http_resp = None
    text = ""

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
        debug_lines.append(f"HTTP_ERROR = {repr(e)}")
        if http_resp is not None:
            debug_lines.append(f"http_status = {http_resp.status_code}")
            debug_lines.append(f"http_text_preview = {http_resp.text[:400]}...")
        _log_debug_block(debug_lines)
        raise RuntimeError(f"调用 deepseek-chat 失败: {e}") from e

    try:
        data = http_resp.json()  # type: ignore[union-attr]
    except Exception as e:  # noqa: BLE001
        body_preview = http_resp.text[:800] if http_resp is not None else "<no response>"  # type: ignore[union-attr]
        debug_lines.append(f"PARSE_HTTP_JSON_ERROR = {repr(e)}")
        debug_lines.append(f"http_body_preview = {body_preview}")
        _log_debug_block(debug_lines)
        raise RuntimeError(f"解析 deepseek-chat 返回 JSON 失败: {e}; text={body_preview}") from e

    # OpenAI 风格响应：从 choices[0].message.content 提取文本
    choices = data.get("choices") or []
    if not choices:
        debug_lines.append("API_RESPONSE_HAS_NO_CHOICES")
        _log_debug_block(debug_lines)
        raise RuntimeError("deepseek-chat 返回结果中不包含 choices 字段")

    message = (choices[0] or {}).get("message") or {}
    text = str(message.get("content") or "")
    debug_lines.append(f"llm_raw_output_len = {len(text)}")
    debug_lines.append("--- llm_raw_output preview (first 800 chars) ---")
    debug_lines.append(text[:800])

    try:
        kv = _parse_kv_output(text)
        debug_lines.append("KV_PARSE_RESULT = success")
    except Exception as e:  # noqa: BLE001
        debug_lines.append("KV_PARSE_RESULT = failed")
        debug_lines.append(f"KV_ERROR = {repr(e)}")
        _log_debug_block(debug_lines)
        raise ValueError(f"LLM 输出无法解析为 KV 格式: {e}; 原始输出: {text}") from e

    entry_id = f"ent_{uuid4().hex[:8]}"
    title = str(kv.get("title") or "").strip()
    summary = str(kv.get("summary") or "").strip()
    content = raw_text

    now = datetime.utcnow().isoformat(timespec="seconds") + "Z"

    entry: Dict[str, Any] = {
        "entry_id": entry_id,
        "title": title,
        "summary_ai": summary,
        "input_content": content,
        "created_at": base_meta.get("note_datetime") or now,
    }

    if "project_code" in base_meta:
        entry["project_code"] = base_meta["project_code"]
    if "user_id" in base_meta:
        entry["user_id"] = base_meta["user_id"]

    debug_lines.append(f"final_title = {title!r}")
    debug_lines.append(f"final_summary_len = {len(summary)}")
    debug_lines.append(f"write_db = {write_db}")

    if write_db:
        try:
            insert_entry(entry)
            debug_lines.append("DB_WRITE_RESULT = success")
        except Exception as e:  # noqa: BLE001
            debug_lines.append("DB_WRITE_RESULT = failed")
            debug_lines.append(f"DB_ERROR = {repr(e)}")
            _log_debug_block(debug_lines)
            raise

    chunk = ChunkResult(entry_id=entry_id, title=title, content=content)
    result = EntryIngestionResult(entries=[chunk])

    _log_debug_block(debug_lines)

    return {
        "entries": [
            {
                "entry_id": c.entry_id,
                "title": c.title,
                "content": c.content,
            }
            for c in result.entries
        ],
    }
