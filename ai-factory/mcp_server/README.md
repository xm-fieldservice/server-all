# Agent Memory Nodes Query MCP Tool
# ======================================

## 概述

这是一个基于MCP（Model Context Protocol）标准的工具，用于查询数据库中指定父节点的所有子孙节点并汇总内容。

## 功能特性

1. **递归查询**：自动获取指定父节点的所有子孙节点
2. **多种输出格式**：支持树形结构、扁平列表、主题汇总三种格式
3. **主题分类**：自动将节点按主题分类（技术方案评估、架构设计、多用户多助手、Q&A缓存、UI与数据结构、性能优化等）
4. **结构化输出**：返回JSON格式的结构化数据，便于AGENT处理

## 安装与配置

### 1. 安装MCP依赖

```bash
pip install mcp
```

### 2. 配置环境变量

确保在 `ai-factory/.env` 文件中配置了数据库连接信息：

```env
AI_PG_HOST=localhost
AI_PG_PORT=5433
AI_PG_DB=rag_db
AI_PG_USER=rag_user
AI_PG_PASSWORD=rag_password
```

## 使用方法

### 方法一：通过启动脚本启动（推荐）

```bash
cd ai-factory/mcp_server
bash start_query_nodes.sh
```

### 方法二：直接启动

```bash
cd ai-factory
python -m mcp_server.query_nodes_tool
```

## MCP工具参数

### 工具名称
`query_agent_memory_nodes`

### 输入参数

| 参数 | 类型 | 必填 | 说明 | 示例 |
|------|------|------|------|------|
| `parent_id` | string | 是 | 父节点的entry_id | `"ent_081d2034"` |
| `format` | string | 否 | 返回格式：tree(树形)、flat(扁平列表)、summary(主题汇总) | `"tree"` |
| `include_summary` | boolean | 否 | 是否包含主题汇总 | `true` |
| `max_depth` | number | 否 | 最大递归深度 | `10` |

### 输出格式

#### format='tree'（树形结构）

```json
{
  "success": true,
  "parent_node": {
    "entry_id": "ent_081d2034",
    "title": "有个性和定制记忆的agent",
    "created_at": "2026-01-11T18:28:32+00:00"
  },
  "statistics": {
    "total_descendants": 47,
    "direct_children": 11,
    "theme_distribution": {
      "技术方案评估": 3,
      "架构设计": 8,
      "多用户多助手": 3,
      "Q&A缓存机制": 6,
      "UI与数据结构": 4,
      "性能优化": 2,
      "其他": 21
    }
  },
  "nodes": [
    {
      "entry_id": "ent_ae9ecdde",
      "title": "智能助手记忆方案选择评估与建议",
      "content": "...",
      "summary_ai": "...",
      "parent_entry_id": "ent_081d2034",
      "space_type": "note",
      "scene_tags": {...},
      "created_at": "2026-01-11T18:29:11+00:00",
      "user_id": "...",
      "project_code": "...",
      "depth": 1,
      "children": [...]
    }
  ]
}
```

#### format='flat'（扁平列表）

```json
{
  "success": true,
  "nodes": [
    {
      "path": "/有个性和定制记忆的agent/智能助手记忆方案选择评估与建议",
      "entry_id": "ent_ae9ecdde",
      "title": "智能助手记忆方案选择评估与建议",
      "summary": "...",
      "created_at": "2026-01-11T18:29:11+00:00",
      "depth": 1
    },
    ...
  ]
}
```

#### format='summary'（主题汇总）

```json
{
  "success": true,
  "themes": {
    "技术方案评估": [
      {
        "entry_id": "ent_ae9ecdde",
        "title": "智能助手记忆方案选择评估与建议",
        "summary": "...",
        "created_at": "2026-01-11T18:29:11+00:00"
      },
      ...
    ],
    "架构设计": [...],
    "多用户多助手": [...],
    "Q&A缓存机制": [...],
    "UI与数据结构": [...],
    "性能优化": [...],
    "其他": [...]
  }
}
```

## 在AGENT中调用

### 示例1：查询树形结构

```
工具: query_agent_memory_nodes
参数: {
  "parent_id": "ent_081d2034",
  "format": "tree"
}
```

### 示例2：查询主题汇总

```
工具: query_agent_memory_nodes
参数: {
  "parent_id": "ent_081d2034",
  "format": "summary"
}
```

### 示例3：查询扁平列表

```
工具: query_agent_memory_nodes
参数: {
  "parent_id": "ent_081d2034",
  "format": "flat",
  "max_depth": 5
}
```

## 主题分类说明

工具会自动将节点按以下主题分类：

1. **技术方案评估**：包含"方案"、"评估"、"选择"、"建议"等关键词
2. **架构设计**：包含"架构"、"设计"、"规划"、"路径"等关键词
3. **多用户多助手**：包含"多用户"、"多助手"、"隔离"、"共享"等关键词
4. **Q&A缓存机制**：包含"q&a"、"缓存"、"问答"、"重复"等关键词
5. **UI与数据结构**：包含"ui"、"界面"、"数据结构"、"表"等关键词
6. **性能优化**：包含"性能"、"速度"、"优化"、"响应"等关键词
7. **其他**：不符合以上分类的内容

## 错误处理

### 常见错误

| 错误 | 原因 | 解决方法 |
|------|------|----------|
| 未找到父节点 | parent_id不存在 | 检查parent_id是否正确 |
| 数据库连接失败 | 环境变量未配置 | 检查.env文件中的数据库配置 |
| MCP包未安装 | 未安装mcp | 运行 `pip install mcp` |

## 文件结构

```
ai-factory/mcp_server/
├── query_nodes_tool.py      # MCP工具主实现
├── start_query_nodes.sh       # 启动脚本
└── README.md                  # 本文档
```

## 扩展开发

如需扩展此工具，可以修改 `query_nodes_tool.py` 中的 `QueryNodesTool` 类：

1. 添加新的查询方法
2. 修改主题分类逻辑（`summarize_by_theme`方法）
3. 添加新的输出格式
4. 扩展输入参数

## 注意事项

1. **递归深度限制**：默认最大递归深度为10，可根据需要调整
2. **性能考虑**：大量节点时可能影响查询性能
3. **数据库连接**：确保数据库服务器可访问
4. **权限控制**：当前工具不进行权限检查，如需控制访问权限请自行添加

## 技术支持

如有问题，请检查：
1. 环境变量是否正确配置
2. 数据库连接是否正常
3. MCP包是否正确安装
4. Python版本是否为3.8+
