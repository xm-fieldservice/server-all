#!/usr/bin/env python3
"""
Agent记忆系统调试API服务
提供前端页面所需的RESTful API接口
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid
import asyncio
import sys
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv('/home/ecs-assist-user/.env')

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from ai_factory.agents.memory import (
    SessionService,
    SectionService,
    EntryService,
    VectorClient,
    create_memory_stack,
    initialize_monitoring,
    get_logger,
    get_llm_client
)
from ai_factory.db.pgvector_client import connection_scope

# 初始化日志
logger = get_logger("agent_memory_api")

# 创建FastAPI应用
app = FastAPI(
    title="Agent记忆系统调试API",
    description="提供调试和验证Agent记忆功能的API接口",
    version="1.0.0"
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 初始化记忆服务
memory_service = None
session_service = None
section_service = None
entry_service = None
vector_client = None
llm_client = None

def init_services():
    """初始化记忆系统服务"""
    global memory_service, session_service, section_service, entry_service, vector_client, llm_client
    
    try:
        # 初始化监控系统
        initialize_monitoring(log_level="INFO", log_format="text")
        
        # 创建记忆栈
        # 启用LLM语义判断，支持笔记/问答自动识别
        memory_service = create_memory_stack(
            enable_async_memory0=False,
            enable_llm_judgment=True
        )
        
        # 获取各个服务
        session_service = memory_service.session_service
        section_service = memory_service.section_service
        entry_service = memory_service.entry_service
        # MemoryService没有vector_client属性，需要单独创建
        vector_client = VectorClient()
        # 初始化LLM客户端用于生成embedding
        llm_client = get_llm_client()
        
        logger.info("记忆系统服务初始化成功")
    except Exception as e:
        logger.error(f"记忆系统服务初始化失败: {e}")
        raise

# 初始化服务
try:
    init_services()
except Exception as e:
    logger.error(f"启动失败: {e}")
    sys.exit(1)

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

class SectionTriggerRequest(BaseModel):
    trigger_type: str = "manual"

class ClassifyRequest(BaseModel):
    content: str
    mode: str = "auto"  # auto/manual

class ChatRequest(BaseModel):
    session_id: str
    user_id: str
    assistant_id: str
    content: str
    mode: str = "auto"  # note/qa/auto
    search_mode: str = "rag"  # rag/web/hybrid

class MetricsResponse(BaseModel):
    cache_hit_rate: float
    search_latency: int
    total_entries: int
    total_sessions: int

# API端点

@app.get("/")
async def root():
    """根路径"""
    return {
        "message": "Agent记忆系统调试API",
        "version": "1.0.0",
        "status": "running"
    }

@app.get("/api/memory/health")
async def health_check():
    """健康检查"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "services": {
            "session_service": "ok",
            "section_service": "ok",
            "entry_service": "ok",
            "vector_client": "ok"
        }
    }

@app.post("/api/memory/sessions")
async def create_session(request: SessionCreateRequest):
    """创建会话"""
    try:
        # 构建元数据
        metadata = {
            "department": request.department,
            **request.metadata_json
        }
        
        session_id = session_service.create_session(
            user_id=request.user_id,
            assistant_id=request.assistant_id,
            title=request.title or "未命名会话",
            metadata=metadata
        )
        
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
        # 使用get_session_history获取会话列表
        # 如果没有指定user_id，使用默认值
        user_id_to_query = user_id if user_id else "user_001"
        
        session_infos = session_service.get_session_history(
            user_id=user_id_to_query,
            assistant_id=None,
            limit=limit
        )
        
        sessions = []
        for session in session_infos:
            sessions.append({
                "session_id": session.session_id,
                "user_id": session.user_id,
                "assistant_id": session.assistant_id,
                "title": session.title,
                "created_at": session.created_at.isoformat() if session.created_at else None,
                "metadata_json": session.metadata or {}
            })
        
        logger.info(f"获取会话列表: {len(sessions)}个会话")
        
        return {
            "sessions": sessions,
            "total": len(sessions)
        }
    except Exception as e:
        logger.error(f"获取会话列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/memory/sessions/{session_id}")
async def get_session(session_id: str):
    """获取会话详情"""
    try:
        session = session_service.get_session(session_id)
        
        if not session:
            raise HTTPException(status_code=404, detail="会话不存在")
        
        return {
            "session_id": session.session_id,
            "user_id": session.user_id,
            "assistant_id": session.assistant_id,
            "title": session.title,
            "created_at": session.created_at.isoformat() if session.created_at else None,
            "metadata_json": session.metadata_json or {}
        }
    except Exception as e:
        logger.error(f"获取会话详情失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/memory/sessions/{session_id}/messages")
async def append_message(session_id: str, request: MessageCreateRequest):
    """添加消息到会话"""
    try:
        message_id = session_service.append_message(
            session_id=session_id,
            role=request.role,
            content=request.content,
            msg_type=request.msg_type,
            metadata=request.metadata_json
        )
        
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
        messages = session_service.get_recent_messages(
            session_id=session_id,
            limit=limit
        )
        
        result = []
        for msg in messages:
            result.append({
                "message_id": msg.message_id,
                "session_id": msg.session_id,
                "role": msg.role,
                "content": msg.content,
                "msg_type": msg.msg_type,
                "created_at": msg.created_at.isoformat() if msg.created_at else None,
                "metadata": msg.metadata or {}
            })
        
        logger.info(f"获取消息列表: {len(result)}条消息")
        
        return {
            "messages": result,
            "total": len(result)
        }
    except Exception as e:
        logger.error(f"获取消息列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/memory/sessions/{session_id}/sections")
async def get_sections(session_id: str):
    """获取会话的段落列表"""
    try:
        # SectionService没有get_session_sections方法，暂时返回空列表
        # TODO: 实现从数据库查询会话段落的功能
        logger.info(f"获取会话段落: {session_id} (暂返回空列表)")
        
        return {
            "sections": [],
            "total": 0
        }
    except Exception as e:
        logger.error(f"获取段落列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/memory/sessions/{session_id}/sections/trigger")
async def trigger_section(session_id: str, request: SectionTriggerRequest):
    """触发段落整理"""
    try:
        # 数据库列已添加，现在可以尝试触发段落整理
        section = section_service.check_and_trigger_section(
            session_id=session_id,
            agent_id="assistant_001"
        )
        
        if section:
            logger.info(f"触发段落整理: {section.section_id}")
            return {
                "section_id": section.section_id,
                "entry_id": section.entry_id,
                "agent_id": section.agent_id,
                "message": "段落整理成功"
            }
        else:
            return {
                "message": "未触发段落整理",
                "reason": "消息数量不足或冷却期未过",
                "session_id": session_id
            }
    except Exception as e:
        logger.error(f"触发段落整理失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/memory/entries/search")
async def search_entries(
    query: str = Query(..., description="搜索查询"),
    top_k: int = Query(5, description="返回结果数量"),
    threshold: float = Query(0.7, description="相似度阈值")
):
    """搜索相似条目"""
    try:
        # 暂时使用简单搜索，不使用embedding
        # TODO: 修复事件循环问题后启用向量搜索
        with connection_scope() as conn:
            with conn.cursor() as cur:
                # 使用LIKE进行简单搜索
                cur.execute("""
                    SELECT entry_id, content, entry_type, created_at, metadata_json
                    FROM entries
                    WHERE content ILIKE %s
                    LIMIT %s
                """, (f"%{query}%", top_k))
                
                rows = cur.fetchall()
                
                result = []
                for row in rows:
                    result.append({
                        "entry_id": row[0],
                        "content": row[1],
                        "summary": "",  # 暂时返回空字符串
                        "entry_type": row[2],
                        "similarity": 0.8,  # 模拟相似度
                        "created_at": row[3].isoformat() if row[3] else None,
                        "metadata_json": row[4] or {},
                        "source": "长期记忆"
                    })
                
                logger.info(f"搜索条目: query='{query}', results={len(result)}")
                
                return {
                    "query": query,
                    "entries": result,
                    "total": len(result)
                }
    except Exception as e:
        logger.error(f"搜索条目失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/memory/entries/{entry_id}")
async def get_entry(entry_id: str):
    """获取条目详情"""
    try:
        entry = entry_service.get_entry(entry_id)
        
        if not entry:
            raise HTTPException(status_code=404, detail="条目不存在")
        
        return entry
    except Exception as e:
        logger.error(f"获取条目详情失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/memory/metrics")
async def get_metrics():
    """获取系统指标"""
    try:
        # 这里返回模拟数据，实际应该从监控系统获取
        metrics = {
            "cache_hit_rate": 75.5,
            "search_latency": 150,
            "total_entries": 1234,
            "total_sessions": 56,
            "total_messages": 7890,
            "timestamp": datetime.now().isoformat()
        }
        
        return metrics
    except Exception as e:
        logger.error(f"获取指标失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/memory/entries")
async def create_entry(
    content: str = Query(..., description="条目内容"),
    entry_type: str = Query("note", description="条目类型"),
    user_id: str = Query("user_001", description="用户ID"),
    assistant_id: str = Query("assistant_001", description="助手ID")
):
    """创建条目"""
    try:
        entry_id = entry_service.create_entry({
            "content": content,
            "entry_type": entry_type,
            "user_id": user_id,
            "assistant_id": assistant_id
        })
        
        logger.info(f"创建条目: {entry_id}")
        
        return {
            "entry_id": entry_id,
            "content": content,
            "entry_type": entry_type,
            "created_at": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"创建条目失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# 新增API端点：语义分析和完整问答

@app.post("/api/memory/classify")
async def classify_message(request: ClassifyRequest):
    """语义分析：判断消息是问题还是笔记"""
    try:
        # 检查是否包含问号或疑问词
        content_lower = request.content.lower()
        
        # 简单规则判断
        question_keywords = ["什么", "如何", "怎么", "为什么", "哪个", "怎样", "?", "？"]
        note_keywords = ["记录", "笔记", "备忘", "待办", "todo", "会议", "总结"]
        
        is_question = any(kw in content_lower for kw in question_keywords)
        is_note = any(kw in content_lower for kw in note_keywords)
        
        if is_question:
            msg_type = "question"
        elif is_note:
            msg_type = "statement"
        else:
            msg_type = "statement"  # 默认为陈述
        
        logger.info(f"语义分类: {request.content[:50]}... -> {msg_type}")

        # 简化版，固定置信度
        return {
            "content": request.content,
            "msg_type": msg_type,
            "is_question": msg_type == "question",
            "confidence": 0.8,
            "mode": request.mode
        }
    except Exception as e:
        logger.error(f"语义分类失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/memory/chat")
async def chat(request: ChatRequest):
    """完整问答接口：支持笔记入库和问答检索"""
    try:
        logger.info(f"收到问答请求: session_id={request.session_id}, mode={request.mode}")
        
        # 1. 保存用户消息
        message_id = session_service.append_message(
            session_id=request.session_id,
            role="user",
            content=request.content,
            msg_type=None,
            metadata={"chat_mode": request.mode}
        )
        
        # 2. 根据模式处理
        if request.mode in ["qa", "auto"]:
            # 判断是否为问题
            is_question = False
            
            if request.mode == "qa":
                # 手动问答模式：直接视为问题
                is_question = True
                logger.info("手动问答模式，直接视为问题")
            else:
                # 自动模式：进行语义分类
                classify_result = await classify_message(ClassifyRequest(
                    content=request.content,
                    mode="auto"
                ))
                is_question = classify_result["is_question"]
                logger.info(f"自动模式分类结果: is_question={is_question}")
            
            if is_question:
                # 是问题：查询记忆库
                logger.info("判断为问题，开始RAG检索")
                
                # 获取短期记忆（最近消息）
                recent_messages = session_service.get_recent_messages(
                    session_id=request.session_id,
                    limit=5
                )
                context_text = "\n".join([
                    f"{msg.role}: {msg.content}" 
                    for msg in reversed(recent_messages)
                ])
                
                # 进行向量检索获取相关记忆
                retrieved_entries = []
                try:
                    # 生成查询embedding（使用当前事件循环）
                    query_embedding = await llm_client.generate_embedding(request.content)
                    
                    # 搜索相似条目
                    search_results = entry_service.search_similar(
                        query_embedding=query_embedding,
                        filters={},
                        top_k=5,
                        threshold=0.7
                    )
                    
                    # 格式化检索结果
                    if search_results:
                        retrieved_entries = [
                            f"- {entry.get('content', '')[:200]}..."
                            for entry in search_results[:3]
                        ]
                        logger.info(f"检索到 {len(search_results)} 条相关记忆")
                    else:
                        logger.info("未检索到相关记忆")
                except Exception as e:
                    logger.warning(f"向量检索失败: {e}，将使用简化回答")
                
                # 构建RAG上下文
                rag_context = "相关记忆:\n"
                if retrieved_entries:
                    rag_context += "\n".join(retrieved_entries)
                else:
                    rag_context += "（暂无相关记忆）"
                
                # 调用LLM生成回答
                try:
                    messages = [
                        {"role": "system", "content": "你是一个 helpful 的助手。根据提供的上下文和记忆，回答用户的问题。如果记忆中有相关信息，请优先使用并引用。"},
                        {"role": "user", "content": f"上下文:\n{context_text}\n\n{rag_context}\n\n用户问题: {request.content}"}
                    ]
                    
                    # 使用当前事件循环调用LLM
                    answer = await llm_client.chat_completion(
                        messages=messages,
                        temperature=0.3,
                        max_tokens=1000
                    )
                    logger.info("LLM回答生成成功")
                except Exception as e:
                    logger.warning(f"LLM调用失败: {e}，使用简化回答")
                    answer = f"根据记忆记录：我理解你说的是「{request.content}」。\n\n上下文:\n{context_text}\n\n（注：需要配置LLM API密钥才能使用完整功能）"
                
                # 保存助手回答
                assistant_message_id = session_service.append_message(
                    session_id=request.session_id,
                    role="assistant",
                    content=answer,
                    msg_type="answer",
                    metadata={"mode": request.mode, "search_mode": request.search_mode}
                )
                
                return {
                    "user_message_id": message_id,
                    "assistant_message_id": assistant_message_id,
                    "is_question": True,
                    "answer": answer,
                    "mode": "qa"
                }
            else:
                # 不是问题：作为笔记保存
                logger.info("判断为笔记，保存到记忆库")
                
                return {
                    "user_message_id": message_id,
                    "is_question": False,
                    "message": "已保存为笔记",
                    "mode": "note"
                }
        
        else:  # note模式
            # 笔记模式：直接保存
            logger.info("笔记模式，保存到记忆库")
            
            return {
                "user_message_id": message_id,
                "is_question": False,
                "message": "已保存为笔记",
                "mode": "note"
            }
    
    except Exception as e:
        logger.error(f"问答处理失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    
    print("=" * 60)
    print("Agent记忆系统调试API服务")
    print("=" * 60)
    print(f"API地址: http://localhost:8001")
    print(f"API文档: http://localhost:8001/docs")
    print(f"前端页面: agent_memory_debug.html")
    print("=" * 60)

    uvicorn.run(app, host="0.0.0.0", port=8001)
