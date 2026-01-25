#!/usr/bin/env python3
"""
Agent记忆系统调试API服务 - 简化版（使用内存存储）
用于绕过数据库RLS限制，提供调试功能
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid
import logging

logger = logging.getLogger(__name__)

# 创建FastAPI应用
app = FastAPI(
    title="Agent记忆系统调试API（内存版）",
    description="用于调试和验证Agent记忆功能的API接口（内存存储，绕过RLS）",
    version="1.0.0-dev"
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 内存存储
memory_store = {
    "sessions": [],
    "messages": [],
    "sections": [],
    "entries": []
}

# Pydantic模型
class SessionCreateRequest(BaseModel):
    user_id: str
    assistant_id: str
    title: Optional[str] = None
    department: Optional[str] = "AI研发部"
    metadata_json: Optional[Dict[str, Any]] = {}

class MessageCreateRequest(BaseModel):
    role: str
    content: str
    agent_id: str
    msg_type: Optional[str] = None
    metadata_json: Optional[Dict[str, Any]] = {}

class ChatRequest(BaseModel):
    session_id: str
    user_id: str
    assistant_id: str
    content: str
    mode: str = "auto"
    search_mode: str = "rag"

# API端点
@app.get("/")
async def root():
    return {
        "message": "Agent记忆系统调试API（内存版）",
        "version": "1.0.0-dev",
        "status": "running",
        "note": "使用内存存储，数据不会持久化"
    }

@app.get("/api/memory/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "storage": "memory",
        "sessions_count": len(memory_store["sessions"]),
        "messages_count": len(memory_store["messages"])
    }

@app.post("/api/memory/sessions")
async def create_session(request: SessionCreateRequest):
    """创建会话"""
    try:
        session_id = f"session_{uuid.uuid4().hex}"
        
        session = {
            "session_id": session_id,
            "user_id": request.user_id,
            "assistant_id": request.assistant_id,
            "title": request.title or "未命名会话",
            "metadata_json": {
                "department": request.department,
                **request.metadata_json
            },
            "created_at": datetime.now().isoformat()
        }
        
        memory_store["sessions"].insert(0, session)  # 插入到开头
        
        logger.info(f"创建会话: {session_id}")
        
        return {
            "session_id": session_id,
            "user_id": request.user_id,
            "assistant_id": request.assistant_id,
            "title": request.title,
            "created_at": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"创建会话失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/memory/sessions")
async def get_sessions(
    user_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
):
    """获取会话列表"""
    try:
        sessions = memory_store["sessions"]
        
        # 过滤
        if user_id:
            sessions = [s for s in sessions if s.get("user_id") == user_id]
        
        # 分页
        total = len(sessions)
        sessions = sessions[offset:offset+limit]
        
        logger.info(f"获取会话列表: {len(sessions)}个会话")
        
        return {
            "sessions": sessions,
            "total": total
        }
    except Exception as e:
        logger.error(f"获取会话列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/memory/sessions/{session_id}/messages")
async def append_message(session_id: str, request: MessageCreateRequest):
    """添加消息到会话"""
    try:
        message_id = f"msg_{uuid.uuid4().hex}"
        
        message = {
            "message_id": message_id,
            "session_id": session_id,
            "role": request.role,
            "content": request.content,
            "msg_type": request.msg_type,
            "metadata_json": request.metadata_json,
            "created_at": datetime.now().isoformat()
        }
        
        memory_store["messages"].append(message)
        
        logger.info(f"添加消息: {message_id}")
        
        return {
            "message_id": message_id,
            "session_id": session_id,
            "role": request.role,
            "content": request.content,
            "created_at": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"添加消息失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/memory/sessions/{session_id}/messages")
async def get_messages(session_id: str, limit: int = 50, offset: int = 0):
    """获取会话消息列表"""
    try:
        messages = [m for m in memory_store["messages"] if m.get("session_id") == session_id]
        
        total = len(messages)
        messages = messages[offset:offset+limit]
        
        return {
            "messages": messages,
            "total": total
        }
    except Exception as e:
        logger.error(f"获取消息列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/memory/metrics")
async def get_metrics():
    """获取系统指标"""
    return {
        "cache_hit_rate": 75.5,
        "search_latency": 150,
        "total_entries": len(memory_store.get("entries", [])),
        "total_sessions": len(memory_store.get("sessions", [])),
        "total_messages": len(memory_store.get("messages", [])),
        "timestamp": datetime.now().isoformat()
    }

@app.post("/api/memory/chat")
async def chat(request: ChatRequest):
    """完整问答接口：支持笔记入库和问答检索"""
    try:
        logger.info(f"收到问答请求: session_id={request.session_id}, mode={request.mode}")

        # 保存用户消息
        user_message_id = f"msg_{uuid.uuid4().hex}"
        memory_store["messages"].append({
            "message_id": user_message_id,
            "session_id": request.session_id,
            "role": "user",
            "content": request.content,
            "msg_type": None,
            "metadata_json": {"chat_mode": request.mode},
            "created_at": datetime.now().isoformat()
        })

        # 根据模式处理
        if request.mode in ["qa", "auto"]:
            # 判断是否为问题
            is_question = False

            if request.mode == "qa":
                # 手动问答模式：直接视为问题
                is_question = True
                logger.info("手动问答模式，直接视为问题")
            else:
                # 自动模式：进行简单语义分类
                content_lower = request.content.lower()
                question_keywords = ["什么", "如何", "怎么", "为什么", "哪个", "怎样", "?", "？"]
                note_keywords = ["记录", "笔记", "备忘", "待办", "todo", "会议", "总结"]

                has_question = any(kw in content_lower for kw in question_keywords)
                has_note = any(kw in content_lower for kw in note_keywords)

                is_question = has_question and not has_note
                logger.info(f"自动模式分类结果: is_question={is_question}")

            if is_question:
                # 是问题：生成模拟回答
                logger.info("判断为问题，生成模拟回答")

                answer = f"这是来自记忆系统的模拟回答：\n\n您的问题是：「{request.content}」\n\n（注：这是内存版API，使用模拟回答，数据不会持久化到数据库）"

                # 保存助手回答
                assistant_message_id = f"msg_{uuid.uuid4().hex}"
                memory_store["messages"].append({
                    "message_id": assistant_message_id,
                    "session_id": request.session_id,
                    "role": "assistant",
                    "content": answer,
                    "msg_type": "answer",
                    "metadata_json": {"mode": request.mode, "search_mode": request.search_mode},
                    "created_at": datetime.now().isoformat()
                })

                return {
                    "user_message_id": user_message_id,
                    "assistant_message_id": assistant_message_id,
                    "is_question": True,
                    "answer": answer,
                    "mode": "qa"
                }
            else:
                # 不是问题：作为笔记保存
                logger.info("判断为笔记，仅保存消息")
                return {
                    "user_message_id": user_message_id,
                    "is_question": False,
                    "message": "已保存为笔记（内存存储）",
                    "mode": "note"
                }

        else:  # note模式
            # 笔记模式：直接保存，不生成回答
            logger.info("笔记模式，仅保存到内存")
            return {
                "user_message_id": user_message_id,
                "is_question": False,
                "message": "已保存为笔记（内存存储）",
                "mode": "note"
            }

    except Exception as e:
        logger.error(f"问答处理失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    
    print("=" * 60)
    print("Agent记忆系统调试API服务（内存版）")
    print("=" * 60)
    print(f"API地址: http://localhost:8001")
    print(f"API文档: http://localhost:8001/docs")
    print(f"前端页面: agent_memory_debug.html")
    print("注意: 使用内存存储，数据不会持久化")
    print("=" * 60)
    
    uvicorn.run(app, host="0.0.0.0", port=8001)
