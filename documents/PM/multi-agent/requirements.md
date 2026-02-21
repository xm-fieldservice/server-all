# Multi-Agent MVP 需求文档

> **项目名称**: Multi-Agent 交互系统 MVP  
> **创建日期**: 2026-02-21  
> **版本**: v1.0

---

## 1. 需求概述

构建一个 MVP 演示系统，实现自建 Agent (A) 与 OpenCode Agent (B) 之间的自动交互。

### 1.1 核心功能

| 序号 | 功能 | 描述 |
|------|------|------|
| F1 | Agent A (AutoGen) | 负责接收用户指令、梳理文字、转发给 B |
| F2 | Agent B (OpenCode) | 通过 HTTP API 调用，执行实际任务 |
| F3 | MD 文档写入 | A 将 B 的反馈追加写入 Markdown 文件 |
| F4 | 问答页面 | 简单 Web 界面，用户向 A 发指令 |

### 1.2 用户流程

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  用户       │────▶│  问答页面    │────▶│  Agent A    │────▶│  Agent B    │
│  输入指令   │     │  提交指令    │     │  文字梳理    │     │  (OpenCode) │
└─────────────┘     └─────────────┘     └──────┬──────┘     └──────┬──────┘
                                                │                    │
                                                ▼                    ▼
                                         ┌─────────────┐     ┌─────────────┐
                                         │  写入 MD    │◀────│  返回结果    │
                                         │  文档       │     │             │
                                         └─────────────┘     └─────────────┘
```

---

## 2. 功能详设

### 2.1 Agent A (AutoGen)

- **技术栈**: AutoGen + Python
- **职责**:
  1. 接收用户原始指令
  2. 对指令进行简单文字梳理（去噪、格式化）
  3. 调用 Agent B (OpenCode HTTP API)
  4. 接收 B 的返回结果
  5. 将结果追加写入 MD 文档

### 2.2 Agent B (OpenCode)

- **技术栈**: OpenCode HTTP Server
- **部署方式**: 启动 `opencode serve --port 4096`
- **接口调用**:
  - 创建 Session: `POST /session`
  - 发送消息: `POST /session/:id/message`
  - 获取结果: `GET /session/:id/message`

### 2.3 MD 文档写入

- **文件位置**: `multi-agent/logs/conversation.md`
- **写入模式**: 追加写入 (append)
- **文档格式**:

```markdown
# 对话记录

## 2026-02-21 10:30:00

### 用户指令
帮我查一下有几个 git 仓库

### Agent A 梳理后
请查询当前目录下的 git 仓库数量

### Agent B 返回
有 6 个 git 仓库：
- /root
- /root/.openclaw/workspace
- /root/ai-factory
- /root/.trae-cn-server/ai-agent/snapshot/xxx/v2 (x3)

### 执行时间
10:30:00 - 10:30:15 (15秒)
```

### 2.4 问答页面

- **技术栈**: Flask / FastAPI + HTML
- **功能**:
  - 文本输入框
  - 提交按钮
  - 结果展示区
- **页面路径**: `/`

---

## 3. 技术架构

### 3.1 组件关系

```
┌─────────────────────────────────────────────────────────────────┐
│                        问答页面 (Web)                            │
│                    http://localhost:5000                        │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Flask Server                                │
│                  (Agent A 控制器)                                │
│  - / (首页)                                                     │
│  - /api/chat (POST)                                            │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                ┌──────────┴──────────┐
                │                     │
                ▼                     ▼
┌──────────────────────┐   ┌──────────────────────┐
│   AutoGen Agent A    │   │   MD 文件写入        │
│   - 文字梳理          │   │   logs/conversation.md│
│   - 调用 OpenCode    │   │   (追加模式)          │
└──────────┬───────────┘   └──────────────────────┘
           │
           │ HTTP POST
           ▼
┌──────────────────────────────────────────────────────────────────┐
│                    OpenCode Server                               │
│                http://localhost:4096                            │
│  - POST /session/:id/message                                     │
│  - GET /session/:id/message                                      │
└──────────────────────────────────────────────────────────────────┘
```

### 3.2 目录结构

```
multi-agent/
├── app.py                    # Flask 主应用
├── agent_a.py                # AutoGen Agent A 定义
├── opencode_client.py        # OpenCode HTTP 客户端
├── md_writer.py              # MD 文档写入模块
├── logs/
│   └── conversation.md       # 对话记录
├── templates/
│   └── index.html            # 问答页面
├── requirements.txt          # 依赖
└── README.md                 # 使用说明
```

---

## 4. 接口定义

### 4.1 问答页面 API

**请求**
```http
POST /api/chat
Content-Type: application/json

{
  "message": "用户输入的指令"
}
```

**响应**
```json
{
  "success": true,
  "session_id": "xxx",
  "result": "Agent B 返回的结果",
  "timestamp": "2026-02-21 10:30:00"
}
```

---

## 5. MVP 里程碑

| 阶段 | 任务 | 状态 |
|------|------|------|
| M1 | 启动 OpenCode Server | - |
| M2 | 实现 OpenCode HTTP 客户端 | - |
| M3 | 实现 Agent A (AutoGen) | - |
| M4 | 实现 MD 文档写入 | - |
| M5 | 实现问答页面 | - |
| M6 | 联调测试 | - |

---

## 6. 待确认事项

- [ ] OpenCode Server 是否已配置认证？
- [ ] Agent A 需要使用哪个 LLM 提供商？
- [ ] MD 文档是否需要定期清理？

---

## 7. 附录

### 7.1 OpenCode API 关键端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /session | 创建新 session |
| POST | /session/:id/message | 发送消息 |
| GET | /session/:id/message | 获取消息列表 |
| GET | /session | 列出所有 session |

### 7.2 依赖

```
flask
pyautogen
requests
sseclient-py (可选)
```
