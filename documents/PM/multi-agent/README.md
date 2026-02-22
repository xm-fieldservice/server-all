# Multi-Agent MVP

> 自建 Agent A (AutoGen) 与 OpenCode Agent B 交互系统

## 重要说明：OpenCode 目录问题

### 问题背景

OpenCode HTTP API 创建 session 时，工作目录由**服务器启动时决定**，而非 API 参数指定。

| 场景 | 工作目录 | 结果 |
|------|---------|------|
| OpenCode Web 手动打开文件夹 | 用户选择 | ✅ 正确回答 |
| multi-agent 通过 API 调用 | `/root`（默认） | ❌ 答非所问 |

**测试验证**：
```bash
# API 传入 directory 参数被忽略
curl -X POST /session -d '{"directory":"/path/to/dir"}'
# 返回: {"directory": "/root", ...}
```

### 解决方案：使用 cd 指令切换目录

**关键发现**：虽然 API 不支持动态指定目录，但可以通过**指令切换目录**：

```python
# 1. 创建 session 后，先执行 cd
message = "cd /root/ai-factory/documents/PM && glob *.py"

# 2. 同一 session 内，保持目录状态
# 后续消息会自动在 PM 目录下执行
message = "读取 app.py 的内容"
```

**测试结果**：
```
# 第一条消息
cd /root/ai-factory/documents/PM && glob *.py
→ Found 4 Python files in `/root/ai-factory/documents/PM/multi-agent/`:

# 第二条消息（同一 session）
读取 app.py 的内容
→ 成功读取 app.py 内容（自动在 PM 目录下查找）
```

### 结论

| 功能 | 是否支持 |
|------|---------|
| API 参数指定目录 | ❌ 不支持 |
| 指令 `cd` 切换目录 | ✅ 支持 |
| 同一 session 保持目录 | ✅ 支持 |
| 项目知识库 (AGENTS.md) | ❌ 不自动加载 |

### 应用到 multi-agent

在 multi-agent 页面实现目录选择：
1. 用户选择项目（如 PM）
2. 后端在消息前自动加 `cd {项目路径} && `
3. 同一 session 内后续消息保持该目录

---

## 快速开始

### 1. 安装依赖

```bash
cd /root/ai-factory/documents/PM/multi-agent
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
# DeepSeek API
export DEEPSEEK_API_KEY="your-deepseek-api-key"
export DEEPSEEK_API_BASE="https://api.deepseek.com/v1"

# OpenCode Server (可选)
export OPENCODE_URL="http://localhost:4096"
```

### 3. 启动 OpenCode Server

```bash
# 终端 1
opencode serve --port 4096
```

### 4. 启动 Web 服务

```bash
# 终端 2
cd /root/ai-factory/documents/PM/multi-agent
python app.py
```

### 5. 访问

打开浏览器访问: http://47.92.174.170:7480

## 项目结构

```
multi-agent/
├── app.py                 # Flask Web 应用
├── agent_a.py             # AutoGen Agent A
├── opencode_client.py     # OpenCode HTTP 客户端
├── md_writer.py           # MD 文档写入模块
├── requirements.txt       # Python 依赖
├── logs/
│   └── conversation.md    # 对话记录
├── templates/
│   └── index.html         # 问答页面
└── README.md              # 本文件
```

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | / | 首页 |
| POST | /qa/api/chat | 发送对话 |
| GET | /qa/api/history | 获取历史记录 |
| GET | /qa/api/health | 健康检查 |

## 使用流程

1. 用户在问答页面输入指令
2. Agent A 接收指令并进行简单文字梳理
3. Agent A 调用 OpenCode API (Agent B)
4. Agent B 执行任务并返回结果
5. Agent A 将完整对话写入 `logs/conversation.md`
6. 结果展示给用户

## Session 管理

### 当前行为

| 方法 | 行为 |
|------|------|
| `call()` | 每次创建新 session → 发送消息 → 返回结果 |
| `send_message()` | 发送到指定 session（需自行管理 session_id） |

**结论**：每次用户输入都会创建全新 session，不支持多轮对话。

### 复用 Session

如需多轮对话，可使用 `OpenCodeClient`：

```python
# 1. 先创建 session
session_info = client.create_session(title="用户问答")
session_id = session_info["id"]  # 保存这个 ID

# 2. 后续消息复用同一 session
client.send_message("第2条消息", session_id=session_id)
client.send_message("第3条消息", session_id=session_id)
```

### Session 与目录结合

结合目录切换功能：

```python
# 创建 session 后，先 cd 到目标目录
first_message = f"cd {project_dir} && {user_message}"

# 同一 session 内自动保持目录
client.send_message("继续提问...", session_id=session_id)
```

---

## Sisyphus Agent 配置

### Agents (11个)

| Agent | 模型 | 职责 |
|-------|------|------|
| Sisyphus | glm-5-free | 主调度，复杂任务 |
| Atlas | glm-5-free | 主机路由 |
| Prometheus | glm-5-free | 战略规划 |
| Hephaestus | glm-5-free | 自主深度工作 |
| Oracle | kimi-k2.5-free | 战略顾问 |
| Metis | kimi-k2.5-free | 预规划分析 |
| Momus | kimi-k2.5-free | 计划验证 |
| librarian | big-pickle | 文档研究 |
| explore | gpt-5-nano | 快速搜索 |
| multimodal-looker | kimi-k2.5-free | 媒体分析 |
| Sisyphus-Junior | glm-5-free | Category执行 |

### Categories (8个)

| Category | 模型 | 用途 |
|----------|------|------|
| code | glm-5-free | 代码开发 |
| docs | big-pickle | 文档 |
| business-logic | glm-5-free | 业务逻辑 |
| visual-engineering | kimi-k2.5-free | UI |
| code-review | kimi-k2.5-free | 审查 |
| research | big-pickle | 研究 |
| planning | glm-5-free | 规划 |
| quick | gpt-5-nano | 简单任务 |

### 模型选择逻辑

- **代码类任务** → GLM 5 Free (最强代码能力)
- **分析/推理类** → Kimi K2.5 Free (高IQ)
- **快速/轻量** → GPT 5 Nano (最轻量)
- **文档/研究** → Big Pickle (免费快速)

---

## 服务部署（ systemd）

### 服务配置

服务文件位于：`/etc/systemd/system/multi-agent.service`

```ini
[Unit]
Description=Multi-Agent QA Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/ai-factory/documents/PM/multi-agent
Environment="PATH=/usr/local/bin:/usr/bin:/bin"
Environment="PYTHONUNBUFFERED=1"
ExecStart=/usr/bin/python3 /root/ai-factory/documents/PM/multi-agent/app.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### 管理命令

```bash
# 启动服务
systemctl start multi-agent

# 停止服务
systemctl stop multi-agent

# 重启服务
systemctl restart multi-agent

# 查看状态
systemctl status multi-agent

# 开机自启
systemctl enable multi-agent

# 取消开机自启
systemctl disable multi-agent
```

### 日志查看

```bash
# 查看服务日志
journalctl -u multi-agent -f

# 或查看应用日志
tail -f /tmp/multi-agent.log
```

### 注意事项

- Debug 模式默认关闭，防止自动重载导致崩溃
- 服务异常退出后会自动重启（Restart=always）
- 端口：7480
