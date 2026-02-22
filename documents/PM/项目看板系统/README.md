# 项目看板系统 - 需求管理

> **创建日期**: 2026-02-22  
> **状态**: 需求采集阶段

---

## 一、项目概述

项目看板系统是**双循环管理体系的唯一结合点**，定位为大一统的需求到开发全流程追踪系统。

### 核心定位

- **系统边界**: 大一统系统（战略→目标→规划→计划→项目→任务→笔记→日程→议题）
- **向上承接**: 双向关联（项目可关联战略/目标/计划，双向追溯）
- **向下支撑**: 内置子系统（任务/笔记/日程/议题内置）
- **核心价值**: 可视化追踪 > 协作执行 > 知识沉淀

---

## 二、文档索引

| 文档 | 说明 |
|------|------|
| [00_总纲.md](./00_总纲.md) | 系统总纲，模块索引 |
| [M1_数据层.md](./M1_数据层.md) | 数据层详细需求 |
| [M3_大循环脑图.md](./模块详情_M3_脑图模块_v1.0.md) | 脑图模块详细需求 |

---

## 三、模块清单

| 编号 | 模块名称 | 层级 | 状态 | 说明 |
|------|----------|------|------|------|
| M1 | 数据层 | 基础设施 | **已采集** | entries 数据库 + pgvector 向量索引 |
| M2 | AI工厂 | 基础设施 | 规划中 | AutoGen + LangGraph + 向量库 |
| M3 | 大循环脑图 | 核心业务 | **已采集** | 展示器+编辑器+推理可视化 |
| M4 | 项目管理框架 | 核心业务 | **已采集** | 双循环中枢 + PM六大职责 + Agent对齐 |
| M5 | Agent货架管理 | 核心业务 | 规划中 | 工厂化组装与管理 |
| M6 | 企业微信集成 | 用户集成 | 规划中 | 用户管理+终端+聊天+自建应用 |
| M7 | 关系管理 | 核心业务 | 规划中 | 高维-低维一体化关联管理 |
| M8 | 个人档案管理 | 用户服务 | 规划中 | 个人行为解读与发展档案 |

---

## 四、Neo4j 关系图谱

### 4.1 部署信息

| 项目 | 值 |
|------|------|
| **部署方式** | Docker容器 |
| **容器名称** | neo4j_requirements |
| **镜像版本** | neo4j:latest (2026.01.4) |

### 4.2 访问信息

| 项目 | 值 |
|------|------|
| **Web界面** | http://localhost:7475 |
| **Bolt端口** | bolt://localhost:7688 |
| **用户名** | neo4j |
| **密码** | requirements123 |

### 4.3 数据目录

| 目录 | 宿主机路径 | 容器路径 |
|------|------------|----------|
| 数据存储 | /root/ai-factory/data/neo4j/data | /data |
| 日志 | /root/ai-factory/data/neo4j/logs | /logs |
| 导入 | /root/ai-factory/data/neo4j/import | /var/lib/neo4j/import |
| 插件 | /root/ai-factory/data/neo4j/plugins | /plugins |

### 4.4 管理命令

```bash
# 启动容器
docker start neo4j_requirements

# 停止容器
docker stop neo4j_requirements

# 查看日志
docker logs neo4j_requirements

# 进入容器
docker exec -it neo4j_requirements bash

# 重启容器
docker restart neo4j_requirements

# 删除容器（数据保留在挂载目录）
docker rm -f neo4j_requirements
```

### 4.5 图谱统计

| 类型 | 数量 |
|------|------|
| 系统节点 | 1 |
| 模块节点 | 8 |
| CONTAINS 关系 | 8 |
| DEPENDS_ON 关系 | 4 |
| USES 关系 | 3 |
| INTEGRATES_WITH 关系 | 2 |

### 4.6 常用查询

```cypher
// 查看完整图谱
MATCH (s:System)-[:CONTAINS]->(m:Module) 
OPTIONAL MATCH (m)-[r:DEPENDS_ON|USES|INTEGRATES_WITH]->(target:Module)
RETURN s, m, r, target

// 查找被依赖最多的模块
MATCH (m:Module)<-[r:DEPENDS_ON|USES]-() 
RETURN m.id, m.name, count(r) as importance 
ORDER BY importance DESC

// 查找依赖链
MATCH path = (m1:Module)-[:DEPENDS_ON|USES*1..3]->(m2:Module) 
RETURN m1.id, length(path), m2.id

// 查找孤立节点（无依赖关系）
MATCH (m:Module) 
WHERE NOT (m)-[:DEPENDS_ON|USES]->() AND NOT (m)<-[:DEPENDS_ON|USES]-() 
RETURN m
```

---

## 五、开发优先级建议

基于图谱依赖分析：

| 优先级 | 模块 | 理由 |
|--------|------|------|
| **P1** | M2 AI工厂 | 被依赖最多（3个模块），解锁下游模块 |
| **P2** | M1 数据层 | 已有基础，M3和M6依赖 |
| **P3** | M3 脑图 | 核心视图，依赖M1/M2/M7 |

---

## 六、更新日志

| 日期 | 更新内容 |
|------|----------|
| 2026-02-22 | 创建项目结构，完成M3脑图模块采集 |
| 2026-02-22 | 部署Neo4j图谱，导入模块节点和关系 |
| 2026-02-22 | 完成M1数据层模块需求采集 |
| 2026-02-22 | 完成M4项目管理框架需求采集（整合现有PM文档） |
