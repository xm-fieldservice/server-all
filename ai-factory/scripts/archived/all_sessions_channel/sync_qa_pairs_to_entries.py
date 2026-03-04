#!/usr/bin/env python3
"""
数据对齐脚本 - 同步 all_sessions.md 到 entries (问答对解析版)

功能：
1. 解析 all_sessions.md 中的问答对
2. 每个问答对拆分为:
   - input_content: USER 问题
   - answer_payload: ASSISTANT 回答 (JSON格式)
   - title: LLM生成的标题
ai: LLM生成的摘要

使用   - summary_：
    python scripts/archived/all_sessions_channel/sync_qa_pairs_to_entries.py

环境变量：
    AI_PG_HOST - 数据库主机 (默认: localhost)
    AI_PG_PORT - 数据库端口 (默认: 5434)
    AI_PG_DB - 数据库名 (默认: rag_db)
    AI_PG_USER - 数据库用户 (默认: rag_user)
    AI_PG_PASSWORD - 数据库密码 (默认: rag_password)
"""

import os
import re
import sys
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Set, Optional

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ai_factory.db.pgvector_client import get_connection
from ai_factory.integrations.entries_ingest import entries_ingest


ALL_SESSIONS_FILE = Path("/root/ai-factory/documents/all_sessions.md")


def extract_qa_pairs(text: str) -> List[Dict[str, str]]:
    """提取问答对内容
    
    返回格式:
    [
        {
            "user": "用户问题",
            "assistant": "助手回答",
            "timestamp": "2026-02-15 15:07:01"
        },
        ...
    ]
    """
    qa_pairs = []
    
    # 按问答对分割
    # 格式: ### 问答对 #N (timestamp)
    qa_blocks = re.split(r'### 问答对 #\d+ \([^)]+\)', text)
    
    for block in qa_blocks:
        if not block.strip():
            continue
            
        # 提取 USER 和 ASSISTANT
        user_match = re.search(r'\*\*👤 USER\*\*\s*(.+?)(?=\*\*🤖 ASSISTANT\*\*|$)', block, re.DOTALL)
        assistant_match = re.search(r'\*\*🤖 ASSISTANT\*\*\s*(.+?)(?=---|$)', block, re.DOTALL)
        
        if user_match:
            user_content = user_match.group(1).strip()
            assistant_content = assistant_match.group(1).strip() if assistant_match else None
            
            if user_content:
                qa_pairs.append({
                    "user": user_content,
                    "assistant": assistant_content
                })
    
    return qa_pairs


def extract_sessions_with_qa() -> List[Dict[str, Any]]:
    """从 all_sessions.md 提取所有 sessions 及问答对"""
    if not ALL_SESSIONS_FILE.exists():
        print(f"❌ 文件不存在: {ALL_SESSIONS_FILE}")
        return []
    
    content = ALL_SESSIONS_FILE.read_text(encoding='utf-8')
    
    # 按 --- 分隔不同的会话块
    # 查找会话标题和会话 ID
    sessions = []
    
    # 匹配会话块: --- 之后到下一个 --- 之前
    session_blocks = re.split(r'\n---\n', content)
    
    current_session = None
    current_qa_pairs = []
    
    for block in session_blocks:
        # 查找会话标题 (以 # 开头)
        title_match = re.search(r'^# (.+)$', block.strip(), re.MULTILINE)
        
        # 查找会话 ID
        session_id_match = re.search(r'\*\*会话 ID\*\*:\s*`([^`]+)`', block)
        
        # 查找创建时间
        created_match = re.search(r'\*\*创建时间\*\*:\s*([^\n]+)', block)
        
        # 如果找到新会话的开始，保存上一个会话
        if title_match and session_id_match:
            if current_session and current_qa_pairs:
                current_session['qa_pairs'] = current_qa_pairs
                sessions.append(current_session)
            
            # 开始新会话
            current_session = {
                'session_id': session_id_match.group(1),
                'title': title_match.group(1),
                'created_at': created_match.group(1) if created_match else None,
                'raw_content': block
            }
            current_qa_pairs = []
        
        # 如果在会话中，提取问答对
        if current_session:
            # 提取当前块中的问答对
            qa_in_block = extract_qa_pairs(block)
            current_qa_pairs.extend(qa_in_block)
    
    # 保存最后一个会话
    if current_session and current_qa_pairs:
        current_session['qa_pairs'] = current_qa_pairs
        sessions.append(current_session)
    
    return sessions


def get_existing_entry_ids() -> Set[str]:
    """获取已入库的 entry IDs (用于去重)"""
    conn = get_connection()
    existing = set()
    
    try:
        with conn.cursor() as cur:
            # 查找有 source_session_id 的 entries
            cur.execute('''
                SELECT entry_id, extra_meta->>'source_session_id' as src_sid
                FROM entries 
                WHERE extra_meta IS NOT NULL
                  AND extra_meta->>'source_session_id' IS NOT NULL
            ''')
            
            for row in cur.fetchall():
                if row[1]:
                    existing.add(f"{row[1]}_{row[0]}")
    finally:
        conn.close()
    
    return existing


def import_qa_pair_to_entries(session: Dict[str, Any], qa_pair: Dict[str, str], index: int) -> bool:
    """导入单个问答对到 entries
    
    字段映射:
    - input_content: USER 问题
    - answer_payload: ASSISTANT 回答 (JSON格式: {"text": "..."})
    - title: LLM生成的标题 (这里先用用户问题作为标题)
    - summary_ai: LLM生成的摘要 (这里先用用户问题作为摘要)
    """
    user_question = qa_pair.get("user", "").strip()
    assistant_answer = qa_pair.get("assistant")
    
    if not user_question:
        return False
    
    try:
        # 构建 answer_payload
        answer_payload = None
        if assistant_answer:
            answer_payload = {"text": assistant_answer}
        
        # 构建 payload - 注意这里直接使用 input_content 而不是 raw_text
        # 因为 entries_ingest 会处理 raw_text 生成 title/summary
        # 这里我们手动设置以便更好地控制
        payload = {
            # input_content 应该是原始问题
            "input_content": user_question,
            # title 和 summary_ai 暂时用问题本身，后续可以通过 LLM 优化
            "title": user_question[:60] if len(user_question) > 60 else user_question,
            "summary_ai": user_question[:200] if len(user_question) > 200 else user_question,
            "project_code": "opencode-sessions",
            "user_id": "session-importer",
            "note_datetime": session.get('created_at') or datetime.now().isoformat(),
            "extra_context": {
                "tags_snapshot": {
                    "department": ["AI工厂"],
                    "planning": ["会话归档"],
                    "execution": ["自动导入"],
                    "source": ["all_sessions_md"],
                    "session_id": [session['session_id']],
                    "qa_index": [str(index)]
                }
            },
            "extra_meta": {
                "space_type": "qa_pair",
                "source_session_id": session['session_id'],
                "qa_index": index,
                "section": "OpenCode会话",
                "section_type": "qa_pair",
                "visibility": "private",
                "source_system": "opencode"
            }
        }
        
        # 添加 answer_payload
        if answer_payload:
            payload["answer_payload"] = answer_payload
        
        result = entries_ingest(payload)
        entry_id = result.get("entries", [{}])[0].get("entry_id", "unknown")
        print(f"  ✅ 已导入: {session['session_id']}[{index}] -> {entry_id}")
        return True
        
    except Exception as e:
        print(f"  ❌ 导入失败 {session['session_id']}[{index}]: {e}")
        return False


def main():
    print("=" * 70)
    print("🔄 数据对齐: all_sessions.md → entries (问答对解析版)")
    print("=" * 70)
    
    # 步骤1: 提取 all_sessions.md 中的 sessions 和问答对
    print("\n📖 步骤1: 解析 all_sessions.md...")
    sessions = extract_sessions_with_qa()
    print(f"✅ 找到 {len(sessions)} 个会话")
    
    # 统计问答对数量
    total_qa = sum(len(s.get('qa_pairs', [])) for s in sessions)
    print(f"✅ 共找到 {total_qa} 个问答对")
    
    # 步骤2: 检查已入库的 entries
    print("\n📊 步骤2: 检查已入库的 entries...")
    existing = get_existing_entry_ids()
    print(f"✅ 数据库中已有 {len(existing)} 条会话记录")
    
    # 步骤3: 导入问答对
    print("\n📥 步骤3: 导入问答对...")
    imported = 0
    skipped = 0
    
    for session in sessions:
        qa_pairs = session.get('qa_pairs', [])
        
        for i, qa in enumerate(qa_pairs):
            # 生成唯一标识用于去重
            unique_id = f"{session['session_id']}_{i}"
            
            if unique_id in existing:
                skipped += 1
                continue
            
            if import_qa_pair_to_entries(session, qa, i):
                imported += 1
    
    # 总结
    print("\n" + "=" * 70)
    print("📋 同步总结")
    print("=" * 70)
    print(f"   all_sessions.md 总会话: {len(sessions)}")
    print(f"   all_sessions.md 问答对总数: {total_qa}")
    print(f"   已入库记录: {len(existing)}")
    print(f"   本次导入: {imported}")
    print(f"   跳过(已存在): {skipped}")
    
    if imported > 0:
        print(f"\n💡 提示: 成功导入 {imported} 条问答对")
        print("   - input_content = USER 问题")
        print("   - answer_payload = ASSISTANT 回答 (JSON格式)")
        print("   - title/summary_ai = 用户问题")


if __name__ == "__main__":
    main()
