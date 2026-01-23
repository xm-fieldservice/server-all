"""
QA Bot 处理器：调用 AI 工厂的 RAG 问答接口，并将答案通过企业微信下行消息发送给用户。

企业微信后台配置：
- AgentID: 1000025（由环境变量 WECOM_QA_AGENT_ID 指定）
- 消息类型：text
- 处理逻辑：调用 /qa/rag，获取答案后通过企业微信 message/send API 回复。
"""
import os
from typing import Any, Dict, Optional

import requests

from ..registry import register_handler

# 配置
WECOM_QA_AGENT_ID = os.getenv("WECOM_QA_AGENT_ID", "")
WECOM_CORP_ID = os.getenv("WECOM_CORP_ID", "")
WECOM_APP_SECRET = os.getenv("WECOM_APP_SECRET", "")
AI_FACTORY_BASE_URL = os.getenv("AI_FACTORY_BASE_URL", "http://127.0.0.1:8001")

if not WECOM_QA_AGENT_ID:
    print("[WARNING] WECOM_QA_AGENT_ID not configured, QA Bot will not be registered.")


def _get_wecom_access_token() -> Optional[str]:
    """获取企业微信 API 的 access_token。"""
    if not WECOM_CORP_ID or not WECOM_APP_SECRET:
        print("[qa-bot] Missing WECOM_CORP_ID or WECOM_APP_SECRET")
        return None

    token_url = (
        "https://qyapi.weixin.qq.com/cgi-bin/gettoken"
        f"?corpid={WECOM_CORP_ID}&corpsecret={WECOM_APP_SECRET}"
    )
    try:
        token_resp = requests.get(token_url, timeout=5)
        token_resp.raise_for_status()
        token_data = token_resp.json()
    except Exception as exc:
        print(f"[qa-bot] ERROR getting access_token: {exc!r}")
        return None

    if token_data.get("errcode") != 0:
        print(f"[qa-bot] gettoken error: {token_data}")
        return None

    access_token = token_data.get("access_token", "")
    if not access_token:
        print("[qa-bot] no access_token returned")
        return None

    return access_token


def _send_wecom_message(userid: str, content: str) -> bool:
    """通过企业微信应用消息发送文本给指定用户。

    Args:
        userid: 企业微信用户 ID
        content: 消息内容

    Returns:
        是否成功发送（仅表示 API 调用成功，不保证用户收到）
    """
    access_token = _get_wecom_access_token()
    if not access_token:
        return False

    send_url = (
        "https://qyapi.weixin.qq.com/cgi-bin/message/send"
        f"?access_token={access_token}"
    )
    send_body = {
        "touser": userid,
        "msgtype": "text",
        "agentid": int(WECOM_QA_AGENT_ID) if WECOM_QA_AGENT_ID.isdigit() else WECOM_QA_AGENT_ID,
        "text": {"content": content},
        "safe": 0,
    }
    try:
        send_resp = requests.post(send_url, json=send_body, timeout=5)
        send_resp.raise_for_status()
        send_data = send_resp.json()
        print(f"[qa-bot] send result: {send_data}")
        if send_data.get("errcode") == 0:
            return True
        else:
            print(f"[qa-bot] send error: {send_data}")
            return False
    except Exception as exc:
        print(f"[qa-bot] ERROR sending message: {exc!r}")
        return False


@register_handler(
    agent_id=WECOM_QA_AGENT_ID,
    name="企业问答助手",
    description="接收用户问题，调用 AI 工厂 RAG 接口，并将答案通过企业微信回复。",
)
async def handle_qa_bot(userid: str, content: str, msg_type: str, **kwargs) -> Optional[dict]:
    """处理 QA Bot 消息。

    Args:
        userid: 企业微信用户 ID（FromUserName）
        content: 消息内容（问题文本）
        msg_type: 消息类型，应为 'text'
        **kwargs: 额外参数（如 create_time, agent_id_raw 等）

    Returns:
        可选的回复字典。本处理器会主动调用企业微信下行 API，因此返回 None 即可。
    """
    if msg_type != "text":
        return None

    if not content or not userid:
        return None

    print(f"[qa-bot] Processing question from {userid}: {content[:50]}...")

    # 1. 调用 AI 工厂的 QA API
    internal_user_id = f"wecom:{userid}"
    qa_payload = {
        "question_text": content,
        "user_id": internal_user_id,
        # 可根据需要添加更多参数，如 workspace、context 等
    }
    qa_url = AI_FACTORY_BASE_URL.rstrip("/") + "/qa/rag"
    try:
        print(f"[qa-bot] Calling AI factory QA: {qa_url}")
        qa_resp = requests.post(qa_url, json=qa_payload, timeout=30)
        qa_resp.raise_for_status()
        qa_result = qa_resp.json()
        print(f"[qa-bot] QA result: {qa_result}")
        # 假设答案字段为 "answer" 或 "response"，根据实际 API 调整
        answer = qa_result.get("answer") or qa_result.get("response") or qa_result.get("text")
        if not answer:
            answer = "抱歉，AI 暂时无法生成答案。"
    except Exception as exc:
        print(f"[qa-bot] ERROR calling QA API: {exc!r}")
        answer = "系统处理请求时出错，请稍后重试。"

    # 2. 通过企业微信下行 API 将答案发回用户
    success = _send_wecom_message(userid, answer)
    if not success:
        print("[qa-bot] Failed to send answer via WeCom.")

    # 本处理器已主动发送消息，无需网关再回复
    return None