# Agent记忆系统调试与使用页面

## 概述

这是一个用于调试和验证Agent记忆系统的Web界面，提供可视化的交互方式来测试记忆系统的各项功能。

## 功能特性

### 1. 会话管理
- 创建/删除会话
- 设置会话元数据（部门、Agent ID等）
- 实时显示会话列表

### 2. 消息流管理
- 实时显示用户和助手的消息
- 手动标记消息类型（笔记/问答）
- 查看话题边界标记

### 3. 话题总结
- 手动触发段落整理
- 查看自动生成的段落总结
- 编辑总结内容并提交

### 4. 检索验证
- 模拟检索功能
- 显示检索结果的相似度
- 标记检索结果准确性

### 5. 监控面板
- 实时显示系统指标
- 缓存命中率
- 搜索延迟
- 总条目数

### 6. 操作日志
- 实时显示操作日志
- 按级别过滤日志
- 导出日志功能

## 安装和启动

### 前置条件

1. Python 3.8+
2. PostgreSQL 数据库（已配置）
3. 已安装AI Factory项目依赖

### 安装依赖

```bash
# 安装FastAPI和Uvicorn
pip install fastapi uvicorn python-multipart

# 确保已安装项目依赖
pip install -r requirements.txt
```

### 启动服务

#### 方式1：直接运行

```bash
cd /home/ecs-assist-user/ai-factory
python ai_factory/web/agent_memory_api.py
```

#### 方式2：使用启动脚本

```bash
cd /home/ecs-assist-user/ai-factory
bash start_memory_debug.sh
```

### 访问页面

启动服务后，在浏览器中打开以下URL：

- **前端页面**: `file:///home/ecs-assist-user/ai-factory/ai_factory/web/agent_memory_debug.html`
- **API文档**: http://localhost:8000/docs
- **API地址**: http://localhost:8000

## 使用指南

### 创建会话

1. 点击左侧"新建"按钮
2. 输入会话标题
3. 选择部门（可选）
4. 点击"创建"

### 发送消息

1. 选择一个会话
2. 在输入框中输入消息
3. 点击"发送"按钮
4. 消息会立即显示在消息流中

### 标记消息类型

1. 在消息卡片右上角的下拉菜单中选择类型
2. 可选类型：笔记（note）、问答（qa）
3. 系统会自动记录类型变更

### 触发段落总结

1. 在一个会话中积累足够多的消息
2. 点击"触发总结"按钮
3. 系统会自动识别话题边界
4. 生成段落总结并保存到记忆库

### 检索验证

1. 在右侧检索框输入问题或关键词
2. 点击"搜索"按钮
3. 查看检索结果和相似度
4. 使用👍/👎标记结果准确性

### 查看监控指标

- 页面顶部显示实时监控指标
- 包括缓存命中率、搜索延迟、总条目数
- 指标每5秒自动更新

### 查看操作日志

- 右下角显示操作日志
- 可以按级别过滤（全部/信息/警告/错误）
- 最新日志显示在最上方

## API接口文档

### 健康检查

```http
GET /api/memory/health
```

### 创建会话

```http
POST /api/memory/sessions
Content-Type: application/json

{
  "user_id": "user_001",
  "assistant_id": "assistant_001",
  "title": "测试会话",
  "department": "AI研发部"
}
```

### 获取会话列表

```http
GET /api/memory/sessions?limit=50&offset=0
```

### 添加消息

```http
POST /api/memory/sessions/{session_id}/messages
Content-Type: application/json

{
  "role": "user",
  "content": "你好，介绍一下AI工厂",
  "agent_id": "assistant_001",
  "metadata_json": {
    "entry_type": "note"
  }
}
```

### 搜索条目

```http
GET /api/memory/entries/search?query=什么是AI工厂&top_k=5&threshold=0.7
```

### 触发段落整理

```http
POST /api/memory/sessions/{session_id}/sections/trigger
Content-Type: application/json

{
  "trigger_type": "manual"
}
```

### 获取系统指标

```http
GET /api/memory/metrics
```

## 架构设计

### 前端

- **框架**: React 18 + Babel
- **样式**: TailwindCSS + FontAwesome
- **特点**: 单文件HTML，无需构建工具

### 后端

- **框架**: FastAPI
- **数据库**: PostgreSQL + pgvector
- **特点**: RESTful API，支持异步操作

### 服务架构

```
┌─────────────────────────────────────────┐
│         前端页面 (React)                 │
└─────────────────┬───────────────────────┘
                  │ HTTP/REST
┌─────────────────▼───────────────────────┐
│         FastAPI服务                      │
├─────────────────────────────────────────┤
│  会话管理  消息管理  段落管理           │
│  条目管理  检索服务  监控指标           │
└─────────────────┬───────────────────────┘
                  │
┌─────────────────▼───────────────────────┐
│      Agent记忆系统服务层                │
├─────────────────────────────────────────┤
│  SessionService  SectionService        │
│  EntryService    VectorClient          │
│  MemoryService                        │
└─────────────────┬───────────────────────┘
                  │
┌─────────────────▼───────────────────────┐
│      PostgreSQL + pgvector              │
└─────────────────────────────────────────┘
```

## 故障排查

### 问题1：无法连接到API服务

**检查点**:
- 确认API服务已启动
- 检查端口8000是否被占用
- 查看浏览器控制台的错误信息

**解决方案**:
```bash
# 检查端口占用
lsof -i :8000

# 重启服务
python ai_factory/web/agent_memory_api.py
```

### 问题2：数据库连接失败

**检查点**:
- 确认PostgreSQL服务已启动
- 检查数据库配置（.env文件）
- 检查数据库权限

**解决方案**:
```bash
# 检查数据库连接
psql -h localhost -U postgres -d ai_factory

# 查看日志
tail -f logs/agent_memory_api.log
```

### 问题3：页面显示异常

**检查点**:
- 确认浏览器支持ES6+
- 检查CDN资源加载情况
- 清除浏览器缓存

**解决方案**:
- 使用最新版Chrome/Firefox浏览器
- 按F12打开开发者工具查看错误
- 刷新页面或清除缓存

## 性能优化建议

### 前端优化

1. **懒加载**: 大量消息时使用虚拟滚动
2. **缓存**: 缓存会话列表和消息数据
3. **防抖**: 搜索输入使用防抖处理
4. **代码分割**: 按需加载React组件

### 后端优化

1. **连接池**: 配置数据库连接池
2. **异步处理**: 使用async/await处理IO操作
3. **批量操作**: 批量查询和插入数据
4. **缓存**: 使用Redis缓存热点数据

### 数据库优化

1. **索引**: 为常用查询字段创建索引
2. **分区**: 按时间分区历史数据
3. **清理**: 定期清理过期数据
4. **监控**: 监控查询性能和慢查询

## 扩展功能

### 计划中的功能

1. **话题可视化**: 使用图表展示话题切换
2. **记忆图谱**: 可视化条目之间的关联
3. **导出功能**: 导出会话和条目数据
4. **多租户支持**: 支持多个用户的独立空间
5. **实时协作**: 多人同时调试和标注

### 自定义开发

前端代码结构清晰，易于扩展：

```javascript
// 添加新组件
const NewComponent = ({ data }) => {
    return <div>...</div>
};

// 在主应用中使用
const App = () => {
    return (
        <div>
            <NewComponent data={...} />
        </div>
    );
};
```

后端添加新接口：

```python
@app.get("/api/memory/your-endpoint")
async def your_endpoint(param: str):
    # 实现逻辑
    return {"result": "success"}
```

## 支持和反馈

如有问题或建议，请联系开发团队。

**文档版本**: 1.0.0  
**最后更新**: 2026-01-18  
**系统状态**: ✅ 生产就绪
