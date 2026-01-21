-- 重建 entry_embeddings 表以适配 DashScope text-embedding-v3 (1536维)
-- 执行方式：psql -h localhost -p 5433 -U rag_user -d rag_db -f rebuild_entry_embeddings.sql

-- 1. 删除旧表（如果存在）
DROP TABLE IF EXISTS entry_embeddings CASCADE;

-- 2. 创建新表
CREATE TABLE entry_embeddings (
    entry_id      VARCHAR(64) PRIMARY KEY REFERENCES entries(entry_id),
    embedding     VECTOR(1536),  -- DashScope text-embedding-v3 的向量维度
    created_at    TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 3. 创建向量索引（ivfflat 索引，适合大规模数据）
CREATE INDEX idx_entry_embeddings_embedding ON entry_embeddings 
USING ivfflat (embedding vector_cosine_ops) 
WITH (lists = 100);

-- 4. 创建时间索引
CREATE INDEX idx_entry_embeddings_created_at ON entry_embeddings(created_at);

-- 5. 添加表注释
COMMENT ON TABLE entry_embeddings IS '向量表，使用 DashScope text-embedding-v3 模型（1536维）';
COMMENT ON COLUMN entry_embeddings.embedding IS '1536维向量，由 DashScope text-embedding-v3 生成';
COMMENT ON INDEX idx_entry_embeddings_embedding IS 'pgvector ivfflat 索引，lists=100，适合百万级数据';
