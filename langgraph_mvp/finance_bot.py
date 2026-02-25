"""
财务 Bot 处理器

企业微信应用：财务助手
- AgentID: 1000026（由环境变量 WECOM_FINANCE_AGENT_ID 指定）
- 处理财务相关请求（记账、查账）
"""
import os
from typing import Optional

import requests

from registry import register_handler

WECOM_FINANCE_AGENT_ID = os.getenv("WECOM_FINANCE_AGENT_ID", "")
WECOM_FINANCE_AGENT_SECRET = os.getenv("WECOM_FINANCE_AGENT_SECRET", "")
WECOM_CORP_ID = os.getenv("WECOM_CORP_ID", "")
WECOM_APP_SECRET = os.getenv("WECOM_APP_SECRET", "")

if not WECOM_FINANCE_AGENT_ID:
    print("[WARNING] WECOM_FINANCE_AGENT_ID not configured, Finance Bot will not be registered.")


def _get_wecom_access_token() -> Optional[str]:
    """获取企业微信 API 的 access_token"""
    if not WECOM_CORP_ID:
        print("[finance-bot] Missing WECOM_CORP_ID")
        return None
    
    # 优先使用 agent 专属 secret
    secret = WECOM_FINANCE_AGENT_SECRET or WECOM_APP_SECRET
    if not secret:
        print("[finance-bot] Missing WECOM_FINANCE_AGENT_SECRET or WECOM_APP_SECRET")
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
        print(f"[finance-bot] ERROR getting access_token: {exc!r}")
        return None
    
    if token_data.get("errcode") != 0:
        print(f"[finance-bot] gettoken error: {token_data}")
        return None
    
    access_token = token_data.get("access_token", "")
    if not access_token:
        print("[finance-bot] no access_token returned")
        return None
    
    return access_token


def _send_wecom_message(userid: str, content: str) -> bool:
    """通过企业微信应用消息发送文本"""
    print(f"[finance-bot] Preparing to send message to {userid}")
    access_token = _get_wecom_access_token()
    if not access_token:
        print("[finance-bot] No access token, sending failed")
        return False
    
    print(f"[finance-bot] Got access token: {access_token[:20]}...")
    
    send_url = (
        f"https://qyapi.weixin.qq.com/cgi-bin/message/send"
        f"?access_token={access_token}"
    )
    send_body = {
        "touser": userid,
        "msgtype": "text",
        "agentid": int(WECOM_FINANCE_AGENT_ID) if WECOM_FINANCE_AGENT_ID.isdigit() else WECOM_FINANCE_AGENT_ID,
        "text": {"content": content},
        "safe": 0,
    }
    print(f"[finance-bot] Sending to {send_url} with body: {send_body}")
    try:
        send_resp = requests.post(send_url, json=send_body, timeout=5)
        print(f"[finance-bot] Response status: {send_resp.status_code}")
        send_resp.raise_for_status()
        send_data = send_resp.json()
        print(f"[finance-bot] Response data: {send_data}")
        if send_data.get("errcode") == 0:
            print(f"[finance-bot] Message sent successfully to {userid}")
            return True
        else:
            print(f"[finance-bot] send error: {send_data}")
            return False
    except Exception as exc:
        print(f"[finance-bot] ERROR sending message: {exc!r}")
        return False


@register_handler(
    agent_id=WECOM_FINANCE_AGENT_ID,
    name="财务助手",
    description="企业财务助手，支持记账和查账功能",
)
async def handle_finance_bot(userid: str, content: str, msg_type: str, **kwargs) -> Optional[dict]:
    """处理财务 Bot 消息"""
    if msg_type != "text":
        return None
    
    if not content or not userid:
        return None
    
    print(f"[finance-bot] Processing from {userid}: {content[:50]}...")
    
    # 导入财务 Agent
    from langgraph_mvp.agents.finance import run_finance_task
    
    # 运行财务任务（userid 就是用户标识）
    try:
        result = run_finance_task(
            user_input=content,
            user_id=userid  # 直接用企业微信的 userid
        )
        
        # 获取回复
        messages = result.get("messages", [])
        if messages:
            response_text = messages[-1].content
        else:
            response_text = "处理完成，但没有返回结果"
            
    except Exception as exc:
        print(f"[finance-bot] ERROR: {exc!r}")
        response_text = f"处理出错：{str(exc)}"
    
    # 发送回复
    _send_wecom_message(userid, response_text)
    
    return None


if __name__ == "__main__":
    # 测试
    import asyncio
    
    async def test():
        result = await handle_finance_bot(
            userid="zhangsan",
            content="查询我的开支记录",
            msg_type="text"
        )
        print(f"Result: {result}")
    
    asyncio.run(test())
