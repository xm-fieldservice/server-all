"""
内务Agent - 企微消息入口

处理来自企业微信的消息，调用内务Agent工作流
"""
import os
import uuid
from typing import Optional

import requests

from registry import register_handler

# 环境配置
WECOM_INTERNAL_AFFAIRS_AGENT_ID = os.getenv("WECOM_INTERNAL_AFFAIRS_AGENT_ID", "")
WECOM_INTERNAL_AFFAIRS_AGENT_SECRET = os.getenv("WECOM_INTERNAL_AFFAIRS_AGENT_SECRET", "")
WECOM_CORP_ID = os.getenv("WECOM_CORP_ID", "")
WECOM_ENV = os.getenv("WECOM_ENV", "test")  # test / production

if not WECOM_INTERNAL_AFFAIRS_AGENT_ID:
    print("[WARNING] WECOM_INTERNAL_AFFAIRS_AGENT_ID not configured, Internal Affairs Bot will not be registered.")


def _get_wecom_access_token() -> Optional[str]:
    """获取企业微信 API 的 access_token"""
    if not WECOM_CORP_ID:
        print("[InternalAffairsBot] Missing WECOM_CORP_ID")
        return None
    
    secret = WECOM_INTERNAL_AFFAIRS_AGENT_SECRET or os.getenv("WECOM_APP_SECRET", "")
    if not secret:
        print("[InternalAffairsBot] Missing WECOM_INTERNAL_AFFAIRS_AGENT_SECRET")
        return None
    
    token_url = (
        f"https://qyapi.weixin.qq.com/cgi-bin/gettoken"
        f"?corpid={WECOM_CORP_ID}&corpsecret={secret}"
    )
    try:
        token_resp = requests.get(token_url, timeout=5)
        token_resp.raise_for_status()
        token_data = token_resp.json()
    except Exception as exc:
        print(f"[InternalAffairsBot] ERROR getting access_token: {exc!r}")
        return None
    
    if token_data.get("errcode") != 0:
        print(f"[InternalAffairsBot] gettoken error: {token_data}")
        return None
    
    access_token = token_data.get("access_token", "")
    if not access_token:
        print("[InternalAffairsBot] no access_token returned")
        return None
    
    return access_token


def _send_wecom_message(userid: str, content: str) -> bool:
    """通过企业微信应用消息发送文本"""
    print(f"[InternalAffairsBot] Preparing to send message to {userid}")
    
    access_token = _get_wecom_access_token()
    if not access_token:
        print("[InternalAffairsBot] No access token, sending failed")
        return False
    
    send_url = (
        f"https://qyapi.weixin.qq.com/cgi-bin/message/send"
        f"?access_token={access_token}"
    )
    
    agent_id = WECOM_INTERNAL_AFFAIRS_AGENT_ID
    send_body = {
        "touser": userid,
        "msgtype": "text",
        "agentid": int(agent_id) if agent_id.isdigit() else agent_id,
        "text": {"content": content},
        "safe": 0,
    }
    
    print(f"[InternalAffairsBot] Sending to {send_url}")
    try:
        send_resp = requests.post(send_url, json=send_body, timeout=10)
        send_resp.raise_for_status()
        send_data = send_resp.json()
        
        if send_data.get("errcode") == 0:
            print(f"[InternalAffairsBot] Message sent successfully to {userid}")
            return True
        else:
            print(f"[InternalAffairsBot] send error: {send_data}")
            return False
    except Exception as exc:
        print(f"[InternalAffairsBot] ERROR sending message: {exc!r}")
        return False


def build_thread_id(userid: str, agent_type: str = "internal_affairs") -> str:
    """构建LangGraph会话ID"""
    return f"{agent_type}_{userid}_{uuid.uuid4().hex[:8]}"


@register_handler(
    agent_id=WECOM_INTERNAL_AFFAIRS_AGENT_ID,
    name="内务助手",
    description="企业内务助手，支持报销、借款、记账、查账功能",
)
async def handle_internal_affairs_bot(userid: str, content: str, msg_type: str, **kwargs) -> Optional[dict]:
    """
    处理内务Agent消息
    
    Args:
        userid: 企业微信用户ID
        content: 消息内容
        msg_type: 消息类型
    
    Returns:
        处理结果
    """
    if msg_type != "text":
        return {
            "type": "text",
            "content": "暂只支持文字消息，请发送文字描述您的需求"
        }
    
    if not content or not userid:
        return {"type": "text", "content": "消息无效"}
    
    print(f"[InternalAffairsBot] Processing from {userid}: {content[:50]}...")
    print(f"[InternalAffairsBot] Environment: {WECOM_ENV}")
    
    # 导入内务Agent
    try:
        from langgraph_mvp.agents.internal_affairs import run_internal_affairs
    except ImportError as e:
        print(f"[InternalAffairsBot] Import error: {e}")
        _send_wecom_message(userid, "系统暂不可用，请稍后再试")
        return None
    
    # 构建或获取会话ID
    thread_id = kwargs.get("thread_id") or build_thread_id(userid)
    
    try:
        # 调用内务Agent工作流
        result = run_internal_affairs(
            user_input=content,
            user_id=userid,
            thread_id=thread_id
        )
        
        # 提取回复
        messages = result.get("messages", [])
        if messages:
            last_msg = messages[-1]
            if isinstance(last_msg, tuple):
                response_text = last_msg[1]
            elif isinstance(last_msg, dict):
                response_text = last_msg.get("content", "处理完成")
            else:
                response_text = str(last_msg)
        else:
            response_text = "处理完成，但没有返回结果"
        
    except Exception as exc:
        print(f"[InternalAffairsBot] ERROR: {exc!r}")
        response_text = f"处理出错：{str(exc)}"
    
    # 发送回复
    _send_wecom_message(userid, response_text)
    
    return None


# 便捷函数：供其他模块调用
async def trigger_internal_affairs(userid: str, content: str) -> str:
    """
    触发内务Agent处理
    
    可用于测试或从其他渠道调用
    """
    result = await handle_internal_affairs_bot(
        userid=userid,
        content=content,
        msg_type="text"
    )
    return result


if __name__ == "__main__":
    # 测试
    import asyncio
    
    async def test():
        result = await handle_internal_affairs_bot(
            userid="test_user",
            content="报销客户招待费用500元",
            msg_type="text"
        )
        print(f"Result: {result}")
    
    asyncio.run(test())
