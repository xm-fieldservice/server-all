from __future__ import annotations

"""批量刷新 entries 表中的 title/summary，并重新写入向量库 entry_embeddings。

使用说明：

    # 在 ai-factory 虚拟环境中、项目根目录下执行
    python refresh_titles_summaries_and_embeddings.py

依赖：
- 复用 entries_ingest 中的 DeepSeek 配置（INGEST_MODEL_NAME, INGEST_MODEL_BASE_URL, DEEPSEEK_API_KEY）
- 复用 vectorize_entries_with_ollama 中的向量化逻辑（_build_embedding_text, call_ollama_embedding, upsert_entry_embedding）

安全性：
- 会对 entries.title / entries.summary_ai 做 UPDATE；
- 会对 entry_embeddings 做 UPSERT（覆盖旧 embedding）。
- 建议先在测试库或少量数据上试跑，再在全量数据上跑。
"""

import json
import os
from json import JSONDecodeError
from typing import Any, Dict, List, Optional

import requests

from ai_factory.db.pgvector_client import connection_scope
from ai_factory.vectorize_entries_with_ollama import (
    _build_embedding_text,
    call_ollama_embedding,
    upsert_entry_embedding,
)


def _build_title_summary(raw_text: str) -> Dict[str, str]:
    """使用与 entries_ingest 相同的提示词，为一条原始内容生成 title/summary。"""

    raw_text = (raw_text or "").strip()
    if not raw_text:
        return {"title": "", "summary": ""}

    # 与 entries_ingest 一致的模型配置
    model_name = os.getenv("INGEST_MODEL_NAME", "deepseek-chat")
    base_url = os.getenv("INGEST_MODEL_BASE_URL", "https://api.deepseek.com").rstrip("/")

    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY 未设置，无法调用 deepseek-chat API")

    prompt = f"""
下面是一条完整的工作记录，请你严格按下面要求输出一个 JSON 对象：

字段要求：
1. title: 根据工作记录内容生成一个中文标题，可以略长一些（例如 20~40 个中文字符），最长不超过约 60 字；在一行内尽量包含关键脚本/模块/对象/目的等关键信息，同时保持可读。
2. summary: 用中文对这条工作记录做内容概述，一般控制在大约 300~600 字内，summary 字段的内容请使用 Markdown 结构化格式输出。
   - 如果内容较多，可以适当写长一些，只要结构清晰、不要为了凑字数重复内容即可。
   - 建议使用**结构化表达**（Markdown 标题 + 无序列表/有序列表等），但**不要生硬套用固定模版**，而是根据原文的自然结构来梳理：
     - 可以按时间阶段、任务子模块、问题与方案、尝试与结果等维度划分小节；
     - 小节标题自由命名，例如“问题现象与影响”、“排查思路”、“尝试方案A/B”、“结论与后续计划”等；
     - 每个小节内部用列表列出关键事实、命令、脚本、参数、结论。
   - 在不改变事实的前提下，尽量在 summary 中保留原文中出现的显式时间、地点、人名、重要概念等专有名词，以自然的方式融入总结，不要生造内容。
   - 如果工作记录中提到了脚本、程序、SQL、配置文件、关键命令等与代码/操作相关的对象，请在 summary 中明确写出：
     - 对应的名称（例如脚本名、文件名、SQL 名称、命令行工具等），以及
     - 关键路径或所在模块/用途（例如位于哪个目录、用于对齐何种数据、用于检查/修复什么问题等），以及
     - 如有典型的调用方式或关键参数（例如命令行示例、主要参数名），也用一行简要说明。
   - 如果没有此类对象，则按普通工作记录总结即可。

输出要求：
- 只输出一个 JSON 对象，字段名固定为 title、summary。
- 不要输出解释文字或额外说明。

工作记录原文如下：
----------------
{raw_text}
----------------
"""

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
        raise RuntimeError(f"调用 deepseek-chat 失败: {e}") from e

    try:
        data = http_resp.json()
    except JSONDecodeError as e:  # noqa: BLE001
        raise RuntimeError(
            f"解析 deepseek-chat 返回 JSON 失败: {e}; text={http_resp.text[:500]}"
        ) from e

    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("deepseek-chat 返回结果中不包含 choices 字段")

    message = (choices[0] or {}).get("message") or {}
    text = str(message.get("content") or "")

    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = candidate.split("\n", 1)[-1]
    if candidate.endswith("```"):
        candidate = candidate.rsplit("```", 1)[0]
    start = candidate.find("{")
    end = candidate.rfind("}")
    json_text = (
        candidate[start : end + 1]
        if start != -1 and end != -1 and end > start
        else candidate
    )

    try:
        obj = json.loads(json_text)
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"LLM 输出无法解析为 JSON: {e}; 原始输出: {text}") from e

    title = str(obj.get("title") or "").strip()
    summary = str(obj.get("summary") or "").strip()
    return {"title": title, "summary": summary}


def _fetch_entries(batch_size: int = 50, since_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """按 entry_id 升序分批获取 entries 记录。

    - 如提供 since_id，则只取 entry_id 大于该值的记录。
    - 这里假设 entry_id 可按字符串做简单顺序（ent_xxxx 风格）。
    """

    conditions: List[str] = []
    params: List[Any] = []

    if since_id is not None:
        conditions.append("entry_id > %s")
        params.append(since_id)

    where_sql = ""
    if conditions:
        where_sql = "WHERE " + " AND ".join(conditions)

    sql = f"""
        SELECT entry_id, title, summary_ai, content, project_code, user_id, created_at
        FROM entries
        {where_sql}
        ORDER BY entry_id ASC
        LIMIT %s;
    """
    params.append(batch_size)

    with connection_scope() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
            colnames = [d[0] for d in cur.description]

    return [dict(zip(colnames, row)) for row in rows]


def _update_entry_title_summary(entry_id: str, title: str, summary: str) -> None:
    sql = "UPDATE entries SET title = %s, summary_ai = %s WHERE entry_id = %s"
    with connection_scope() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (title, summary, entry_id))


def _reprocess_specific_entries(entry_ids: List[str]) -> None:
    processed = 0

    for entry_id in entry_ids:
        with connection_scope() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT entry_id, title, summary_ai, content, project_code, user_id, created_at "
                    "FROM entries WHERE entry_id = %s",
                    (entry_id,),
                )
                row = cur.fetchone()
                if row is None:
                    print(f"[entry {entry_id}] 未找到记录，跳过。")
                    continue

                colnames = [d[0] for d in cur.description]
                entry = dict(zip(colnames, row))

        content = str(entry.get("content") or "")

        try:
            ts = _build_title_summary(content)
            new_title = ts["title"]
            new_summary = ts["summary"]

            _update_entry_title_summary(entry_id, new_title, new_summary)

            entry["title"] = new_title
            entry["summary_ai"] = new_summary

            emb_text = _build_embedding_text(entry)
            embedding = call_ollama_embedding(emb_text)

            entry_for_embedding = dict(entry)
            entry_for_embedding.setdefault("mode", "NOTE")
            upsert_entry_embedding(entry_for_embedding, embedding)

            processed += 1
            print(f"[entry {entry_id}] 补处理完成，已更新 title/summary + embedding。")
        except Exception as exc:  # noqa: BLE001
            print(f"[entry {entry_id}] 补处理失败: {exc!r}")

    print(f"\n补处理完成，共处理指定 entries: {processed} 条。")


def process_all_entries(batch_size: int = 50) -> None:
    """分批处理所有 entries：

    - 使用当前提示词重新生成 title/summary（Markdown 结构化，但不强制固定章节名）；
    - 更新 entries 表中的 title/summary_ai 字段；
    - 基于新的 title+summary 文本重新计算 embedding，并写入 entry_embeddings。
    """

    processed = 0
    last_id: Optional[str] = None

    while True:
        batch = _fetch_entries(batch_size=batch_size, since_id=last_id)
        if not batch:
            break

        print(f"\n==== 新批次，条数: {len(batch)} (since_id={last_id}) ====")

        for entry in batch:
            entry_id = str(entry.get("entry_id"))
            content = str(entry.get("content") or "")

            try:
                # 1）用 DeepSeek 重新生成标题和摘要（Markdown 结构化）
                ts = _build_title_summary(content)
                new_title = ts["title"]
                new_summary = ts["summary"]

                _update_entry_title_summary(entry_id, new_title, new_summary)

                # 更新 entry dict 以便构造 embedding 文本
                entry["title"] = new_title
                entry["summary_ai"] = new_summary

                # 2）基于新的 title+summary 重算 embedding
                emb_text = _build_embedding_text(entry)
                embedding = call_ollama_embedding(emb_text)

                entry_for_embedding = dict(entry)
                entry_for_embedding.setdefault("mode", "NOTE")
                upsert_entry_embedding(entry_for_embedding, embedding)

                processed += 1
                print(f"[entry {entry_id}] 已更新 title/summary + embedding。")
            except Exception as exc:  # noqa: BLE001
                print(f"[entry {entry_id}] 处理失败: {exc!r}")

            last_id = entry_id

    print(f"\n处理完成，总计更新 entries: {processed} 条（包含重算 embedding）。")


def main() -> None:
    # 临时补处理：仅针对之前失败的少量记录重新生成 title/summary + embedding。
    target_ids = [
        "ent_a8396f16",
        "ent_a8f94d50",
    ]
    _reprocess_specific_entries(target_ids)


if __name__ == "__main__":
    main()
