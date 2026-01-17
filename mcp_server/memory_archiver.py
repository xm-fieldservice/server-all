import asyncio
import json
import uuid
import sys
import os
from datetime import datetime
from typing import Optional, List, Dict, Any

# Ensure ai-factory root is in sys.path
sys.path.insert(0, "/home/ecs-assist-user/ai-factory")

from mcp.server.models import InitializationOptions
from mcp.server import NotificationOptions, Server
from mcp.server.stdio import stdio_server
import mcp.types as types

from ai_factory.db.entries_repo import insert_entry

server = Server("memory-archiver")

@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """列出可用工具"""
    return [
        types.Tool(
            name="archive_execution_result",
            description="将当前任务的执行结果、总结或重要发现永久保存到 AI 工厂的记忆库中，以便日后查询。",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "保存内容的标题，简明扼要"
                    },
                    "content": {
                        "type": "string",
                        "description": "详细的执行结果或笔记内容"
                    },
                    "summary": {
                        "type": "string",
                        "description": "（可选）由 AI 生成的内容摘要"
                    },
                    "tags": {
                        "type": "object",
                        "description": "（可选）场景标签，例如 {'task': 'refactor', 'language': 'python'}"
                    }
                },
                "required": ["title", "content"]
            },
        )
    ]

@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """执行工具"""
    if name == "archive_execution_result":
        title = arguments.get("title")
        content = arguments.get("content")
        summary = arguments.get("summary")
        tags = arguments.get("tags")
        
        entry_id = f"ent_{uuid.uuid4().hex[:8]}"
        entry = {
            "entry_id": entry_id,
            "title": title,
            "content": content,
            "summary_ai": summary or title,
            "space_type": "note",
            "scene_tags": tags or {"source": "codebuddy-execution"},
            "created_at": datetime.now(),
            "user_id": "system",
            "project_code": "codebuddy"
        }
        
        try:
            insert_entry(entry)
            result = {
                "success": True,
                "entry_id": entry_id,
                "message": f"成功保存到记忆库，ID: {entry_id}"
            }
            return [types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
        except Exception as e:
            return [types.TextContent(type="text", text=f"Error: {str(e)}")]
            
    raise ValueError(f"Unknown tool: {name}")

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="memory-archiver",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )

if __name__ == "__main__":
    asyncio.run(main())
