import asyncio
import json
import uuid
import sys
import os
from datetime import datetime
from typing import Optional, List, Dict, Any

# Ensure ai-factory root is in sys.path
sys.path.insert(0, "/home/ecs-assist-user/ai-factory")

try:
    from mcp.server import Server
    from mcp.server.models import Tool, TextContent
    from mcp.types import (
        Tool as MCPTool,
        TextContent as MCPTextContent,
    )
except ImportError:
    print("Error: mcp package not installed. Run: pip install mcp")
    sys.exit(1)

from ai_factory.db.entries_repo import insert_entry

class MemoryArchiverTool:
    def __init__(self):
        self.name = "archive_execution_result"
        self.description = "将当前任务的执行结果、总结或重要发现永久保存到 AI 工厂的记忆库中，以便日后查询。"
        
    def archive(self, title: str, content: str, summary: Optional[str] = None, tags: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        entry_id = f"ent_{uuid.uuid4().hex[:8]}"
        entry = {
            "entry_id": entry_id,
            "title": title,
            "content": content,
            "summary_ai": summary or title,
            "space_type": "note",
            "scene_tags": tags or {"source": "codebuddy-execution"},
            "created_at": datetime.now(),
            "user_id": "system",  # Or could be passed in
            "project_code": "codebuddy"
        }
        
        try:
            insert_entry(entry)
            return {
                "success": True,
                "entry_id": entry_id,
                "message": f"成功保存到记忆库，ID: {entry_id}"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

async def main():
    server = Server("memory-archiver")
    archiver = MemoryArchiverTool()
    
    mcp_tool = MCPTool(
        name=archiver.name,
        description=archiver.description,
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
        }
    )
    
    async def handle_archive(arguments: Dict[str, Any]) -> List[MCPTextContent]:
        title = arguments.get("title")
        content = arguments.get("content")
        summary = arguments.get("summary")
        tags = arguments.get("tags")
        
        result = archiver.archive(title, content, summary, tags)
        return [MCPTextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    
    server.add_tool(mcp_tool, handle_archive)
    
    print(f"Memory Archiver MCP Server starting...", file=sys.stderr)
    await server.run()

if __name__ == "__main__":
    asyncio.run(main())
