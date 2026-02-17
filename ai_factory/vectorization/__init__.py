"""向量化策略模式 - 统一向量化接口

提供统一的向量化策略接口，支持多种向量化后端：
- DashScope (生产环境主用)
- Ollama (本地备用)
- DeepSeek (云端备用)

使用方式:
    from ai_factory.vectorization import get_strategy, VectorizationBackend
    
    # 获取默认策略 (DashScope)
    strategy = get_strategy()
    
    # 或者指定后端
    strategy = get_strategy(VectorizationBackend.OLLAMA)
    
    # 生成向量
    embedding = strategy.embed("需要向量化的文本")
    
    # 构建向量化文本
    text = strategy.build_text(entry_dict)
    
    # 保存向量
    strategy.save_embedding(entry_id, embedding)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Protocol
import os


class VectorizationBackend(Enum):
    """向量化后端类型"""
    DASHSCOPE = "dashscope"
    OLLAMA = "ollama"
    DEEPSEEK = "deepseek"


@dataclass
class EmbeddingConfig:
    """向量化配置"""
    model_name: str
    dimension: int
    batch_size: int = 50
    timeout: int = 60
    max_retries: int = 3


class VectorizationStrategy(ABC):
    """向量化策略抽象基类
    
    所有向量化后端必须实现此接口，确保统一调用方式。
    """
    
    def __init__(self, config: Optional[EmbeddingConfig] = None):
        self.config = config or self._default_config()
    
    @abstractmethod
    def _default_config(self) -> EmbeddingConfig:
        """返回默认配置"""
        pass
    
    @abstractmethod
    def embed(self, text: str) -> List[float]:
        """将文本转换为向量
        
        Args:
            text: 输入文本
            
        Returns:
            List[float]: 向量数组
            
        Raises:
            ValueError: 文本为空或无效
            RuntimeError: API调用失败
        """
        pass
    
    def build_text(self, entry: Dict[str, Any]) -> str:
        """构建用于向量化的文本
        
        默认实现：title + summary_ai + content[:2000]
        子类可以重写此方法实现自定义逻辑。
        
        Args:
            entry: entries表记录字典
            
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
        content = entry.get("input_content") or ""
        if content.strip():
            parts.append(f"内容: {content.strip()[:2000]}")
        
        return "\n\n".join(parts) or "(empty entry)"
    
    def save_embedding(
        self, 
        entry_id: str, 
        embedding: List[float],
        connection_scope=None
    ) -> bool:
        """保存向量到数据库
        
        Args:
            entry_id: 条目ID
            embedding: 向量数组
            connection_scope: 数据库连接上下文管理器（可选）
            
        Returns:
            bool: 是否成功
        """
        if connection_scope is None:
            from ai_factory.db.pgvector_client import connection_scope
        
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
            print(f"  [ERROR] Failed to save embedding: {e}")
            return False
    
    def process_entry(self, entry: Dict[str, Any]) -> bool:
        """处理单个entry：构建文本→生成向量→保存
        
        Args:
            entry: entries表记录，必须包含entry_id
            
        Returns:
            bool: 是否成功
        """
        entry_id = entry.get("entry_id")
        if not entry_id:
            print("  [ERROR] entry_id is required")
            return False
        
        try:
            # 1. 构建文本
            text = self.build_text(entry)
            
            # 2. 生成向量
            embedding = self.embed(text)
            
            # 3. 保存向量
            return self.save_embedding(entry_id, embedding)
            
        except Exception as e:
            print(f"  [ERROR] Failed to process entry {entry_id}: {e}")
            return False


class DashScopeStrategy(VectorizationStrategy):
    """DashScope向量化策略
    
    使用阿里云DashScope API，text-embedding-v4模型。
    生产环境主用策略。
    """
    
    def _default_config(self) -> EmbeddingConfig:
        return EmbeddingConfig(
            model_name=os.getenv("EMBEDDING_MODEL_NAME", "text-embedding-v4"),
            dimension=1024,
            batch_size=50,
            timeout=60
        )
    
    def embed(self, text: str) -> List[float]:
        """调用DashScope API生成向量"""
        import httpx
        
        if not text or not text.strip():
            raise ValueError("Input text cannot be empty")
        
        api_key = os.getenv("DASHSCOPE_API_KEY", "")
        if not api_key:
            raise RuntimeError("DASHSCOPE_API_KEY not configured")
        
        base_url = os.getenv(
            "DASHSCOPE_BASE_URL", 
            "https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        
        url = f"{base_url}/embeddings"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": self.config.model_name,
            "input": text,
            "encoding_format": "float",
            "parameters": {
                "text_type": "document"
            }
        }
        
        try:
            with httpx.Client(timeout=self.config.timeout) as client:
                response = client.post(url, json=data, headers=headers)
                response.raise_for_status()
                
                result = response.json()
                
                if "data" in result and len(result["data"]) > 0:
                    embedding = result["data"][0]["embedding"]
                    if len(embedding) != self.config.dimension:
                        raise ValueError(
                            f"Unexpected embedding dim {len(embedding)}, "
                            f"expected {self.config.dimension}"
                        )
                    return embedding
                else:
                    raise ValueError(f"Unexpected response format: {result}")
                    
        except httpx.HTTPStatusError as e:
            raise RuntimeError(f"DashScope API error: {e.response.status_code} - {e.response.text}")
        except Exception as e:
            raise RuntimeError(f"Failed to generate embedding: {e}")


class OllamaStrategy(VectorizationStrategy):
    """Ollama向量化策略
    
    使用本地Ollama服务，qwen3-embedding:4b模型。
    适用于离线环境或备用方案。
    """
    
    def _default_config(self) -> EmbeddingConfig:
        return EmbeddingConfig(
            model_name="qwen3-embedding:4b",
            dimension=1024,
            batch_size=10,
            timeout=120
        )
    
    def embed(self, text: str) -> List[float]:
        """调用Ollama本地服务生成向量"""
        import requests
        import json
        
        if not text or not text.strip():
            raise ValueError("Input text cannot be empty")
        
        ollama_url = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434/api/embeddings")
        
        payload = {
            "model": self.config.model_name,
            "prompt": text
        }
        
        try:
            response = requests.post(
                ollama_url, 
                data=json.dumps(payload), 
                timeout=self.config.timeout
            )
            response.raise_for_status()
            
            data = response.json()
            embedding = data.get("embedding", [])
            
            if not embedding:
                raise ValueError("Empty embedding returned from Ollama")
            
            # Ollama可能返回不同维度，需要检查
            if len(embedding) != self.config.dimension:
                print(f"  [WARN] Ollama returned dim {len(embedding)}, expected {self.config.dimension}")
            
            return embedding
            
        except requests.exceptions.ConnectionError:
            raise RuntimeError(
                f"Cannot connect to Ollama at {ollama_url}. "
                "Is Ollama running?"
            )
        except Exception as e:
            raise RuntimeError(f"Ollama embedding failed: {e}")


# 策略注册表
_strategy_registry: Dict[VectorizationBackend, type] = {
    VectorizationBackend.DASHSCOPE: DashScopeStrategy,
    VectorizationBackend.OLLAMA: OllamaStrategy,
}


def get_strategy(
    backend: Optional[VectorizationBackend] = None,
    config: Optional[EmbeddingConfig] = None
) -> VectorizationStrategy:
    """获取向量化策略实例
    
    Args:
        backend: 后端类型，默认从环境变量 VECTORIZATION_BACKEND 读取，
                未设置则使用 DASHSCOPE
        config: 自定义配置，None则使用默认配置
        
    Returns:
        VectorizationStrategy: 策略实例
        
    Raises:
        ValueError: 未知的后端类型
    """
    if backend is None:
        backend_str = os.getenv("VECTORIZATION_BACKEND", "dashscope").lower()
        try:
            backend = VectorizationBackend(backend_str)
        except ValueError:
            raise ValueError(f"Unknown backend: {backend_str}")
    
    strategy_class = _strategy_registry.get(backend)
    if strategy_class is None:
        raise ValueError(f"Backend {backend} not registered")
    
    return strategy_class(config)


def register_strategy(
    backend: VectorizationBackend, 
    strategy_class: type
) -> None:
    """注册自定义策略
    
    Args:
        backend: 后端类型枚举
        strategy_class: 策略类，必须继承VectorizationStrategy
    """
    if not issubclass(strategy_class, VectorizationStrategy):
        raise TypeError("Strategy class must inherit from VectorizationStrategy")
    
    _strategy_registry[backend] = strategy_class


def list_available_backends() -> List[str]:
    """列出所有可用的向量化后端"""
    return [backend.value for backend in _strategy_registry.keys()]


# 便捷函数 - 保持向后兼容
def generate_embedding(text: str, backend: Optional[str] = None) -> List[float]:
    """生成向量的便捷函数（向后兼容）
    
    Args:
        text: 输入文本
        backend: 后端名称（dashscope/ollama），默认dashscope
        
    Returns:
        List[float]: 向量
    """
    if backend:
        backend_enum = VectorizationBackend(backend.lower())
    else:
        backend_enum = VectorizationBackend.DASHSCOPE
    
    strategy = get_strategy(backend_enum)
    return strategy.embed(text)


def build_embedding_text(entry: Dict[str, Any]) -> str:
    """构建向量化文本的便捷函数（向后兼容）
    
    使用默认策略的build_text方法。
    """
    strategy = get_strategy()
    return strategy.build_text(entry)


def upsert_entry_embedding(
    entry: Dict[str, Any], 
    embedding: List[float]
) -> bool:
    """保存entry向量的便捷函数（向后兼容）
    
    使用默认策略的save_embedding方法。
    """
    entry_id = entry.get("entry_id")
    if not entry_id:
        raise ValueError("entry_id is required")
    
    strategy = get_strategy()
    return strategy.save_embedding(entry_id, embedding)
