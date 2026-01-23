import asyncio
import json
import uuid
import sys
import os
from datetime import datetime
from typing import Optional, List, Dict, Any

# Ensure ai-factory root is in sys.path
sys.path.insert(0, "/root/ai-factory")

from mcp.server.models import InitializationOptions
from mcp.server import NotificationOptions, Server
from mcp.server.stdio import stdio_server
import mcp.types as types

# 尝试加载数据库操作模块
try:
    from ai_factory.db.entries_repo import insert_entry
except ImportError:
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    from ai_factory.db.entries_repo import insert_entry

server = Server("记录-mcp")

@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """列出可用工具"""
    return [
        types.Tool(
            name="save_structured_record",
            description=(
                "【四级架构】保存结构化记录到长期记忆库。\n"
                "架构逻辑：\n"
                "Level 1 (Title): 核心索引，语义最高浓缩。\n"
                "Level 2 (Summary): AI 提炼的干货摘要，用于向量召回。\n"
                "Level 3 (Content): 原始素材事实，作为 LLM 背景补充。\n"
                "Level 4 (Metadata): 分类标签与维度，用于首选切片（SQL 硬过滤）。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "L1: 核心抬头/标题"
                    },
                    "summary": {
                        "type": "string",
                        "description": "L2: 提炼后的总结摘要（用于主要检索）"
                    },
                    "content": {
                        "type": "string",
                        "description": "L3: 原始对话、代码或素材"
                    },
                    "meta_tags": {
                        "type": "object",
                        "description": "L4: 元数据标签，例如 {'project': 'A', 'importance': 'high'}"
                    }
                },
                "required": ["title", "summary", "content"]
            },
        )
    ]

@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """执行工具"""
    if name == "save_structured_record":
        title = arguments.get("title")
        summary = arguments.get("summary")
        content = arguments.get("content")
        meta_tags = arguments.get("meta_tags") or {}
        
        # 强制标记来源为 CodeBuddy 桌面版
        meta_tags["source"] = "codebuddy-desktop"
        meta_tags["recorded_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        entry_id = f"ent_{uuid.uuid4().hex[:8]}"
        entry = {
            "entry_id": entry_id,
            "title": title,         # Level 1: 独立字段
            "summary": summary,     # Level 2: 独立字段
            "content": content,     # Level 3: 独立字段
            "space_type": "note",
            "scene_tags": meta_tags, # Level 4: 基础标签
            "extra_meta": meta_tags, # Level 4: 扩展维度
            "created_at": datetime.now(),
            "user_id": "codebuddy-user",
            "project_code": meta_tags.get("project", "default")
        }
        
        try:
            insert_entry(entry)
            return [types.TextContent(type="text", text=f"✅ 四级火箭架构记录已存档。\nID: {entry_id}\nL1-L4 已对齐。")]
        except Exception as e:
            return [types.TextContent(type="text", text=f"❌ 存档失败: {str(e)}\n请检查数据库是否在线。")]
            
    raise ValueError(f"Unknown tool: {name}")

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="记录-mcp",
                server_version="2.0.0", # 架构升级版
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )

if __name__ == "__main__":
    asyncio.run(main())
