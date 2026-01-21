#!/usr/bin/env python3
"""测试 DashScope Embedding API"""

import asyncio
import httpx
import os
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

async def test_dashscope_embedding():
    """测试 DashScope Embedding API"""
    api_key = os.getenv("DASHSCOPE_API_KEY", "")
    base_url = "https://dashscope.aliyuncs.com/api/v1"
    model = "text-embedding-v3"
    
    url = f"{base_url}/services/embeddings/text-embedding/text-embedding"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    data = {
        "model": model,
        "input": {
            "texts": ["测试文本"]
        },
        "parameters": {
            "text_type": "document"
        }
    }
    
    print(f"URL: {url}")
    print(f"Model: {model}")
    print(f"Request: {data}")
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, json=data, headers=headers)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"Result keys: {list(result.keys())}")
            if "output" in result and "embeddings" in result["output"]:
                embedding = result["output"]["embeddings"][0]["embedding"]
                print(f"Embedding length: {len(embedding)}")

if __name__ == "__main__":
    asyncio.run(test_dashscope_embedding())
