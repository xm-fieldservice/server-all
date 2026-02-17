#!/usr/bin/env python3
"""
OpenCode Session Exporter - 支持增量导出到统一文档
导出 OpenCode 会话并转换为可读的 Markdown 格式
支持增量导出到 all_sessions.md 统一文档
"""

import json
import sys
import re
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional, Set, Dict, List

STORAGE_PATH = Path.home() / ".local/share/opencode/storage"
EXPORT_DIR = Path.home() / "Documents/OpenCode_Exports"
ALL_SESSIONS_FILE = Path("/root/ai-factory/documents/all_sessions.md")
METADATA_FILE = EXPORT_DIR / ".export_metadata.json"


def load_json(path: Path) -> dict:
    """加载 JSON 文件"""
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_json(data: dict, path: Path):
    """保存 JSON 文件"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def format_timestamp(ts: int) -> str:
    """格式化时间戳"""
    if not ts:
        return "未知时间"
    return datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d %H:%M:%S")


def load_metadata() -> dict:
    """加载导出元数据"""
    if METADATA_FILE.exists():
        try:
            return load_json(METADATA_FILE)
        except Exception:
            pass
    return {
        "last_export": None,
        "exported_sessions": {},
        "full_export_done": False
    }


def save_metadata(metadata: dict):
    """保存导出元数据"""
    save_json(metadata, METADATA_FILE)


def get_exported_session_ids() -> Set[str]:
    """从 all_sessions.md 中获取已导出的会话 ID 集合"""
    if not ALL_SESSIONS_FILE.exists():
        return set()
    
    try:
        content = ALL_SESSIONS_FILE.read_text(encoding='utf-8')
        # 匹配会话 ID 格式: `ses_xxxxxxxx`
        session_ids = set(re.findall(r'`(ses_[a-zA-Z0-9]+)`', content))
        return session_ids
    except Exception:
        return set()


def get_last_export_position() -> int:
    """获取上次导出在 all_sessions.md 中的位置（行号）"""
    if not ALL_SESSIONS_FILE.exists():
        return 0
    
    try:
        content = ALL_SESSIONS_FILE.read_text(encoding='utf-8')
        matches = list(re.findall(r'`(ses_[a-zA-Z0-9]+)`', content))
        return len(matches)
    except Exception:
        return 0


def append_session_to_all(md_content: str):
    """将会话内容追加到 all_sessions.md"""
    ALL_SESSIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    with open(ALL_SESSIONS_FILE, 'a', encoding='utf-8') as f:
        f.write("\n")
        f.write(md_content)


def get_latest_turn_from_session(session_data: dict) -> tuple[str, str]:
    """从会话数据中获取最新的问答对内容 (user_content, assistant_content)"""
    messages = session_data.get("messages", [])
    if not messages:
        return ("", "")
    
    # 找到最后一条 user 消息
    latest_user_idx = -1
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].get("role", "").lower() == "user":
            latest_user_idx = i
            break
    
    if latest_user_idx == -1:
        return ("", "")
    
    user_content = extract_text_from_message(messages[latest_user_idx])
    
    # 检查下一条是否是 assistant
    assistant_content = ""
    if latest_user_idx + 1 < len(messages):
        next_msg = messages[latest_user_idx + 1]
        if next_msg.get("role", "").lower() == "assistant":
            assistant_content = extract_text_from_message(next_msg)
    
    return (user_content[:200], assistant_content[:200])  # 只比较前200字符


def get_latest_turn_from_md() -> tuple[str, str]:
    """从 MD 文档中获取最新的问答对内容"""
    if not ALL_SESSIONS_FILE.exists():
        return ("", "")
    
    try:
        content = ALL_SESSIONS_FILE.read_text(encoding='utf-8')
        
        # 找到最后一个问答对 #N
        import re
        matches = list(re.finditer(r'### 问答对 #\d+ \(([^)]+)\)', content))
        if not matches:
            return ("", "")
        
        # 从最后一个问答对位置开始解析
        last_match = matches[-1]
        start_pos = last_match.end()
        section = content[start_pos:]
        
        # 提取 USER 内容
        user_match = re.search(r'\*\*👤 USER\*\*\s*\n([^\n]+(?:\n(?![\*\-]|\*\*🤖).*)*)', section)
        user_content = user_match.group(1).strip() if user_match else ""
        
        # 提取 ASSISTANT 内容（到下一个分隔线或文档结束）
        assistant_match = re.search(r'\*\*🤖 ASSISTANT\*\*\s*(?:\*Agent:[^\*]+\*\s*)?\n([^\n]+(?:\n(?![\-]{3,}|###).*)*)', section)
        assistant_content = assistant_match.group(1).strip() if assistant_match else ""
        
        return (user_content[:200], assistant_content[:200])
    except Exception:
        return ("", "")


def verify_export(session_data: dict) -> bool:
    """校验刚写入的内容是否正确"""
    session_id = session_data.get("session", {}).get("id", "")
    
    source_user, source_assistant = get_latest_turn_from_session(session_data)
    md_user, md_assistant = get_latest_turn_from_md()
    
    # 如果都没有内容，认为是空会话
    if not source_user and not md_user:
        return True
    
    # 清洗内容：移除多余空白，只保留前100字符比较
    def clean_content(text):
        return ' '.join(text.split())[:100]
    
    source_user_clean = clean_content(source_user)
    md_user_clean = clean_content(md_user)
    source_assistant_clean = clean_content(source_assistant)
    md_assistant_clean = clean_content(md_assistant)
    
    # 只要 USER 内容匹配就认为是成功的（ASSISTANT 可能太长被截断）
    return source_user_clean == md_user_clean


def export_to_all_sessions(mode: str = "incremental"):
    """
    增量导出会话到 all_sessions.md 统一文档
    """
    # 如果是全量重建，先清空文件
    if mode == "full" and ALL_SESSIONS_FILE.exists():
        ALL_SESSIONS_FILE.unlink()
        print(f"🗑️  已清空 {ALL_SESSIONS_FILE}")
    
    metadata = load_metadata()
    sessions = list_sessions()
    
    if not sessions:
        print("❌ 没有找到任何会话")
        return
    
    # 获取已导出的会话 ID
    exported_ids = get_exported_session_ids()
    last_count = get_last_export_position()
    
    print(f"\n📦 共有 {len(sessions)} 个会话")
    print(f"📄 统一文档: {ALL_SESSIONS_FILE}")
    print(f"📋 导出模式: {'全量重建' if mode == 'full' else '增量追加'}")
    print(f"📊 已导出会话: {len(exported_ids)} 个")
    print()
    
    exported_count = 0
    skipped_count = 0
    new_sessions = []
    updated_sessions = []
    
    for idx, session in enumerate(sessions, 1):
        session_id = session.get("id")
        title = session.get("title", "无标题")[:40]
        updated = session.get("time", {}).get("updated", 0)
        
        _, current_msg_count, current_turn_count = export_session_with_count(session)
        current_hash = get_session_hash(session, current_turn_count)
        
        should_export = False
        reason = ""
        
        if mode == "full":
            should_export = True
            reason = "全量导出"
        else:
            if session_id not in exported_ids:
                should_export = True
                reason = "新增会话"
                new_sessions.append(title)
            else:
                last_exported = metadata["exported_sessions"].get(session_id, {})
                last_updated = last_exported.get("updated", 0)
                last_turn_count = last_exported.get("turn_count", 0)
                
                if current_turn_count > last_turn_count:
                    should_export = True
                    reason = f"新增问答对 (+{current_turn_count - last_turn_count}个)"
                    updated_sessions.append(title)
                elif last_updated != updated:
                    should_export = True
                    reason = "内容更新"
                    updated_sessions.append(title)
                elif last_exported.get("hash") != current_hash:
                    should_export = True
                    reason = "结构变化"
                    updated_sessions.append(title)
        
        print(f"  [{idx:2d}] {title}")
        
        if should_export:
            try:
                result, msg_count, turn_count = export_session_with_count(session)
                if result["messages"]:
                    md_content = session_to_markdown(result, is_update=bool(session_id in exported_ids))
                    append_session_to_all(md_content)
                    
                    # 校验写入内容
                    if verify_export(result):
                        print(f"     ✅ 校验通过")
                    else:
                        print(f"     ⚠️  校验警告：内容可能不匹配")
                    
                    metadata["exported_sessions"][session_id] = {
                        "updated": updated,
                        "hash": current_hash,
                        "message_count": msg_count,
                        "turn_count": turn_count,
                        "last_exported": datetime.now().isoformat(),
                        "title": title
                    }
                    
                    exported_count += 1
                    print(f"     ✅ {reason}: 已追加到 all_sessions.md")
                else:
                    print(f"     ⚠️  无消息内容，跳过")
            except Exception as e:
                print(f"     ❌ 导出失败: {e}")
        else:
            skipped_count += 1
            print(f"     ⏭️  无变化，跳过")
    
    metadata["last_export"] = datetime.now().isoformat()
    metadata["full_export_done"] = metadata["full_export_done"] or (mode == "full")
    save_metadata(metadata)
    
    print(f"\n" + "=" * 50)
    print(f"✅ 导出完成！")
    print(f"   总会话: {len(sessions)}")
    print(f"   本次导出: {exported_count}")
    print(f"   跳过: {skipped_count}")
    print(f"   文档: {ALL_SESSIONS_FILE}")
    print(f"=" * 50)
    
    try:
        # 查找最后一个会话 ID 的位置来估算
        content = ALL_SESSIONS_FILE.read_text(encoding='utf-8')
        matches = list(re.finditer(r'`(ses_[a-zA-Z0-9]+)`', content))
        return len(matches)
    except Exception:
        return 0


def list_sessions() -> list[dict]:
    """列出所有会话"""
    sessions = []
    session_base = STORAGE_PATH / "session"

    if not session_base.exists():
        print(f"❌ 会话目录不存在: {session_base}")
        return sessions

    for subdir in session_base.iterdir():
        if subdir.is_dir():
            for session_file in subdir.glob("*.json"):
                try:
                    data = load_json(session_file)
                    sessions.append(data)
                except Exception:
                    continue

    sessions.sort(key=lambda s: s.get("time", {}).get("updated", 0), reverse=True)
    return sessions


def get_session_hash(session: dict, message_count: int = 0) -> str:
    """生成会话内容哈希，用于检测变化"""
    content = {
        "title": session.get("title", ""),
        "updated": session.get("time", {}).get("updated"),
        "directory": session.get("directory", ""),
        "message_count": message_count,
    }
    return hashlib.md5(json.dumps(content, sort_keys=True).encode()).hexdigest()


def export_session_with_count(session_data: dict) -> tuple[dict, int, int]:
    """导出指定会话，返回会话数据、消息数量和问答对数量"""
    session_id = session_data.get("id")
    message_path = STORAGE_PATH / "message" / session_id

    if not message_path.exists():
        return {"session": session_data, "messages": []}, 0, 0

    messages = []
    for msg_file in sorted(message_path.glob("*.json")):
        try:
            msg = load_json(msg_file)
            msg_id = msg.get("id")
            parts_dir = STORAGE_PATH / "part" / msg_id

            if parts_dir.exists():
                parts = []
                for part_file in sorted(parts_dir.glob("*.json")):
                    parts.append(load_json(part_file))
                msg["content_parts"] = parts
            messages.append(msg)
        except Exception:
            continue

    messages.sort(key=lambda m: m.get("time", {}).get("created", 0))

    non_empty_messages = []
    for msg in messages:
        content = extract_text_from_message(msg)
        if content.strip():
            msg["_extracted_text"] = content
            non_empty_messages.append(msg)

    # 计算问答对数量：USER 后跟 ASSISTANT 算一对
    turn_count = 0
    for i, msg in enumerate(non_empty_messages):
        if msg.get("role") == "user":
            # 检查下一条是否是 assistant
            if i + 1 < len(non_empty_messages) and non_empty_messages[i + 1].get("role") == "assistant":
                turn_count += 1

    return {"session": session_data, "messages": non_empty_messages}, len(non_empty_messages), turn_count


def export_session(session_data: dict) -> dict:
    """导出指定会话"""
    result, _, _ = export_session_with_count(session_data)
    return result


def extract_text_from_message(msg: dict) -> str:
    """从消息中提取文本内容"""
    if "_extracted_text" in msg:
        return msg["_extracted_text"]

    parts = msg.get("content_parts", [])
    if not parts:
        return msg.get("summary", {}).get("title", "")

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
    return "\n".join(texts)


def session_to_markdown(data: dict, is_update: bool = False) -> str:
    """将会话数据转换为 Markdown 格式"""
    session = data["session"]
    messages = data["messages"]

    md_lines = []

    title = session.get("title", "无标题会话")
    session_id = session.get("id", "unknown")
    created = format_timestamp(session.get("time", {}).get("created"))
    updated = format_timestamp(session.get("time", {}).get("updated"))
    directory = session.get("directory", "未知目录")

    if is_update:
        md_lines.append(f"# {title} (更新)")
    else:
        md_lines.append(f"# {title}")

    md_lines.append("")
    md_lines.append("---")
    md_lines.append("")
    md_lines.append(f"**会话 ID**: `{session_id}`")
    md_lines.append(f"**创建时间**: {created}")
    md_lines.append(f"**更新时间**: {updated}")
    md_lines.append(f"**导出时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    md_lines.append(f"**工作目录**: `{directory}`")
    md_lines.append("")
    md_lines.append("---")
    md_lines.append("")
    md_lines.append("## 对话内容")
    md_lines.append("")

    turn_number = 0
    i = 0
    while i < len(messages):
        msg = messages[i]
        role = msg.get("role", "unknown").lower()
        
        if role == "user":
            turn_number += 1
            user_msg = msg
            assistant_msg = None
            
            if i + 1 < len(messages) and messages[i + 1].get("role", "").lower() == "assistant":
                assistant_msg = messages[i + 1]
                i += 2
            else:
                i += 1
            
            user_time = format_timestamp(user_msg.get("time", {}).get("created"))
            md_lines.append(f"### 问答对 #{turn_number} ({user_time})")
            md_lines.append("")
            
            md_lines.append(f"**👤 USER**")
            user_content = extract_text_from_message(user_msg)
            if user_content:
                md_lines.append(user_content)
            md_lines.append("")
            
            if assistant_msg:
                md_lines.append(f"**🤖 ASSISTANT**")
                agent = assistant_msg.get("agent", "")
                model = assistant_msg.get("model", {}).get("modelID", "")
                if agent:
                    md_lines.append(f"*Agent: {agent}*")
                if model:
                    md_lines.append(f"*Model: {model}*")
                md_lines.append("")
                assistant_content = extract_text_from_message(assistant_msg)
                if assistant_content:
                    md_lines.append(assistant_content)
                md_lines.append("")
            
            md_lines.append("---")
            md_lines.append("")
        else:
            i += 1

    return "\n".join(md_lines)


def get_filename_for_session(session: dict, idx: int) -> str:
    """获取会话的文件名"""
    title = session.get("title", "无标题")[:40]
    safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).strip()
    safe_title = safe_title.replace(" ", "_")[:50]
    return f"{idx:02d}_{safe_title}_{session['id'][:8]}.md"


def export_all_sessions(mode: str = "incremental", output_dir: str = None):
    """
    导出会话

    Args:
        mode: 导出模式
            - "full": 全量导出，所有会话重新导出
            - "incremental": 增量导出，只导出新增或更新的会话
        output_dir: 输出目录，默认使用 ~/Documents/OpenCode_Exports
    """
    # 支持命令行第一个参数作为输出目录
    if output_dir is None and len(sys.argv) > 1:
        arg = sys.argv[1]
        if not arg.startswith("-"):
            output_dir = arg

    if output_dir:
        output_path = Path(output_dir).expanduser().resolve()
    else:
        output_path = EXPORT_DIR
    output_path.mkdir(parents=True, exist_ok=True)

    metadata = load_metadata()
    sessions = list_sessions()

    if not sessions:
        print("❌ 没有找到任何会话")
        return

    print(f"\n📦 共有 {len(sessions)} 个会话")
    print(f"📁 导出目录: {output_path}")
    print(f"📋 导出模式: {'全量' if mode == 'full' else '增量'}")
    print()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    summary_file = output_path / f"session_summary_{timestamp}.md"
    change_log_file = output_path / f"changelog_{timestamp}.md"

    summary_lines = ["# OpenCode 会话导出摘要", "", f"导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", ""]
    summary_lines.append(f"**导出模式**: {'全量' if mode == 'full' else '增量'}")
    summary_lines.append("")

    if mode == "incremental":
        changelog_lines = ["# OpenCode 会话变更日志", "", f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", ""]
        changelog_lines.append("## 新增或更新的会话\n")

    exported_count = 0
    skipped_count = 0
    new_sessions = []
    updated_sessions = []

    for idx, session in enumerate(sessions, 1):
        session_id = session.get("id")
        title = session.get("title", "无标题")[:40]
        updated = session.get("time", {}).get("updated", 0)
        current_hash = get_session_hash(session)
        md_filename = get_filename_for_session(session, idx)
        md_file = output_path / md_filename

        metadata_entry = metadata["exported_sessions"].get(session_id, {})
        last_exported_hash = metadata_entry.get("hash")
        last_updated = metadata_entry.get("updated")

        should_export = False
        reason = ""

        if mode == "full":
            should_export = True
            reason = "全量导出"
        else:
            if session_id not in metadata["exported_sessions"]:
                should_export = True
                reason = "新增会话"
                new_sessions.append(title)
            elif last_updated != updated:
                should_export = True
                reason = "内容更新"
                updated_sessions.append(title)
            elif current_hash != last_exported_hash:
                should_export = True
                reason = "结构变化"
                updated_sessions.append(title)
            else:
                should_export = False
                reason = "无变化"

        print(f"  [{idx:2d}] {title}")

        if should_export:
            try:
                result = export_session(session)
                if result["messages"]:
                    md_content = session_to_markdown(result, is_update=bool(metadata_entry))

                    with open(md_file, 'w', encoding='utf-8') as f:
                        f.write(md_content)

                    metadata["exported_sessions"][session_id] = {
                        "filename": md_filename,
                        "updated": updated,
                        "hash": current_hash,
                        "last_exported": datetime.now().isoformat(),
                        "title": title
                    }

                    exported_count += 1
                    print(f"     ✅ {reason}: {md_filename}")

                    if mode == "incremental":
                        changelog_lines.append(f"- **{title}** ({reason})")
                        changelog_lines.append(f"  - ID: `{session_id}`")
                        changelog_lines.append(f"  - 文件: {md_filename}")
                        changelog_lines.append("")
                else:
                    print(f"     ⚠️  无消息内容，跳过")
            except Exception as e:
                print(f"     ❌ 导出失败: {e}")
        else:
            skipped_count += 1
            print(f"     ⏭️  无变化，跳过")

    metadata["last_export"] = datetime.now().isoformat()
    metadata["full_export_done"] = metadata["full_export_done"] or (mode == "full")
    save_metadata(metadata)

    summary_lines.append("## 导出统计\n")
    summary_lines.append(f"- **总会话数**: {len(sessions)}")
    summary_lines.append(f"- **本次导出**: {exported_count}")
    summary_lines.append(f"- **跳过（无变化）**: {skipped_count}")
    summary_lines.append("")
    summary_lines.append("## 新增会话\n")
    summary_lines.append(f"共 {len(new_sessions)} 个")
    for s in new_sessions:
        summary_lines.append(f"- {s}")
    summary_lines.append("")
    summary_lines.append("## 更新的会话\n")
    summary_lines.append(f"共 {len(updated_sessions)} 个")
    for s in updated_sessions:
        summary_lines.append(f"- {s}")
    summary_lines.append("")

    summary_lines.append("## 会话列表\n")
    summary_lines.append("| # | 标题 | 目录 | 更新时间 | 状态 |")
    summary_lines.append("|---|------|------|---------|------|")

    for idx, session in enumerate(sessions, 1):
        title = session.get("title", "无标题")[:35]
        directory = session.get("directory", "")[-25:]
        updated = format_timestamp(session.get("time", {}).get("updated"))
        session_id = session.get("id")

        if session_id in metadata["exported_sessions"]:
            status = "✅"
        else:
            status = "⏳"

        summary_lines.append(f"| {idx} | {title} | {directory} | {updated} | {status} |")

    with open(summary_file, 'w', encoding='utf-8') as f:
        f.write("\n".join(summary_lines))

    if mode == "incremental" and exported_count > 0:
        changelog_lines.append(f"\n---\n*共 {exported_count} 个会话更新*")
        with open(change_log_file, 'w', encoding='utf-8') as f:
            f.write("\n".join(changelog_lines))

    print(f"\n" + "=" * 50)
    print(f"✅ 导出完成！")
    print(f"   总会话: {len(sessions)}")
    print(f"   本次导出: {exported_count}")
    print(f"   跳过: {skipped_count}")
    print(f"=" * 50)
    print(f"\n📋 摘要: {summary_file}")
    if mode == "incremental" and exported_count > 0:
        print(f"📝 变更日志: {change_log_file}")


def list_sessions_status():
    """查看导出状态"""
    metadata = load_metadata()
    sessions = list_sessions()

    print("\n📊 OpenCode 会话导出状态\n")
    last_export = metadata.get("last_export", "从未导出")
    if last_export:
        last_export = datetime.fromisoformat(last_export).strftime("%Y-%m-%d %H:%M:%S")
    print(f"上次导出: {last_export}")
    print(f"全量导出: {'✅ 已完成' if metadata.get('full_export_done') else '❌ 未完成'}")
    print(f"已导出: {len(metadata.get('exported_sessions', {}))} 个会话")
    print(f"总会话: {len(sessions)} 个")
    print()

    pending = []
    for session in sessions:
        session_id = session.get("id")
        if session_id not in metadata.get("exported_sessions", {}):
            pending.append(session)

    if pending:
        print(f"⏳ 待导出 ({len(pending)} 个):\n")
        for s in pending[:10]:
            title = s.get("title", "无标题")[:50]
            updated = format_timestamp(s.get("time", {}).get("updated"))
            print(f"   • {title}")
            print(f"     更新: {updated}")
        if len(pending) > 10:
            print(f"   ... 还有 {len(pending) - 10} 个")
    else:
        print("✅ 所有会话已导出")


if __name__ == "__main__":
    print("""
╔═══════════════════════════════════════════════════════╗
║        OpenCode Session Exporter                     ║
║        会话导出工具 - 支持增量导出                    ║
╚═══════════════════════════════════════════════════════╝
""")

    if len(sys.argv) > 1:
        arg = sys.argv[1]

        if arg in ["--list", "-l"]:
            sessions = list_sessions()
            print(f"\n找到 {len(sessions)} 个会话:\n")
            for idx, s in enumerate(sessions, 1):
                title = s.get("title", "无标题")[:45]
                updated = format_timestamp(s.get("time", {}).get("updated"))
                print(f"  {idx:2d}. {title}")
                print(f"      ID: {s.get('id', 'unknown')}")
                print(f"      更新: {updated}")
                print()

        elif arg in ["--status", "-s"]:
            list_sessions_status()

        elif arg in ["--full", "-f"]:
            export_all_sessions(mode="full")

        elif arg in ["--incremental", "-i"]:
            export_all_sessions(mode="incremental")

        elif arg in ["--all-sessions", "-a"]:
            export_to_all_sessions(mode="incremental")

        elif arg in ["--rebuild-all", "-r"]:
            export_to_all_sessions(mode="full")

        elif arg in ["--help", "-h"]:
            print("""
用法: python3 export_sessions.py [选项]

选项:
  --list, -l        列出所有会话
  --status, -s     查看导出状态
  --full, -f       全量导出到独立文件
  --incremental, -i  增量导出到独立文件
  --all-sessions, -a  增量追加到 all_sessions.md（推荐）
  --rebuild-all, -r  重建 all_sessions.md（清空后重新导出）
  --help, -h       显示此帮助信息

示例:
  python3 export_sessions.py --status        # 查看导出状态
  python3 export_sessions.py --all-sessions   # 增量追加到统一文档
  python3 export_sessions.py --rebuild-all    # 重建统一文档

说明:
  --all-sessions: 增量追加到 documents/all_sessions.md
  --rebuild-all: 清空后重新导出所有会话到统一文档
""")
        else:
            print(f"未知参数: {arg}")
            print("使用 --help 查看帮助")
    else:
        export_to_all_sessions(mode="incremental")
