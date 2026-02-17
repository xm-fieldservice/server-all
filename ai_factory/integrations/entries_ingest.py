"""标准化入库通道 - entries_ingest

💾 [2] 入库通道节点
职责: 接收已处理好的payload → 写入entries表 → 向量化

重要说明:
- 本模块**不包含**LLM处理（title/summary生成）
- LLM处理必须在调用方完成（如 session_to_entries [1]节点）
- 本模块只负责标准化入库 + 向量化

使用方式:
    from ai_factory.integrations.entries_ingest import entries_ingest
    
    # payload必须包含LLM处理好的字段
    payload = {
        "title": "LLM生成的标题",           # 必须
        "summary_ai": "LLM生成的摘要",      # 必须
        "raw_text": "原始内容",              # 必须
        "project_code": "pm-agent",          # 必须
        "user_id": "pm-agent",               # 可选
        "extra_context": {...},              # 可选
    }
    
    result = entries_ingest(payload)

通道说明:
- 1号通道（直写）: 直接调用entries_ingest同步执行
- 2号通道（排队）: HTTP API接收请求 → 入队 → 出队调用entries_ingest
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
from uuid import uuid4

from ai_factory.agents.entry_agents import ChunkResult
from ai_factory.db.entries_repo import insert_entry
from ai_factory.vectorization import get_strategy


ROOT_DIR = Path(__file__).resolve().parents[2]
FAILED_MD_PATH = ROOT_DIR / "写库失败笔记保存文档.md"


@dataclass
class EntryIngestionResult:
    """单次规整/写入操作的聚合结果。"""
    entries: List[ChunkResult]


def _build_scene_tags_from_payload(payload: Dict[str, Any], text: str) -> Dict[str, List[str]]:
    """从payload构建scene_tags。"""
    extra_ctx = payload.get("extra_context") or {}
    tags_snapshot = extra_ctx.get("tags_snapshot") or {}
    
    scene_tags: Dict[str, List[str]] = {}
    if isinstance(tags_snapshot, dict):
        for key, val in tags_snapshot.items():
            if isinstance(val, list):
                scene_tags[key] = [str(x).strip() for x in val if x]
            elif val:
                scene_tags[key] = [str(val).strip()]
    
    return scene_tags


def _append_failed_entry_to_md(raw_text: str, payload: Dict[str, Any], error: BaseException) -> None:
    """将写库失败的原始笔记追加到统一的失败文档中。"""
    try:
        note_dt = str(payload.get("note_datetime") or "").strip()
        if not note_dt:
            note_dt = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

        lines: List[str] = []
        lines.append(f"## 📝 笔记 - {note_dt}\n\n")
        lines.append(raw_text.rstrip("\n") + "\n\n")

        FAILED_MD_PATH.parent.mkdir(parents=True, exist_ok=True)
        with FAILED_MD_PATH.open("a", encoding="utf-8") as f:
            f.writelines(lines)
    except Exception as file_err:
        print(f"[entries_ingest] 写入失败文档时出错: {file_err!r}")


def _vectorize_entry_sync(entry: Dict[str, Any], context: str = "entries_ingest") -> bool:
    """同步向量化 entry 并写入 embeddings 表。"""
    try:
        strategy = get_strategy()
        success = strategy.process_entry(entry)
        if success:
            print(f"[{context}] 向量化完成 (1024维)")
        return success
    except Exception as exc:
        print(f"[{context}] 向量化失败: {exc!r}")
        return False


def entries_ingest(payload: Dict[str, Any]) -> Dict[str, Any]:
    """💾 [2] 标准化入库通道
    
    接收已处理好的payload（包含LLM生成的title和summary），
    写入entries表并执行向量化。
    
    Args:
        payload: 必须包含以下字段
            - title: str (LLM生成, ≤60字符)
            - summary_ai: str (LLM生成, ≤500字符)  
            - raw_text: str (原始内容)
            - project_code: str (项目代码)
            - user_id: str (可选, 操作者)
            - extra_context: dict (可选, 包含tags_snapshot)
            - extra_meta: dict (可选)
            - note_datetime: str (可选)
    
    Returns:
        dict: {"entries": [{"entry_id": ..., "title": ..., "content": ...}]}
    """
    # 验证必填字段
    required_fields = ["title", "summary_ai", "raw_text", "project_code"]
    missing = [f for f in required_fields if not payload.get(f)]
    if missing:
        raise ValueError(f"必填字段缺失: {missing}")
    
    title = payload["title"]
    summary = payload["summary_ai"]
    raw_text = payload["raw_text"]
    project_code = payload["project_code"]
    user_id = payload.get("user_id", "pm-agent")
    
    entry_id = f"ent_{uuid4().hex[:8]}"
    created_at = datetime.utcnow().isoformat()
    
    # 构建entry
    # 优先使用 input_content（问答对的用户问题），否则使用 raw_text
    input_content = payload.get("input_content", raw_text)
    
    entry: Dict[str, Any] = {
        "entry_id": entry_id,
        "title": title,
        "summary_ai": summary,
        "input_content": input_content,
        "project_code": project_code,
        "user_id": user_id,
        "created_at": created_at,
    }
    
    # 添加scene_tags
    scene_tags = _build_scene_tags_from_payload(payload, raw_text)
    if scene_tags:
        entry["scene_tags"] = scene_tags
    
    # 添加extra_meta
    extra_meta = payload.get("extra_meta", {})
    if extra_meta:
        entry.setdefault("extra_meta", {}).update(extra_meta)
    
    # 添加 answer_payload（问答对的回答）
    answer_payload = payload.get("answer_payload")
    if answer_payload:
        entry["answer_payload"] = answer_payload
    
    # 应用tree字段
    try:
        from ai_factory.domain.tree_meta import TreeMeta, apply_tree_meta_to_entry
        meta = TreeMeta.from_payload(payload)
        apply_tree_meta_to_entry(entry, meta)
    except Exception:
        entry.setdefault("space_type", "note")
    
    # 写入数据库
    try:
        insert_entry(entry)
    except Exception as e:
        _append_failed_entry_to_md(raw_text, payload, e)
        raise RuntimeError(f"写入entries表失败: {e}")
    
    # 向量化
    _vectorize_entry_sync(entry)
    
    # 返回结果
    chunk = ChunkResult(entry_id=entry_id, title=title, content=raw_text)
    result = EntryIngestionResult(entries=[chunk])
    
    return {"entries": [asdict(c) for c in result.entries]}
