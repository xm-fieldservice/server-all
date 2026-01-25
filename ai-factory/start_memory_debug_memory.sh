#!/bin/bash

# Agent记忆系统调试服务启动脚本（内存版）

echo "========================================"
echo "Agent记忆系统调试服务（内存版）"
echo "========================================"

# 进入项目目录
cd "$(dirname "$0")"

# 停止现有服务
echo "停止现有服务..."
pkill -9 -f "agent_memory_api*.py" 2>/dev/null

# 等待进程结束
sleep 1

# 启动内存版服务
echo "启动内存版API服务..."
echo "API地址: http://localhost:8001"
echo "API文档: http://localhost:8001/docs"
echo "前端页面: ai_factory/web/agent_memory_debug.html"
echo ""
echo "注意: 使用内存存储，数据不会持久化"
echo "按 Ctrl+C 停止服务"
echo "========================================"

python3 ai_factory/web/agent_memory_api_memory.py
