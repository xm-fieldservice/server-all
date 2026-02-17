#!/usr/bin/env python3
"""
📥 [1] session_to_entries 节点 - 项目私域数据导入工具（重写版）

职责：从session数据库导出 + LLM处理title和summary
归属：PM-clerk（执行）/ PM-agent（审核）

核心改进：
- 正确读取OpenCode三层存储结构（session → messages → parts）
- 为每个问答对生成独立的entry
- 复用已验证的export_sessions.py核心函数

使用示例：
    python import_project_sessions_v2.py --project pm-agent --operator pm-agent --batch-all
"""

import os
import sys
import argparse
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

# 复用已验证的export_sessions核心函数
sys.path.insert(0, str(Path(__file__).parent / "archived" / "all_sessions_channel"))
from export_sessions import (
    export_session_with_count,
    extract_text_from_message,
    STORAGE_PATH,
)

from ai_factory.db.pgvector_client import get_connection
from ai_factory.integrations.entries_ingest import entries_ingest

# LLM处理函数
from ai_factory.vectorize_entries_with_ollama import (
    generate_title_with_ollama,
    generate_summary_with_ollama,
)

USE_LOCAL_LLM = os.getenv("USE_LOCAL_LLM", "true").lower() == "true"


class ProjectSessionImporterV2:
    """项目级Session导入器（V2 - 正确读取问答对）"""
    
    def __init__(self, project_code: str, operator: str = "pm-agent"):
        self.project_code = project_code
        self.operator = operator
        self.stats = {
            'sessions_found': 0,
            'qa_pairs_found': 0,
            'imported': 0,
            'skipped': 0,
            'failed': 0
        }
    
    def get_opencode_sessions(self) -> List[Dict]:
        """从OpenCode存储读取所有session元数据"""
        sessions = []
        session_dir = STORAGE_PATH / "session"
        
        if not session_dir.exists():
            return sessions
        
        for project_hash_dir in session_dir.iterdir():
            if not project_hash_dir.is_dir():
                continue
            
            for session_file in project_hash_dir.glob("ses_*.json"):
                try:
                    import json
                    data = json.loads(session_file.read_text())
                    data['_storage_path'] = str(session_file)
                    sessions.append(data)
                except Exception as e:
                    print(f"  ⚠️  读取失败 {session_file.name}: {e}")
        
        return sessions
    
    def is_session_imported(self, session_id: str) -> bool:
        """检查session是否已导入"""
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COUNT(*) FROM entries 
                    WHERE extra_meta->>'source_session_id' = %s
                    OR extra_meta->>'session_id' = %s
                """, (session_id, session_id))
                return cur.fetchone()[0] > 0
        finally:
            conn.close()
    
    def extract_qa_pairs(self, session_data: Dict) -> List[Dict]:
        """从session中提取问答对
        
        返回: [{"user": "问题...", "assistant": "回答...", "time": "..."}]
        """
        # 使用export_sessions的核心函数获取完整数据
        full_data, msg_count, turn_count = export_session_with_count(session_data)
        messages = full_data.get("messages", [])
        
        qa_pairs = []
        
        # 识别问答对：user后跟assistant
        for i, msg in enumerate(messages):
            if msg.get("role", "").lower() != "user":
                continue
            
            user_content = extract_text_from_message(msg)
            if not user_content.strip():
                continue
            
            # 找对应的assistant回复
            assistant_content = ""
            if i + 1 < len(messages):
                next_msg = messages[i + 1]
                if next_msg.get("role", "").lower() == "assistant":
                    assistant_content = extract_text_from_message(next_msg)
            
            qa_pairs.append({
                "user": user_content,
                "assistant": assistant_content,
                "time": msg.get("time", {}).get("created", 0),
                "msg_id": msg.get("id", ""),
            })
        
        return qa_pairs
    
    def generate_title_and_summary(self, user_content: str, assistant_content: str) -> tuple:
        """使用LLM生成title和summary"""
        combined = f"用户问题：{user_content}\n\n助手回答：{assistant_content}"
        content_len = len(combined)
        
        if content_len <= 60:
            title = combined[:60]
            summary = combined
            print(f"    📝 短内容，直接使用原文")
        elif content_len <= 600:
            if USE_LOCAL_LLM:
                try:
                    title = generate_title_with_ollama(combined, max_length=60)
                    if not title:
                        title = user_content[:60]
                    print(f"    📝 LLM生成title: {title[:30]}...")
                except Exception as e:
                    print(f"    ⚠️  LLM失败，使用原文: {e}")
                    title = user_content[:60]
            else:
                # 使用DeepSeek API（简化版）
                title = user_content[:60]
            summary = combined[:500]
        else:
            if USE_LOCAL_LLM:
                try:
                    title = generate_title_with_ollama(combined, max_length=60)
                    summary = generate_summary_with_ollama(combined, max_length=500)
                    if not title:
                        title = user_content[:60]
                    if not summary:
                        summary = combined[:500]
                    print(f"    📝 LLM生成: title={title[:30]}..., summary={summary[:50]}...")
                except Exception as e:
                    print(f"    ⚠️  LLM失败，使用原文: {e}")
                    title = user_content[:60]
                    summary = combined[:500]
            else:
                title = user_content[:60]
                summary = combined[:500]
        
        return title, summary
    
    def build_scene_tags(self, session: Dict, qa_index: int) -> Dict[str, List[str]]:
        """构建scene_tags"""
        tags = {
            "project_code": [self.project_code],
            "operator": [self.operator],
            "department": ["AI工厂"],
            "team": ["项目管理部"],
            "source": ["opencode_session"],
            "import_method": ["direct_importer_v2"],
            "type": ["qa_pair"],
            "knowledge_level": ["record"],
            "status": ["active"],
            "visibility": ["private"],
        }
        
        # 从session标题推断业务类型
        title = session.get('title', '').lower()
        
        if any(kw in title for kw in ['设计', '架构', '方案', '规划', '草案', '基线']):
            tags["planning"] = ["架构设计"]
            tags["knowledge_level"] = ["knowledge"]
        elif any(kw in title for kw in ['评审', 'review', '评估']):
            tags["planning"] = ["评审记录"]
            tags["knowledge_level"] = ["information"]
        elif any(kw in title for kw in ['任务', '工单', 'todo', '执行']):
            tags["execution"] = ["任务执行"]
        elif any(kw in title for kw in ['bug', 'fix', '错误', '调试']):
            tags["execution"] = ["问题修复"]
        elif any(kw in title for kw in ['实现', '开发', '编码']):
            tags["execution"] = ["开发实现"]
        elif any(kw in title for kw in ['测试', '验证', '检查']):
            tags["monitoring"] = ["测试验证"]
        else:
            tags["planning"] = ["讨论记录"]
        
        return tags
    
    def import_qa_pair(self, session: Dict, qa_pair: Dict, qa_index: int) -> bool:
        """导入单个问答对"""
        session_id = session.get('id', '')
        user_content = qa_pair.get("user", "")
        assistant_content = qa_pair.get("assistant", "")
        
        if not user_content.strip():
            return False
        
        # LLM生成title和summary
        print(f"    🤖 LLM处理 QA#{qa_index}...")
        title, summary = self.generate_title_and_summary(user_content, assistant_content)
        
        # 构建完整内容
        content_parts = [
            f"# {title}",
            f"\n**Session ID**: `{session_id}`",
            f"**问答对序号**: #{qa_index}",
            f"**项目代码**: {self.project_code}",
            f"**导入者**: {self.operator}\n",
            f"## 用户问题\n{user_content}\n",
        ]
        
        if assistant_content:
            content_parts.append(f"## 助手回答\n{assistant_content}\n")
        
        full_content = "\n".join(content_parts)
        
        # 构建scene_tags
        scene_tags = self.build_scene_tags(session, qa_index)
        
        # 构建extra_meta
        extra_meta = {
            "source_session_id": session_id,
            "source_system": "opencode",
            "import_method": "project_importer_v2",
            "project_code": self.project_code,
            "operator": self.operator,
            "qa_pair_index": qa_index,
            "msg_id": qa_pair.get("msg_id", ""),
            "space_type": "qa_pair",
            "visibility": "private",
            "access_control": f"project:{self.project_code}",
            "llm_processed": True,
        }
        
        # 构建payload
        payload = {
            "title": title,
            "summary_ai": summary,
            "raw_text": full_content,
            "project_code": self.project_code,
            "user_id": self.operator,
            "extra_context": {
                "tags_snapshot": scene_tags
            },
            "extra_meta": extra_meta
        }
        
        # 调用入库通道
        try:
            result = entries_ingest(payload)
            entry_id = result.get("entries", [{}])[0].get("entry_id", "unknown")
            print(f"      ✅ 已导入: QA#{qa_index} → {entry_id}")
            return True
        except Exception as e:
            print(f"      ❌ 导入失败 QA#{qa_index}: {e}")
            return False
    
    def import_session(self, session: Dict) -> int:
        """导入单个session的所有问答对，返回成功导入数量"""
        session_id = session.get('id', '')
        
        # 检查是否已导入
        if self.is_session_imported(session_id):
            print(f"  ⏭️  跳过（已导入）: {session_id[:25]}...")
            self.stats['skipped'] += 1
            return 0
        
        # 提取问答对
        print(f"  📖 提取问答对: {session_id[:25]}...")
        qa_pairs = self.extract_qa_pairs(session)
        
        if not qa_pairs:
            print(f"  ⚠️  无问答对: {session_id[:25]}...")
            return 0
        
        self.stats['qa_pairs_found'] += len(qa_pairs)
        print(f"  📊 找到 {len(qa_pairs)} 个问答对")
        
        # 导入每个问答对
        success_count = 0
        for i, qa_pair in enumerate(qa_pairs, 1):
            if self.import_qa_pair(session, qa_pair, i):
                success_count += 1
        
        return success_count
    
    def run(self, batch_all: bool = False, dry_run: bool = False):
        """运行导入流程"""
        print("=" * 70)
        print(f"🔄 项目私域数据导入 V2")
        print(f"   项目代码: {self.project_code}")
        print(f"   操作者: {self.operator}")
        print(f"   模式: {'批量导入' if batch_all else '选择性导入'}")
        print("=" * 70)
        
        # 扫描sessions
        print("\n📖 扫描 OpenCode sessions...")
        sessions = self.get_opencode_sessions()
        self.stats['sessions_found'] = len(sessions)
        print(f"✅ 找到 {len(sessions)} 个会话\n")
        
        if dry_run:
            print("🏃 模拟运行模式（不实际导入）：\n")
            for session in sessions[:5]:
                qa_pairs = self.extract_qa_pairs(session)
                title = session.get('title', 'N/A')[:40]
                print(f"  - {session.get('id', 'N/A')[:30]}: {title}... ({len(qa_pairs)}个问答对)")
            if len(sessions) > 5:
                print(f"  ... 还有 {len(sessions) - 5} 个")
            return
        
        # 导入
        print(f"📥 开始导入到项目 '{self.project_code}'...\n")
        for i, session in enumerate(sessions, 1):
            print(f"[{i}/{len(sessions)}]", end=" ")
            success = self.import_session(session)
            if success > 0:
                self.stats['imported'] += success
        
        # 报告
        print(f"\n{'='*70}")
        print(f"📊 导入完成报告")
        print(f"{'='*70}")
        print(f"   发现会话:    {self.stats['sessions_found']}")
        print(f"   问答对总数:  {self.stats['qa_pairs_found']}")
        print(f"   成功导入:    {self.stats['imported']}")
        print(f"   跳过(已存在): {self.stats['skipped']}")
        print(f"   失败:        {self.stats['failed']}")
        print(f"   项目代码:    {self.project_code}")
        print(f"   数据隔离:    ✅ scene_tags.project_code = {self.project_code}")
        print(f"{'='*70}\n")


def main():
    parser = argparse.ArgumentParser(
        description='项目私域数据导入工具 V2 - 正确提取问答对'
    )
    parser.add_argument(
        '--project', '-p',
        required=True,
        help='项目代码（数据隔离标识，如 pm-agent, ai-factory）'
    )
    parser.add_argument(
        '--operator', '-o',
        default='pm-agent',
        choices=['pm-agent', 'pm-clerk'],
        help='操作者身份（默认: pm-agent）'
    )
    parser.add_argument(
        '--batch-all', '-b',
        action='store_true',
        help='批量导入所有未导入的sessions'
    )
    parser.add_argument(
        '--dry-run', '-d',
        action='store_true',
        help='模拟运行，查看将要导入的内容'
    )
    
    args = parser.parse_args()
    
    # 执行导入
    importer = ProjectSessionImporterV2(
        project_code=args.project,
        operator=args.operator
    )
    importer.run(batch_all=args.batch_all, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
