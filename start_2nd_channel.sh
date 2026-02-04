#!/bin/bash
# AI工厂2号通道服务启动脚本
# 用于systemd服务调用

cd /home/ecs-assist-user/ai-factory

# 设置环境变量（根据实际情况修改）
export AI_PG_HOST=localhost
export AI_PG_PORT=5433
export AI_PG_DB=rag_db
export AI_PG_USER=rag_user
export AI_PG_PASSWORD=rag_password

# 启动AI工厂服务
exec uvicorn ai_factory.web.entries_browser_app:app --host 0.0.0.0 --port 8001 --workers 2
