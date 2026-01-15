#!/bin/bash
# MCP Server启动脚本: Agent Memory Nodes Query Tool
# ==========================================

set -e

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

# 加载环境变量
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
else
    echo "警告: 未找到.env文件"
    echo "请确保已配置以下环境变量："
    echo "  - AI_PG_HOST"
    echo "  - AI_PG_PORT"
    echo "  - AI_PG_DB"
    echo "  - AI_PG_USER"
    echo "  - AI_PG_PASSWORD"
fi

# 检查Python环境
if command -v python3 &> /dev/null; then
    PYTHON_CMD=python3
else
    PYTHON_CMD=python
fi

# 检查mcp是否安装
echo "检查MCP依赖..."
if ! $PYTHON_CMD -c "import mcp" 2>/dev/null; then
    echo "MCP未安装，正在安装..."
    $PYTHON_CMD -m pip install mcp
fi

# 检查数据库连接
echo "检查数据库连接..."
$PYTHON_CMD -c "
from ai_factory.db.pgvector_client import connection_scope
try:
    with connection_scope() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT 1')
        print('数据库连接成功')
except Exception as e:
    print(f'数据库连接失败: {e}')
    exit(1)
"

# 启动MCP服务器
echo ""
echo "========================================"
echo "Agent Memory Nodes Query MCP Server"
echo "========================================"
echo "启动时间: $(date -Iseconds)"
echo "工具名称: query_agent_memory_nodes"
echo "工具描述: 查询指定父节点的所有子孙节点并汇总内容"
echo ""
echo "使用示例:"
echo "  - 调用工具: query_agent_memory_nodes"
echo "  - 参数: parent_id='ent_081d2034', format='summary'"
echo ""
echo "按 Ctrl+C 停止服务器"
echo "========================================"
echo ""

# 启动服务器
$PYTHON_CMD -m mcp_server.query_nodes_tool
