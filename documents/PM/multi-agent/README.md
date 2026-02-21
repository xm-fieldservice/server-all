# Multi-Agent MVP

> 自建 Agent A (AutoGen) 与 OpenCode Agent B 交互系统

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

打开浏览器访问: http://localhost:5000

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
| POST | /api/chat | 发送对话 |
| GET | /api/history | 获取历史记录 |
| GET | /api/health | 健康检查 |

## 使用流程

1. 用户在问答页面输入指令
2. Agent A 接收指令并进行简单文字梳理
3. Agent A 调用 OpenCode API (Agent B)
4. Agent B 执行任务并返回结果
5. Agent A 将完整对话写入 `logs/conversation.md`
6. 结果展示给用户
