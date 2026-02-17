#!/usr/bin/env python3
"""
📥 [1] session_to_entries 节点 - 项目私域数据导入工具

职责：从session数据库导出 + LLM处理title和summary
归属：PM-clerk（执行）/ PM-agent（审核）

节点流程：
1. 读取OpenCode session文件
2. 提取session内容（messages）
3. LLM生成title（≤60字符）
4. LLM生成summary（≤500字符）
5. 构建完整payload → 调用💾 [2] entries_ingest

功能：
1. 直接从 OpenCode 读取 sessions
2. LLM处理生成title和summary_ai
3. 自动标记项目归属（project_code）
4. 支持多项目数据隔离（scene_tags.project_code）
5. 由PM或书记员执行，确保数据私域化

核心概念：
- 项目代码（project_code）: 如 pm-agent, ai-factory
- 操作者（operator）: 如 pm-agent（PM自己）, pm-clerk（书记员）
- 数据隔离: 通过 scene_tags.project_code 实现项目级隔离

使用示例：
    # PM自己导入
    python import_project_sessions.py --project pm-agent --operator pm-agent
    
    # 书记员导入
    python import_project_sessions.py --project pm-agent --operator pm-clerk
    
    # 批量导入所有未归档sessions
    python import_project_sessions.py --project pm-agent --batch-all
"""

import os
import sys
import json
import argparse
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from ai_factory.db.pgvector_client import get_connection
from ai_factory.integrations.entries_ingest import entries_ingest

# LLM处理函数（从ollama模块导入，后续可迁移到LLM策略模式）
from ai_factory.vectorize_entries_with_ollama import (
    generate_title_with_ollama,
    generate_summary_with_ollama,
)

# 环境变量控制是否使用本地LLM
USE_LOCAL_LLM = os.getenv("USE_LOCAL_LLM", "true").lower() == "true"


# OpenCode 存储路径
OPENCODE_STORAGE = Path(os.getenv("OPENCODE_STORAGE_PATH", 
                                  "~/.local/share/opencode")).expanduser()


class ProjectSessionImporter:
    """项目级Session导入器"""
    
    def __init__(self, project_code: str, operator: str = "pm-agent"):
        """
        初始化导入器
        
        Args:
            project_code: 项目代码（数据隔离标识）
            operator: 操作者（pm-agent 或 pm-clerk）
        """
        self.project_code = project_code
        self.operator = operator
        self.stats = {
            'found': 0,
            'imported': 0,
            'skipped': 0,
            'failed': 0
        }
    
    def get_opencode_sessions(self) -> List[Dict]:
        """从OpenCode存储读取所有sessions"""
        sessions = []
        session_dir = OPENCODE_STORAGE / "storage" / "session"
        
        if not session_dir.exists():
            return sessions
        
        # 遍历所有project目录
        for project_hash_dir in session_dir.iterdir():
            if not project_hash_dir.is_dir():
                continue
            
            # 读取该project下的所有session
            for session_file in project_hash_dir.glob("ses_*.json"):
                try:
                    data = json.loads(session_file.read_text())
                    data['_storage_path'] = str(session_file)
                    sessions.append(data)
                except Exception as e:
                    print(f"  ⚠️  读取失败 {session_file.name}: {e}")
        
        return sessions
    
    def is_session_imported(self, session_id: str) -> bool:
        """检查session是否已导入（通过extra_meta.source_session_id）"""
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                # 检查是否已存在该session_id的导入记录
                cur.execute("""
                    SELECT COUNT(*) FROM entries 
                    WHERE extra_meta->>'source_session_id' = %s
                    OR extra_meta->>'session_id' = %s
                """, (session_id, session_id))
                return cur.fetchone()[0] > 0
        finally:
            conn.close()
    
    def build_scene_tags(self, session: Dict) -> Dict[str, List[str]]:
        """
        构建scene_tags - 项目私域数据标记核心
        
        标记体系：
        - project_code: 项目代码（数据隔离标识）
        - department: 部门/组织
        - operator: 操作者身份
        - source: 数据来源
        - planning/execution: 业务层级
        - type: 记录类型
        """
        tags = {
            # 核心项目标记（数据隔离）
            "project_code": [self.project_code],
            "operator": [self.operator],
            
            # 组织标记
            "department": ["AI工厂"],
            "team": ["项目管理部"],
            
            # 数据来源标记
            "source": ["opencode_session"],
            "import_method": ["direct_importer"],
            
            # 类型标记
            "type": ["session_record"],
            "knowledge_level": ["record"],
            
            # 工作目录推断
            "workspace": []
        }
        
        # 从工作目录推断信息
        directory = session.get('directory', '')
        if directory:
            tags["workspace"] = [directory]
            
            if 'ai-factory' in directory:
                tags["department"] = ["AI工厂"]
                tags["project_scope"] = ["core"]
            elif 'documents' in directory:
                tags["department"] = ["知识管理部"]
                tags["project_scope"] = ["documentation"]
            elif 'scripts' in directory or 'src' in directory:
                tags["department"] = ["研发部"]
                tags["project_scope"] = ["development"]
        
        # 从标题推断业务类型
        title = session.get('title', '').lower()
        
        # 规划层
        if any(kw in title for kw in ['设计', '架构', '方案', '规划', '草案', '基线']):
            tags["planning"] = ["架构设计"]
            tags["knowledge_level"] = ["knowledge"]
        elif any(kw in title for kw in ['评审', 'review', '评估']):
            tags["planning"] = ["评审记录"]
            tags["knowledge_level"] = ["information"]
        
        # 执行层
        elif any(kw in title for kw in ['任务', '工单', 'todo', '执行']):
            tags["execution"] = ["任务执行"]
        elif any(kw in title for kw in ['bug', 'fix', '错误', '调试']):
            tags["execution"] = ["问题修复"]
        elif any(kw in title for kw in ['实现', '开发', '编码']):
            tags["execution"] = ["开发实现"]
        
        # 监控层
        elif any(kw in title for kw in ['测试', '验证', '检查']):
            tags["monitoring"] = ["测试验证"]
        else:
            tags["planning"] = ["讨论记录"]
        
        # 状态标记
        tags["status"] = ["active"]
        tags["visibility"] = ["private"]  # 私域数据
        
        return tags
    
    def extract_text_from_message(self, msg: dict) -> str:
        """从消息中提取文本内容（从 content_parts）
        
        OpenCode 存储结构:
        - storage/message/ses_xxx/msg_yyy.json - 消息元数据
        - storage/part/msg_yyy/*.json - 消息内容（content_parts）
        """
        msg_id = msg.get("id", "")
        
        # 尝试从 part 目录读取 content_parts
        parts_dir = Path.home() / f".local/share/opencode/storage/part/{msg_id}"
        if parts_dir.exists():
            parts = []
            for part_file in sorted(parts_dir.glob("*.json")):
                try:
                    part_data = json.loads(part_file.read_text())
                    parts.append(part_data)
                except Exception:
                    continue
            
            if parts:
                texts = []
                for part in parts:
                    part_type = part.get("type", "")
                    if part_type == "text":
                        texts.append(part.get("text", ""))
                    elif part_type == "tool_use":
                        tool_name = part.get("name", "unknown")
                        tool_input = part.get("input", {})
                        texts.append(f"【工具调用: {tool_name}】")
                        if isinstance(tool_input, dict) and tool_input:
                            texts.append(json.dumps(tool_input, ensure_ascii=False, indent=2))
                    elif part_type == "tool_result":
                        content = part.get("content", "")
                        if isinstance(content, str):
                            texts.append(content[:500])
                        else:
                            texts.append(json.dumps(content, ensure_ascii=False, indent=2)[:500])
                    elif part_type == "reasoning_content":
                        texts.append(f"【思考内容】\n{part.get('text', '')}")
                    elif part_type == "redacted_reasoning_content":
                        texts.append("【思考内容-已编辑】")
                
                full_text = "\n".join(texts)
                if full_text.strip():
                    return full_text
        
        # 回退：使用旧的逻辑
        if "_extracted_text" in msg:
            return msg["_extracted_text"]
        
        # 优先使用 summary.title
        summary = msg.get("summary", {})
        if summary and isinstance(summary, dict):
            title = summary.get("title", "")
            if title:
                return title
        
        return msg.get("text", "") or msg.get("content", "")
    
    def extract_qa_pairs_from_messages(self, session_id: str) -> List[Dict[str, str]]:
        """从 message 目录提取问答对
        
        OpenCode 数据结构:
        - storage/message/ses_xxx/msg_yyy.json - 消息元数据
        - storage/part/msg_yyy/*.json - 消息内容（content_parts）
        
        Returns:
            List[Dict]: [{"user": "...", "assistant": "..."}, ...]
        """
        qa_pairs = []
        message_dir = Path.home() / ".local/share/opencode/storage/message" / session_id
        
        if not message_dir.exists():
            return qa_pairs
        
        # 读取所有消息并按时间排序
        messages = []
        for msg_file in message_dir.glob("msg_*.json"):
            try:
                data = json.loads(msg_file.read_text())
                messages.append(data)
            except Exception:
                continue
        
        # 按创建时间排序
        messages.sort(key=lambda m: m.get("time", {}).get("created", 0))
        
        # 提取每条消息的文本内容
        for msg in messages:
            msg["_extracted_text"] = self.extract_text_from_message(msg)
        
        # 过滤空消息
        messages = [m for m in messages if m.get("_extracted_text", "").strip()]
        
        # 遍历消息，提取问答对
        i = 0
        while i < len(messages):
            msg = messages[i]
            role = msg.get("role", "")
            
            if role == "user":
                user_content = msg.get("_extracted_text", "")
                
                if not user_content:
                    i += 1
                    continue
                
                # 查找紧跟其后的 assistant 消息
                assistant_content = ""
                if i + 1 < len(messages):
                    next_msg = messages[i + 1]
                    if next_msg.get("role") == "assistant":
                        assistant_content = next_msg.get("_extracted_text", "")
                        i += 2  # 跳过 assistant 消息
                    else:
                        i += 1
                else:
                    i += 1
                
                qa_pairs.append({
                    "user": user_content[:1000],
                    "assistant": assistant_content[:5000] if assistant_content else None
                })
            else:
                i += 1
        
        return qa_pairs
    
    def extract_session_content(self, session: Dict) -> str:
        """提取session的实际内容（messages）
        
        优先从 message 目录提取问答对格式的内容
        """
        session_id = session.get('id', '')
        
        # 首先尝试从 message 目录提取问答对
        qa_pairs = self.extract_qa_pairs_from_messages(session_id)
        
        if qa_pairs:
            # 转换为可读格式
            content_parts = []
            for i, qa in enumerate(qa_pairs, 1):
                user = qa.get("user", "")
                assistant = qa.get("assistant", "")
                content_parts.append(f"### 问答对 #{i}")
                content_parts.append(f"**👤 USER**: {user}")
                if assistant:
                    content_parts.append(f"**🤖 ASSISTANT**: {assistant[:500]}")
                content_parts.append("---")
            return "\n".join(content_parts)
        
        # 回退：提取 messages
        content_parts = []
        
        # 提取messages
        messages = session.get('messages', [])
        if messages:
            for msg in messages[-10:]:  # 只取最后10条避免过长
                role = msg.get('role', 'unknown')
                text = msg.get('text', '') or msg.get('content', '')
                if text:
                    content_parts.append(f"[{role}]: {text[:200]}")  # 每条限制200字符
        
        # 如果没有messages，使用metadata
        if not content_parts:
            metadata = session.get('metadata', {})
            if metadata:
                content_parts.append(str(metadata))
        
        return "\n".join(content_parts) if content_parts else "(empty session)"

    def generate_title_and_summary_from_qa(self, user_question: str, assistant_answer: str) -> tuple[str, str]:
        """基于问答对整体生成title和summary
        
        title和summary_ai应该总结整个问答对的内容，而不是只基于问题。
        
        Args:
            user_question: 用户问题
            assistant_answer: 助手回答（可能为None）
            
        Returns:
            tuple: (title, summary)
            title: 不少于30字（除非内容本身很短）
            summary: 300-500字（除非内容本身很少）
        """
        # 组合问答内容
        combined_content = f"问题：{user_question}\n\n"
        if assistant_answer:
            combined_content += f"回答：{assistant_answer}"
        else:
            combined_content += "回答：（无）"
        
        # 调用DeepSeek API生成title和summary
        title, summary = self._call_deepseek_for_qa_title_and_summary(
            user_question, assistant_answer or "（无回答）"
        )
        
        # 确保最小长度（如果内容允许）
        if len(user_question) + len(assistant_answer or "") > 100:
            if len(title) < 30:
                print(f"    ⚠️  Title太短({len(title)}字)，使用原文补充")
                title = user_question[:min(50, len(user_question))]
            if len(summary) < 300:
                print(f"    ⚠️  Summary太短({len(summary)}字)，使用原文补充")
                summary = combined_content[:min(500, len(combined_content))]
        
        return title, summary

    def _call_deepseek_for_title(self, content: str) -> str:
        """调用DeepSeek API生成title"""
        import requests
        
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            print("    ⚠️  DEEPSEEK_API_KEY未设置，使用原文")
            return content[:60]
        
        prompt = f"""基于以下内容生成一个简洁的中文标题（≤60字符），只返回标题本身：

{content[:2000]}

标题："""
        
        try:
            resp = requests.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": "deepseek-chat",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 100
                },
                timeout=30
            )
            resp.raise_for_status()
            title = resp.json()["choices"][0]["message"]["content"].strip()
            print(f"    📝 DeepSeek生成title: {title[:30]}...")
            return title[:60]
        except Exception as e:
            print(f"    ⚠️  DeepSeek API失败: {e}")
            return content[:60]

    def _call_deepseek_for_title_and_summary(self, content: str) -> tuple[str, str]:
        """调用DeepSeek API生成title和summary"""
        import requests
        
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            print("    ⚠️  DEEPSEEK_API_KEY未设置，使用原文")
            return content[:60], content[:500]
        
        prompt = f"""基于以下内容生成：
1. 简洁中文标题（≤60字符）
2. 内容摘要（≤500字符）

格式要求：
标题：[标题内容]
摘要：[摘要内容]

内容：
{content[:3000]}
"""
        
        try:
            resp = requests.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": "deepseek-chat",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 800
                },
                timeout=60
            )
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"]
            
            # 解析结果
            title = ""
            summary = ""
            for line in text.split("\n"):
                if line.startswith("标题："):
                    title = line[3:].strip()
                elif line.startswith("摘要："):
                    summary = line[3:].strip()
            
            if not title:
                title = content[:60]
            if not summary:
                summary = content[:500]
            
            print(f"    📝 DeepSeek生成: title={title[:30]}..., summary={summary[:50]}...")
            return title[:60], summary[:500]
        except Exception as e:
            print(f"    ⚠️  DeepSeek API失败: {e}")
            return content[:60], content[:500]

    def _call_deepseek_for_qa_title_and_summary(self, user_question: str, assistant_answer: str) -> tuple[str, str]:
        """调用DeepSeek API基于问答对生成title和summary
        
        title和summary应该总结整个问答对，而不仅仅是问题。
        """
        import requests
        
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            print("    ⚠️  DEEPSEEK_API_KEY未设置")
            combined = f"问题：{user_question}\n\n回答：{assistant_answer}"
            return combined[:60], combined[:500]
        
        prompt = f"""基于以下问答对，生成标题和内容摘要。

要求：
1. 标题（≥30字，≤60字）：概括问答对的核心主题和关键结论
2. 摘要（≥300字，≤500字）：总结用户问题的核心诉求和AI回答的关键要点，突出价值收获

格式要求：
标题：[标题内容]
摘要：[摘要内容]

问答对：
【用户问题】
{user_question[:1500]}

【AI回答】
{assistant_answer[:2500]}
"""
        
        try:
            resp = requests.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": "deepseek-chat",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 800
                },
                timeout=60
            )
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"]
            
            # 解析结果 - 改进版，处理多行摘要
            title = ""
            summary = ""
            in_summary = False
            summary_lines = []
            
            for line in text.split("\n"):
                line_stripped = line.strip()
                
                # 解析标题
                if line_stripped.startswith("标题：") or line_stripped.startswith("标题:"):
                    title = line_stripped[3:].strip() if line_stripped.startswith("标题：") else line_stripped[2:].strip()
                    in_summary = False
                # 检测摘要开始
                elif line_stripped.startswith("摘要：") or line_stripped.startswith("摘要:"):
                    # 检查同一行是否还有内容
                    content = line_stripped[3:].strip() if line_stripped.startswith("摘要：") else line_stripped[2:].strip()
                    if content:
                        summary_lines.append(content)
                    in_summary = True
                # 如果在摘要区域，收集内容
                elif in_summary and line_stripped:
                    summary_lines.append(line_stripped)
            
            summary = "\n".join(summary_lines)
            
            # 清理可能的引号
            title = title.strip('"\'')
            summary = summary.strip('"\'')
            
            if not title:
                combined = f"问题：{user_question}\n\n回答：{assistant_answer}"
                title = combined[:60]
            if not summary:
                combined = f"问题：{user_question}\n\n回答：{assistant_answer}"
                summary = combined[:500]
            
            print(f"    📝 DeepSeek生成: title={title[:40]}...")
            return title, summary
        except Exception as e:
            print(f"    ⚠️  DeepSeek API失败: {e}")
            combined = f"问题：{user_question}\n\n回答：{assistant_answer}"
            return combined[:60], combined[:500]

    def import_session(self, session: Dict) -> bool:
        """📥 [1] 导入单个session，执行LLM处理后入库"""
        session_id = session.get('id', '')
        if not session_id:
            print(f"  ❌ Session无ID，跳过")
            self.stats['failed'] += 1
            return False
        
        # 检查是否已导入
        if self.is_session_imported(session_id):
            print(f"  ⏭️  跳过（已导入）: {session_id[:25]}...")
            self.stats['skipped'] += 1
            return False
        
        # 获取session信息
        original_title = session.get('title', f'Session {session_id[:8]}')
        directory = session.get('directory', '')
        
        # 时间处理
        time_data = session.get('time', {})
        created_ts = time_data.get('created') or session.get('created')
        if isinstance(created_ts, (int, float)):
            created_dt = datetime.fromtimestamp(created_ts / 1000)
        else:
            created_dt = datetime.now()
        
        # 🔥 关键步骤1：提取session内容
        print(f"  📖 提取内容: {session_id[:25]}...")
        
        # 先构建 scene_tags 和 extra_meta（提前定义以便问答对使用）
        scene_tags = self.build_scene_tags(session)
        extra_meta = {
            "source_session_id": session_id,
            "source_system": "opencode",
            "import_method": "project_importer_v2",
            "project_code": self.project_code,
            "operator": self.operator,
            "space_type": "session_record",
            "section": "",
            "section_type": "session",
            "visibility": "private",
            "access_control": f"project:{self.project_code}",
            "original_directory": directory,
            "original_title": original_title,
            "slug": session.get('slug', ''),
            "version": session.get('version', ''),
            "llm_processed": True,
        }
        
        qa_pairs = self.extract_qa_pairs_from_messages(session_id)
        
        # 根据是否有问答对选择不同的处理方式
        if qa_pairs and len(qa_pairs) > 0:
            # 有问答对：每个问答对单独入库
            print(f"  💬 发现 {len(qa_pairs)} 个问答对")
            imported_count = 0
            
            for qa_idx, qa in enumerate(qa_pairs):
                user_question = qa.get("user", "")
                assistant_answer = qa.get("assistant")
                
                if not user_question:
                    continue
                
                # 构建单个问答对的 payload
                # input_content = 用户问题
                # answer_payload = 助手回答
                answer_payload = None
                if assistant_answer:
                    answer_payload = {"text": assistant_answer}
                
                # 构建 scene_tags
                qa_tags = dict(scene_tags)
                qa_tags["type"] = ["qa_pair"]  # 标记为问答对
                
                # 构建 extra_meta
                qa_meta = dict(extra_meta)
                qa_meta["qa_index"] = qa_idx
                qa_meta["section_type"] = "qa_pair"
                
                # LLM 生成 title 和 summary（基于问答对整体）
                qa_title, qa_summary = self.generate_title_and_summary_from_qa(user_question, assistant_answer or "")
                
                # 构建 content
                qa_content_parts = [
                    f"# {qa_title}",
                    f"\n**Session**: `{session_id}`",
                    f"**问答序号**: {qa_idx + 1}",
                    f"**原始问题**: {user_question}",
                ]
                if assistant_answer:
                    qa_content_parts.append(f"\n**AI回答**:\n{assistant_answer[:1000]}")
                
                qa_full_content = "\n".join(qa_content_parts)
                
                # 构建 payload
                qa_payload = {
                    "input_content": user_question,  # ✅ 用户问题
                    "title": qa_title,
                    "summary_ai": qa_summary,
                    "raw_text": qa_full_content,
                    "project_code": self.project_code,
                    "user_id": self.operator,
                    "note_datetime": created_dt.isoformat(),
                    "extra_context": {
                        "tags_snapshot": qa_tags
                    },
                    "extra_meta": qa_meta
                }
                
                # 添加 answer_payload
                if answer_payload:
                    qa_payload["answer_payload"] = answer_payload  # ✅ 助手回答
                
                # 导入
                try:
                    result = entries_ingest(qa_payload)
                    entry_id = result.get("entries", [{}])[0].get("entry_id", "unknown")
                    imported_count += 1
                except Exception as e:
                    print(f"    ⚠️  导入失败 [{qa_idx}]: {e}")
            
            if imported_count > 0:
                print(f"  ✅ 已导入 {imported_count} 个问答对")
                self.stats['imported'] += imported_count
                return True
            else:
                self.stats['failed'] += 1
                return False
        else:
            # 无问答对：使用原有逻辑（整个 session 作为一条记录）
            session_content = self.extract_session_content(session)
        
        # 🔥 关键步骤2：LLM处理生成title和summary
        print(f"  🤖 LLM处理中...")
        llm_title, llm_summary = self.generate_title_and_summary_from_qa(session_content, "")
        
        # 构建完整内容（包含metadata）
        content_parts = [
            f"# {llm_title}",
            f"\n**原始Session标题**: {original_title}",
            f"**Session ID**: `{session_id}`",
            f"**工作目录**: {directory}",
            f"**项目代码**: {self.project_code}",
            f"**导入者**: {self.operator}",
            f"**创建时间**: {created_dt.strftime('%Y-%m-%d %H:%M')}\n",
            f"## AI摘要\n{llm_summary}\n",
            f"## 原始内容\n{session_content[:2000]}"  # 限制长度
        ]
        
        # 添加git统计信息
        git_summary = session.get('summary', {})
        if git_summary:
            content_parts.append("\n## 变更统计\n")
            content_parts.append(f"- 新增: {git_summary.get('additions', 0)} 行")
            content_parts.append(f"- 删除: {git_summary.get('deletions', 0)} 行")
            content_parts.append(f"- 修改文件: {git_summary.get('files', 0)} 个")
        
        full_content = "\n".join(content_parts)
        
        # 构建scene_tags
        scene_tags = self.build_scene_tags(session)
        
        # 构建extra_meta
        extra_meta = {
            "source_session_id": session_id,
            "source_system": "opencode",
            "import_method": "project_importer_v2",
            "project_code": self.project_code,
            "operator": self.operator,
            "space_type": "session_record",
            "section": llm_title,
            "section_type": "session",
            "visibility": "private",
            "access_control": f"project:{self.project_code}",
            "original_directory": directory,
            "original_title": original_title,
            "slug": session.get('slug', ''),
            "version": session.get('version', ''),
            "llm_processed": True,  # 标记已LLM处理
        }
        
        # 🔥 关键步骤3：构建完整payload（包含LLM生成的title和summary）
        payload = {
            "title": llm_title,              # ✅ LLM生成
            "summary_ai": llm_summary,       # ✅ LLM生成
            "raw_text": full_content,        # 完整内容
            "project_code": self.project_code,
            "user_id": self.operator,
            "note_datetime": created_dt.isoformat(),
            "extra_context": {
                "tags_snapshot": scene_tags
            },
            "extra_meta": extra_meta
        }
        
        # 🔥 关键步骤4：调用💾 [2] 入库通道
        try:
            result = entries_ingest(payload)
            entry_id = result.get("entries", [{}])[0].get("entry_id", "unknown")
            print(f"  ✅ 已导入: {session_id[:25]}... → {entry_id}")
            self.stats['imported'] += 1
            return True
        except Exception as e:
            print(f"  ❌ 导入失败 {session_id}: {e}")
            self.stats['failed'] += 1
            return False
    
    def run(self, batch_all: bool = False, dry_run: bool = False):
        """运行导入流程"""
        print("=" * 70)
        print(f"🔄 项目私域数据导入")
        print(f"   项目代码: {self.project_code}")
        print(f"   操作者: {self.operator}")
        print(f"   模式: {'批量导入' if batch_all else '选择性导入'}")
        print("=" * 70)
        
        # 扫描sessions
        print("\n📖 扫描 OpenCode sessions...")
        sessions = self.get_opencode_sessions()
        self.stats['found'] = len(sessions)
        print(f"✅ 找到 {len(sessions)} 个会话\n")
        
        if dry_run:
            print("🏃 模拟运行模式（不实际导入）：\n")
            for session in sessions[:5]:
                title = session.get('title', 'N/A')[:40]
                print(f"  - {session.get('id', 'N/A')[:30]}: {title}...")
            if len(sessions) > 5:
                print(f"  ... 还有 {len(sessions) - 5} 个")
            return
        
        # 导入
        print(f"📥 开始导入到项目 '{self.project_code}'...\n")
        for i, session in enumerate(sessions, 1):
            print(f"[{i}/{len(sessions)}]", end=" ")
            self.import_session(session)
        
        # 报告
        print(f"\n{'='*70}")
        print(f"📊 导入完成报告")
        print(f"{'='*70}")
        print(f"   发现会话:    {self.stats['found']}")
        print(f"   成功导入:    {self.stats['imported']}")
        print(f"   跳过(已存在): {self.stats['skipped']}")
        print(f"   失败:        {self.stats['failed']}")
        print(f"   项目代码:    {self.project_code}")
        print(f"   数据隔离:    ✅ scene_tags.project_code = {self.project_code}")
        print(f"{'='*70}\n")
        
        # 提示
        print("💡 查询项目数据的SQL示例：")
        print(f"   SELECT * FROM entries WHERE project_code = '{self.project_code}';")
        print(f"   SELECT * FROM entries WHERE scene_tags->>'project_code' = '{self.project_code}';")


def main():
    parser = argparse.ArgumentParser(
        description='项目私域数据导入工具 - 将OpenCode sessions标记为项目私有数据'
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
    importer = ProjectSessionImporter(
        project_code=args.project,
        operator=args.operator
    )
    importer.run(batch_all=args.batch_all, dry_run=args.dry_run)


# ==============================================================================
# 🎯 便利API - 供其他Agent和脚本调用
# ==============================================================================

def import_single_session(
    session_id: str,
    project_code: str,
    operator: str = "pm-agent"
) -> Dict[str, Any]:
    """导入单个session（便利API）
    
    供Agent直接调用，无需实例化Importer类。
    
    Args:
        session_id: Session ID
        project_code: 项目代码（数据隔离标识）
        operator: 操作者身份
        
    Returns:
        dict: {
            "success": bool,
            "entry_id": str or None,
            "title": str or None,
            "message": str
        }
    """
    importer = ProjectSessionImporter(
        project_code=project_code,
        operator=operator
    )
    
    # 获取所有sessions
    sessions = importer.get_opencode_sessions()
    
    # 找到目标session
    target_session = None
    for session in sessions:
        if session.get('id') == session_id:
            target_session = session
            break
    
    if not target_session:
        return {
            "success": False,
            "entry_id": None,
            "title": None,
            "message": f"未找到session: {session_id}"
        }
    
    # 执行导入
    success = importer.import_session(target_session)
    
    if success:
        # 获取导入结果
        return {
            "success": True,
            "entry_id": f"ent_{session_id[:8]}",  # 简化返回
            "title": target_session.get('title', '')[:60],
            "message": f"✅ 导入成功: {session_id[:25]}..."
        }
    else:
        return {
            "success": False,
            "entry_id": None,
            "title": None,
            "message": f"❌ 导入失败: {session_id[:25]}..."
        }


def import_all_sessions(
    project_code: str,
    operator: str = "pm-agent",
    dry_run: bool = False
) -> Dict[str, Any]:
    """批量导入所有未归档sessions（便利API）
    
    Args:
        project_code: 项目代码
        operator: 操作者身份
        dry_run: 是否模拟运行
        
    Returns:
        dict: {
            "success": bool,
            "stats": {
                "found": int,
                "imported": int,
                "skipped": int,
                "failed": int
            },
            "message": str
        }
    """
    importer = ProjectSessionImporter(
        project_code=project_code,
        operator=operator
    )
    
    importer.run(batch_all=True, dry_run=dry_run)
    
    return {
        "success": True,
        "stats": dict(importer.stats),
        "message": f"📊 导入完成: 发现{importer.stats['found']}个, "
                   f"成功{importer.stats['imported']}个"
    }


def check_session_imported(session_id: str) -> bool:
    """检查session是否已导入（便利API）
    
    Args:
        session_id: Session ID
        
    Returns:
        bool: 是否已导入
    """
    # 临时创建importer来检查（不需要project_code）
    importer = ProjectSessionImporter(project_code="temp")
    return importer.is_session_imported(session_id)


# ==============================================================================
# CLI入口
# ==============================================================================

if __name__ == "__main__":
    main()
