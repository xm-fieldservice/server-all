"""
LLM 和 Embedding 服务客户端
支持远端 API 调用：qwen3-embedding (DashScope) 和 deepseek-chat

新增功能：
- 指数退避重试机制
- 请求超时控制
- 请求缓存（减少重复调用）
"""

import os
import threading
import asyncio
import hashlib
import time
import logging
from typing import List, Dict, Any, Optional, Tuple
import httpx
from pydantic import BaseModel
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

logger = logging.getLogger(__name__)


class RequestCache:
    """简单的请求缓存类"""

    def __init__(self, max_size: int = 1000, ttl: int = 3600):
        """初始化请求缓存

        Args:
            max_size: 最大缓存条目数
            ttl: 缓存存活时间（秒），默认 1 小时
        """
        self._cache: Dict[str, Tuple[Any, float]] = {}
        self._max_size = max_size
        self._ttl = ttl
        self._lock = threading.Lock()

    def _generate_key(self, url: str, data: Dict[str, Any]) -> str:
        """生成缓存键

        Args:
            url: 请求 URL
            data: 请求数据

        Returns:
            str: 缓存键
        """
        # 将 URL 和数据序列化为字符串
        cache_str = f"{url}:{str(data)}"
        # 使用 MD5 生成键
        return hashlib.md5(cache_str.encode('utf-8')).hexdigest()

    def get(self, url: str, data: Dict[str, Any]) -> Optional[Any]:
        """从缓存中获取数据

        Args:
            url: 请求 URL
            data: 请求数据

        Returns:
            Optional[Any]: 缓存的数据，如果不存在或已过期则返回 None
        """
        key = self._generate_key(url, data)

        with self._lock:
            if key in self._cache:
                value, timestamp = self._cache[key]

                # 检查是否过期
                if time.time() - timestamp < self._ttl:
                    return value
                else:
                    # 过期，删除
                    del self._cache[key]

        return None

    def set(self, url: str, data: Dict[str, Any], value: Any) -> None:
        """将数据存入缓存

        Args:
            url: 请求 URL
            data: 请求数据
            value: 要缓存的数据
        """
        key = self._generate_key(url, data)

        with self._lock:
            # 如果缓存已满，删除最旧的条目
            if len(self._cache) >= self._max_size:
                oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k][1])
                del self._cache[oldest_key]

            # 存入缓存
            self._cache[key] = (value, time.time())

    def clear(self) -> None:
        """清空缓存"""
        with self._lock:
            self._cache.clear()

    def size(self) -> int:
        """获取缓存大小

        Returns:
            int: 缓存条目数
        """
        with self._lock:
            return len(self._cache)


class LLMConfig(BaseModel):
    """LLM 配置"""
    api_key: str
    base_url: str
    model: str


class EmbeddingConfig(BaseModel):
    """Embedding 配置"""
    api_key: str
    base_url: str
    model: str


class LLMClient:
    """LLM 和 Embedding 服务客户端

    新增功能：
    - 指数退避重试机制
    - 请求超时控制
    - 请求缓存
    """

    def __init__(
        self,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        retry_backoff_factor: float = 2.0,
        request_timeout: float = 60.0,
        enable_cache: bool = True,
        cache_ttl: int = 3600
    ):
        """初始化 LLM 客户端

        Args:
            max_retries: 最大重试次数
            retry_delay: 初始重试延迟（秒）
            retry_backoff_factor: 重试退避因子
            request_timeout: 请求超时（秒）
            enable_cache: 是否启用缓存
            cache_ttl: 缓存存活时间（秒）
        """
        self._llm_config = self._load_llm_config()
        self._embedding_config = self._load_embedding_config()

        # 重试配置
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        self._retry_backoff_factor = retry_backoff_factor

        # 请求超时
        self._request_timeout = request_timeout

        # 初始化 HTTP 客户端（带超时）
        self._http_client = httpx.AsyncClient(timeout=request_timeout)

        # 初始化缓存
        self._enable_cache = enable_cache
        self._embedding_cache = RequestCache(max_size=1000, ttl=cache_ttl) if enable_cache else None
        self._llm_cache = RequestCache(max_size=1000, ttl=cache_ttl) if enable_cache else None

        # 创建全局事件循环，避免 asyncio.run() 多次调用导致事件循环关闭
        self._loop = None
        self._loop_lock = threading.Lock()

    def _get_loop(self):
        """获取或创建事件循环"""
        with self._loop_lock:
            if self._loop is None or self._loop.is_closed():
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
            return self._loop

    def _load_llm_config(self) -> LLMConfig:
        """加载 LLM 配置"""
        api_key = os.getenv("DEEPSEEK_API_KEY", "")
        base_url = os.getenv("INGEST_MODEL_BASE_URL", "https://api.deepseek.com")
        model = os.getenv("INGEST_MODEL_NAME", "deepseek-chat")

        if not api_key:
            raise ValueError("DEEPSEEK_API_KEY not found in environment variables")

        return LLMConfig(
            api_key=api_key,
            base_url=base_url,
            model=model
        )

    def _load_embedding_config(self) -> EmbeddingConfig:
        """加载 Embedding 配置"""
        # qwen3-embedding 使用阿里云 DashScope API
        api_key = os.getenv("DASHSCOPE_API_KEY", "")
        # DashScope 原生 API base_url（不使用环境变量，直接指定）
        base_url = "https://dashscope.aliyuncs.com/api/v1"
        model = os.getenv("EMBEDDING_MODEL_NAME", "text-embedding-v3")

        if not api_key:
            raise ValueError("DASHSCOPE_API_KEY not found in environment variables")

        return EmbeddingConfig(
            api_key=api_key,
            base_url=base_url,
            model=model
        )

    async def _retry_with_backoff(
        self,
        func,
        *args,
        **kwargs
    ):
        """带指数退避的重试机制

        Args:
            func: 要重试的异步函数
            *args: 函数参数
            **kwargs: 函数关键字参数

        Returns:
            函数返回值

        Raises:
            最后一次尝试的异常
        """
        last_exception = None

        for attempt in range(self._max_retries):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                last_exception = e

                # 如果是最后一次尝试，直接抛出异常
                if attempt == self._max_retries - 1:
                    logger.error(f"Max retries ({self._max_retries}) reached. Giving up.")
                    raise e

                # 计算延迟时间（指数退避）
                delay = self._retry_delay * (self._retry_backoff_factor ** attempt)
                logger.warning(
                    f"Attempt {attempt + 1}/{self._max_retries} failed: {e}. "
                    f"Retrying in {delay:.1f}s..."
                )

                # 等待后重试
                await asyncio.sleep(delay)

        # 如果所有尝试都失败，抛出最后一次异常
        raise last_exception

    async def generate_embedding(self, text: str) -> List[float]:
        """
        生成文本的向量嵌入（异步）

        使用 DashScope OpenAI 兼容模式 v1 API
        支持缓存和重试机制

        Args:
            text: 输入文本

        Returns:
            List[float]: 向量嵌入
        """
        if not text or not text.strip():
            raise ValueError("Input text cannot be empty")

        # 调用 DashScope API 生成 embedding
        # DashScope 原生 API 路径
        url = f"{self._embedding_config.base_url}/services/embeddings/text-embedding/text-embedding"
        headers = {
            "Authorization": f"Bearer {self._embedding_config.api_key}",
            "Content-Type": "application/json"
        }
        # DashScope 原生 API 格式
        data = {
            "model": self._embedding_config.model,
            "input": {
                "texts": [text]
            },
            "parameters": {
                "text_type": "document"
            }
        }

        # 检查缓存
        if self._enable_cache and self._embedding_cache:
            cached_result = self._embedding_cache.get(url, data)
            if cached_result is not None:
                logger.debug(f"Embedding cache hit for text: {text[:50]}...")
                return cached_result

        # 定义请求函数（用于重试）
        async def _do_request():
            # Debug: 打印请求信息
            logger.debug(f"Embedding request: URL={url}, model={self._embedding_config.model}")
            response = await self._http_client.post(url, json=data, headers=headers)
            logger.debug(f"Embedding response: status={response.status_code}")
            if response.status_code != 200:
                # 打印错误响应体
                logger.error(f"Embedding error response: {response.text}")
            response.raise_for_status()
            result = response.json()
            logger.debug(f"Embedding result keys: {list(result.keys())}")

            # 提取 embedding（DashScope 原生格式：{"output": {"embeddings": [{"text_index": 0, "embedding": [...]}]}}）
            if "output" in result and "embeddings" in result["output"] and len(result["output"]["embeddings"]) > 0:
                embedding = result["output"]["embeddings"][0]["embedding"]
                # 存入缓存
                if self._enable_cache and self._embedding_cache:
                    self._embedding_cache.set(url, data, embedding)
                return embedding
            else:
                raise ValueError(f"Unexpected response format: {result}")

        # 使用重试机制执行请求
        return await self._retry_with_backoff(_do_request)

    def generate_embedding_sync(self, text: str) -> List[float]:
        """
        生成文本的向量嵌入（同步）

        Args:
            text: 输入文本

        Returns:
            List[float]: 向量嵌入
        """
        import asyncio
        loop = self._get_loop()
        return loop.run_until_complete(self.generate_embedding(text))

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2000,
        **kwargs
    ) -> str:
        """
        调用 LLM 生成回复（异步）

        支持缓存和重试机制

        Args:
            messages: 消息列表，格式为 [{"role": "user", "content": "..."}]
            temperature: 温度参数
            max_tokens: 最大 token 数
            **kwargs: 其他参数

        Returns:
            str: LLM 生成的回复
        """
        url = f"{self._llm_config.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._llm_config.api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": self._llm_config.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            **kwargs
        }

        # 检查缓存（仅当 temperature 较低时使用缓存，因为高温度会产生随机结果）
        if self._enable_cache and self._llm_cache and temperature < 0.3:
            cached_result = self._llm_cache.get(url, data)
            if cached_result is not None:
                logger.debug(f"Chat completion cache hit for messages: {messages[-1]['content'][:50]}...")
                return cached_result

        # 定义请求函数（用于重试）
        async def _do_request():
            response = await self._http_client.post(url, json=data, headers=headers)
            response.raise_for_status()
            result = response.json()

            # 提取回复内容
            if "choices" in result and len(result["choices"]) > 0:
                content = result["choices"][0]["message"]["content"]
                # 存入缓存（仅当 temperature 较低时）
                if self._enable_cache and self._llm_cache and temperature < 0.3:
                    self._llm_cache.set(url, data, content)
                return content
            else:
                raise ValueError(f"Unexpected response format: {result}")

        # 使用重试机制执行请求
        return await self._retry_with_backoff(_do_request)

    def chat_completion_sync(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2000,
        **kwargs
    ) -> str:
        """
        调用 LLM 生成回复（同步）

        Args:
            messages: 消息列表，格式为 [{"role": "user", "content": "..."}]
            temperature: 温度参数
            max_tokens: 最大 token 数
            **kwargs: 其他参数

        Returns:
            str: LLM 生成的回复
        """
        import asyncio
        loop = self._get_loop()
        return loop.run_until_complete(self.chat_completion(messages, temperature, max_tokens, **kwargs))

    async def summarize_messages(
        self,
        messages: List[Dict[str, Any]],
        section_title: Optional[str] = None
    ) -> str:
        """
        整理并总结消息

        Args:
            messages: 消息列表
            section_title: 可选的 section 标题

        Returns:
            str: 整理后的内容
        """
        # 构建提示词
        prompt_parts = [
            "你是一个专业的对话整理助手。请整理以下对话内容，生成结构化的总结。",
        ]

        if section_title:
            prompt_parts.append(f"本次对话的主题是：{section_title}")

        prompt_parts.append("\n\n对话内容：\n")

        # 添加对话内容
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            prompt_parts.append(f"{role}: {content}")

        prompt_parts.append("\n\n请生成结构化的总结，包含：")
        prompt_parts.append("1. 主要讨论的内容")
        prompt_parts.append("2. 关键信息点")
        prompt_parts.append("3. 待办事项（如有）")
        prompt_parts.append("4. 结论或下一步行动（如有）")

        # 调用 LLM
        messages_llm = [{"role": "user", "content": "\n".join(prompt_parts)}]
        return await self.chat_completion(
            messages=messages_llm,
            temperature=0.5,
            max_tokens=1500
        )

    def summarize_messages_sync(
        self,
        messages: List[Dict[str, Any]],
        section_title: Optional[str] = None
    ) -> str:
        """
        整理并总结消息（同步）

        Args:
            messages: 消息列表
            section_title: 可选的 section 标题

        Returns:
            str: 整理后的内容
        """
        import asyncio
        loop = self._get_loop()
        return loop.run_until_complete(self.summarize_messages(messages, section_title))

    async def generate_section_title(
        self,
        messages: List[Dict[str, Any]]
    ) -> str:
        """
        生成 Section 标题

        Args:
            messages: 消息列表

        Returns:
            str: Section 标题
        """
        # 构建提示词
        prompt_parts = [
            "你是一个专业的对话分析助手。请根据以下对话内容，生成一个简洁的标题（不超过 20 个字）。",
            "\n\n对话内容：\n"
        ]

        # 添加对话内容（只取前 10 条）
        for msg in messages[:10]:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            prompt_parts.append(f"{role}: {content}")

        prompt_parts.append("\n\n请生成一个简洁的标题：")

        # 调用 LLM
        messages_llm = [{"role": "user", "content": "\n".join(prompt_parts)}]
        return await self.chat_completion(
            messages=messages_llm,
            temperature=0.3,
            max_tokens=100
        )

    def generate_section_title_sync(
        self,
        messages: List[Dict[str, Any]]
    ) -> str:
        """
        生成 Section 标题（同步）

        Args:
            messages: 消息列表

        Returns:
            str: Section 标题
        """
        import asyncio
        loop = self._get_loop()
        return loop.run_until_complete(self.generate_section_title(messages))

    async def generate_scene_tags(
        self,
        content: str,
        agent_id: str
    ) -> Dict[str, List[str]]:
        """
        生成场景标签

        Args:
            content: 内容
            agent_id: Agent ID

        Returns:
            Dict[str, List[str]]: 场景标签
        """
        # 构建提示词
        prompt_parts = [
            "你是一个专业的标签生成助手。请根据以下内容，生成合适的场景标签。",
            f"\n\nAgent ID: {agent_id}",
            f"\n\n内容：\n{content}",
            "\n\n请生成以下维度的标签（每个维度返回 1-3 个标签）：",
            "1. department（部门）：如 总部、软件、软件部、现场、知识库、内务",
            "2. execution（执行类型）：如 项目、任务、议题、笔记、其他",
            "3. planning（规划类型）：如 项目、计划、战略、目标、其他",
            "4. status（状态）：如 待开始、进行中、已完成、已取消",
            "5. work（工作状态）：如 in_work、paused、completed",
            "\n\n请以 JSON 格式返回，格式如下：",
            '{',
            '  "department": ["标签1", "标签2"],',
            '  "execution": ["标签1"],',
            '  "planning": ["标签1"],',
            '  "status": ["标签1"],',
            '  "work": ["标签1"]',
            '}'
        ]

        # 调用 LLM
        messages_llm = [{"role": "user", "content": "\n".join(prompt_parts)}]
        response = await self.chat_completion(
            messages=messages_llm,
            temperature=0.3,
            max_tokens=500
        )

        # 解析 JSON
        import json
        try:
            # 尝试提取 JSON 部分
            start_idx = response.find('{')
            end_idx = response.rfind('}') + 1
            if start_idx >= 0 and end_idx > start_idx:
                json_str = response[start_idx:end_idx]
                scene_tags = json.loads(json_str)
            else:
                # 如果无法提取 JSON，返回默认标签
                scene_tags = {
                    "department": ["总部"],
                    "execution": ["笔记"],
                    "planning": ["项目"],
                    "status": ["进行中"],
                    "work": ["in_work"]
                }
        except json.JSONDecodeError:
            # JSON 解析失败，返回默认标签
            scene_tags = {
                "department": ["总部"],
                "execution": ["笔记"],
                "planning": ["项目"],
                "status": ["进行中"],
                "work": ["in_work"]
            }

        return scene_tags

    def generate_scene_tags_sync(
        self,
        content: str,
        agent_id: str
    ) -> Dict[str, List[str]]:
        """
        生成场景标签（同步）

        Args:
            content: 内容
            agent_id: Agent ID

        Returns:
            Dict[str, List[str]]: 场景标签
        """
        import asyncio
        loop = self._get_loop()
        return loop.run_until_complete(self.generate_scene_tags(content, agent_id))

    async def merge_contents(
        self,
        contents: List[str],
        target_section_id: str
    ) -> str:
        """
        合并多个内容

        Args:
            contents: 内容列表
            target_section_id: 目标 section ID

        Returns:
            str: 合并后的内容
        """
        # 构建提示词
        prompt_parts = [
            "你是一个专业的内容合并助手。请将以下多个内容合并成一个结构化的总结。",
            f"\n\n目标 Section ID: {target_section_id}",
            "\n\n需要合并的内容：\n"
        ]

        for i, content in enumerate(contents, 1):
            prompt_parts.append(f"\n内容 {i}：\n{content}")

        prompt_parts.append("\n\n请生成一个结构化的合并总结，包含：")
        prompt_parts.append("1. 主要讨论的内容（综合所有内容）")
        prompt_parts.append("2. 关键信息点（去重整理）")
        prompt_parts.append("3. 待办事项（如有）")
        prompt_parts.append("4. 结论或下一步行动（如有）")

        # 调用 LLM
        messages_llm = [{"role": "user", "content": "\n".join(prompt_parts)}]
        return await self.chat_completion(
            messages=messages_llm,
            temperature=0.5,
            max_tokens=2000
        )

    def merge_contents_sync(
        self,
        contents: List[str],
        target_section_id: str
    ) -> str:
        """
        合并多个内容（同步）

        Args:
            contents: 内容列表
            target_section_id: 目标 section ID

        Returns:
            str: 合并后的内容
        """
        import asyncio
        loop = self._get_loop()
        return loop.run_until_complete(self.merge_contents(contents, target_section_id))

    async def determine_memory_relation(
        self,
        new_content: str,
        old_content: str
    ) -> Dict[str, Any]:
        """
        使用 LLM 判定两条记忆内容的关系类型

        Args:
            new_content: 新内容
            old_content: 旧内容

        Returns:
            Dict[str, Any]: 包含关系类型和理由的字典，格式为：
                {
                    "relation": "new" | "update" | "override" | "duplicate",
                    "reason": "判定理由",
                    "confidence": 0.0-1.0
                }
        """
        # 构建提示词
        prompt_parts = [
            "你是一个专业的记忆关系判定助手。请分析以下两条记忆内容，判断它们之间的关系。",
            "",
            "关系类型定义：",
            "1. NEW（全新知识点）：两条内容语义完全不同，没有重叠或关联。",
            "2. UPDATE（旧知识强化/补充）：语义一致，新内容包含更多细节或补充说明，没有冲突或取代信号。",
            "3. OVERRIDE（规则更新/冲突）：新内容与旧内容明显矛盾或取代，例如：",
            "   - 数值/阈值改变",
            "   - 配置参数变更",
            "   - 明确标记'旧方案废弃，改为 X'",
            "   - 包含'不再''作废''改为''新版本是'等冲突信号词",
            "4. DUPLICATE（几乎重复）：文本高度相似，仅有措辞/格式差异，无新增信息。",
            "",
            "请以 JSON 格式返回结果，格式如下：",
            '{',
            '  "relation": "new" | "update" | "override" | "duplicate",',
            '  "reason": "判定理由（简短说明）",',
            '  "confidence": 0.0-1.0',
            '}',
            "",
            "旧内容：",
            old_content,
            "",
            "新内容：",
            new_content,
        ]

        # 调用 LLM
        messages_llm = [{"role": "user", "content": "\n".join(prompt_parts)}]
        response = await self.chat_completion(
            messages=messages_llm,
            temperature=0.1,  # 低温度，确保输出稳定
            max_tokens=300
        )

        # 解析 JSON
        import json
        try:
            # 尝试提取 JSON 部分
            start_idx = response.find('{')
            end_idx = response.rfind('}') + 1
            if start_idx >= 0 and end_idx > start_idx:
                json_str = response[start_idx:end_idx]
                result = json.loads(json_str)
                
                # 验证结果格式
                relation = result.get("relation", "").lower()
                if relation not in ["new", "update", "override", "duplicate"]:
                    # 如果关系类型无效，默认为 new
                    result["relation"] = "new"
                    result["reason"] = "LLM 返回了无效的关系类型，默认为 new"
                
                # 确保 confidence 在 0-1 之间
                confidence = result.get("confidence", 0.5)
                try:
                    confidence = float(confidence)
                    confidence = max(0.0, min(1.0, confidence))
                except (ValueError, TypeError):
                    confidence = 0.5
                result["confidence"] = confidence
                
                return result
            else:
                # 如果无法提取 JSON，返回默认结果
                return {
                    "relation": "new",
                    "reason": "LLM 返回格式错误，默认为 new",
                    "confidence": 0.5
                }
        except json.JSONDecodeError:
            # JSON 解析失败，返回默认结果
            return {
                "relation": "new",
                "reason": "JSON 解析失败，默认为 new",
                "confidence": 0.5
            }

    def determine_memory_relation_sync(
        self,
        new_content: str,
        old_content: str
    ) -> Dict[str, Any]:
        """
        使用 LLM 判定两条记忆内容的关系类型（同步）

        Args:
            new_content: 新内容
            old_content: 旧内容

        Returns:
            Dict[str, Any]: 包含关系类型和理由的字典
        """
        import asyncio
        loop = self._get_loop()
        return loop.run_until_complete(self.determine_memory_relation(new_content, old_content))

    async def close(self):
        """关闭 HTTP 客户端"""
        await self._http_client.aclose()
    
    def close_sync(self):
        """关闭 HTTP 客户端（同步）"""
        import asyncio
        loop = self._get_loop()
        loop.run_until_complete(self.close())

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close_sync()


# 全局 LLM 客户端实例（单例模式）
_llm_client_instance: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    """获取全局 LLM 客户端实例"""
    global _llm_client_instance
    if _llm_client_instance is None:
        _llm_client_instance = LLMClient()
    return _llm_client_instance
