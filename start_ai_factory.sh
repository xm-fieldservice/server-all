#!/usr/bin/env bash

# 一键启动 AI 工厂 Web 服务（服务器版）
# 功能：
# - 进入 ai-factory 项目目录
# - 激活本地虚拟环境（如果存在 .venv）
# - 自动加载 .env（包含 CLASH_HOST / CLASH_PORT / DB 等环境变量）
# - 使用 uvicorn 启动 FastAPI Web（entries 浏览/调试服务）

set -euo pipefail

PROJECT_DIR="/home/ecs-assist-user/ai-factory"
cd "${PROJECT_DIR}"

echo "[start_ai_factory] 当前目录: $(pwd)"

# 1) 激活虚拟环境（如存在）
if [ -d "${PROJECT_DIR}/.venv" ]; then
  echo "[start_ai_factory] 检测到 .venv，开始激活虚拟环境..."
  # shellcheck disable=SC1091
  source "${PROJECT_DIR}/.venv/bin/activate"
  echo "[start_ai_factory] 虚拟环境已激活."
else
  echo "[start_ai_factory] 未发现 .venv，使用系统 Python 运行。"
fi

# 2) 加载环境变量（包括 CLASH_* / DB 配置等）
ENV_LOADED=false

# 2.1 优先加载项目内 .env
if [ -f "${PROJECT_DIR}/.env" ]; then
  echo "[start_ai_factory] 加载项目内 .env 环境变量..."
  set -a
  # shellcheck disable=SC1091
  source "${PROJECT_DIR}/.env"
  set +a
  ENV_LOADED=true
fi

# 2.2 若项目内无 .env，尝试加载家目录下的 .env（例如 /home/ecs-assist-user/.env）
#     但只导入 KEY=VALUE 形式的行，忽略单独一行的密钥，避免被当作命令执行。
if [ "$ENV_LOADED" = false ] && [ -f "/home/ecs-assist-user/.env" ]; then
  echo "[start_ai_factory] 从 /home/ecs-assist-user/.env 导入 KEY=VALUE 形式的环境变量..."
  set -a
  # 仅保留形如 KEY=VALUE 的行，忽略注释和不规范行
  # shellcheck disable=SC1090
  source <(grep -E '^[A-Za-z_][A-Za-z0-9_]*=' "/home/ecs-assist-user/.env" || true)
  set +a
  ENV_LOADED=true
fi

# 2.3 额外尝试加载 ai-factory/env.txt（格式同 .env，用于服务器版配置）
if [ -f "${PROJECT_DIR}/env.txt" ]; then
  echo "[start_ai_factory] 从 env.txt 导入 KEY=VALUE 形式的环境变量..."
  set -a
  # 仅保留形如 KEY=VALUE 的行，忽略注释和不规范行
  # shellcheck disable=SC1090
  source <(grep -E '^[A-Za-z_][A-Za-z0-9_]*=' "${PROJECT_DIR}/env.txt" || true)
  set +a
  ENV_LOADED=true
fi

if [ "$ENV_LOADED" = false ]; then
  echo "[start_ai_factory] 警告：未找到 .env/env.txt，将只使用当前环境中的变量。"
fi

HOST_VALUE="${HOST:-0.0.0.0}"
PORT_VALUE="${PORT:-8000}"

echo "[start_ai_factory] 使用 HOST=${HOST_VALUE} PORT=${PORT_VALUE} 启动 AI 工厂 Web 服务..."
echo "[start_ai_factory] 当前 CLASH 配置: CLASH_HOST=${CLASH_HOST:-<未设置>} CLASH_PORT=${CLASH_PORT:-<未设置>}"

# 3) 启动 uvicorn Web 服务
exec python -m uvicorn ai_factory.web.entries_browser_app:app \
  --host "${HOST_VALUE}" \
  --port "${PORT_VALUE}"
