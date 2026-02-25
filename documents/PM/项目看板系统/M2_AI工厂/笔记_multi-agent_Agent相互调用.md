# multi-agent 笔记：Agent相互调用

> **主题**: Agent A 与 Agent B 交互机制  
> **来源**: `/root/ai-factory/documents/PM/multi-agent/`  
> **日期**: 2026-02-22

---

## 一、系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                    multi-agent 系统                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   ┌─────────────┐      ┌─────────────┐                    │
│   │  Agent A    │ ───→ │  Agent B    │                    │
│   │ (AutoGen)  │      │ (OpenCode)  │                    │
│   └─────────────┘      └─────────────┘                    │
│         │                    │                             │
│         └────────┬───────────┘                             │
│                  ▼                                         │
│           ┌─────────────┐                                   │
│           │  Web界面   │                                   │
│           │ (Flask)   │                                   │
│           └─────────────┘                                   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 二、Agent A (AutoGen)

**角色**：任务规划 + 任务分发 + 结果整合

**能力**：
- 接收用户指令
- 简单文字梳理
- 调用 Agent B 执行任务
- 整合结果返回用户

---

## 三、Agent B (OpenCode)

**角色**：任务执行

**能力**：
- 文件操作（读取、写入、搜索）
- 代码执行
- Web 信息获取

**关键发现**：
- OpenCode HTTP API 创建 session 时，工作目录由**服务器启动时决定**
- API 参数 `directory` 被忽略
- **解决方案**：使用 `cd` 指令切换目录

---

## 四、调用流程

```
1. 用户输入指令
   ↓
2. Agent A 接收指令，文字梳理
   ↓
3. Agent A 调用 OpenCode API (Agent B)
   ↓
4. Agent B 执行任务（需先用 cd 切换目录）
   ↓
5. Agent B 返回结果
   ↓
6. Agent A 整合结果，写入 logs/conversation.md
   ↓
7. 展示给用户
```

---

## 五、关键技术点

### 5.1 目录切换

```python
# 关键：创建 session 后，先执行 cd
message = "cd /root/ai-factory/documents/PM && glob *.py"

# 同一 session 内，保持目录状态
message = "读取 app.py 的内容"
```

### 5.2 Session 管理

| 方法 | 行为 |
|------|------|
| `call()` | 每次创建新 session |
| `send_message()` | 发送到指定 session（需自行管理 session_id） |

**当前问题**：每次用户输入创建全新 session，不支持多轮对话。

---

## 六、Sisyphus Agent 配置

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

---

## 七、待整合功能

- [ ] 与脑图模块 (M3) 联动：问答结果写入脑图
- [ ] Session 复用：支持多轮对话
- [ ] Agent 货架对接：从 M5 选择 Agent
- [ ] 企微集成：通过 M6 发送消息

---

## 八、相关文件

| 文件 | 说明 |
|------|------|
| `multi-agent/app.py` | Flask Web 应用 |
| `multi-agent/agent_a.py` | AutoGen Agent A |
| `multi-agent/opencode_client.py` | OpenCode HTTP 客户端 |
| `multi-agent/md_writer.py` | MD 文档写入模块 |
| `multi-agent/templates/index.html` | 问答页面 |
