from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

import base64
import hashlib
import os
import struct
import xml.etree.ElementTree as ET
import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field


app = FastAPI(title="WeCom Gateway (N1)")

# ai-factory entries 写入接口的基础地址，可通过环境变量覆盖。
# 默认指向本机运行的 entries_browser_app:
#   uvicorn ai_factory.web.entries_browser_app:app --reload --port 8001
AI_FACTORY_BASE_URL = os.getenv("AI_FACTORY_BASE_URL", "http://127.0.0.1:8001")
WECOM_CALLBACK_TOKEN = os.getenv("WECOM_CALLBACK_TOKEN", "devWecomToken")
WECOM_CORP_ID = os.getenv("WECOM_CORP_ID", "")
WECOM_ENCODING_AES_KEY = os.getenv("WECOM_ENCODING_AES_KEY", "")
WECOM_QA_AGENT_ID = os.getenv("WECOM_QA_AGENT_ID", "")
WECOM_NOTE_AGENT_ID = os.getenv("WECOM_NOTE_AGENT_ID", "")
WECOM_APP_SECRET = os.getenv("WECOM_APP_SECRET", "")


from wecom_gateway.registry import get_handler
from wecom_gateway import handlers  # 触发注册，确保所有处理器自动注册


class DebugWecomNote(BaseModel):
    """本地调试用：模拟企业微信里的一条“记：...”笔记消息。

    实际接入企业微信时，请求体会由 WeCom 回调 XML/JSON 解析而来，
    这里只保留最小必要字段，方便本地打通 entries_ingest 流程。
    """

    userid: str = Field(..., description="企业微信用户 ID")
    content: str = Field(..., description="笔记正文，已去掉前缀“记：”")
    department_id: Optional[str] = Field(
        None,
        description="用户所属部门 ID，可选。若不提供，将只在 extra_context 中标记 wecom.userid。",
    )
    department_name: Optional[str] = Field(
        None,
        description="部门名称，可选，用于 tags_snapshot.department。",
    )
    note_datetime: Optional[datetime] = Field(
        None,
        description="笔记时间，默认为当前时间。",
    )


def _wecom_signature(token: str, timestamp: str, nonce: str, data: str) -> str:
    items = [token, timestamp, nonce, data]
    items.sort()
    to_hash = "".join(items)
    return hashlib.sha1(to_hash.encode("utf-8")).hexdigest()


def _wecom_decrypt(encrypted: str) -> str:
    """解密企业微信 Encrypt 字段，返回内部明文 XML 字符串。

    按官方文档：
    - AESKey = Base64_Decode(EncodingAESKey + "=")
    - 使用 AES-CBC，key = AESKey，iv = AESKey[:16]
    - 解密结果：16字节随机数 + 4字节网络序消息长度 + 消息体 + CorpID
    """

    if not WECOM_ENCODING_AES_KEY:
        raise ValueError("WECOM_ENCODING_AES_KEY is not configured")

    # 还原 AES key
    aes_key = base64.b64decode(WECOM_ENCODING_AES_KEY + "=")
    iv = aes_key[:16]

    from Crypto.Cipher import AES  # 依赖 pycryptodome

    cipher = AES.new(aes_key, AES.MODE_CBC, iv)
    # 企业微信 Encrypt 是 base64 编码的
    cipher_text = base64.b64decode(encrypted)
    plain_padded = cipher.decrypt(cipher_text)

    # 去掉 PKCS#7 填充
    pad = plain_padded[-1]
    if pad < 1 or pad > 32:
        raise ValueError("Invalid padding")
    plain = plain_padded[:-pad]

    # 跳过 16 字节随机数
    if len(plain) < 20:
        raise ValueError("Decrypted data too short")
    content = plain[16:]
    msg_len = struct.unpack("!I", content[:4])[0]
    xml_bytes = content[4 : 4 + msg_len]
    # corp_id = content[4 + msg_len :].decode("utf-8", errors="ignore")  # 如需校验可启用

    return xml_bytes.decode("utf-8")


@app.get("/wecom/callback")
async def wecom_callback_get(
    msg_signature: Optional[str] = None,
    signature: Optional[str] = None,
    timestamp: str = "",
    nonce: str = "",
    echostr: str = "",
):
    provided_sig = msg_signature or signature
    if not provided_sig:
        raise HTTPException(status_code=400, detail="missing signature")

    expect = _wecom_signature(WECOM_CALLBACK_TOKEN, timestamp, nonce, echostr)
    # 调试日志：打印企业微信提供的签名与本地计算值，便于排查“回调地址校验未通过”问题
    try:
        print("[wecom-callback][GET] provided_sig =", provided_sig)
        print("[wecom-callback][GET] expect_sig   =", expect)
        print("[wecom-callback][GET] timestamp   =", timestamp)
        print("[wecom-callback][GET] nonce       =", nonce)
        print("[wecom-callback][GET] echostr(len)=", len(echostr))
    except Exception:  # noqa: BLE001
        # 打印日志失败不影响正常签名校验
        pass

    if expect != provided_sig:
        raise HTTPException(status_code=403, detail="invalid signature")

    # 安全模式下，企业微信要求返回“解密后的 echostr 明文”
    # 文档要求：使用 EncodingAESKey 对 echostr 进行 AES-CBC 解密，
    # 取出 16字节随机数 + 4字节长度 + 明文 + CorpID 结构中的“明文”部分返回。
    if WECOM_ENCODING_AES_KEY and echostr:
        try:
            # 复用与消息解密相同的逻辑，只是这里的“消息体”是一个随机串
            decrypted = _wecom_decrypt(echostr)
            try:
                print("[wecom-callback][GET] echostr decrypted len =", len(decrypted))
            except Exception:  # noqa: BLE001
                pass
            # 为了兼容性：如果解密出来的是一个完整 XML，就原样返回；
            # 如果只是一个普通字符串，同样原样返回。
            return PlainTextResponse(content=decrypted)
        except Exception as exc:  # noqa: BLE001
            # 解密失败时，退回到原始行为：直接回显 echostr，
            # 以便在非安全模式或调试阶段仍然可用。
            print("[wecom-callback][GET] ERROR decrypting echostr:", repr(exc))

    # 明文模式或解密失败时，直接回显 echostr
    return PlainTextResponse(content=echostr)


@app.post("/wecom/callback")
async def wecom_callback_post(request: Request) -> PlainTextResponse:
    body = await request.body()
    # 记录原始回调报文前缀，便于调试（包括加密模式下的 <Encrypt> 包）
    try:
        print("[wecom-callback] raw POST body prefix =", body[:200])
    except Exception:  # noqa: BLE001
        # 打日志失败不影响正常返回
        pass

    if not body:
        return PlainTextResponse(content="success")

    raw_text = body.decode("utf-8", errors="ignore")

    # 检查是否为加密消息（含 Encrypt 字段）
    try:
        root = ET.fromstring(raw_text)
    except ET.ParseError:
        return PlainTextResponse(content="success")

    encrypt_elem = root.find("Encrypt")
    if encrypt_elem is not None and encrypt_elem.text:
        # 企业微信加密模式：需要先验签再解密
        qs = request.query_params
        msg_signature = qs.get("msg_signature") or qs.get("signature")
        timestamp = qs.get("timestamp", "")
        nonce = qs.get("nonce", "")
        encrypt = encrypt_elem.text

        if msg_signature:
            expect_sig = _wecom_signature(WECOM_CALLBACK_TOKEN, timestamp, nonce, encrypt)
            if expect_sig != msg_signature:
                print("[wecom-callback] invalid msg_signature for encrypted message")
                return PlainTextResponse(content="success")

        try:
            decrypted_xml = _wecom_decrypt(encrypt)
            print("[wecom-callback] decrypted XML prefix =", decrypted_xml[:200])
            root = ET.fromstring(decrypted_xml)
        except Exception as exc:  # noqa: BLE001
            print("[wecom-callback] ERROR decrypting message:", repr(exc))
            return PlainTextResponse(content="success")

    def _get(tag: str) -> str:
        elem = root.find(tag)
        return elem.text if elem is not None and elem.text is not None else ""

    msg_type = _get("MsgType").strip().lower()
    content = _get("Content").strip()
    from_user = _get("FromUserName").strip()
    create_time_raw = _get("CreateTime").strip()
    agent_id_raw = _get("AgentID").strip()

    print("[wecom-callback] msg_type =", msg_type)
    print("[wecom-callback] content =", content)
    print("[wecom-callback] from_user =", from_user)
    print("[wecom-callback] create_time_raw =", create_time_raw)
    print("[wecom-callback] agent_id =", agent_id_raw)

    # 注册表路由：如果存在该 AgentID 的处理器，则调用它并直接返回
    if agent_id_raw:
        handler = get_handler(agent_id_raw)
        if handler:
            print(f"[wecom-callback] found handler for agent {agent_id_raw}")
            try:
                # 调用处理器，传入核心字段及额外上下文
                await handler(
                    userid=from_user,
                    content=content,
                    msg_type=msg_type,
                    agent_id=agent_id_raw,
                    create_time=create_time_raw,
                )
            except Exception as exc:
                print(f"[wecom-callback] handler error: {exc!r}")
            # 无论处理器成功与否，都向企业微信返回 success，避免重试
            return PlainTextResponse(content="success")

    # 以下为未匹配到任何注册处理器的通用逻辑（保留原有行为）

    if msg_type != "text":
        return PlainTextResponse(content="success")

    if not content or not from_user:
        return PlainTextResponse(content="success")

    try:
        chat_result = _append_chat_message(
            from_user=from_user,
            from_name=from_user,
            to_user="wecom_app",
            to_name="WeCom App",
            content=content,
        )
        try:
            print("[wecom-callback][chat] app_notification =", chat_result.get("app_notification"))
        except Exception:  # noqa: BLE001
            pass
    except Exception as exc:  # noqa: BLE001
        print("[wecom-callback][chat] ERROR appending chat message:", repr(exc))

    note_text = content
    prefixes = ["记：", "记:", "记： ", "记: "]
    for prefix in prefixes:
        if note_text.startswith(prefix):
            note_text = note_text[len(prefix) :].lstrip()
            break
    else:
        return PlainTextResponse(content="success")

    if not note_text:
        return PlainTextResponse(content="success")

    dt = datetime.utcnow()

    internal_user_id = f"wecom:{from_user}"

    # 额外上下文：保留原有结构，便于下游做渠道/用户溯源
    extra_context: Dict[str, Any] = {
        "source_channel": "wecom",
        "source_app": "wecom_work_app",
        "wecom": {
            "userid": from_user,
        },
    }

    # 按照 WeCom 集成约定补充 entries.scene_tags，便于统一查询/分析
    scene_tags: Dict[str, Any] = {
        "channel": "wecom:note_bot",  # 企业微信 · 工作笔记助手
        "semantic_type": "note",      # 语义类型：笔记
        "peer": "self",               # 当前阶段：视为“自言自语”式工作笔记
        "conversation": f"wecom:{from_user}",  # 按用户维度聚合对话
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
        print("[wecom-callback] ingest_payload =", ingest_payload)
        resp = requests.post(url, json=ingest_payload, timeout=10)
        print("[wecom-callback] /entries/ingest status =", resp.status_code)
        print("[wecom-callback] response text prefix =", resp.text[:300])
        # 即使下游返回非 2xx，也先记录日志，不中断企业微信回调链路
    except requests.RequestException as exc:  # noqa: BLE001
        # 当前阶段：ai-factory 可能未启动，捕获异常并打印，仍向 WeCom 返回 success
        print("[wecom-callback] ERROR calling ai-factory /entries/ingest:", repr(exc))

    # 无论下游是否可用，都向企业微信返回 success，避免通道中断
    return PlainTextResponse(content="success")


@app.post("/debug/wecom_mock_note")
async def debug_wecom_mock_note(payload: DebugWecomNote) -> Dict[str, Any]:
    """本地调试入口：模拟一条企业微信“记：...”笔记写入 entries。

    - 不做企业微信签名/加解密，仅用于本地打通：
      WeCom → wecom_gateway → entries_ingest → rag_db.entries。
    - 默认将该记录视为来自企业微信通道的“工作笔记”，
      并按用户所属部门注入部门工作切片的“其他”栏语义所需的基础元数据。
    """

    note_dt = payload.note_datetime or datetime.utcnow()

    # 统一 user_id 约定：前缀 wecom: + 企业微信 userid
    internal_user_id = f"wecom:{payload.userid}"

    extra_context: Dict[str, Any] = {
        "source_channel": "wecom",  # 区分三栏页面 / 企业微信 / 其它通道
        "source_app": "wecom_work_chat_bot",
        "wecom": {
            "userid": payload.userid,
        },
    }

    if payload.department_id:
        extra_context["wecom"]["department_id"] = payload.department_id

    # 使用 tags_snapshot.department 为后续部门/工作切片映射提供依据
    tags_snapshot: Dict[str, Any] = {}
    if payload.department_name:
        tags_snapshot["department"] = [payload.department_name]

    if tags_snapshot:
        extra_context["tags_snapshot"] = tags_snapshot

    ingest_payload: Dict[str, Any] = {
        "raw_text": payload.content,
        "user_id": internal_user_id,
        "note_datetime": note_dt.isoformat(),
        "extra_context": extra_context,
        # 现阶段不在这里直接写 parent_entry_id / space_type，
        # “进入部门工作切片的其他栏”由后续 swimlane 视图基于 department 等标签统一计算。
    }

    # 通过 HTTP 转发到 ai-factory 统一 entries_ingest 接口，避免直接依赖内部实现细节。
    url = AI_FACTORY_BASE_URL.rstrip("/") + "/entries/ingest"
    try:
        resp = requests.post(url, json=ingest_payload, timeout=10)
        resp.raise_for_status()
    except requests.RequestException as exc:  # noqa: BLE001
        # 将下游错误包装为 502，便于在 wecom_gateway 日志中快速定位。
        detail = f"Failed to call ai-factory /entries/ingest: {exc!r}"
        raise HTTPException(status_code=502, detail=detail) from exc

    try:
        data = resp.json()
    except ValueError as exc:  # JSON 解析失败
        raise HTTPException(
            status_code=502,
            detail=f"ai-factory /api/entries/ingest 返回的不是有效 JSON: {exc!r}",
        ) from exc

    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="ai-factory 返回结果不是 JSON 对象")

    return data


MESSAGES: List[Dict[str, Any]] = []
CONVERSATIONS: Dict[str, Dict[str, Any]] = {}


def _append_chat_message(
    from_user: str,
    from_name: str,
    to_user: str,
    to_name: str,
    content: str,
) -> Dict[str, Any]:
    ts = datetime.utcnow().isoformat()
    conversation_id = f"wecom:{from_user}:{to_user}"

    message: Dict[str, Any] = {
        "conversation_id": conversation_id,
        "from_user": from_user,
        "from_name": from_name,
        "to_user": to_user,
        "to_name": to_name,
        "content": content,
        "ts": ts,
    }

    MESSAGES.append(message)

    conv = CONVERSATIONS.get(conversation_id)
    if conv is None:
        conv = {
            "conversation_id": conversation_id,
            "participants": [from_user, to_user],
            "participant_names": {
                from_user: from_name,
                to_user: to_name,
            },
            "last_message_preview": content,
            "last_ts": ts,
            "unread": {},
        }
        CONVERSATIONS[conversation_id] = conv
    else:
        conv["participant_names"][from_user] = from_name
        conv["participant_names"][to_user] = to_name
        conv["last_message_preview"] = content
        conv["last_ts"] = ts

    unread = conv["unread"]
    unread[to_user] = unread.get(to_user, 0) + 1

    app_notification = {
        "to_user": to_user,
        "title": f"{from_name} 发来消息",
        "description": content,
        "conversation_id": conversation_id,
    }

    return {
        "message": message,
        "conversation": conv,
        "app_notification": app_notification,
    }


class DebugChatIncoming(BaseModel):
    from_user: str
    from_name: str
    to_user: str
    to_name: str
    content: str


@app.post("/debug/chat/incoming")
async def debug_chat_incoming(payload: DebugChatIncoming) -> Dict[str, Any]:
    result = _append_chat_message(
        from_user=payload.from_user,
        from_name=payload.from_name,
        to_user=payload.to_user,
        to_name=payload.to_name,
        content=payload.content,
    )

    try:
        print("[debug-chat] app_notification =", result.get("app_notification"))
    except Exception:
        pass

    return result


@app.get("/debug/chat/inbox/{user_id}")
async def debug_chat_inbox(user_id: str) -> Dict[str, Any]:
    items: List[Dict[str, Any]] = []
    for conv in CONVERSATIONS.values():
        if user_id not in conv.get("participants", []):
            continue
        other_users = [u for u in conv["participants"] if u != user_id]
        if other_users:
            peer_id = other_users[0]
            peer_name = conv["participant_names"].get(peer_id, peer_id)
        else:
            peer_id = user_id
            peer_name = conv["participant_names"].get(user_id, user_id)
        items.append(
            {
                "conversation_id": conv["conversation_id"],
                "peer_id": peer_id,
                "peer_name": peer_name,
                "last_message_preview": conv.get("last_message_preview", ""),
                "last_ts": conv.get("last_ts"),
                "unread_count": conv.get("unread", {}).get(user_id, 0),
            }
        )

    items.sort(key=lambda x: x.get("last_ts") or "", reverse=True)
    return {"user_id": user_id, "items": items}


@app.get("/debug/chat/conversation/{conversation_id}")
async def debug_chat_conversation(conversation_id: str) -> Dict[str, Any]:
    msgs = [m for m in MESSAGES if m.get("conversation_id") == conversation_id]
    msgs.sort(key=lambda x: x.get("ts") or "")
    return {"conversation_id": conversation_id, "messages": msgs}


class DebugWecomSendTest(BaseModel):
    touser: str
    content: str


@app.post("/debug/wecom_send_test")
async def debug_wecom_send_test(payload: DebugWecomSendTest) -> Dict[str, Any]:
    if not WECOM_CORP_ID or not WECOM_APP_SECRET or not WECOM_QA_AGENT_ID:
        raise HTTPException(
            status_code=400,
            detail="WECOM_CORP_ID, WECOM_APP_SECRET 或 WECOM_QA_AGENT_ID 未配置",
        )

    token_url = (
        "https://qyapi.weixin.qq.com/cgi-bin/gettoken"
        f"?corpid={WECOM_CORP_ID}&corpsecret={WECOM_APP_SECRET}"
    )

    try:
        token_resp = requests.get(token_url, timeout=5)
        token_resp.raise_for_status()
        token_data = token_resp.json()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"gettoken 请求失败: {exc!r}") from exc

    if token_data.get("errcode") != 0:
        raise HTTPException(status_code=502, detail=f"gettoken 返回错误: {token_data}")

    access_token = token_data.get("access_token", "")
    if not access_token:
        raise HTTPException(status_code=502, detail="gettoken 未返回 access_token")

    send_url = (
        "https://qyapi.weixin.qq.com/cgi-bin/message/send"
        f"?access_token={access_token}"
    )

    send_body = {
        "touser": payload.touser,
        "msgtype": "text",
        "agentid": int(WECOM_QA_AGENT_ID) if WECOM_QA_AGENT_ID.isdigit() else WECOM_QA_AGENT_ID,
        "text": {"content": payload.content},
        "safe": 0,
    }

    try:
        send_resp = requests.post(send_url, json=send_body, timeout=5)
        send_resp.raise_for_status()
        send_data = send_resp.json()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"message/send 请求失败: {exc!r}") from exc

    return {
        "token_result": {
            "errcode": token_data.get("errcode"),
            "errmsg": token_data.get("errmsg"),
        },
        "send_result": send_data,
    }


@app.get("/debug/test_note")
async def debug_test_note(userid: str = "test_user", content: str = "测试笔记内容") -> Dict[str, Any]:
    """模拟企业微信 Note Bot 回调，直接调用 entries ingest 接口，便于调试"""
    if not userid or not content:
        raise HTTPException(status_code=400, detail="userid and content required")

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
        print("[debug-test-note] ingest_payload =", ingest_payload)
        resp = requests.post(url, json=ingest_payload, timeout=10)
        print("[debug-test-note] /entries/ingest status =", resp.status_code)
        print("[debug-test-note] response text =", resp.text[:500])
        resp.raise_for_status()
        result = resp.json()
    except requests.RequestException as exc:
        print("[debug-test-note] ERROR calling ai-factory /entries/ingest:", repr(exc))
        raise HTTPException(status_code=502, detail=f"AI Factory ingest failed: {exc}") from exc

    return {
        "note_payload": ingest_payload,
        "ingest_result": result,
    }
