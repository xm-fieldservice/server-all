"""
Note Bot 处理器：将所有文本消息自动作为工作笔记写入服务器主 DB。

企业微信后台配置：
- AgentID: 1000023（由环境变量 WECOM_NOTE_AGENT_ID 指定）
- 消息类型：text
- 处理逻辑：直接调用 AI Factory 的 /entries/ingest 接口，无需前缀检查。
"""
import os
from datetime import datetime
from typing import Any, Dict, Optional

import requests

from ..registry import register_handler

# 配置
WECOM_NOTE_AGENT_ID = os.getenv("WECOM_NOTE_AGENT_ID", "")
AI_FACTORY_BASE_URL = os.getenv("AI_FACTORY_BASE_URL", "http://127.0.0.1:8001")

if not WECOM_NOTE_AGENT_ID:
    print("[WARNING] WECOM_NOTE_AGENT_ID not configured, Note Bot will not be registered.")
else:
    @register_handler(
        agent_id=WECOM_NOTE_AGENT_ID,
        name="工作笔记助手",
        description="接收企业微信文本消息，自动作为工作笔记写入主数据库。",
    )
    async def handle_note_bot(userid: str, content: str, msg_type: str, **kwargs) -> Optional[dict]:
        """处理 Note Bot 消息。

        Args:
            userid: 企业微信用户 ID（FromUserName）
            content: 消息内容（已去除前缀）
            msg_type: 消息类型，应为 'text'
            **kwargs: 额外参数（如 create_time, agent_id_raw 等）

        Returns:
            可选的回复字典，若需要回复则返回 {"reply": True, "content": "...", "msg_type": "text"}，
            否则返回 None。
        """
        if msg_type != "text":
            # 非文本消息，不处理
            return None

        if not content or not userid:
            return None

        print(f"[note-bot] Processing note from {userid}: {content[:50]}...")

        # 构建笔记入库载荷
        note_text = content
        dt = datetime.utcnow()
        internal_user_id = f"wecom:{userid}"
        extra_context: Dict[str, Any] = {
            "source_channel": "wecom",
            "source_app": "wecom_note_bot",
            "wecom": {
                "userid": userid,
            },
        }
        scene_tags: Dict[str, Any] = {
            "channel": "wecom:note_bot",
            "semantic_type": "note",
            "peer": "self",
            "conversation": f"wecom:{userid}",
        }
        ingest_payload: Dict[str, Any] = {
            "raw_text": note_text,
            "user_id": internal_user_id,
            "note_datetime": dt.isoformat(),
            "source_channel": "wecom",
            "scene_tags": scene_tags,
            "extra_context": extra_context,
        }

        url = AI_FACTORY_BASE_URL.rstrip("/") + "/entries/ingest"
        try:
            print(f"[note-bot] Calling AI Factory ingest: {url}")
            resp = requests.post(url, json=ingest_payload, timeout=10)
            print(f"[note-bot] Ingest status: {resp.status_code}")
            if resp.status_code != 200:
                print(f"[note-bot] Ingest error: {resp.text[:200]}")
        except requests.RequestException as exc:
            print(f"[note-bot] ERROR calling AI Factory: {exc!r}")

        # Note Bot 通常不需要主动回复用户，返回 None 表示不回复
        return None
