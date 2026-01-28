-- 创建 Agent 记忆系统所需的数据库表
-- 基于 `Agent记忆系统详细设计与施工文档.md` 设计

-- 启用 pgvector 扩展（如未启用）
CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================
-- 1. qa_query_index 表（Q&A缓存表）
-- ============================================================
CREATE TABLE IF NOT EXISTS qa_query_index (
    -- 主键
    qa_id VARCHAR(64) PRIMARY KEY,

    -- 用户和助手关联
    user_id VARCHAR(64) NOT NULL,
    assistant_id VARCHAR(64),
    tenant_id VARCHAR(64),

    -- 问题信息
    normalized_question TEXT NOT NULL,
    question_embedding vector(1536),

    -- 答案关联
    answer_entry_id VARCHAR(64) NOT NULL,
    answer_type VARCHAR(32),  -- 'cached' | 'generated'

    -- 命中统计
    hit_count INTEGER NOT NULL DEFAULT 0,
    last_hit_at TIMESTAMP WITH TIME ZONE,

    -- 状态和质量
    status VARCHAR(32) NOT NULL DEFAULT 'active',  -- 'active' | 'deprecated' | 'pending_review'
    quality_score DECIMAL(3,2),

    -- 元数据
    tags VARCHAR(256)[],
    metadata_json JSONB,

    -- 时间戳
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_qa_query_index_user_id ON qa_query_index(user_id);
CREATE INDEX IF NOT EXISTS idx_qa_query_index_assistant_id ON qa_query_index(assistant_id);
CREATE INDEX IF NOT EXISTS idx_qa_query_index_tenant_id ON qa_query_index(tenant_id);
CREATE INDEX IF NOT EXISTS idx_qa_query_index_status ON qa_query_index(status);
CREATE INDEX IF NOT EXISTS idx_qa_query_index_hit_count ON qa_query_index(hit_count);
CREATE INDEX IF NOT EXISTS idx_qa_query_index_last_hit_at ON qa_query_index(last_hit_at);
CREATE INDEX IF NOT EXISTS idx_qa_query_index_question_embedding ON qa_query_index USING ivfflat (question_embedding vector_cosine_ops);

COMMENT ON TABLE qa_query_index IS 'Q&A缓存表，用于快速响应重复问题';

-- ============================================================
-- 2. 扩展 entries 表（添加记忆相关字段）
-- ============================================================

-- 检查并添加新字段（使用 IF NOT EXISTS 避免重复添加）
DO $$
BEGIN
    -- section_id
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'entries' AND column_name = 'section_id'
    ) THEN
        ALTER TABLE entries ADD COLUMN section_id VARCHAR(64);
    END IF;

    -- section_version
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'entries' AND column_name = 'section_version'
    ) THEN
        ALTER TABLE entries ADD COLUMN section_version INTEGER DEFAULT 1;
    END IF;

    -- is_latest
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'entries' AND column_name = 'is_latest'
    ) THEN
        ALTER TABLE entries ADD COLUMN is_latest BOOLEAN DEFAULT TRUE;
    END IF;

    -- agent_id
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'entries' AND column_name = 'agent_id'
    ) THEN
        ALTER TABLE entries ADD COLUMN agent_id VARCHAR(64);
    END IF;

    -- source_session_id
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'entries' AND column_name = 'source_session_id'
    ) THEN
        ALTER TABLE entries ADD COLUMN source_session_id VARCHAR(64);
    END IF;

    -- importance
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'entries' AND column_name = 'importance'
    ) THEN
        ALTER TABLE entries ADD COLUMN importance DECIMAL(3, 2) DEFAULT 1.0;
    END IF;

    -- usage_count
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'entries' AND column_name = 'usage_count'
    ) THEN
        ALTER TABLE entries ADD COLUMN usage_count INTEGER DEFAULT 0;
    END IF;

    -- last_seen_at
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'entries' AND column_name = 'last_seen_at'
    ) THEN
        ALTER TABLE entries ADD COLUMN last_seen_at TIMESTAMP WITH TIME ZONE;
    END IF;

    -- overridden_entry_ids
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'entries' AND column_name = 'overridden_entry_ids'
    ) THEN
        ALTER TABLE entries ADD COLUMN overridden_entry_ids TEXT[];
    END IF;
END $$;

-- 创建索引（使用 IF NOT EXISTS 避免重复创建）
CREATE INDEX IF NOT EXISTS idx_entries_section_id ON entries(section_id);
CREATE INDEX IF NOT EXISTS idx_entries_section_version ON entries(section_id, section_version);
CREATE INDEX IF NOT EXISTS idx_entries_is_latest ON entries(is_latest);
CREATE INDEX IF NOT EXISTS idx_entries_agent_id ON entries(agent_id);
CREATE INDEX IF NOT EXISTS idx_entries_source_session_id ON entries(source_session_id);
CREATE INDEX IF NOT EXISTS idx_entries_importance ON entries(importance);
CREATE INDEX IF NOT EXISTS idx_entries_overridden_entry_ids ON entries USING GIN (overridden_entry_ids);

-- ============================================================
-- 3. 创建外键约束（可选，仅保留与 entries 相关的约束）
-- ============================================================

-- qa_query_index.answer_entry_id -> entries
ALTER TABLE qa_query_index
ADD CONSTRAINT IF NOT EXISTS fk_qa_query_index_answer_entry_id
FOREIGN KEY (answer_entry_id) REFERENCES entries(entry_id) ON DELETE CASCADE;

-- ============================================================
-- 完成
-- ============================================================

-- 验证表创建（仅检查与 entries 直接相关的表）
SELECT
    'qa_query_index' as table_name,
    COUNT(*) as row_count
FROM qa_query_index
UNION ALL
SELECT
    'entries' as table_name,
    COUNT(*) as row_count
FROM entries;
