#!/usr/bin/env python3
"""
⏸️ [已封存 - 2026-02-17] ⏸️

⚠️  此脚本已暂时封存，不再主动使用 ⚠️

封存原因:
- 数据导入策略调整，改为直接从 OpenCode SQLite/JSON 导入到 entries
- 避免 all_sessions.md → entries 的中间环节
- 替代方案: import_project_sessions.py (项目私域直接导入)

封存详情: scripts/archived/all_sessions_channel/README.md

---

数据对齐脚本 - 同步 all_sessions.md 到 entries 并补齐向量化

功能：
1. 解析 all_sessions.md 中的 sessions
2. 检查哪些 sessions 未入库到 entries
3. 批量导入未入库的 sessions
4. 补齐未向量化的 entries

使用：
    python scripts/sync_all_sessions_to_entries.py

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
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Set

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from ai_factory.db.pgvector_client import get_connection
from ai_factory.integrations.entries_ingest import entries_ingest


ALL_SESSIONS_FILE = Path("/root/ai-factory/documents/all_sessions.md")


def extract_sessions_from_md() -> List[Dict[str, Any]]:
    """从 all_sessions.md 提取所有 sessions"""
    if not ALL_SESSIONS_FILE.exists():
        print(f"❌ 文件不存在: {ALL_SESSIONS_FILE}")
        return []
    
    content = ALL_SESSIONS_FILE.read_text(encoding='utf-8')
    
    # 按会话分割（以 --- 和 # 开头分隔）
    session_pattern = r'\n# ([^\n]+)\n\n---\n\n\*\*会话 ID\*\*:\s*`([^`]+)`'
    sessions = []
    
    # 提取会话块
    parts = re.split(r'\n---\n\n', content)
    
    for i, part in enumerate(parts[1:], 1):  # 跳过第一个空块
        # 提取会话ID
        session_id_match = re.search(r'\*\*会话 ID\*\*:\s*`([^`]+)`', part)
        if not session_id_match:
            continue
        
        session_id = session_id_match.group(1)
        
        # 提取标题
        title_match = re.search(r'# ([^\n]+)', part)
        title = title_match.group(1) if title_match else f"Session {session_id[:8]}"
        
        # 提取创建时间
        created_match = re.search(r'\*\*创建时间\*\*:\s*([^\n]+)', part)
        created_at = created_match.group(1) if created_match else None
        
        # 提取内容（问答对）
        qa_content = extract_qa_pairs(part)
        
        sessions.append({
            'session_id': session_id,
            'title': title,
            'created_at': created_at,
            'content': qa_content,
            'raw_text': part
        })
    
    return sessions


def extract_qa_pairs(text: str) -> str:
    """提取问答对内容"""
    qa_pattern = r'### 问答对 #\d+[^#]+?\*\*👤 USER\*\*([^#]+?)(?:\*\*🤖 ASSISTANT\*\*([^#]+?))?\n---'
    matches = re.findall(qa_pattern, text, re.DOTALL)
    
    qa_list = []
    for user_msg, assistant_msg in matches[:5]:  # 只取前5轮，避免太长
        user_clean = user_msg.strip()[:200] if user_msg else ""
        if user_clean:
            qa_list.append(f"Q: {user_clean}")
        if assistant_msg:
            assistant_clean = assistant_msg.strip()[:200]
            if assistant_clean:
                qa_list.append(f"A: {assistant_clean}")
    
    return "\n".join(qa_list) if qa_list else text[:500]


def get_existing_session_ids() -> Set[str]:
    """获取已入库的 session IDs"""
    conn = get_connection()
    existing = set()
    
    try:
        with conn.cursor() as cur:
            # 查找 source_session_id 或 scene_tags 中包含 session 标记的 entries
            cur.execute('''
                SELECT entry_id, scene_tags::text 
                FROM entries 
                WHERE scene_tags::text LIKE '%session%' 
                   OR input_content LIKE '%ses_%'
            ''')
            
            for row in cur.fetchall():
                entry_id, tags = row
                # 尝试提取 session_id
                match = re.search(r'ses_[a-z0-9]+', str(tags) + entry_id)
                if match:
                    existing.add(match.group(0))
    finally:
        conn.close()
    
    return existing


def import_session_to_entries(session: Dict[str, Any]) -> bool:
    """导入单个 session 到 entries"""
    try:
        payload = {
            "raw_text": f"# {session['title']}\n\n{session['content']}",
            "project_code": "opencode-sessions",
            "user_id": "session-importer",
            "note_datetime": session['created_at'] or datetime.now().isoformat(),
            "extra_context": {
                "tags_snapshot": {
                    "department": ["AI工厂"],
                    "planning": ["会话归档"],
                    "execution": ["自动导入"],
                    "source": ["all_sessions_md"],
                    "session_id": [session['session_id']]
                }
            },
            "extra_meta": {
                "space_type": "session_record",
                "source_session_id": session['session_id'],
                "section": "OpenCode会话",
                "section_type": "session",
                "visibility": "private",
                "source_system": "opencode"
            }
        }
        
        result = entries_ingest(payload)
        entry_id = result.get("entries", [{}])[0].get("entry_id", "unknown")
        print(f"  ✅ 已导入: {session['session_id']} -> {entry_id}")
        return True
        
    except Exception as e:
        print(f"  ❌ 导入失败 {session['session_id']}: {e}")
        return False


def check_and_fix_embeddings():
    """检查并补齐未向量化的记录"""
    conn = get_connection()
    
    try:
        with conn.cursor() as cur:
            # 查找未向量化的记录
            cur.execute('''
                SELECT e.entry_id, e.title, e.input_content
                FROM entries e
                LEFT JOIN entry_embeddings em ON e.entry_id = em.entry_id
                WHERE em.entry_id IS NULL
                ORDER BY e.created_at DESC
            ''')
            
            missing = cur.fetchall()
            
            if not missing:
                print("✅ 所有记录都已向量化")
                return 0
            
            print(f"\n⚠️  发现 {len(missing)} 条未向量化记录")
            
            # 这里可以调用向量化脚本
            # 目前仅报告，实际向量化需要调用 DashScope/Ollama
            for row in missing[:5]:  # 只显示前5条
                entry_id, title, content = row
                print(f"  - {entry_id}: {title[:50] if title else 'N/A'}...")
            
            if len(missing) > 5:
                print(f"  ... 还有 {len(missing) - 5} 条")
            
            return len(missing)
            
    finally:
        conn.close()


def main():
    print("=" * 60)
    print("🔄 数据对齐: all_sessions.md → entries")
    print("=" * 60)
    
    # 步骤1: 提取 all_sessions.md 中的 sessions
    print("\n📖 步骤1: 解析 all_sessions.md...")
    sessions = extract_sessions_from_md()
    print(f"✅ 找到 {len(sessions)} 个会话")
    
    # 步骤2: 检查已入库的 sessions
    print("\n📊 步骤2: 检查已入库的 sessions...")
    existing = get_existing_session_ids()
    print(f"✅ 数据库中已有 {len(existing)} 个会话标记")
    
    # 步骤3: 找出未入库的 sessions
    all_session_ids = {s['session_id'] for s in sessions}
    missing_ids = all_session_ids - existing
    
    print(f"\n🔍 步骤3: 对比结果")
    print(f"   all_sessions.md 中的会话: {len(all_session_ids)}")
    print(f"   已入库的会话: {len(existing)}")
    print(f"   ⚠️  未入库的会话: {len(missing_ids)}")
    
    # 步骤4: 导入未入库的 sessions
    if missing_ids:
        print(f"\n📥 步骤4: 导入 {len(missing_ids)} 个未入库会话...")
        imported = 0
        for session in sessions:
            if session['session_id'] in missing_ids:
                if import_session_to_entries(session):
                    imported += 1
        print(f"✅ 成功导入 {imported} 个会话")
    else:
        print("\n✅ 所有会话都已入库")
    
    # 步骤5: 检查向量化完整性
    print("\n🔍 步骤5: 检查向量化完整性...")
    missing_embeddings = check_and_fix_embeddings()
    
    # 总结
    print("\n" + "=" * 60)
    print("📋 同步总结")
    print("=" * 60)
    print(f"   all_sessions.md 总会话: {len(sessions)}")
    print(f"   已入库: {len(existing)}")
    print(f"   本次导入: {len(missing_ids)}")
    print(f"   未向量化: {missing_embeddings}")
    
    if missing_embeddings > 0:
        print("\n💡 提示: 运行以下命令补齐向量化:")
        print("   python ai_factory/vectorize_entries_with_dashscope.py")


if __name__ == "__main__":
    main()
