from __future__ import annotations

"""entries_ingest 调试链路（独立于正式入库链路）。

本模块提供一个单独的调试入口 `entries_ingest_debug`：
- 不修改现有 ai_factory.integrations.entries_ingest.entries_ingest 的行为；
- 复用相同的 prompt / 模型调用 / JSON 解析逻辑；
- 额外将关键中间状态写入调试日志，便于分析 LLM 输出和解析失败原因；
- 默认不写入数据库（write_db=False），只在需要时显式开启。

典型用法：

    from ai_factory.integrations.entries_ingest_debug import entries_ingest_debug

    result = entries_ingest_debug(
        {
            "raw_text": some_text,
            "project_code": "db_vec",
            "note_datetime": "2025-12-02 17:30:33",
        },
        debug_tag="db_vec_defect_retry INDEX=184",
        write_db=False,
    )

日志文件默认写入 ai-factory 根目录下的 logs/entries_ingest_debug.log。
可通过环境变量 ENTRIES_INGEST_DEBUG_LOG_PATH 自定义路径。
"""

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

import requests

from ai_factory.agents.entry_agents import ChunkResult
from ai_factory.db.entries_repo import insert_entry


@dataclass
class EntryIngestionResult:
    """单次规整/写入操作的聚合结果（与正式链路保持一致）。"""

    entries: List[ChunkResult]


def _get_debug_log_path() -> Path:
    """获取调试日志路径，若不存在 logs 目录则自动创建。

    优先使用 ENTRIES_INGEST_DEBUG_LOG_PATH，否则默认:
    - <ai-factory 根>/logs/entries_ingest_debug.log
    """

    env_path = os.getenv("ENTRIES_INGEST_DEBUG_LOG_PATH")
    if env_path:
        path = Path(env_path).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    # 默认：假定本文件在 ai_factory/integrations/ 下
    this_file = Path(__file__).resolve()
    root = this_file.parents[2]  # ai-factory 根目录
    logs_dir = root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir / "entries_ingest_debug.log"


def _log_debug_block(lines: List[str]) -> None:
    """追加写入一块调试信息到日志文件。

    每次调用写入一段分隔块，便于后续 grep / 对照查看。
    """

    log_path = _get_debug_log_path()

    ts = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    header = [
        "",  # 保证块之间有空行
        f"[DEBUG entries_ingest] {ts}",
        "----------------------------------------",
    ]
    footer = ["----------------------------------------", ""]

    text = "\n".join(header + lines + footer)
    try:
        with log_path.open("a", encoding="utf-8") as f:
            f.write(text)
    except Exception:
        # 调试日志失败不影响主流程
        pass


def entries_ingest_debug(
    payload: Dict[str, Any],
    *,
    debug_tag: Optional[str] = None,
    write_db: bool = False,
) -> Dict[str, Any]:
    """调试版入库链路：附加输出 prompt / LLM 输出 / JSON 解析过程。

    与正式 entries_ingest 的差异：
    - 独立实现在本模块，不改变原有 entries_ingest 行为；
    - 默认 write_db=False，仅用于分析 LLM 行为；
    - 额外记录：raw_text 长度、prompt 片段、模型返回原文片段、
      解析前的 candidate/json_text 片段，以及异常信息等。
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

    prompt = f"""
下面是一条完整的工作记录，请你严格按下面要求输出一个 JSON 对象：

字段要求：
1. title: 根据工作记录内容生成一个中文标题，简短但能准确概括主要内容，不要超过一行。
2. summary: 用中文对这条工作记录做内容概述，控制在大约 200~300 字内，不够就原样总结，不要为了凑字数重复内容。

输出要求：
- 只输出一个 JSON 对象，字段名固定为 title、summary。
- 不要输出解释文字或额外说明。

工作记录原文如下：
----------------
{raw_text}
----------------
"""

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
    candidate = ""
    json_text = ""

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

    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = candidate.split("\n", 1)[-1]
    if candidate.endswith("```"):
        candidate = candidate.rsplit("```", 1)[0]

    debug_lines.append("--- candidate after strip code fences (first 400 chars) ---")
    debug_lines.append(candidate[:400])

    start = candidate.find("{")
    end = candidate.rfind("}")
    json_text = (
        candidate[start : end + 1]
        if start != -1 and end != -1 and end > start
        else candidate
    )

    debug_lines.append(f"json_text_len = {len(json_text)}")
    debug_lines.append("--- json_text preview (first 400 chars) ---")
    debug_lines.append(json_text[:400])

    try:
        obj = json.loads(json_text)
        debug_lines.append("JSON_PARSE_RESULT = success")
    except Exception as e:
        debug_lines.append("JSON_PARSE_RESULT = failed")
        debug_lines.append(f"JSON_ERROR = {repr(e)}")
        _log_debug_block(debug_lines)
        raise ValueError(f"LLM 输出无法解析为 JSON: {e}; 原始输出: {text}") from e

    # 仅 title / summary 由模型生成；entry_id 与 content 由程序管理
    entry_id = f"ent_{uuid4().hex[:8]}"
    title = str(obj.get("title") or "").strip()
    summary = str(obj.get("summary") or "").strip()
    content = raw_text

    now = datetime.utcnow().isoformat(timespec="seconds") + "Z"

    entry: Dict[str, Any] = {
        "entry_id": entry_id,
        "title": title,
        "summary_ai": summary,
        "content": content,
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
        "entries": [asdict(c) for c in result.entries],
    }
