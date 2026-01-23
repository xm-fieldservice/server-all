-- ============================================================
-- chat_sections表V3完整升级脚本
-- ============================================================
-- 版本: v3.0
-- 创建时间: 2026-01-23
-- 说明: 升级chat_sections表，添加V3四层隔离字段，保留所有原始字段
-- ============================================================

-- ============================================================
-- 1. 创建chat_sections_v3临时表（完整结构）
-- ============================================================
CREATE TABLE IF NOT EXISTS chat_sections_v3 (
    -- 主键
    section_id VARCHAR(64) PRIMARY KEY,

    -- 会话关联
    session_id VARCHAR(64) NOT NULL,

    -- 片段信息（保留原始字段）
    title VARCHAR(256),
    status VARCHAR(32) NOT NULL DEFAULT 'active',  -- 'active' | 'completed' | 'archived'
    trigger_type VARCHAR(32) NOT NULL DEFAULT 'auto',  -- 'auto' | 'manual' | 'timeout'
    message_count INTEGER NOT NULL DEFAULT 0,

    -- 摘要（保留原始字段）
    summary_content TEXT,
    summary_entry_id VARCHAR(64),

    -- 代理关联（保留原始字段）
    agent_id VARCHAR(64) NOT NULL,

    -- V3四层隔离字段（新增）
    user_id VARCHAR(64),
    agent_type VARCHAR(64),
    agent_instance_id VARCHAR(64),

    -- 元数据（V3新增）
    metadata_json JSONB,

    -- 时间戳
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP WITH TIME ZONE
);

-- ============================================================
-- 2. 迁移数据从chat_sections到chat_sections_v3
-- ============================================================
INSERT INTO chat_sections_v3 (
    section_id, session_id, title, status, trigger_type, message_count,
    summary_content, summary_entry_id, agent_id, user_id, agent_type,
    agent_instance_id, created_at, updated_at, completed_at
)
SELECT
    section_id, session_id, title,
    COALESCE(status, 'active') as status,
    COALESCE(trigger_type, 'auto') as trigger_type,
    COALESCE(message_count, 0) as message_count,
    summary_content, summary_entry_id, agent_id,
    user_id, agent_type, agent_instance_id,
    created_at, updated_at, completed_at
FROM chat_sections;

-- ============================================================
-- 3. 删除旧表，重命名新表
-- ============================================================
DROP TABLE IF EXISTS chat_sections CASCADE;
ALTER TABLE chat_sections_v3 RENAME TO chat_sections;

-- ============================================================
-- 4. 创建外键约束
-- ============================================================
-- chat_sections -> chat_sessions
ALTER TABLE chat_sections
ADD CONSTRAINT fk_chat_sections_session_id
FOREIGN KEY (session_id) REFERENCES chat_sessions(session_id) ON DELETE CASCADE;

-- chat_sections.summary_entry_id -> entries
ALTER TABLE chat_sections
ADD CONSTRAINT fk_chat_sections_summary_entry_id
FOREIGN KEY (summary_entry_id) REFERENCES entries(entry_id) ON DELETE SET NULL;

-- ============================================================
-- 5. 创建索引
-- ============================================================
-- 原始索引
CREATE INDEX IF NOT EXISTS idx_chat_sections_session_id ON chat_sections(session_id);
CREATE INDEX IF NOT EXISTS idx_chat_sections_status ON chat_sections(status);
CREATE INDEX IF NOT EXISTS idx_chat_sections_trigger_type ON chat_sections(trigger_type);
CREATE INDEX IF NOT EXISTS idx_chat_sections_agent_id ON chat_sections(agent_id);
CREATE INDEX IF NOT EXISTS idx_chat_sections_created_at ON chat_sections(created_at);
CREATE INDEX IF NOT EXISTS idx_chat_sections_completed_at ON chat_sections(completed_at);

-- V3四层隔离索引（新增）
CREATE INDEX IF NOT EXISTS idx_chat_sections_user_agent
    ON chat_sections (user_id, agent_type, agent_instance_id);

CREATE INDEX IF NOT EXISTS idx_chat_sections_agent_user
    ON chat_sections (agent_type, user_id);

CREATE INDEX IF NOT EXISTS idx_chat_sections_session_user_agent
    ON chat_sections (session_id, user_id, agent_type, agent_instance_id);

-- ============================================================
-- 6. 启用RLS行级安全（V3新增）
-- ============================================================
ALTER TABLE chat_sections ENABLE ROW LEVEL SECURITY;

-- 创建策略：用户只能访问自己的数据
CREATE POLICY user_agent_isolation ON chat_sections
    FOR ALL
    USING (
        user_id = current_setting('app.current_user_id', true) OR
        current_setting('app.current_user_id', true) IS NULL
    );

-- ============================================================
-- 7. 数据验证
-- ============================================================
SELECT
    'chat_sections' as table_name,
    COUNT(*) as total_count,
    COUNT(*) FILTER (WHERE user_id IS NOT NULL) as user_id_count,
    COUNT(*) FILTER (WHERE agent_type IS NOT NULL) as agent_type_count,
    COUNT(*) FILTER (WHERE agent_instance_id IS NOT NULL) as agent_instance_id_count,
    COUNT(*) FILTER (WHERE status IS NOT NULL) as status_count,
    COUNT(*) FILTER (WHERE trigger_type IS NOT NULL) as trigger_type_count,
    COUNT(*) FILTER (WHERE summary_content IS NOT NULL) as summary_count
FROM chat_sections;

-- ============================================================
-- 8. 升级完成
-- ============================================================
SELECT 'chat_sections表V3升级完成' as status;
