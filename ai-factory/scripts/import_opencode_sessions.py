#!/usr/bin/env python3
"""
OpenCode Session 直接导入工具 - 支持项目私域数据隔离

功能：
1. 直接从 OpenCode SQLite/JSON 读取 session 数据
2. 导入到 entries 表，自动标记项目归属
3. 支持多项目数据隔离（scene_tags.project_code）
4. 自动提取会话标签并入库

使用：
    # PM-agent 项目导入
    python scripts/import_opencode_sessions.py --project pm-agent
    
    # 其他项目导入
    python scripts/import_opencode_sessions.py --project my-project --agent pm-clerk

环境变量：
    OPENCODE_STORAGE_PATH - OpenCode存储路径
    AI_PG_* - PostgreSQL连接配置
"""

import os
import sys
import json
import sqlite3
import argparse
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from ai_factory.db.pgvector_client import get_connection
from ai_factory.integrations.entries_ingest import entries_ingest


# OpenCode 存储路径
OPENCODE_STORAGE = Path(os.getenv("OPENCODE_STORAGE_PATH", 
                                  "~/.local/share/opencode")).expanduser()
SESSION_STORAGE = OPENCODE_STORAGE / "storage" / "session"
DB_PATH = OPENCODE_STORAGE / "opencode.db"


class OpenCodeSessionImporter:
    """OpenCode Session 导入器"""
    
    def __init__(self, project_code: str, operator: str = "pm-agent"):
        """
        初始化导入器
        
        Args:
            project_code: 项目代码（如 pm-agent）
            operator: 操作者身份（如 pm-agent, pm-clerk）
        """
        self.project_code = project_code
        self.operator = operator
        self.imported_count = 0
        self.skipped_count = 0
        
    def get_all_sessions(self) -> List[Dict[str, Any]]:
        """获取所有 OpenCode sessions"""
        sessions = []
        
        # 方法1: 从JSON文件读取
        if SESSION_STORAGE.exists():
            for project_dir in SESSION_STORAGE.iterdir():
                if project_dir.is_dir():
                    for session_file in project_dir.glob("ses_*.json"):
                        try:
                            data = json.loads(session_file.read_text())
                            data['_source_file'] = str(session_file)
                            sessions.append(data)
                        except Exception as e:
                            print(f"  ⚠️  读取失败 {session_file}: {e}")
        
        # 方法2: 从SQLite读取（如果可访问）
        try:
            sessions.extend(self._read_from_sqlite())
        except Exception as e:
            print(f"  ℹ️  SQLite读取失败（可能正在被使用）: {e}")
        
        return sessions
    
    def _read_from_sqlite(self) -> List[Dict[str, Any]]:
        """从SQLite数据库读取"""
        sessions = []
        if not DB_PATH.exists():
            return sessions
        
        # 复制数据库到临时位置（避免锁定）
        import shutil
        temp_db = Path(f"/tmp/opencode_temp_{datetime.now().timestamp()}.db")
        shutil.copy(DB_PATH, temp_db)
        
        try:
            conn = sqlite3.connect(temp_db)
            cursor = conn.cursor()
            
            # 读取sessions表
            cursor.execute("""
                SELECT id, title, created_at, updated_at, 
                       project_id, directory, model
                FROM sessions
                ORDER BY updated_at DESC
            """)
            
            for row in cursor.fetchall():
                sessions.append({
                    'id': row[0],
                    'title': row[1],
                    'created': row[2],
                    'updated': row[3],
                    'projectID': row[4],
                    'directory': row[5],
                    'model': row[6],
                    '_source': 'sqlite'
                })
            
            conn.close()
        finally:
            # 清理临时文件
            if temp_db.exists():
                temp_db.unlink()
        
        return sessions
    
    def _get_session_messages(self, session_id: str) -> List[Dict[str, str]]:
        """获取session的对话内容"""
        messages = []
        
        # 尝试从content_parts目录读取
        content_dir = OPENCODE_STORAGE / "storage" / "content_parts" / session_id
        if content_dir.exists():
            for msg_file in sorted(content_dir.glob("*.json")):
                try:
                    data = json.loads(msg_file.read_text())
                    if 'content' in data:
                        messages.append({
                            'role': data.get('role', 'unknown'),
                            'content': data['content'],
                            'timestamp': data.get('timestamp')
                        })
                except:
                    pass
        
        return messages
    
    def _is_already_imported(self, session_id: str) -> bool:
        """检查session是否已导入"""
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COUNT(*) FROM entries 
                    WHERE scene_tags::text LIKE %s
                    OR extra_meta::text LIKE %s
                """, (f'%"session_id": ["{session_id}"]%', 
                      f'%"source_session_id": "{session_id}"%'))
                return cur.fetchone()[0] > 0
        finally:
            conn.close()
    
    def _extract_tags_from_session(self, session: Dict) -> Dict[str, List[str]]:
        """从session提取标签"""
        tags = {
            "department": ["AI工厂"],
            "source": ["opencode_direct"],
            "type": ["session"],
            "project_code": [self.project_code],
            "operator": [self.operator]
        }
        
        # 从目录提取信息
        directory = session.get('directory', '')
        if 'ai-factory' in directory:
            tags["department"] = ["AI工厂"]
        elif 'documents' in directory:
            tags["department"] = ["文档部"]
        
        # 从标题提取关键词
        title = session.get('title', '').lower()
        if any(kw in title for kw in ['设计', '架构', '方案']):
            tags["planning"] = ["架构设计"]
        elif any(kw in title for kw in ['任务', '工单', 'todo']):
            tags["execution"] = ["任务执行"]
        elif any(kw in title for kw in ['bug', 'fix', '错误']):
            tags["execution"] = ["问题修复"]
        else:
            tags["planning"] = ["讨论记录"]
        
        return tags
    
    def import_session(self, session: Dict[str, Any]) -> bool:
        """导入单个session到entries"""
        session_id = session.get('id')
        
        # 检查是否已导入
        if self._is_already_imported(session_id):
            print(f"  ⏭️  跳过（已导入）: {session_id}")
            self.skipped_count += 1
            return False
        
        # 获取对话内容
        messages = self._get_session_messages(session_id)
        
        # 构建内容
        title = session.get('title', f'Session {session_id[:8]}')
        directory = session.get('directory', '')
        created = session.get('time', {}).get('created') or session.get('created')
        
        # 格式化时间
        if isinstance(created, (int, float)):
            created_dt = datetime.fromtimestamp(created / 1000)
        else:
            created_dt = datetime.now()
        
        # 构建内容文本
        content_lines = [f"# {title}", f"\n工作目录: {directory}", f"Session ID: {session_id}\n"]
        
        if messages:
            content_lines.append("## 对话内容\n")
            for i, msg in enumerate(messages[:10], 1):  # 只取前10条
                role = "用户" if msg.get('role') == 'user' else "助手"
                content_preview = msg.get('content', '')[:200]
                content_lines.append(f"**{role}**: {content_preview}...\n")
        else:
            content_lines.append("（对话内容暂不可访问）")
        
        content = "\n".join(content_lines)
        
        # 提取标签
        tags = self._extract_tags_from_session(session)
        
        # 构建payload
        payload = {
            "raw_text": content,
            "project_code": self.project_code,  # 关键：标记项目归属
            "user_id": self.operator,
            "note_datetime": created_dt.isoformat(),
            "extra_context": {
                "tags_snapshot": tags
            },
            "extra_meta": {
                "space_type": "session_record",
                "source_session_id": session_id,
                "source_system": "opencode",
                "import_method": "direct_import",
                "section": title,
                "section_type": "session",
                "visibility": "private",  # 私域数据
                "project_code": self.project_code,  # 冗余标记
                "operator": self.operator
            }
        }
        
        try:
            result = entries_ingest(payload)
            entry_id = result.get("entries", [{}])[0].get("entry_id", "unknown")
            print(f"  ✅ 已导入: {session_id[:20]}... → {entry_id}")
            self.imported_count += 1
            return True
        except Exception as e:
            print(f"  ❌ 导入失败 {session_id}: {e}")
            return False
    
    def run(self, dry_run: bool = False):
        """运行导入流程"""
        print(f"\n{'='*60}")
        print(f"🔄 OpenCode Session 直接导入")
        print(f"   项目: {self.project_code}")
        print(f"   操作者: {self.operator}")
        print(f"{'='*60}\n")
        
        # 获取所有sessions
        print("📖 扫描 OpenCode sessions...")
        sessions = self.get_all_sessions()
        print(f"✅ 找到 {len(sessions)} 个会话\n")
        
        if dry_run:
            print("🏃 模拟运行模式（不实际导入）:\n")
            for session in sessions[:5]:
                print(f"  - {session.get('id', 'N/A')}: {session.get('title', 'N/A')}")
            if len(sessions) > 5:
                print(f"  ... 还有 {len(sessions) - 5} 个")
            return
        
        # 导入每个session
        print("📥 开始导入...\n")
        for i, session in enumerate(sessions, 1):
            print(f"[{i}/{len(sessions)}]", end=" ")
            self.import_session(session)
        
        # 总结
        print(f"\n{'='*60}")
        print(f"📊 导入完成")
        print(f"{'='*60}")
        print(f"   总会话: {len(sessions)}")
        print(f"   成功导入: {self.imported_count}")
        print(f"   跳过（已存在）: {self.skipped_count}")
        print(f"   项目代码: {self.project_code}")
        print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(
        description='将 OpenCode sessions 直接导入到 entries 表'
    )
    parser.add_argument(
        '--project', '-p',
        default='pm-agent',
        help='项目代码 (默认: pm-agent)'
    )
    parser.add_argument(
        '--operator', '-o',
        default='pm-agent',
        help='操作者身份 (默认: pm-agent, 可选: pm-clerk)'
    )
    parser.add_argument(
        '--dry-run', '-d',
        action='store_true',
        help='模拟运行，不实际导入'
    )
    
    args = parser.parse_args()
    
    # 创建导入器并运行
    importer = OpenCodeSessionImporter(
        project_code=args.project,
        operator=args.operator
    )
    importer.run(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
