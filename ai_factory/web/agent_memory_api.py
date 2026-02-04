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
    EntryService,
    VectorClient,
    initialize_monitoring,
    get_logger,
    get_llm_client
)
from ai_factory.db.pgvector_client import connection_scope
from ai_factory.web.access_api import router as access_router

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

# 挂载 2号通道（接入层）三合一路由
app.include_router(access_router)

# 初始化记忆服务（仅 entries + 向量检索，不再依赖 chat* 表）
entry_service = None
vector_client = None
llm_client = None

def init_services():
    """初始化记忆系统服务（entries-only 模式）"""
    global entry_service, vector_client, llm_client
    
    try:
        # 初始化监控系统
        initialize_monitoring(log_level="INFO", log_format="text")
        
        # 仅初始化长期记忆相关组件
        vector_client = VectorClient()
        entry_service = EntryService(vector_client=vector_client)
        llm_client = get_llm_client()
        
        logger.info("记忆系统服务初始化成功（entries-only）")
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
            "entry_service": "ok",
            "vector_client": "ok"
        }
    }

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
                    SELECT entry_id, input_content AS content, created_at
                    FROM entries
                    WHERE input_content ILIKE %s
                    LIMIT %s
                """, (f"%{query}%", top_k))
                
                rows = cur.fetchall()
                
                result = []
                for row in rows:
                    result.append({
                        "entry_id": row[0],
                        "content": row[1],
                        "summary": "",  # 暂时返回空字符串
                        "entry_type": "note",
                        "similarity": 0.8,  # 模拟相似度
                        "created_at": row[2].isoformat() if row[2] else None,
                        "metadata_json": {},
                        "source": "entries"
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
    """获取系统指标（不再统计 chat* 表）"""
    try:
        # 这里返回模拟数据，实际应该从监控系统获取
        metrics = {
            "cache_hit_rate": 75.5,
            "search_latency": 150,
            "total_entries": 1234,
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
    """完整问答接口已下线：当前仅支持 entries 级别操作"""
    raise HTTPException(status_code=410, detail="/api/memory/chat 已下线：chat* 表与会话级存储已移除，仅保留 entries 级记忆接口")

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
