# 企业微信回调通道调试指南

## 一、配置检查清单

### 1.1 环境变量配置 (.env 文件)

已完成配置的环境变量：

```bash
# 企业微信配置
WECOM_CORP_ID=                    # ⚠️ 需要填写企业ID
WECOM_QA_AGENT_ID=1000025         # ✓ 问答机器人AgentID
WECOM_NOTE_AGENT_ID=1000023       # ✓ 笔记机器人AgentID  
WECOM_APP_SECRET=kkq4Y9R37...     # ✓ 应用Secret
WECOM_CALLBACK_URL=http://xmapp.xiangmin.com.cn/wecom/callback  # ✓ 回调地址
WECOM_CALLBACK_TOKEN=XzudqbfuMq...  # ✓ 回调Token
WECOM_ENCODING_AES_KEY=E6e7M5aZ...  # ✓ 加密密钥
```

**重要提示**：
- `WECOM_CORP_ID` 需要从企业微信管理后台获取
- `WECOM_NOTE_AGENT_ID=1000023` 用于笔记机器人
- `WECOM_QA_AGENT_ID=1000025` 用于问答机器人
- 两个应用使用相同的 `WECOM_APP_SECRET`、`WECOM_CALLBACK_TOKEN` 和 `WECOM_ENCODING_AES_KEY`

### 1.2 依赖安装

必需的 Python 包：
```bash
pip3 install fastapi uvicorn pycryptodome requests --break-system-packages
```

## 二、服务启动与测试

### 2.1 启动服务

```bash
cd /root/wechat-workspace/wecom_gateway
bash start.sh
```

服务将监听在 `http://0.0.0.0:8002`

### 2.2 检查服务状态

```bash
# 检查进程
ps aux | grep "uvicorn app:app"

# 访问API文档
curl http://localhost:8002/docs

# 或在浏览器访问
# http://localhost:8002/docs
```

### 2.3 运行调试工具

```bash
cd /root/wechat-workspace/wecom_gateway

# 检查配置和环境
python3 debug_callback.py

# 运行完整测试
python3 test_callback.py
```

## 三、测试结果

### 3.1 回调验证测试 (GET)
✅ **通过** - 服务器正确处理签名验证并返回 echostr

### 3.2 笔记机器人消息 (AgentID=1000023)
✅ **通过** - 消息成功接收，处理器正确触发

### 3.3 问答机器人消息 (AgentID=1000025)
✅ **通过** - 消息成功接收，处理器正确触发

### 3.4 调试接口
⚠️ **部分失败** - AI Factory 服务未运行 (404 错误)
- 这是正常的，因为 AI Factory 需要单独启动
- 启动命令: `uvicorn ai_factory.web.entries_browser_app:app --port 8001`

## 四、处理器架构

### 4.1 处理器注册表

系统使用注册表模式，通过 `AgentID` 路由到不同的处理器：

```python
# 笔记机器人 (AgentID=1000023)
@register_handler(agent_id="1000023", name="工作笔记助手")
async def handle_note_bot(userid, content, msg_type, **kwargs):
    # 将消息保存到 AI Factory 的 entries 系统
    pass

# 问答机器人 (AgentID=1000025)
@register_handler(agent_id="1000025", name="企业问答助手")
async def handle_qa_bot(userid, content, msg_type, **kwargs):
    # 调用 AI Factory 的 RAG 接口并回复
    pass
```

### 4.2 消息流程

```
企业微信服务器
    ↓ (POST /wecom/callback)
回调验证 (签名/解密)
    ↓
根据 AgentID 路由
    ↓
调用对应处理器
    ↓
处理器业务逻辑
    ↓
返回 "success" (必须返回，否则企业微信会重试)
```

## 五、企业微信后台配置

在企业微信管理后台配置以下信息：

### 5.1 应用配置
1. 登录企业微信管理后台
2. 进入"应用管理" → 选择对应应用
3. 点击"接收消息"配置

### 5.2 回调配置
```
URL: http://xmapp.xiangmin.com.cn/wecom/callback
Token: XzudqbfuMqOkoPJsIZCFJpc2754jYG7
EncodingAESKey: E6e7M5aZSsBdp3ovSsSKlVlfDyPaQrVzJLLHCpU7KD1
```

### 5.3 验证步骤
1. 填写上述配置
2. 点击"保存" - 企业微信会发送验证请求
3. 服务器正确响应后，配置保存成功

## 六、调试技巧

### 6.1 查看实时日志

```bash
# 方法1: 查看文件日志
tail -f /root/wechat-workspace/wecom_gateway/wecom.log

# 方法2: 查看进程输出
ps aux | grep uvicorn
# 找到进程ID后
tail -f /proc/[PID]/fd/1  # 标准输出
```

### 6.2 手动测试回调

```bash
# 测试签名验证 (GET)
curl "http://localhost:8002/wecom/callback?msg_signature=xxx&timestamp=xxx&nonce=xxx&echostr=test"

# 测试消息接收 (POST)
curl -X POST "http://localhost:8002/wecom/callback" \
  -H "Content-Type: text/xml" \
  -d '<xml>
    <ToUserName><![CDATA[ww123456]]></ToUserName>
    <FromUserName><![CDATA[TestUser]]></FromUserName>
    <CreateTime>1234567890</CreateTime>
    <MsgType><![CDATA[text]]></MsgType>
    <Content><![CDATA[测试消息]]></Content>
    <AgentID>1000023</AgentID>
  </xml>'
```

### 6.3 使用调试端点

服务提供了几个调试端点：

```bash
# 测试笔记功能
curl "http://localhost:8002/debug/test_note?userid=test_user&content=测试笔记"

# 模拟企业微信发送消息
curl -X POST "http://localhost:8002/debug/wecom_send_test" \
  -H "Content-Type: application/json" \
  -d '{"touser": "userid", "content": "测试消息"}'
```

## 七、常见问题

### 7.1 签名验证失败
**原因**：Token 配置不一致
**解决**：确保 `.env` 中的 `WECOM_CALLBACK_TOKEN` 与企业微信后台配置一致

### 7.2 解密失败
**原因**：EncodingAESKey 配置错误
**解决**：
1. 检查 `WECOM_ENCODING_AES_KEY` 长度必须是 43 字符
2. 确保与企业微信后台配置一致

### 7.3 消息不触发处理器
**原因**：AgentID 配置错误
**解决**：
1. 检查 `.env` 中的 `WECOM_NOTE_AGENT_ID` 和 `WECOM_QA_AGENT_ID`
2. 确保与企业微信后台的应用 AgentID 一致

### 7.4 AI Factory 连接失败
**原因**：AI Factory 服务未启动
**解决**：
```bash
cd /path/to/ai_factory
uvicorn web.entries_browser_app:app --port 8001
```

### 7.5 回调地址无法访问
**原因**：防火墙或网络配置问题
**解决**：
1. 确保服务器 8002 端口对外开放
2. 检查域名解析是否正确
3. 测试外网访问: `curl http://xmapp.xiangmin.com.cn/wecom/callback`

## 八、下一步工作

### 8.1 必须完成
- [ ] 获取并配置 `WECOM_CORP_ID`
- [ ] 在企业微信后台完成回调地址验证
- [ ] 启动 AI Factory 服务

### 8.2 可选优化
- [ ] 配置日志轮转
- [ ] 添加监控告警
- [ ] 实现消息重试机制
- [ ] 添加性能指标收集

## 九、联系方式

如有问题，请查看：
- 服务日志: `/root/wechat-workspace/wecom_gateway/wecom.log`
- API 文档: `http://localhost:8002/docs`
- 源码目录: `/root/wechat-workspace/wecom_gateway/`

---

**调试状态**: ✅ 基本功能正常
**最后更新**: 2026-01-23
