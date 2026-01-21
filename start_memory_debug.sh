#!/bin/bash

# Agent记忆系统调试服务启动脚本

echo "========================================"
echo "Agent记忆系统调试服务"
echo "========================================"

# 进入项目目录
cd "$(dirname "$0")"

# 检查Python环境
if ! command -v python3 &> /dev/null; then
    echo "错误: 未找到Python3"
    exit 1
fi

# 检查依赖
echo "检查依赖..."
python3 -c "import fastapi; import uvicorn; import psycopg2" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "缺少依赖，正在安装..."
    pip install fastapi uvicorn[standard] python-multipart
fi

# 检查端口占用
if lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo "警告: 端口8000已被占用"
    read -p "是否终止占用该端口的进程? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        lsof -ti:8000 | xargs kill -9
        echo "已终止占用端口的进程"
    else
        echo "退出"
        exit 1
    fi
fi

# 启动服务
echo "启动API服务..."
echo "API地址: http://localhost:8000"
echo "API文档: http://localhost:8000/docs"
echo "前端页面: ai_factory/web/agent_memory_debug.html"
echo ""
echo "按 Ctrl+C 停止服务"
echo "========================================"

python3 ai_factory/web/agent_memory_api.py
