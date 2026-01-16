"""
LLM 和 Embedding 服务客户端
支持远端 API 调用：qwen3-embedding (DashScope) 和 deepseek-chat
"""

import os
import threading
import asyncio
from typing import List, Dict, Any, Optional
import httpx
from pydantic import BaseModel
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()


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
    """LLM 和 Embedding 服务客户端"""

    def __init__(self):
        self._llm_config = self._load_llm_config()
        self._embedding_config = self._load_embedding_config()
        self._http_client = httpx.AsyncClient(timeout=60.0)
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

    async def generate_embedding(self, text: str) -> List[float]:
        """
        生成文本的向量嵌入（异步）

        使用 DashScope OpenAI 兼容模式 v1 API

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

        # Debug: 打印请求信息
        print(f"[LLMClient] Embedding request: URL={url}, model={self._embedding_config.model}")
        response = await self._http_client.post(url, json=data, headers=headers)
        print(f"[LLMClient] Embedding response: status={response.status_code}")
        if response.status_code != 200:
            # 打印错误响应体
            print(f"[LLMClient] Embedding error response: {response.text}")
        response.raise_for_status()
        result = response.json()
        print(f"[LLMClient] Embedding result keys: {list(result.keys())}")

        # 提取 embedding（DashScope 原生格式：{"output": {"embeddings": [{"text_index": 0, "embedding": [...]}]}}）
        if "output" in result and "embeddings" in result["output"] and len(result["output"]["embeddings"]) > 0:
            embedding = result["output"]["embeddings"][0]["embedding"]
            return embedding
        else:
            raise ValueError(f"Unexpected response format: {result}")

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

        response = await self._http_client.post(url, json=data, headers=headers)
        response.raise_for_status()
        result = response.json()

        # 提取回复内容
        if "choices" in result and len(result["choices"]) > 0:
            return result["choices"][0]["message"]["content"]
        else:
            raise ValueError(f"Unexpected response format: {result}")

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
