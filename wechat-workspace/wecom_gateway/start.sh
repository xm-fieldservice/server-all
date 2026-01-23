#!/bin/bash
cd "$(dirname "$0")"
set -a
source ../../.env
set +a
# 添加 wechat-workspace 到 PYTHONPATH，以便导入 wecom_gateway 包
export PYTHONPATH="${PYTHONPATH}:$(pwd)/.."
exec uvicorn app:app --host 0.0.0.0 --port 8002 --log-level info