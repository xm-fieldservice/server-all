"""统一向量化脚本：使用 DashScope API 向量化 entries 表

目标：
- 统一使用 DashScope text-embedding-v3 模型（1536维）
- 批量处理 entries 表，写入 entry_embeddings
- 支持增量更新（只处理未向量化的条目）
- 支持重新向量化（指定 entry_id）

使用方式：
    # 批量向量化所有未处理的 entries
    python vectorize_entries_with_dashscope.py

    # 指定批次大小
    python vectorize_entries_with_dashscope.py --batch-size 100

    # 指定最大批次
    python vectorize_entries_with_dashscope.py --max-batches 10

    # 重新向量化指定的 entry
    python vectorize_entries_with_dashscope.py --revectorize entry_id_1 entry_id_2

依赖：
- 已正确配置 DASHSCOPE_API_KEY 和 EMBEDDING_MODEL_NAME 环境变量
- 已重建 entry_embeddings 表（VECTOR(1536)）
"""

import argparse
import os
import time
from typing import List, Dict, Any, Optional

from dotenv import load_dotenv
import httpx

# 加载环境变量
load_dotenv('/home/ecs-assist-user/.env')

from ai_factory.db.pgvector_client import connection_scope


# DashScope API 配置
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
DASHSCOPE_BASE_URL = os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL_NAME", "text-embedding-v3")

# 向量维度
EMBEDDING_DIM = 1536

# 批处理配置
DEFAULT_BATCH_SIZE = 50
DEFAULT_MAX_BATCHES = None

# HTTP 客户端
HTTP_CLIENT = httpx.Client(timeout=60.0)


def generate_embedding(text: str) -> List[float]:
    """调用 DashScope API 生成 embedding

    Args:
        text: 输入文本

    Returns:
        List[float]: 1536维向量

    Raises:
        Exception: API调用失败
    """
    if not text or not text.strip():
        raise ValueError("Input text cannot be empty")

    url = f"{DASHSCOPE_BASE_URL}/embeddings"
    headers = {
        "Authorization": f"Bearer {DASHSCOPE_API_KEY}",
        "Content-Type": "application/json"
    }

    data = {
        "model": EMBEDDING_MODEL,
        "input": text,
        "encoding_format": "float"
    }

    response = HTTP_CLIENT.post(url, json=data, headers=headers)
    response.raise_for_status()

    result = response.json()

    # 提取 embedding
    if "data" in result and len(result["data"]) > 0:
        embedding = result["data"][0]["embedding"]
        if len(embedding) != EMBEDDING_DIM:
            raise ValueError(f"Unexpected embedding dim {len(embedding)}, expected {EMBEDDING_DIM}")
        return embedding
    else:
        raise ValueError(f"Unexpected response format: {result}")


def build_embedding_text(entry: Dict[str, Any]) -> str:
    """构建用于向量化的文本

    使用规则：title + summary_ai + content[:2000]

    Args:
        entry: entries 表的一条记录

    Returns:
        str: 用于向量化的文本
    """
    parts = []

    # 1. 标题
    title = entry.get("title") or ""
    if title.strip():
        parts.append(f"标题: {title.strip()}")

    # 2. AI摘要
    summary = entry.get("summary_ai") or ""
    if summary.strip():
        parts.append(f"摘要: {summary.strip()}")

    # 3. 内容（截断到2000字符）
    content = entry.get("content") or ""
    if content.strip():
        parts.append(f"内容: {content.strip()[:2000]}")

    return "\n\n".join(parts) or "(empty entry)"


def fetch_unembedded_entries(limit: int = 50) -> List[Dict[str, Any]]:
    """获取尚未向量化的 entries

    Args:
        limit: 返回数量限制

    Returns:
        List[Dict[str, Any]]: entries 列表
    """
    sql = """
        SELECT e.entry_id,
               e.title,
               e.summary_ai,
               e.content,
               e.created_at
        FROM entries e
        LEFT JOIN entry_embeddings emb ON e.entry_id = emb.entry_id
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


def fetch_entry_by_id(entry_id: str) -> Optional[Dict[str, Any]]:
    """根据 entry_id 获取记录

    Args:
        entry_id: 条目ID

    Returns:
        Optional[Dict[str, Any]]: entry 记录，不存在则返回 None
    """
    sql = """
        SELECT entry_id,
               title,
               summary_ai,
               content,
               created_at
        FROM entries
        WHERE entry_id = %s;
    """

    with connection_scope() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (entry_id,))
            row = cur.fetchone()
            if row is None:
                return None

            colnames = [d[0] for d in cur.description]
            return dict(zip(colnames, row))


def upsert_embedding(entry_id: str, embedding: List[float]) -> bool:
    """插入或更新向量到 entry_embeddings 表

    Args:
        entry_id: 条目ID
        embedding: 向量

    Returns:
        bool: 是否成功
    """
    sql = """
        INSERT INTO entry_embeddings (entry_id, embedding)
        VALUES (%s, %s)
        ON CONFLICT (entry_id) DO UPDATE SET
            embedding = EXCLUDED.embedding,
            created_at = CURRENT_TIMESTAMP;
    """

    try:
        with connection_scope() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (entry_id, embedding))
        return True
    except Exception as e:
        print(f"  [ERROR] Failed to upsert embedding: {e}")
        return False


def process_batch(entries: List[Dict[str, Any]]) -> int:
    """处理一批 entries

    Args:
        entries: entries 列表

    Returns:
        int: 成功处理的数量
    """
    success_count = 0

    for idx, entry in enumerate(entries, start=1):
        entry_id = entry.get("entry_id")
        try:
            # 1. 构建文本
            text = build_embedding_text(entry)

            # 2. 生成向量
            embedding = generate_embedding(text)

            # 3. 写入数据库
            if upsert_embedding(entry_id, embedding):
                success_count += 1
                print(f"  [{idx}/{len(entries)}] ✓ entry_id={entry_id}")
            else:
                print(f"  [{idx}/{len(entries)}] ✗ entry_id={entry_id} - database error")

        except Exception as e:
            print(f"  [{idx}/{len(entries)}] ✗ entry_id={entry_id} - {e}")

    return success_count


def revectorize_entries(entry_ids: List[str]) -> int:
    """重新向量化指定的 entries

    Args:
        entry_ids: entry_id 列表

    Returns:
        int: 成功处理的数量
    """
    success_count = 0

    for idx, entry_id in enumerate(entry_ids, start=1):
        try:
            # 1. 获取 entry
            entry = fetch_entry_by_id(entry_id)
            if entry is None:
                print(f"  [{idx}/{len(entry_ids)}] ✗ entry_id={entry_id} - not found")
                continue

            # 2. 构建文本
            text = build_embedding_text(entry)

            # 3. 生成向量
            embedding = generate_embedding(text)

            # 4. 写入数据库
            if upsert_embedding(entry_id, embedding):
                success_count += 1
                print(f"  [{idx}/{len(entry_ids)}] ✓ entry_id={entry_id}")
            else:
                print(f"  [{idx}/{len(entry_ids)}] ✗ entry_id={entry_id} - database error")

        except Exception as e:
            print(f"  [{idx}/{len(entry_ids)}] ✗ entry_id={entry_id} - {e}")

    return success_count


def main(batch_size: int, max_batches: Optional[int], revectorize: Optional[List[str]] = None):
    """主函数

    Args:
        batch_size: 每批处理的数量
        max_batches: 最大批次数（None表示不限制）
        revectorize: 要重新向量化的 entry_id 列表
    """
    # 检查 API 配置
    if not DASHSCOPE_API_KEY:
        print("ERROR: DASHSCOPE_API_KEY not found in environment variables")
        return

    print("=" * 60)
    print("统一向量化脚本 - DashScope API")
    print("=" * 60)
    print(f"  API Key: {DASHSCOPE_API_KEY[:10]}...")
    print(f"  Base URL: {DASHSCOPE_BASE_URL}")
    print(f"  Model: {EMBEDDING_MODEL}")
    print(f"  Embedding Dim: {EMBEDDING_DIM}")
    print("=" * 60)

    total_success = 0
    batch_count = 0

    if revectorize:
        # 模式1：重新向量化指定 entries
        print(f"\n模式: 重新向量化指定 entries ({len(revectorize)} 条)")
        total_success = revectorize_entries(revectorize)

    else:
        # 模式2：批量向量化未处理的 entries
        print(f"\n模式: 批量向量化未处理的 entries")
        print(f"  Batch Size: {batch_size}")
        print(f"  Max Batches: {max_batches or 'unlimited'}")
        print("\n开始处理...\n")

        while True:
            # 检查批次限制
            if max_batches is not None and batch_count >= max_batches:
                print(f"\n达到最大批次限制 ({max_batches})，停止处理")
                break

            # 获取一批未向量化的 entries
            entries = fetch_unembedded_entries(limit=batch_size)
            if not entries:
                print("\n所有 entries 已处理完成！")
                break

            print(f"\n批次 {batch_count + 1}: 处理 {len(entries)} 条 entries")
            batch_success = process_batch(entries)
            total_success += batch_success
            batch_count += 1

            # 防抖，避免对 API 和 DB 造成瞬时压力
            time.sleep(0.5)

    # 汇总
    print("\n" + "=" * 60)
    print("向量化完成")
    print("=" * 60)
    print(f"  成功处理: {total_success} 条")
    print(f"  批次数量: {batch_count}")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="统一向量化脚本 - DashScope API")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"每批处理的数量 (default: {DEFAULT_BATCH_SIZE})"
    )
    parser.add_argument(
        "--max-batches",
        type=int,
        default=DEFAULT_MAX_BATCHES,
        help="最大批次数 (default: unlimited)"
    )
    parser.add_argument(
        "--revectorize",
        nargs="*",
        help="重新向量化的 entry_id 列表"
    )

    args = parser.parse_args()

    try:
        main(
            batch_size=args.batch_size,
            max_batches=args.max_batches,
            revectorize=args.revectorize
        )
    except KeyboardInterrupt:
        print("\n\n用户中断")
    finally:
        HTTP_CLIENT.close()
