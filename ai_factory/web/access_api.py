#!/usr/bin/env python3
"""
2号通道 接入层 API（三合一：NOTE 入库、RAG 查询、WEB 查询）
- 前缀：/access/v1
- 鉴权：可选 X-API-Key（通过环境变量 ACCESS_API_KEY 开启）
"""
from __future__ import annotations

import os
import re
import asyncio
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Header, HTTPException

from ai_factory.integrations.task_manager import task_manager, QueueFullError
from ai_factory.integrations.task_types import TaskType
from ai_factory.integrations.rag_api import qa_answer_rag
from ai_factory.integrations.web_api import qa_answer_web

router = APIRouter(prefix="/access/v1", tags=["access-v1"])


def _check_api_key(x_api_key: Optional[str] = Header(default=None)) -> None:
    required = os.getenv("ACCESS_API_KEY")
    if required:
        if not x_api_key or x_api_key != required:
            raise HTTPException(status_code=401, detail="Unauthorized: bad X-API-Key")


@router.post("/entries/ingest")
async def submit_entries_ingest(payload: Dict[str, Any], idempotency_key: Optional[str] = Header(default=None), _: None = Depends(_check_api_key)) -> Dict[str, Any]:
    """提交 NOTE 入库任务（异步）。"""
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="payload 必须为 JSON 对象")

    raw_text = str(payload.get("raw_text", ""))
    if not raw_text.strip():
        raise HTTPException(status_code=400, detail="raw_text 不能为空")

    # 请求体大小限制（1MB，以UTF-8字节长度计）
    if len(raw_text.encode("utf-8")) > 1_000_000:
        raise HTTPException(status_code=413, detail="raw_text 超过 1MB 限制")

    # 幂等键格式校验（可选）
    if idempotency_key:
        if not re.fullmatch(r"[a-zA-Z0-9\-]{8,64}", idempotency_key or ""):
            raise HTTPException(status_code=400, detail="idempotency_key 格式错误")

    try:
        job_id = task_manager.submit_task(TaskType.NOTE, payload, idempotency_key)
    except QueueFullError as e:
        raise HTTPException(status_code=429, detail=str(e)) from e

    return {"ok": True, "job_id": job_id, "status": "queued"}


@router.get("/jobs/{job_id}")
async def get_job_status(job_id: str, _: None = Depends(_check_api_key)) -> Dict[str, Any]:
    job = task_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job 不存在")
    return {"ok": True, "data": job.to_dict()}


@router.post("/rag/query")
async def rag_query(payload: Dict[str, Any], idempotency_key: Optional[str] = Header(default=None), _: None = Depends(_check_api_key)) -> Dict[str, Any]:
    """RAG 同步查询，超时则转异步排队。"""
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="payload 必须为 JSON 对象")

    question = str(payload.get("question_text", "")).strip()
    if not question:
        raise HTTPException(status_code=400, detail="question_text 不能为空")

    # 可选：校验 top_k
    top_k = payload.get("top_k")
    if top_k is not None:
        try:
            tk = int(top_k)
            if tk <= 0 or tk > 100:
                raise ValueError
        except Exception:
            raise HTTPException(status_code=400, detail="top_k 必须为 1~100 的整数")

    # 幂等键格式校验（可选）
    if idempotency_key:
        if not re.fullmatch(r"[a-zA-Z0-9\-]{8,64}", idempotency_key or ""):
            raise HTTPException(status_code=400, detail="idempotency_key 格式错误")

    timeout_s = float(os.getenv("ACCESS_SYNC_TIMEOUT_SECONDS", "8"))
    try:
        result = await asyncio.wait_for(asyncio.to_thread(qa_answer_rag, payload), timeout=timeout_s)
        return {"ok": True, "data": result}
    except asyncio.TimeoutError:
        try:
            job_id = task_manager.submit_task(TaskType.RAG, payload, idempotency_key)
        except QueueFullError as e:
            raise HTTPException(status_code=429, detail=str(e)) from e
        return {"ok": True, "job_id": job_id, "status": "queued"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/web/search")
async def web_search(payload: Dict[str, Any], idempotency_key: Optional[str] = Header(default=None), _: None = Depends(_check_api_key)) -> Dict[str, Any]:
    """WEB 同步查询，超时则转异步排队。"""
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="payload 必须为 JSON 对象")

    question = str(payload.get("question_text", "")).strip()
    if not question:
        raise HTTPException(status_code=400, detail="question_text 不能为空")

    if idempotency_key:
        if not re.fullmatch(r"[a-zA-Z0-9\-]{8,64}", idempotency_key or ""):
            raise HTTPException(status_code=400, detail="idempotency_key 格式错误")

    timeout_s = float(os.getenv("ACCESS_SYNC_TIMEOUT_SECONDS", "8"))
    try:
        result = await asyncio.wait_for(asyncio.to_thread(qa_answer_web, payload), timeout=timeout_s)
        return {"ok": True, "data": result}
    except asyncio.TimeoutError:
        try:
            job_id = task_manager.submit_task(TaskType.WEB, payload, idempotency_key)
        except QueueFullError as e:
            raise HTTPException(status_code=429, detail=str(e)) from e
        return {"ok": True, "job_id": job_id, "status": "queued"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
