# 向量化实现归档

**归档时间**: 2026-02-17
**归档原因**: 已迁移到统一向量化策略模式
**新架构**: `ai_factory/vectorization/`

---

## 归档文件说明

### vectorize_entries_with_dashscope.py
- **原用途**: DashScope API 向量化实现
- **功能**: 批量向量化 entries 表，写入 entry_embeddings
- **状态**: ✅ 已迁移到策略模式 (`ai_factory/vectorization/__init__.py`)
- **新用法**:
  ```python
  from ai_factory.vectorization import get_strategy
  strategy = get_strategy()  # 默认 DashScope
  embedding = strategy.embed("文本")
  ```

### vectorize_entries_with_ollama.py
- **原用途**: Ollama 本地向量化实现
- **功能**: 使用本地 Ollama 服务生成向量
- **状态**: ✅ 已迁移到策略模式 (`ai_factory/vectorization/__init__.py`)
- **新用法**:
  ```python
  from ai_factory.vectorization import get_strategy, VectorizationBackend
  strategy = get_strategy(VectorizationBackend.OLLAMA)
  embedding = strategy.embed("文本")
  ```

### vectorize_entries_with_deepseek.py
- **原用途**: DeepSeek API 向量化实现
- **功能**: 使用 DeepSeek API 生成向量（实际上使用的是 OpenAI 兼容接口）
- **状态**: ⚠️ 未完全迁移（DeepSeek 策略尚未实现）
- **注意**: 如果需要使用，请使用 DashScope 策略替代，或实现 DeepSeekStrategy

---

## 架构变更说明

### 旧架构问题
1. **代码重复**: 3个文件都有 `_build_embedding_text()`, `upsert_embedding()` 等重复函数
2. **接口不统一**: 每个文件有自己的调用方式
3. **维护困难**: 修改一个功能需要改3个地方

### 新架构优势
1. **统一接口**: `VectorizationStrategy` 抽象基类定义标准接口
2. **策略模式**: 通过 `get_strategy()` 获取具体实现，可配置切换
3. **代码复用**: 通用逻辑（如文本构建、向量保存）在基类中实现
4. **易于扩展**: 新增后端只需实现 `VectorizationStrategy` 接口

### 迁移指南

**向量化文本**:
```python
# 旧方式
from ai_factory.vectorize_entries_with_dashscope import build_embedding_text
text = build_embedding_text(entry)

# 新方式
from ai_factory.vectorization import get_strategy
strategy = get_strategy()
text = strategy.build_text(entry)
```

**生成向量**:
```python
# 旧方式
from ai_factory.vectorize_entries_with_dashscope import generate_embedding
embedding = generate_embedding(text)

# 新方式
from ai_factory.vectorization import generate_embedding
embedding = generate_embedding(text)  # 向后兼容

# 或
from ai_factory.vectorization import get_strategy
strategy = get_strategy()
embedding = strategy.embed(text)
```

**保存向量**:
```python
# 旧方式
from ai_factory.vectorize_entries_with_dashscope import upsert_embedding
upsert_embedding(entry_id, embedding)

# 新方式
from ai_factory.vectorization import get_strategy
strategy = get_strategy()
strategy.save_embedding(entry_id, embedding)

# 或一键处理
strategy.process_entry(entry)  # 构建文本 → 生成向量 → 保存
```

---

## 保留的函数

以下函数因涉及标题/摘要生成（非向量化），仍保留在原模块：
- `generate_title_with_ollama()` - 使用 Ollama 生成标题
- `generate_summary_with_ollama()` - 使用 Ollama 生成摘要

这些函数后续会迁移到独立的 LLM 策略模式。

---

## 回退说明

如需要回退到旧实现：
1. 从本目录复制文件回原位置
2. 更新导入语句
3. 注意：旧实现存在代码重复和维护问题，建议优先修复新架构

---

**维护者**: PM-agent Team  
**最后更新**: 2026-02-17
