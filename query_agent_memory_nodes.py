#!/usr/bin/env python3
"""查询父节点ID为ent_081d2034的所有子节点，用于Agent记忆可行性评估。

此脚本会：
1. 查询指定父节点的所有直接子节点
2. 递归查询所有子孙节点
3. 导出为Markdown格式文档
"""

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

# 添加项目根目录到Python路径
project_root = Path(__file__).resolve().parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
from ai_factory.db.pgvector_client import connection_scope

# 加载环境变量
env_path = project_root / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path, override=False)

# 父节点ID
PARENT_ENTRY_ID = "ent_081d2034"

# 输出文件路径
OUTPUT_MD = project_root / "agent_memory_nodes_export.md"


def get_entry_by_id(entry_id: str) -> Optional[Dict[str, Any]]:
    """根据entry_id获取单条记录。"""
    sql = """
        SELECT entry_id, title, summary_ai, content, project_code, user_id,
               created_at, space_type, parent_entry_id, scene_tags, memo
        FROM entries
        WHERE entry_id = %s
    """
    with connection_scope() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (entry_id,))
            row = cur.fetchone()
            if row is None:
                return None
            colnames = [d[0] for d in cur.description]
            return dict(zip(colnames, row))


def get_children_by_parent(parent_id: str) -> List[Dict[str, Any]]:
    """获取指定父节点的所有直接子节点。"""
    sql = """
        SELECT entry_id, title, summary_ai, content, project_code, user_id,
               created_at, space_type, parent_entry_id, scene_tags, memo
        FROM entries
        WHERE parent_entry_id = %s
        ORDER BY created_at, entry_id
    """
    with connection_scope() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (parent_id,))
            rows = cur.fetchall()
            colnames = [d[0] for d in cur.description]
            return [dict(zip(colnames, row)) for row in rows]


def get_all_descendants(parent_id: str) -> List[Dict[str, Any]]:
    """递归获取所有子孙节点（包括子节点、孙节点等）。"""
    all_nodes: List[Dict[str, Any]] = []
    visited: Set[str] = set()

    def _recursive_collect(current_id: str, level: int = 0) -> None:
        if current_id in visited:
            return
        visited.add(current_id)

        children = get_children_by_parent(current_id)
        for child in children:
            child['_level'] = level
            all_nodes.append(child)
            _recursive_collect(child['entry_id'], level + 1)

    _recursive_collect(parent_id)
    return all_nodes


def format_entry_as_md(entry: Dict[str, Any], level: int = 0) -> str:
    """将单条记录格式化为Markdown。"""
    indent = "  " * level
    lines = []

    # 标题
    title = entry.get('title', '(无标题)')
    entry_id = entry.get('entry_id', '')
    created_at = entry.get('created_at', '')
    space_type = entry.get('space_type', '')

    header_level = min(4 + level, 6)
    lines.append(f"{indent}{'#' * header_level} {title}")
    lines.append(f"{indent}**ID:** `{entry_id}` | **创建时间:** `{created_at}` | **类型:** `{space_type}`")
    lines.append("")

    # 摘要
    summary = entry.get('summary_ai')
    if summary:
        lines.append(f"{indent}**AI摘要:**")
        lines.append(f"{indent}{summary}")
        lines.append("")

    # 内容
    content = entry.get('content', '')
    if content:
        lines.append(f"{indent}**内容:**")
        lines.append(f"{indent}```")
        lines.extend([f"{indent}{line}" for line in content.split('\n')])
        lines.append(f"{indent}```")
        lines.append("")

    # scene_tags
    scene_tags = entry.get('scene_tags')
    if scene_tags:
        lines.append(f"{indent}**场景标签:**")
        if isinstance(scene_tags, str):
            try:
                scene_tags = json.loads(scene_tags)
            except Exception:
                pass
        if isinstance(scene_tags, dict):
            lines.append(f"{indent}```json")
            lines.extend([f"{indent}{line}" for line in json.dumps(scene_tags, ensure_ascii=False, indent=2).split('\n')])
            lines.append(f"{indent}```")
        else:
            lines.append(f"{indent}`{scene_tags}`")
        lines.append("")

    # memo
    memo = entry.get('memo')
    if memo:
        lines.append(f"{indent}**Memo:**")
        if isinstance(memo, str):
            try:
                memo = json.loads(memo)
            except Exception:
                pass
        if isinstance(memo, dict):
            lines.append(f"{indent}```json")
            lines.extend([f"{indent}{line}" for line in json.dumps(memo, ensure_ascii=False, indent=2).split('\n')])
            lines.append(f"{indent}```")
        else:
            lines.append(f"{indent}`{memo}`")
        lines.append("")

    lines.append(f"{indent}---")
    lines.append("")

    return "\n".join(lines)


def export_to_markdown(parent_entry: Optional[Dict[str, Any]],
                       children: List[Dict[str, Any]],
                       all_descendants: List[Dict[str, Any]]) -> str:
    """导出为Markdown格式。"""
    lines = []

    # 文档标题
    lines.append("# Agent记忆相关节点导出")
    lines.append("")
    lines.append(f"**父节点ID:** `{PARENT_ENTRY_ID}`")
    lines.append(f"**导出时间:** `{os.popen('date').read().strip()}`")
    lines.append("")

    # 父节点信息
    if parent_entry:
        lines.append("## 父节点信息")
        lines.append("")
        lines.extend(format_entry_as_md(parent_entry).split('\n'))

    # 直接子节点
    lines.append("## 直接子节点")
    lines.append("")
    if children:
        lines.append(f"**数量:** {len(children)}")
        lines.append("")
        for child in children:
            lines.extend(format_entry_as_md(child).split('\n'))
    else:
        lines.append("无直接子节点")
        lines.append("")

    # 所有子孙节点（树形结构）
    lines.append("## 所有子孙节点（树形结构）")
    lines.append("")
    if all_descendants:
        lines.append(f"**数量:** {len(all_descendants)}")
        lines.append("")
        for node in all_descendants:
            lines.extend(format_entry_as_md(node, level=node.get('_level', 0)).split('\n'))
    else:
        lines.append("无子孙节点")
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    print(f"开始查询父节点ID为 {PARENT_ENTRY_ID} 的所有子节点...")

    # 获取父节点信息
    print(f"获取父节点信息...")
    parent_entry = get_entry_by_id(PARENT_ENTRY_ID)
    if parent_entry is None:
        print(f"错误：未找到父节点 {PARENT_ENTRY_ID}")
        return 1
    print(f"父节点标题: {parent_entry.get('title')}")

    # 获取直接子节点
    print(f"获取直接子节点...")
    children = get_children_by_parent(PARENT_ENTRY_ID)
    print(f"找到 {len(children)} 个直接子节点")

    # 获取所有子孙节点
    print(f"获取所有子孙节点...")
    all_descendants = get_all_descendants(PARENT_ENTRY_ID)
    print(f"找到 {len(all_descendants)} 个子孙节点（包括子节点）")

    # 导出为Markdown
    print(f"导出为Markdown...")
    md_content = export_to_markdown(parent_entry, children, all_descendants)
    OUTPUT_MD.write_text(md_content, encoding='utf-8')
    print(f"已导出到: {OUTPUT_MD}")

    # 打印统计信息
    print("\n统计信息:")
    print(f"  父节点: 1")
    print(f"  直接子节点: {len(children)}")
    print(f"  所有子孙节点: {len(all_descendants)}")

    # 按space_type统计
    space_type_count: Dict[str, int] = {}
    for node in all_descendants:
        st = node.get('space_type', 'unknown')
        space_type_count[st] = space_type_count.get(st, 0) + 1
    print(f"\n按space_type统计:")
    for st, count in sorted(space_type_count.items()):
        print(f"  {st}: {count}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
