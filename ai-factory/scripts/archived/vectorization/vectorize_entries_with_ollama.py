from __future__ import annotations

"""Batch vectorize entries table into entry_embeddings using Ollama qwen3-embedding:4b.

v0 目标：
- 只读 rag_db.entries，写入 entry_embeddings；
- 以单条 entry 为向量单位，文本为 summary_ai + title + content[:2000]；
- 向量维度固定为 1024（来自 qwen3-embedding:4b）；
- 每次批量处理少量记录，方便你多次运行补齐。

使用方式（在 ai-factory 虚拟环境中）：

  python vectorize_entries_with_ollama.py

需要：
- Postgres 中已存在 entry_embeddings 表（VECTOR(2560)）；
- 本机已启动 Ollama，并已拉取 qwen3-embedding:4b 模型；
- AI_PG_* 环境变量已正确配置（复用 ai_factory.db.pgvector_client）。
"""

import json
import time
from typing import Any, Dict, List, Optional

import requests

from ai_factory.db.pgvector_client import connection_scope


OLLAMA_URL = "http://127.0.0.1:11434/api/embeddings"
EMBEDDING_MODEL = "qwen3-embedding:4b"
EMBEDDING_DIM = 1024

# 每批最多处理多少条 entries
BATCH_SIZE = 50
# content 截断长度
CONTENT_MAX_CHARS = 2000


def _build_embedding_text(entry: Dict[str, Any]) -> str:
    summary = (entry.get("summary_ai") or "").strip()
    title = (entry.get("title") or "").strip()

    parts: List[str] = []
    if summary:
        parts.append(summary)
    if title:
        parts.append(title)

    return "\n\n".join(parts) or "(empty entry)"


def fetch_unembedded_entries(limit: int = BATCH_SIZE) -> List[Dict[str, Any]]:
    """取还没有 embedding 的 entries，按 created_at 升序。

    约定：entry_embeddings.entry_id 为主键，缺失表示尚未向量化。
    """

    sql = """
        SELECT e.entry_id,
               e.title,
               e.summary_ai,
               e.input_content,
               e.project_code,
               e.user_id,
               e.created_at
        FROM entries e
        LEFT JOIN entry_embeddings emb
               ON e.entry_id = emb.entry_id
        WHERE emb.entry_id IS NULL
        ORDER BY e.created_at ASC
        LIMIT %s;
    """

    with connection_scope() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (limit,))
            rows = cur.fetchall()
            colnames = [d[0] for d in cur.description]

    return [dict(zip(colnames, row)) for row in rows]


def call_ollama_embedding(text: str, dimensions: int = None) -> List[float]:
    """调用 Ollama embeddings 接口，返回 1024 维向量。

    Args:
        text: 输入文本
        dimensions: 指定输出维度（默认1024），传入None则使用默认维度
    """
    payload = {
        "model": EMBEDDING_MODEL,
        "prompt": text,
    }
    if dimensions:
        payload["dimensions"] = dimensions
    resp = requests.post(OLLAMA_URL, data=json.dumps(payload), timeout=60)
    resp.raise_for_status()
    data = resp.json()

    emb = data.get("embedding")
    if not isinstance(emb, list):
        raise ValueError(f"Unexpected embedding response format: {data}")
    expected_dim = dimensions if dimensions else EMBEDDING_DIM
    if len(emb) != expected_dim:
        raise ValueError(
            f"Unexpected embedding dim {len(emb)}, expected {expected_dim}."
        )
    return [float(x) for x in emb]


def upsert_entry_embedding(entry: Dict[str, Any], embedding: List[float]) -> None:
    """将向量写入 entry_embeddings 表。

    使用 INSERT ... ON CONFLICT 保证幂等。
    """

    sql = """
        INSERT INTO entry_embeddings (
            entry_id,
            embedding,
            project_code,
            user_id,
            mode,
            created_at
        ) VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (entry_id) DO UPDATE SET
            embedding    = EXCLUDED.embedding,
            project_code = EXCLUDED.project_code,
            user_id      = EXCLUDED.user_id,
            mode         = EXCLUDED.mode,
            created_at   = EXCLUDED.created_at;
    """

    with connection_scope() as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql,
                (
                    entry["entry_id"],
                    embedding,
                    entry.get("project_code"),
                    entry.get("user_id"),
                    entry.get("mode"),
                    entry.get("created_at"),
                ),
            )


def process_batch(limit: int = BATCH_SIZE) -> int:
    """处理一批尚未向量化的 entries，返回本批处理条数。"""

    entries = fetch_unembedded_entries(limit=limit)
    if not entries:
        print("没有找到需要向量化的 entries。")
        return 0

    print(f"本批待向量化 entries 数量: {len(entries)}")

    for idx, entry in enumerate(entries, start=1):
        entry_id = entry.get("entry_id")
        try:
            text = _build_embedding_text(entry)
            emb = call_ollama_embedding(text)
            upsert_entry_embedding(entry, emb)
            print(f"[{idx}/{len(entries)}] entry_id={entry_id} 向量化完成。")
        except Exception as exc:  # noqa: BLE001
            print(f"[{idx}/{len(entries)}] entry_id={entry_id} 向量化失败: {exc}")

    return len(entries)


def main(max_batches: Optional[int] = None) -> None:
    """循环批处理 entries 直到完成或达到批次上限。"""

    total = 0
    batch_count = 0

    while True:
        if max_batches is not None and batch_count >= max_batches:
            break

        print("\n==== 新批次 ====")
        n = process_batch(limit=BATCH_SIZE)
        if n <= 0:
            break

        total += n
        batch_count += 1
        # 简单防抖，避免对 Ollama/DB 造成瞬时压力
        time.sleep(0.5)

    print(f"\n向量化结束，总计处理 entries: {total} 条，批次: {batch_count}。")


OLLAMA_CHAT_URL = "http://127.0.0.1:11434/api/generate"
CHAT_MODEL = "qwen3:14b"


def call_ollama_chat(prompt: str, max_tokens: int = 500, temperature: float = 0.3) -> str:
    """调用Ollama Chat API生成内容（用于title/summary生成）。

    Args:
        prompt: 提示词
        max_tokens: 最大生成token数
        temperature: 温度（越低越确定性）

    Returns:
        生成的文本
    """
    payload = {
        "model": CHAT_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_predict": max_tokens,
            "temperature": temperature
        }
    }

    try:
        resp = requests.post(OLLAMA_CHAT_URL, json=payload, timeout=180)
        resp.raise_for_status()
        result = resp.json()
        return result.get("response", "").strip()
    except Exception as e:
        raise RuntimeError(f"Ollama Chat 调用失败: {e}")


def generate_title_with_ollama(content: str, max_length: int = 60) -> str:
    """使用本地Ollama生成简洁标题。

    Args:
        content: 原始内容
        max_length: 标题最大长度

    Returns:
        生成的标题
    """
    prompt = f"""
你是一个工作记录标题生成助手。请根据以下内容生成一个简洁的中文标题。

要求：
1. 长度不超过{max_length}个中文字符
2. 只使用原文中已出现的信息
3. 不要添加原文中没有的背景或细节
4. 标题要清晰表达核心内容

内容：
---
{content}
---

请直接输出标题，不要任何解释或格式标记。
"""
    return call_ollama_chat(prompt, max_tokens=max_length, temperature=0.2)


def generate_summary_with_ollama(content: str, max_length: int = 500) -> str:
    """使用本地Ollama生成摘要。

    Args:
        content: 原始内容
        max_length: 摘要最大长度

    Returns:
        生成的摘要
    """
    prompt = f"""
你是一个工作记录摘要助手。请根据以下内容生成一个中文摘要。

要求：
1. 长度约{max_length}个字
2. 保留关键决策、问题和方案
3. 不要添加原文没有的推测
4. 使用简洁的Markdown段落格式

内容：
---
{content}
---

请直接输出摘要，不要任何解释或格式标记。
"""
    return call_ollama_chat(prompt, max_tokens=max_length, temperature=0.3)


if __name__ == "__main__":
    main()
