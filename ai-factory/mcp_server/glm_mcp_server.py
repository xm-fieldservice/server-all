import asyncio
import os
import json
import sys
from mcp.server.models import InitializationOptions
from mcp.server import NotificationOptions, Server
from mcp.server.stdio import stdio_server
import mcp.types as types
from openai import OpenAI

# 配置智谱 API
API_KEY = "c2ba47535b254f258224b0cdc087db01.mPJXV3QiJzqIngl5"
BASE_URL = "https://open.bigmodel.cn/api/paas/v4/"

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

server = Server("zhipu-glm-tools")

@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """列出可用工具"""
    return [
        types.Tool(
            name="glm_chat",
            description="调用智谱 GLM-4.7 (glm-4-plus) 模型进行深度代码分析或对话",
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "需要发送给 GLM 的指令或代码"},
                    "model": {"type": "string", "description": "模型名称，默认为 glm-4-plus", "default": "glm-4-plus"},
                },
                "required": ["prompt"],
            },
        )
    ]

@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """执行工具"""
    if name == "glm_chat":
        prompt = arguments.get("prompt")
        model = arguments.get("model", "glm-4-plus")
        
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
            )
            return [types.TextContent(type="text", text=response.choices[0].message.content)]
        except Exception as e:
            return [types.TextContent(type="text", text=f"Error: {str(e)}")]
    
    raise ValueError(f"Unknown tool: {name}")

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="zhipu-glm",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )

if __name__ == "__main__":
    asyncio.run(main())
