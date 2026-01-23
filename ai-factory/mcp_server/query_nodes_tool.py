"""
MCP Server: Agent Memory Nodes Query Tool
=========================================

这是一个基于MCP（Model Context Protocol）标准的服务器，
提供查询父节点所有子节点并汇总内容的能力。

功能说明：
--------
1. 接受父节点ID作为输入
2. 递归查询数据库获取所有子孙节点
3. 按层级结构整理内容
4. 返回结构化的JSON结果

使用方式：
--------
1. 安装依赖：pip install mcp
2. 启动服务器：python -m ai_factory.mcp_server.query_nodes_tool
3. 在MCP客户端中调用工具：query_agent_memory_nodes

配置说明：
--------
环境变量：
- AI_PG_HOST: PostgreSQL主机地址
- AI_PG_PORT: PostgreSQL端口
- AI_PG_DB: 数据库名称
- AI_PG_USER: 数据库用户名
- AI_PG_PASSWORD: 数据库密码
"""

import asyncio
import json
from typing import Optional, List, Dict, Any
from datetime import datetime

try:
    from mcp.server import Server
    from mcp.server.models import Tool, TextContent
    from mcp.types import (
        Resource,
        Tool as MCPTool,
        TextContent as MCPTextContent,
    )
except ImportError:
    # 如果MCP未安装，提供一个模拟接口
    Server = None
    print("警告: mcp包未安装，请运行: pip install mcp")

from ai_factory.db.pgvector_client import connection_scope


class QueryNodesTool:
    """查询节点树并汇总内容的工具类"""
    
    def __init__(self):
        self.name = "query_agent_memory_nodes"
        self.description = "查询指定父节点的所有子孙节点并汇总内容"
        
    def get_entry_by_id(self, entry_id: str) -> Optional[Dict[str, Any]]:
        """获取单个条目"""
        with connection_scope() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT entry_id, title, content, summary_ai, 
                           parent_entry_id, space_type, scene_tags,
                           created_at, user_id, project_code
                    FROM entries
                    WHERE entry_id = %s
                """, (entry_id,))
                row = cur.fetchone()
                if row:
                    return {
                        'entry_id': row[0],
                        'title': row[1],
                        'content': row[2],
                        'summary_ai': row[3],
                        'parent_entry_id': row[4],
                        'space_type': row[5],
                        'scene_tags': row[6],
                        'created_at': row[7].isoformat() if row[7] else None,
                        'user_id': row[8],
                        'project_code': row[9],
                    }
        return None
    
    def get_children_by_parent(self, parent_id: str) -> List[Dict[str, Any]]:
        """获取直接子节点"""
        with connection_scope() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT entry_id, title, content, summary_ai,
                           parent_entry_id, space_type, scene_tags,
                           created_at, user_id, project_code
                    FROM entries
                    WHERE parent_entry_id = %s AND space_type = 'note'
                    ORDER BY created_at ASC
                """, (parent_id,))
                rows = cur.fetchall()
                return [{
                    'entry_id': row[0],
                    'title': row[1],
                    'content': row[2],
                    'summary_ai': row[3],
                    'parent_entry_id': row[4],
                    'space_type': row[5],
                    'scene_tags': row[6],
                    'created_at': row[7].isoformat() if row[7] else None,
                    'user_id': row[8],
                    'project_code': row[9],
                } for row in rows]
    
    def get_all_descendants(self, parent_id: str, max_depth: int = 10) -> List[Dict[str, Any]]:
        """递归获取所有子孙节点"""
        def _recursive_fetch(current_id: str, depth: int, result: List[Dict[str, Any]]):
            if depth > max_depth:
                return
            
            children = self.get_children_by_parent(current_id)
            for child in children:
                child['depth'] = depth
                child['children'] = []
                result.append(child)
                _recursive_fetch(child['entry_id'], depth + 1, child['children'])
        
        all_nodes = []
        _recursive_fetch(parent_id, 0, all_nodes)
        return all_nodes
    
    def summarize_by_theme(self, nodes: List[Dict[str, Any]]) -> Dict[str, Any]:
        """按主题汇总节点内容"""
        themes = {
            '技术方案评估': [],
            '架构设计': [],
            '多用户多助手': [],
            'Q&A缓存机制': [],
            'UI与数据结构': [],
            '性能优化': [],
            '其他': []
        }
        
        for node in nodes:
            title = node.get('title', '')
            summary = node.get('summary_ai', '') or node.get('content', '')
            
            # 简单的主题分类逻辑
            if any(kw in title.lower() for kw in ['方案', '评估', '选择', '建议']):
                themes['技术方案评估'].append({
                    'entry_id': node['entry_id'],
                    'title': title,
                    'summary': summary[:500] if len(summary) > 500 else summary,
                    'created_at': node['created_at']
                })
            elif any(kw in title.lower() for kw in ['架构', '设计', '规划', '路径']):
                themes['架构设计'].append({
                    'entry_id': node['entry_id'],
                    'title': title,
                    'summary': summary[:500] if len(summary) > 500 else summary,
                    'created_at': node['created_at']
                })
            elif any(kw in title.lower() for kw in ['多用户', '多助手', '隔离', '共享']):
                themes['多用户多助手'].append({
                    'entry_id': node['entry_id'],
                    'title': title,
                    'summary': summary[:500] if len(summary) > 500 else summary,
                    'created_at': node['created_at']
                })
            elif any(kw in title.lower() for kw in ['q&a', '缓存', '问答', '重复']):
                themes['Q&A缓存机制'].append({
                    'entry_id': node['entry_id'],
                    'title': title,
                    'summary': summary[:500] if len(summary) > 500 else summary,
                    'created_at': node['created_at']
                })
            elif any(kw in title.lower() for kw in ['ui', '界面', '数据结构', '表']):
                themes['UI与数据结构'].append({
                    'entry_id': node['entry_id'],
                    'title': title,
                    'summary': summary[:500] if len(summary) > 500 else summary,
                    'created_at': node['created_at']
                })
            elif any(kw in title.lower() for kw in ['性能', '速度', '优化', '响应']):
                themes['性能优化'].append({
                    'entry_id': node['entry_id'],
                    'title': title,
                    'summary': summary[:500] if len(summary) > 500 else summary,
                    'created_at': node['created_at']
                })
            else:
                themes['其他'].append({
                    'entry_id': node['entry_id'],
                    'title': title,
                    'summary': summary[:500] if len(summary) > 500 else summary,
                    'created_at': node['created_at']
                })
        
        return themes
    
    def flatten_nodes(self, nodes: List[Dict[str, Any]], prefix: str = '') -> List[Dict[str, Any]]:
        """扁平化节点列表"""
        flat_list = []
        for node in nodes:
            flat_list.append({
                'path': f"{prefix}/{node['title']}",
                'entry_id': node['entry_id'],
                'title': node['title'],
                'summary': node.get('summary_ai', '') or node.get('content', ''),
                'created_at': node['created_at'],
                'depth': node['depth']
            })
            if node.get('children'):
                flat_list.extend(self.flatten_nodes(node['children'], f"{prefix}/{node['title']}"))
        return flat_list
    
    def execute_query(self, parent_id: str, format: str = 'tree', include_summary: bool = True) -> Dict[str, Any]:
        """执行查询并返回结果"""
        # 获取父节点信息
        parent = self.get_entry_by_id(parent_id)
        if not parent:
            return {
                'success': False,
                'error': f'未找到父节点: {parent_id}'
            }
        
        # 获取所有子孙节点
        all_nodes = self.get_all_descendants(parent_id)
        
        # 统计信息
        total_count = len(all_nodes)
        direct_children = len(self.get_children_by_parent(parent_id))
        
        # 按主题汇总
        themes = self.summarize_by_theme(all_nodes) if include_summary else {}
        
        # 扁平化列表
        flat_list = self.flatten_nodes(all_nodes, parent['title'])
        
        result = {
            'success': True,
            'parent_node': {
                'entry_id': parent['entry_id'],
                'title': parent['title'],
                'created_at': parent['created_at']
            },
            'statistics': {
                'total_descendants': total_count,
                'direct_children': direct_children,
                'theme_distribution': {k: len(v) for k, v in themes.items()}
            },
            'query_time': datetime.now().isoformat()
        }
        
        if format == 'tree':
            result['nodes'] = all_nodes
        elif format == 'flat':
            result['nodes'] = flat_list
        elif format == 'summary':
            result['themes'] = themes
        
        return result


# MCP Server 配置
def create_mcp_server() -> Optional[Server]:
    """创建MCP服务器实例"""
    if Server is None:
        print("警告: mcp包未安装，无法创建MCP服务器")
        return None
    
    server = Server("agent-memory-nodes")
    tool = QueryNodesTool()
    
    # 定义MCP工具
    mcp_tool = MCPTool(
        name=tool.name,
        description=tool.description,
        inputSchema={
            "type": "object",
            "properties": {
                "parent_id": {
                    "type": "string",
                    "description": "父节点的entry_id",
                    "example": "ent_081d2034"
                },
                "format": {
                    "type": "string",
                    "description": "返回格式：tree(树形结构)、flat(扁平列表)、summary(主题汇总)",
                    "enum": ["tree", "flat", "summary"],
                    "default": "tree"
                },
                "include_summary": {
                    "type": "boolean",
                    "description": "是否包含主题汇总",
                    "default": True
                },
                "max_depth": {
                    "type": "number",
                    "description": "最大递归深度",
                    "default": 10,
                    "minimum": 1,
                    "maximum": 20
                }
            },
            "required": ["parent_id"]
        }
    )
    
    # 注册工具处理器
    async def handle_query_nodes(arguments: Dict[str, Any]) -> List[MCPTextContent]:
        parent_id = arguments.get('parent_id')
        format = arguments.get('format', 'tree')
        include_summary = arguments.get('include_summary', True)
        max_depth = arguments.get('max_depth', 10)
        
        # 更新工具实例的max_depth
        tool.max_depth = max_depth
        
        # 执行查询
        result = tool.execute_query(parent_id, format, include_summary)
        
        # 返回JSON结果
        return [MCPTextContent(
            type="text",
            text=json.dumps(result, ensure_ascii=False, indent=2)
        )]
    
    # 添加工具到服务器
    server.add_tool(mcp_tool, handle_query_nodes)
    
    return server


def main():
    """启动MCP服务器"""
    print("=" * 60)
    print("Agent Memory Nodes Query MCP Server")
    print("=" * 60)
    print(f"启动时间: {datetime.now().isoformat()}")
    print()
    print("工具名称: query_agent_memory_nodes")
    print("工具描述: 查询指定父节点的所有子孙节点并汇总内容")
    print()
    print("使用示例:")
    print("  - 调用工具: query_agent_memory_nodes")
    print("  - 参数: parent_id='ent_081d2034', format='summary'")
    print()
    print("按 Ctrl+C 停止服务器")
    print("=" * 60)
    
    server = create_mcp_server()
    if server is None:
        print("错误: 无法创建MCP服务器，请先安装mcp包")
        print("运行: pip install mcp")
        return
    
    # 启动服务器
    import asyncio
    asyncio.run(server.run())


if __name__ == "__main__":
    main()
