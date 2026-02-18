#!/usr/bin/env python3

import sys
import json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.import_project_sessions import ProjectSessionImporter
from ai_factory.integrations.entries_ingest import entries_ingest

OPENCODE_STORAGE = Path.home() / ".local/share/opencode"

def get_test_sessions():
    sessions = []
    session_dir = OPENCODE_STORAGE / "storage" / "session"
    
    if not session_dir.exists():
        return sessions
    
    for project_hash_dir in session_dir.iterdir():
        if not project_hash_dir.is_dir():
            continue
        
        for session_file in project_hash_dir.glob("ses_*.json"):
            try:
                data = json.loads(session_file.read_text())
                data['_storage_path'] = str(session_file)
                sessions.append(data)
            except Exception:
                continue
    
    sessions.sort(key=lambda s: s.get('time', {}).get('created', 0), reverse=True)
    
    return sessions[:20]

def test_import_with_write():
    sessions = get_test_sessions()
    print(f"将导入 {len(sessions)} 个测试session到数据库\n")
    
    importer = ProjectSessionImporter(
        project_code="ai-factory",
        operator="pm-clerk"
    )
    
    imported_entries = []
    
    for i, session in enumerate(sessions, 1):
        session_id = session.get('id', '')
        original_title = session.get('title', 'N/A')[:50]
        
        print(f"\n{'='*70}")
        print(f"[{i}/{len(sessions)}] 导入: {original_title}")
        print(f"Session: {session_id[:20]}...")
        print(f"{'='*70}")
        
        qa_pairs = importer.extract_qa_pairs_from_messages(session_id)
        
        if not qa_pairs:
            print("未找到问答对，跳过")
            continue
        
        print(f"发现 {len(qa_pairs)} 个问答对，导入第一个作为测试")
        qa = qa_pairs[0]
        user_question = qa.get("user", "")
        assistant_answer = qa.get("assistant", "") or ""
        
        print(f"\n👤 用户问题: {user_question[:80]}...")
        print(f"🤖 AI回答: {assistant_answer[:150]}...")
        
        title, summary = importer.generate_title_and_summary_from_qa(user_question, assistant_answer)
        
        print(f"\n📝 LLM生成结果:")
        print(f"   Title: {title}")
        print(f"   Summary ({len(summary)}字): {summary[:250]}...")
        
        created_dt = datetime.now()
        
        payload = {
            "input_content": user_question,
            "title": title,
            "summary_ai": summary,
            "raw_text": f"**用户问题**: {user_question}\n\n**AI回答**: {assistant_answer}",
            "project_code": "ai-factory",
            "user_id": "pm-clerk",
            "note_datetime": created_dt.isoformat(),
            "extra_meta": {
                "source_session_id": session_id,
                "test_import": True,
                "qa_index": 0
            }
        }
        
        if assistant_answer:
            payload["answer_payload"] = {"text": assistant_answer}
        
        try:
            result = entries_ingest(payload)
            entry_id = result.get("entries", [{}])[0].get("entry_id", "unknown")
            print(f"\n✅ 成功写入数据库: {entry_id}")
            imported_entries.append({
                "entry_id": entry_id,
                "title": title,
                "summary_len": len(summary)
            })
        except Exception as e:
            print(f"\n❌ 写入失败: {e}")
    
    print(f"\n\n{'='*70}")
    print("导入完成总结")
    print(f"{'='*70}")
    print(f"成功导入: {len(imported_entries)} 条记录")
    for entry in imported_entries:
        print(f"  - {entry['entry_id']}: {entry['title'][:40]}... ({entry['summary_len']}字)")
    print(f"\n请在DB浏览器中查看这些记录")

if __name__ == "__main__":
    test_import_with_write()
