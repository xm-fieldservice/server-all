#!/usr/bin/env python3
"""DeepSeek Embedding 实现

为 ai_factory.integrations.entries_ingest 提供向量化相关函数。

主要修改：
- 使用 DeepSeek API 生成 embedding，替代 Ollama
"""

from __future__ import annotations

from typing import List
import os
import requests
from datetime import datetime

# DeepSeek API 配置
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")

# 默认 embedding 模型
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL_NAME", "deepseek-embedding")


def call_deepseek_embedding(text: str, model: str = EMBEDDING_MODEL) -> List[float]:
    """使用 DeepSeek API 生成文本的 embedding 向量。
    
    Args:
        text: 输入文本
        model: embedding 模型名称，默认 deepseek-embedding
        
    Returns:
        List[float]: embedding 向量
        
    Raises:
        ValueError: 如果 API 调用失败
    """
    if not text or not text.strip():
        raise ValueError("text 不能为空")
    
    if not DEEPSEEK_API_KEY:
        raise ValueError("DEEPSEEK_API_KEY 环境变量未设置")
    
    # DeepSeek embedding API 端点
    url = f"{DEEPSEEK_BASE_URL}/embeddings"
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}"
    }
    
    payload = {
        "model": model,
        "input": text
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        
        result = response.json()
        
        # DeepSeek API 返回格式：
        # {
        #   "object": "list",
        #   "data": [
        #     {
        #       "embedding": [0.1, 0.2, ...],
        #       "index": 0,
        #       ...
        #     }
        #   ],
        #   "model": "deepseek-embedding",
        #   "usage": {...}
        # }
        
        if "data" in result and len(result["data"]) > 0:
            return result["data"][0]["embedding"]
        else:
            raise ValueError(f"DeepSeek API 返回格式异常: {result}")
            
    except requests.exceptions.Timeout:
        raise ValueError(f"DeepSeek API 请求超时")
    except requests.exceptions.RequestException as e:
        raise ValueError(f"DeepSeek API 请求失败: {e}")
    except Exception as e:
        raise ValueError(f"DeepSeek API 调用异常: {e}")


def _build_embedding_text(entry: dict) -> str:
    """构建用于 embedding 的文本。
    
    从 entry 中提取相关信息，组合成适合 embedding 的文本。
    
    Args:
        entry: 条目字典
        
    Returns:
        str: 用于 embedding 的文本
    """
    # 提取 title 和 input_content
    title = entry.get("title", "")
    content = entry.get("input_content", entry.get("content", ""))
    
    # 组合标题和内容
    if title and content:
        return f"{title}\n{content}"
    elif title:
        return title
    elif content:
        return content
    else:
        return ""


def upsert_entry_embedding(entry: dict, embedding: List[float]) -> None:
    """将 embedding 存储到 entry_embeddings 表中。
    
    Args:
        entry: 条目字典，包含 entry_id 和其他字段
        embedding: embedding 向量
    """
    from ai_factory.db.pgvector_client import connection_scope
    from ai_factory.db.entries_repo import get_entry
    
    if not embedding:
        raise ValueError("embedding 不能为空")
    
    entry_id = entry.get("entry_id")
    if not entry_id:
        raise ValueError("entry_id 不能为空")
    
    # 使用 pgvector_client 的 connection_scope
    with connection_scope() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO entry_embeddings (entry_id, embedding)
                VALUES (%s, %s)
                ON CONFLICT (entry_id) DO UPDATE SET
                    embedding = EXCLUDED.embedding,
                    created_at = CURRENT_TIMESTAMP
            """, (entry_id, embedding))


if __name__ == "__main__":
    # 测试代码
    test_text = "这是一条测试文本"
    embedding = call_deepseek_embedding(test_text)
    print(f"Embedding 向量长度: {len(embedding)}")
    print(f"前 5 个维度: {embedding[:5]}")
