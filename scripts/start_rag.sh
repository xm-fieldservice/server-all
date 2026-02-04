#!/bin/bash
# RAG Service Startup Script
# 确保代理环境变量已设置

export CLASH_HTTP_PROXY=http://127.0.0.1:7897
export CLASH_SOCKS_PROXY=127.0.0.1:7897
export HTTP_PROXY=http://127.0.0.1:7897
export HTTPS_PROXY=http://127.0.0.1:7897

# 切换到项目目录
cd /root/ai-factory

# 激活虚拟环境
source .venv/bin/activate

# 停止现有的RAG服务
pkill -f "uvicorn ai_factory.web.api_app:app" 2>/dev/null

# 等待进程完全停止
sleep 2

# 启动RAG服务
nohup uvicorn ai_factory.web.api_app:app --host 0.0.0.0 --port 8000 > rag_server.log 2>&1 &

echo "RAG服务已启动在 http://0.0.0.0:8000"
echo "日志文件: rag_server.log"
