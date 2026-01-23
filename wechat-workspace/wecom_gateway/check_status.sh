#!/bin/bash
# 企业微信回调通道快速检查脚本

echo "========================================"
echo "企业微信回调通道状态检查"
echo "========================================"
echo ""

# 1. 检查服务状态
echo "1. 服务状态:"
if ps aux | grep -q "[u]vicorn app:app"; then
    echo "   ✓ 服务正在运行"
    ps aux | grep "[u]vicorn app:app" | awk '{print "   进程ID:", $2, "| 启动时间:", $9}'
else
    echo "   ✗ 服务未运行"
    echo "   启动命令: cd /root/wechat-workspace/wecom_gateway && bash start.sh"
fi
echo ""

# 2. 检查端口
echo "2. 端口监听:"
if ss -tlnp | grep -q ":8002"; then
    echo "   ✓ 端口 8002 正在监听"
else
    echo "   ✗ 端口 8002 未监听"
fi
echo ""

# 3. 检查配置
echo "3. 环境变量配置:"
cd /root
source .env 2>/dev/null

check_var() {
    local var_name=$1
    local var_value=${!var_name}
    if [ -n "$var_value" ]; then
        echo "   ✓ $var_name"
    else
        echo "   ✗ $var_name (未配置)"
    fi
}

check_var "WECOM_CORP_ID"
check_var "WECOM_QA_AGENT_ID"
check_var "WECOM_NOTE_AGENT_ID"
check_var "WECOM_APP_SECRET"
check_var "WECOM_CALLBACK_TOKEN"
check_var "WECOM_ENCODING_AES_KEY"
echo ""

# 4. 测试连接
echo "4. 服务连通性测试:"
if curl -s http://localhost:8002/docs > /dev/null 2>&1; then
    echo "   ✓ 本地连接正常"
    echo "   API文档: http://localhost:8002/docs"
else
    echo "   ✗ 本地连接失败"
fi
echo ""

# 5. 检查日志
echo "5. 最近日志 (最后5行):"
if [ -f /root/wechat-workspace/wecom_gateway/wecom.log ]; then
    tail -5 /root/wechat-workspace/wecom_gateway/wecom.log | sed 's/^/   /'
else
    echo "   日志文件不存在"
fi
echo ""

# 6. 快速操作提示
echo "========================================"
echo "快速操作命令"
echo "========================================"
echo "启动服务:"
echo "  cd /root/wechat-workspace/wecom_gateway && bash start.sh"
echo ""
echo "停止服务:"
echo "  pkill -f 'uvicorn app:app'"
echo ""
echo "查看日志:"
echo "  tail -f /root/wechat-workspace/wecom_gateway/wecom.log"
echo ""
echo "运行测试:"
echo "  cd /root/wechat-workspace/wecom_gateway && python3 test_callback.py"
echo ""
echo "调试配置:"
echo "  cd /root/wechat-workspace/wecom_gateway && python3 debug_callback.py"
echo ""
