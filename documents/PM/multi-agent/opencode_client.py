import requests
import time
import json
from typing import Optional, Dict, Any, List


class OpenCodeClient:
    """OpenCode HTTP API 客户端"""

    def __init__(self, base_url: str = "http://localhost:4096", timeout: int = 500):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session_id: Optional[str] = None

    def create_session(self, title: Optional[str] = None) -> Dict[str, Any]:
        """创建新 session"""
        url = f"{self.base_url}/session"
        payload = {}
        if title:
            payload["title"] = title

        resp = requests.post(url, json=payload, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        self.session_id = data["id"]
        return data

    def send_message(self, message: str, session_id: Optional[str] = None) -> Dict[str, Any]:
        """发送消息并等待响应"""
        sid = session_id or self.session_id
        if not sid:
            raise ValueError("session_id is required")

        url = f"{self.base_url}/session/{sid}/message"
        payload = {
            "parts": [
                {"type": "text", "text": message}
            ]
        }

        resp = requests.post(url, json=payload, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def get_messages(self, session_id: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """获取 session 消息列表"""
        sid = session_id or self.session_id
        if not sid:
            raise ValueError("session_id is required")

        url = f"{self.base_url}/session/{sid}/message"
        params = {"limit": limit}

        resp = requests.get(url, params=params, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def get_session_status(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """获取 session 状态"""
        sid = session_id or self.session_id
        if not sid:
            raise ValueError("session_id is required")

        url = f"{self.base_url}/session/{sid}"
        resp = requests.get(url, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def call(self, message: str, title: Optional[str] = None, new_session: bool = True) -> Dict[str, Any]:
        """便捷方法：发送消息
        new_session: 是否创建新 session，为 False 时使用已有 session
        """
        if new_session or not self.session_id:
            session_info = self.create_session(title=title)
        else:
            session_info = {"id": self.session_id}
        
        sid = session_info["id"]

        result = self.send_message(message, session_id=sid)
        messages = self.get_messages(session_id=sid)

        return {
            "session_id": sid,
            "session_info": session_info,
            "last_message": result,
            "all_messages": messages
        }

    def get_last_response_text(self, session_id: Optional[str] = None) -> str:
        """获取最后一条 assistant 回复的文本内容"""
        messages = self.get_messages(session_id=session_id, limit=10)

        for msg in reversed(messages):
            if msg.get("info", {}).get("role") == "assistant":
                parts = msg.get("parts", [])
                for part in parts:
                    if part.get("type") == "text":
                        return part.get("text", "")
        return ""

    def list_sessions(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取 session 列表"""
        url = f"{self.base_url}/session"
        params = {"limit": limit}

        resp = requests.get(url, params=params, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def use_session(self, session_id: str) -> None:
        """使用已存在的 session"""
        self.session_id = session_id

    def get_current_session(self) -> Optional[str]:
        """获取当前 session ID"""
        return self.session_id

    def has_session(self) -> bool:
        """检查是否有活动的 session"""
        return self.session_id is not None

    def delete_session(self, session_id: str) -> bool:
        url = f"{self.base_url}/session/{session_id}"
        resp = requests.delete(url, timeout=self.timeout)
        resp.raise_for_status()
        return True


def create_opencode_client() -> OpenCodeClient:
    """工厂函数：创建 OpenCode 客户端"""
    return OpenCodeClient()


if __name__ == "__main__":
    client = create_opencode_client()
    result = client.call("你好，请介绍一下自己", title="测试对话")
    print(f"Session ID: {result['session_id']}")
    print(f"Response: {result['last_message']}")
