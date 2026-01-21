#!/bin/bash
# 一键执行向量化统一方案

set -e  # 遇到错误立即退出

echo "========================================"
echo "向量化统一方案 - 一键执行脚本"
echo "========================================"

# 1. 检查 Docker 容器
echo ""
echo "[1/5] 检查 PostgreSQL 容器..."
CONTAINER_ID=$(docker ps | grep -E 'pgvector|postgres' | head -1 | awk '{print $1}')
if [ -z "$CONTAINER_ID" ]; then
    echo "ERROR: 未找到 PostgreSQL 容器"
    exit 1
fi
echo "✓ 找到容器: $CONTAINER_ID"

# 2. 重建 entry_embeddings 表
echo ""
echo "[2/5] 重建 entry_embeddings 表..."
docker exec $CONTAINER_ID psql -U rag_user -d rag_db -f /dev/stdin << 'EOF'
-- 删除旧表
DROP TABLE IF EXISTS entry_embeddings CASCADE;

-- 创建新表
CREATE TABLE entry_embeddings (
    entry_id      VARCHAR(64) PRIMARY KEY REFERENCES entries(entry_id),
    embedding     VECTOR(1536),
    created_at    TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 创建向量索引
CREATE INDEX idx_entry_embeddings_embedding ON entry_embeddings 
USING ivfflat (embedding vector_cosine_ops) 
WITH (lists = 100);

-- 创建时间索引
CREATE INDEX idx_entry_embeddings_created_at ON entry_embeddings(created_at);

-- 添加注释
COMMENT ON TABLE entry_embeddings IS '向量表，使用 DashScope text-embedding-v3 模型（1536维）';
COMMENT ON COLUMN entry_embeddings.embedding IS '1536维向量，由 DashScope text-embedding-v3 生成';
COMMENT ON INDEX idx_entry_embeddings_embedding IS 'pgvector ivfflat 索引，lists=100，适合百万级数据';
EOF

if [ $? -eq 0 ]; then
    echo "✓ entry_embeddings 表重建成功"
else
    echo "✗ entry_embeddings 表重建失败"
    exit 1
fi

# 3. 检查环境变量
echo ""
echo "[3/5] 检查 DashScope 配置..."
if [ -z "$DASHSCOPE_API_KEY" ]; then
    if [ -f "/home/ecs-assist-user/.env" ]; then
        export $(cat /home/ecs-assist-user/.env | grep -v '^#' | xargs)
        echo "✓ 已加载 /home/ecs-assist-user/.env"
    fi
fi

if [ -z "$DASHSCOPE_API_KEY" ]; then
    echo "ERROR: DASHSCOPE_API_KEY 未配置"
    echo "请在 /home/ecs-assist-user/.env 中添加："
    echo "  DASHSCOPE_API_KEY=your_api_key_here"
    exit 1
fi
echo "✓ DashScope API 配置正确"

# 4. 执行向量化
echo ""
echo "[4/5] 执行批量向量化..."
cd /home/ecs-assist-user/ai-factory

# 激活虚拟环境（如果存在）
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
    echo "✓ 已激活虚拟环境"
fi

# 执行向量化
python vectorize_entries_with_dashscope.py --batch-size 50

if [ $? -eq 0 ]; then
    echo "✓ 向量化执行成功"
else
    echo "✗ 向量化执行失败"
    exit 1
fi

# 5. 验证结果
echo ""
echo "[5/5] 验证向量化结果..."
TOTAL_ENTRIES=$(docker exec $CONTAINER_ID psql -U rag_user -d rag_db -t -c "SELECT COUNT(*) FROM entries;")
TOTAL_EMBEDDINGS=$(docker exec $CONTAINER_ID psql -U rag_user -d rag_db -t -c "SELECT COUNT(*) FROM entry_embeddings;")

echo "  entries 总数: $TOTAL_ENTRIES"
echo "  向量化数量: $TOTAL_EMBEDDINGS"

if [ "$TOTAL_EMBEDDINGS" -eq "$TOTAL_ENTRIES" ]; then
    echo "✓ 向量化覆盖率: 100%"
elif [ "$TOTAL_EMBEDDINGS" -gt 0 ]; then
    COVERAGE=$(echo "scale=2; $TOTAL_EMBEDDINGS * 100 / $TOTAL_ENTRIES" | bc)
    echo "✓ 向量化覆盖率: $COVERAGE%"
else
    echo "⚠ 向量化覆盖率: 0%"
fi

# 完成
echo ""
echo "========================================"
echo "执行完成！"
echo "========================================"
echo ""
echo "后续操作："
echo "  1. 查看详细指南: cat 向量化统一方案-执行指南.md"
echo "  2. 监控向量化覆盖率: 执行 SQL 查询"
echo "  3. 定期增量向量化: python vectorize_entries_with_dashscope.py"
echo ""
