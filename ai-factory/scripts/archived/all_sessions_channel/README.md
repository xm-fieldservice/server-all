# 📦 all_sessions.md 通道脚本 - 暂时封存

> **状态**: ⏸️ 暂时封存  
> **封存日期**: 2026-02-17  
> **原因**: 数据导入策略调整，改为直接从 OpenCode SQLite/JSON 导入到 entries  
> **替代方案**: 使用 `scripts/import_project_sessions.py` (项目私域直接导入)

---

## 📋 封存脚本清单

### 核心导出脚本

| 脚本 | 原位置 | 功能 | 状态 |
|------|--------|------|------|
| **export_sessions.py** | `/root/ai-factory/` | 将 OpenCode sessions 导出到 all_sessions.md | ⏸️ 封存 |
| **sync_all_sessions_to_entries.py** | `scripts/` | 将 all_sessions.md 同步到 entries 表 | ⏸️ 封存 |
| **sync_pipeline.sh** | `scripts/` | 完整同步流水线 | ⏸️ 封存 |

### 测试数据生成

| 脚本 | 原位置 | 功能 | 状态 |
|------|--------|------|------|
| **generate_congestion_data.py** | `/root/ai-factory/` | 从 all_sessions.md 生成拥塞测试数据 | ⏸️ 封存 |
| **generate_test_data.py** | `/root/ai-factory/` | 从 all_sessions.md 生成测试数据 | ⏸️ 封存 |

### 依赖引用

以下文件依赖 export_sessions.py，但暂未封存（仍在使用）：
- `subagents/note_writer/batch_test.py` - 批量测试
- `subagents/note_writer/check_truncation.py` - 截断检查
- `subagents/note_writer/agent.py` - Note Writer Agent

**注意**: 这些 subagents 如果使用 export_sessions.py 功能，需要评估是否需要迁移或同步封存。

---

## 🔄 封存原因

### 原方案（已封存）

```
OpenCode Sessions (SQLite/JSON)
        ↓
export_sessions.py
        ↓
all_sessions.md (统一文档)
        ↓
sync_all_sessions_to_entries.py
        ↓
entries 表
        ↓
向量化
```

**问题**:
1. 中间环节多（需要维护 all_sessions.md）
2. 项目归属不明确（难以区分哪些属于哪个项目）
3. 批量导入容易出错（之前误将所有sessions导入为pm-agent数据）
4. 数据隔离弱（scene_tags标记不够严格）

### 新方案（当前使用）

```
OpenCode Sessions (SQLite/JSON)
        ↓
import_project_sessions.py (直接读取)
        ↓
自动标记项目归属（project_code, operator）
        ↓
entries 表（严格项目隔离）
        ↓
自动向量化
```

**优势**:
1. 直接读取，无中间环节
2. 项目归属明确（通过 --project 参数指定）
3. 操作者身份清晰（通过 --operator 参数指定）
4. 数据隔离严格（scene_tags.project_code）
5. 由PM/书记员主动执行，避免误操作

---

## 📖 历史背景

### 原设计意图

all_sessions.md 通道最初设计目的是：
- 创建一个**人类可读**的统一文档，便于查看所有历史会话
- 作为**中间缓冲区**，方便人工审核后再入库
- 支持**增量导出**，只导出新增的sessions

### 实际使用问题

在实际使用中发现了以下问题：
1. **维护成本高**: all_sessions.md 文件变得很大，解析困难
2. **项目归属模糊**: 难以区分哪些sessions属于哪个项目
3. **导入容易出错**: 批量导入时容易误标记项目归属（如之前误将58条记录全部标记为pm-agent）
4. **中间环节冗余**: 直接读取OpenCode SQLite比先导出到MD再解析更高效

---

## 🚀 替代方案使用指南

### 新项目导入

```bash
# 使用新方案（直接导入）
cd /root/ai-factory
python3 scripts/import_project_sessions.py \
  --project YOUR_PROJECT_CODE \
  --operator pm-agent  # 或 pm-clerk
```

### 对比

| 维度 | 旧方案（封存） | 新方案（当前） |
|------|---------------|---------------|
| 中间文件 | all_sessions.md | 无 |
| 项目标记 | 后期添加 | 导入时自动标记 |
| 执行者 | 系统脚本 | PM/书记员主动执行 |
| 数据隔离 | 弱 | 强（scene_tags.project_code） |
| 灵活性 | 低（批量） | 高（可控） |

---

## ⏰ 解封条件

以下情况可能需要解封：
1. 需要重新审查历史sessions并人工标注项目归属
2. 需要生成人类可读的统一文档供外部审查
3. 新方案出现问题，需要回退到旧方案

**解封前必须**:
1. 明确项目归属策略
2. 添加严格的项目标记验证
3. 避免批量导入导致的数据污染

---

## 📁 相关文档

- `docs/PROJECT_PRIVATE_DATA_IMPORT.md` - 新方案完整文档
- `docs/QUICK_START_IMPORT.md` - 新方案快速指南
- `documents/PM/README.md` - 项目总体说明

---

## ⚠️ 注意事项

1. **不要删除原文件**: 封存的只是副本，原文件仍在原位置（防止依赖断裂）
2. **不要修改封存脚本**: 保持封存状态，避免混淆
3. **优先使用新方案**: 所有新导入都应使用 `import_project_sessions.py`
4. **备份重要数据**: 解封前确保有数据备份

---

**封存负责人**: PM-agent Team  
**封存日期**: 2026-02-17  
**预计解封时间**: 待定（根据项目需要）
