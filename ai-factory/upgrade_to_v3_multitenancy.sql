-- ============================================================
-- V3多租户架构数据库升级脚本
-- ============================================================
-- 版本: v1.0
-- 创建时间: 2026-01-23
-- 说明: 将现有记忆系统升级到V3多租户架构
-- 功能:
--   1. 添加四层隔离字段（user_id, agent_type, agent_instance_id）
--   2. 创建四层隔离索引
--   3. 启用RLS行级安全
--   4. 数据迁移和验证
-- ============================================================

-- ============================================================
-- 0. 升级前检查
-- ============================================================
DO $$
BEGIN
    RAISE NOTICE '========================================';
    RAISE NOTICE 'V3多租户架构升级脚本开始执行';
    RAISE NOTICE '执行时间: %', NOW();
    RAISE NOTICE '========================================';
END $$;

-- ============================================================
-- 1. 升级 chat_sessions 表
-- ============================================================
DO $$
BEGIN
    -- 添加 agent_type 字段
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'chat_sessions' AND column_name = 'agent_type'
    ) THEN
        ALTER TABLE chat_sessions ADD COLUMN agent_type VARCHAR(64);
        RAISE NOTICE '[chat_sessions] 添加 agent_type 字段';
    ELSE
        RAISE NOTICE '[chat_sessions] agent_type 字段已存在，跳过';
    END IF;

    -- 添加 agent_instance_id 字段
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'chat_sessions' AND column_name = 'agent_instance_id'
    ) THEN
        ALTER TABLE chat_sessions ADD COLUMN agent_instance_id VARCHAR(64);
        RAISE NOTICE '[chat_sessions] 添加 agent_instance_id 字段';
    ELSE
        RAISE NOTICE '[chat_sessions] agent_instance_id 字段已存在，跳过';
    END IF;

    -- 迁移数据：如果 agent_type 为空，尝试从 assistant_id 推断
    UPDATE chat_sessions
    SET agent_type = assistant_id
    WHERE agent_type IS NULL AND assistant_id IS NOT NULL;

    RAISE NOTICE '[chat_sessions] 数据迁移完成（agent_type）';
END $$;

-- 创建复合索引
CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_agent
    ON chat_sessions (user_id, agent_type, agent_instance_id);

CREATE INDEX IF NOT EXISTS idx_chat_sessions_agent_user
    ON chat_sessions (agent_type, user_id);

RAISE NOTICE '[chat_sessions] 索引创建完成';

-- ============================================================
-- 2. 升级 chat_sections 表
-- ============================================================
DO $$
BEGIN
    -- 添加 user_id 字段（从关联的 session 获取）
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'chat_sections' AND column_name = 'user_id'
    ) THEN
        ALTER TABLE chat_sections ADD COLUMN user_id VARCHAR(64);
        RAISE NOTICE '[chat_sections] 添加 user_id 字段';
    ELSE
        RAISE NOTICE '[chat_sections] user_id 字段已存在，跳过';
    END IF;

    -- 添加 agent_type 字段
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'chat_sections' AND column_name = 'agent_type'
    ) THEN
        ALTER TABLE chat_sections ADD COLUMN agent_type VARCHAR(64);
        RAISE NOTICE '[chat_sections] 添加 agent_type 字段';
    ELSE
        RAISE NOTICE '[chat_sections] agent_type 字段已存在，跳过';
    END IF;

    -- 添加 agent_instance_id 字段
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'chat_sections' AND column_name = 'agent_instance_id'
    ) THEN
        ALTER TABLE chat_sections ADD COLUMN agent_instance_id VARCHAR(64);
        RAISE NOTICE '[chat_sections] 添加 agent_instance_id 字段';
    ELSE
        RAISE NOTICE '[chat_sections] agent_instance_id 字段已存在，跳过';
    END IF;

    -- 迁移数据：从关联的 chat_sessions 表填充 user_id, agent_type, agent_instance_id
    UPDATE chat_sections cs
    SET
        user_id = s.user_id,
        agent_type = COALESCE(s.agent_type, s.assistant_id),
        agent_instance_id = s.agent_instance_id
    FROM chat_sessions s
    WHERE cs.session_id = s.session_id
      AND (cs.user_id IS NULL OR cs.agent_type IS NULL OR cs.agent_instance_id IS NULL);

    RAISE NOTICE '[chat_sections] 数据迁移完成';
END $$;

-- 创建复合索引
CREATE INDEX IF NOT EXISTS idx_chat_sections_user_agent
    ON chat_sections (user_id, agent_type, agent_instance_id);

CREATE INDEX IF NOT EXISTS idx_chat_sections_agent_user
    ON chat_sections (agent_type, user_id);

RAISE NOTICE '[chat_sections] 索引创建完成';

-- ============================================================
-- 3. 升级 qa_query_index 表
-- ============================================================
DO $$
BEGIN
    -- 添加 agent_type 字段
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'qa_query_index' AND column_name = 'agent_type'
    ) THEN
        ALTER TABLE qa_query_index ADD COLUMN agent_type VARCHAR(64);
        RAISE NOTICE '[qa_query_index] 添加 agent_type 字段';
    ELSE
        RAISE NOTICE '[qa_query_index] agent_type 字段已存在，跳过';
    END IF;

    -- 添加 agent_instance_id 字段
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'qa_query_index' AND column_name = 'agent_instance_id'
    ) THEN
        ALTER TABLE qa_query_index ADD COLUMN agent_instance_id VARCHAR(64);
        RAISE NOTICE '[qa_query_index] 添加 agent_instance_id 字段';
    ELSE
        RAISE NOTICE '[qa_query_index] agent_instance_id 字段已存在，跳过';
    END IF;

    -- 迁移数据：如果 agent_type 为空，尝试从 assistant_id 推断
    UPDATE qa_query_index
    SET agent_type = assistant_id
    WHERE agent_type IS NULL AND assistant_id IS NOT NULL;

    RAISE NOTICE '[qa_query_index] 数据迁移完成（agent_type）';
END $$;

-- 创建复合索引
CREATE INDEX IF NOT EXISTS idx_qa_query_index_user_agent
    ON qa_query_index (user_id, agent_type, agent_instance_id);

CREATE INDEX IF NOT EXISTS idx_qa_query_index_agent_user
    ON qa_query_index (agent_type, user_id);

RAISE NOTICE '[qa_query_index] 索引创建完成';

-- ============================================================
-- 4. 升级 entries 表（添加 Knowledge Node 四级结构字段）
-- ============================================================
DO $$
BEGIN
    -- 四层数据隔离字段（V3新增）
    -- ==========================================

    -- user_id（四层隔离 - 第1层）
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'entries' AND column_name = 'user_id'
    ) THEN
        ALTER TABLE entries ADD COLUMN user_id VARCHAR(64);
        RAISE NOTICE '[entries] 添加 user_id 字段（四层隔离 - 第1层）';
    ELSE
        RAISE NOTICE '[entries] user_id 字段已存在，跳过';
    END IF;

    -- agent_type（四层隔离 - 第2层）
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'entries' AND column_name = 'agent_type'
    ) THEN
        ALTER TABLE entries ADD COLUMN agent_type VARCHAR(64);
        RAISE NOTICE '[entries] 添加 agent_type 字段（四层隔离 - 第2层）';
    ELSE
        RAISE NOTICE '[entries] agent_type 字段已存在，跳过';
    END IF;

    -- agent_instance_id（四层隔离 - 第3层）
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'entries' AND column_name = 'agent_instance_id'
    ) THEN
        ALTER TABLE entries ADD COLUMN agent_instance_id VARCHAR(64);
        RAISE NOTICE '[entries] 添加 agent_instance_id 字段（四层隔离 - 第3层）';
    ELSE
        RAISE NOTICE '[entries] agent_instance_id 字段已存在，跳过';
    END IF;

    -- Knowledge Node 四级结构字段（V3新增）
    -- ==========================================

    -- Level 1: Title（身份标识）
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'entries' AND column_name = 'title'
    ) THEN
        ALTER TABLE entries ADD COLUMN title TEXT NOT NULL DEFAULT '';
        RAISE NOTICE '[entries] 添加 title 字段（Level 1: 身份标识）';
    ELSE
        RAISE NOTICE '[entries] title 字段已存在，跳过';
    END IF;

    -- Level 2: Summary（核心语义，参与向量搜索）
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'entries' AND column_name = 'summary_ai'
    ) THEN
        ALTER TABLE entries ADD COLUMN summary_ai TEXT;
        RAISE NOTICE '[entries] 添加 summary_ai 字段（Level 2: 核心语义）';
    ELSE
        RAISE NOTICE '[entries] summary_ai 字段已存在，跳过';
    END IF;

    -- Level 3: Content（事实依据）
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'entries' AND column_name = 'content'
    ) THEN
        ALTER TABLE entries ADD COLUMN content TEXT;
        RAISE NOTICE '[entries] 添加 content 字段（Level 3: 事实依据）';
    ELSE
        RAISE NOTICE '[entries] content 字段已存在，跳过';
    END IF;

    -- Level 4: Metadata（分类与维度）
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'entries' AND column_name = 'scene_tags'
    ) THEN
        ALTER TABLE entries ADD COLUMN scene_tags JSONB;
        RAISE NOTICE '[entries] 添加 scene_tags 字段（Level 4: 场景标签）';
    ELSE
        RAISE NOTICE '[entries] scene_tags 字段已存在，跳过';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'entries' AND column_name = 'extra_meta'
    ) THEN
        ALTER TABLE entries ADD COLUMN extra_meta JSONB;
        RAISE NOTICE '[entries] 添加 extra_meta 字段（Level 4: 附加元数据）';
    ELSE
        RAISE NOTICE '[entries] extra_meta 字段已存在，跳过';
    END IF;

    -- 分类和关联字段
    -- ==========================================

    -- space_type（空间类型：goal/strategy/plan/project/task/topic/note）
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'entries' AND column_name = 'space_type'
    ) THEN
        ALTER TABLE entries ADD COLUMN space_type TEXT;
        RAISE NOTICE '[entries] 添加 space_type 字段（空间类型）';
    ELSE
        RAISE NOTICE '[entries] space_type 字段已存在，跳过';
    END IF;

    -- project_code（项目代码）
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'entries' AND column_name = 'project_code'
    ) THEN
        ALTER TABLE entries ADD COLUMN project_code TEXT;
        RAISE NOTICE '[entries] 添加 project_code 字段（项目代码）';
    ELSE
        RAISE NOTICE '[entries] project_code 字段已存在，跳过';
    END IF;

    -- parent_entry_id（树形结构）
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'entries' AND column_name = 'parent_entry_id'
    ) THEN
        ALTER TABLE entries ADD COLUMN parent_entry_id TEXT REFERENCES entries(entry_id);
        RAISE NOTICE '[entries] 添加 parent_entry_id 字段（树形结构）';
    ELSE
        RAISE NOTICE '[entries] parent_entry_id 字段已存在，跳过';
    END IF;

    -- 删除冗余字段 project_hint（已迁移到 extra_meta）
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'entries' AND column_name = 'project_hint'
    ) THEN
        -- 如果有数据，先迁移到 extra_meta
        UPDATE entries
        SET extra_meta = jsonb_set(
            COALESCE(extra_meta, '{}'::jsonb),
            '{project_hint}',
            to_jsonb(project_hint)
        )
        WHERE project_hint IS NOT NULL;

        -- 删除旧字段
        ALTER TABLE entries DROP COLUMN project_hint;
        RAISE NOTICE '[entries] 删除 project_hint 字段（已迁移到 extra_meta）';
    ELSE
        RAISE NOTICE '[entries] project_hint 字段不存在，跳过';
    END IF;

    -- 数据迁移：从 chat_sections 填充四层隔离字段
    UPDATE entries e
    SET
        user_id = cs.user_id,
        agent_type = COALESCE(cs.agent_type, cs.agent_id),
        agent_instance_id = cs.agent_instance_id
    FROM chat_sections cs
    WHERE e.section_id = cs.section_id
      AND (e.user_id IS NULL OR e.agent_type IS NULL OR e.agent_instance_id IS NULL);

    -- 如果 entries 中还有 agent_id 字段，也尝试填充
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'entries' AND column_name = 'agent_id'
    ) THEN
        UPDATE entries
        SET agent_type = COALESCE(agent_type, agent_id)
        WHERE agent_id IS NOT NULL;
    END IF;

    RAISE NOTICE '[entries] 数据迁移完成';
END $$;

-- 创建四层隔离索引（V3新增）
CREATE INDEX IF NOT EXISTS idx_entries_user_agent
    ON entries (user_id, agent_type, agent_instance_id);

CREATE INDEX IF NOT EXISTS idx_entries_agent_type_user
    ON entries (agent_type, user_id);

CREATE INDEX IF NOT EXISTS idx_entries_section_user_agent
    ON entries (section_id, user_id, agent_type, agent_instance_id);

-- 创建 Knowledge Node 四级结构索引（V3新增）
CREATE INDEX IF NOT EXISTS idx_entries_scene_tags
    ON entries USING GIN (scene_tags);

CREATE INDEX IF NOT EXISTS idx_entries_space_type
    ON entries (space_type, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_entries_project_code
    ON entries (project_code, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_entries_parent
    ON entries (parent_entry_id);

RAISE NOTICE '[entries] 四层隔离索引和 Knowledge Node 索引创建完成';

-- ============================================================
-- 5. 启用 RLS 行级安全（V3新增）
-- ============================================================

-- 为 entries 表启用 RLS
ALTER TABLE entries ENABLE ROW LEVEL SECURITY;

-- 创建或更新 user_agent_isolation 策略
DROP POLICY IF EXISTS user_agent_isolation ON entries;

CREATE POLICY user_agent_isolation ON entries
    FOR ALL
    USING (
        user_id = current_setting('app.current_user_id', true) OR
        current_setting('app.current_user_id', true) IS NULL
    );

RAISE NOTICE '[entries] RLS 行级安全已启用';

-- （可选）为 chat_sessions 和 chat_sections 也启用 RLS
-- ALTER TABLE chat_sessions ENABLE ROW LEVEL SECURITY;
-- CREATE POLICY user_isolation_sessions ON chat_sessions
--     FOR ALL
--     USING (user_id = current_setting('app.current_user_id', true) OR current_setting('app.current_user_id', true) IS NULL);

-- ALTER TABLE chat_sections ENABLE ROW LEVEL SECURITY;
-- CREATE POLICY user_isolation_sections ON chat_sections
--     FOR ALL
--     USING (user_id = current_setting('app.current_user_id', true) OR current_setting('app.current_user_id', true) IS NULL);

-- ============================================================
-- 6. 数据验证
-- ============================================================

-- 验证四层隔离字段
SELECT
    'chat_sessions' as table_name,
    COUNT(*) FILTER (WHERE user_id IS NOT NULL) as user_id_count,
    COUNT(*) FILTER (WHERE agent_type IS NOT NULL) as agent_type_count,
    COUNT(*) FILTER (WHERE agent_instance_id IS NOT NULL) as agent_instance_id_count
FROM chat_sessions
UNION ALL
SELECT
    'chat_sections' as table_name,
    COUNT(*) FILTER (WHERE user_id IS NOT NULL) as user_id_count,
    COUNT(*) FILTER (WHERE agent_type IS NOT NULL) as agent_type_count,
    COUNT(*) FILTER (WHERE agent_instance_id IS NOT NULL) as agent_instance_id_count
FROM chat_sections
UNION ALL
SELECT
    'qa_query_index' as table_name,
    COUNT(*) FILTER (WHERE user_id IS NOT NULL) as user_id_count,
    COUNT(*) FILTER (WHERE agent_type IS NOT NULL) as agent_type_count,
    COUNT(*) FILTER (WHERE agent_instance_id IS NOT NULL) as agent_instance_id_count
FROM qa_query_index
UNION ALL
SELECT
    'entries' as table_name,
    COUNT(*) FILTER (WHERE user_id IS NOT NULL) as user_id_count,
    COUNT(*) FILTER (WHERE agent_type IS NOT NULL) as agent_type_count,
    COUNT(*) FILTER (WHERE agent_instance_id IS NOT NULL) as agent_instance_id_count
FROM entries;

-- 验证 Knowledge Node 四级结构字段
SELECT
    'entries' as table_name,
    COUNT(*) FILTER (WHERE title IS NOT NULL) as title_count,
    COUNT(*) FILTER (WHERE summary_ai IS NOT NULL) as summary_ai_count,
    COUNT(*) FILTER (WHERE content IS NOT NULL) as content_count,
    COUNT(*) FILTER (WHERE scene_tags IS NOT NULL) as scene_tags_count,
    COUNT(*) FILTER (WHERE extra_meta IS NOT NULL) as extra_meta_count,
    COUNT(*) FILTER (WHERE space_type IS NOT NULL) as space_type_count,
    COUNT(*) FILTER (WHERE project_code IS NOT NULL) as project_code_count,
    COUNT(*) FILTER (WHERE parent_entry_id IS NOT NULL) as parent_entry_id_count
FROM entries;

-- 验证索引
SELECT
    indexname as index_name,
    'OK' as status
FROM pg_indexes
WHERE schemaname = 'public'
  AND indexname IN (
    'idx_entries_user_agent',
    'idx_entries_agent_type_user',
    'idx_entries_section_user_agent',
    'idx_entries_scene_tags',
    'idx_entries_space_type',
    'idx_entries_project_code',
    'idx_entries_parent',
    'idx_chat_sessions_user_agent',
    'idx_chat_sections_user_agent',
    'idx_qa_query_index_user_agent'
  )
ORDER BY indexname;

RAISE NOTICE '========================================';
RAISE NOTICE 'V3多租户架构升级完成';
RAISE NOTICE '请检查上述验证结果';
RAISE NOTICE '========================================';

-- ============================================================
-- 回滚脚本（谨慎使用）
-- ============================================================
-- DROP POLICY IF EXISTS user_agent_isolation ON entries;
-- ALTER TABLE entries DISABLE ROW LEVEL SECURITY;
-- DROP INDEX IF EXISTS idx_entries_user_agent;
-- DROP INDEX IF EXISTS idx_entries_agent_type_user;
-- DROP INDEX IF EXISTS idx_entries_section_user_agent;
-- ALTER TABLE entries DROP COLUMN IF EXISTS agent_instance_id;
-- ALTER TABLE entries DROP COLUMN IF EXISTS agent_type;
-- ALTER TABLE entries DROP COLUMN IF EXISTS user_id;
-- DROP INDEX IF EXISTS idx_qa_query_index_user_agent;
-- DROP INDEX IF EXISTS idx_qa_query_index_agent_user;
-- ALTER TABLE qa_query_index DROP COLUMN IF EXISTS agent_instance_id;
-- ALTER TABLE qa_query_index DROP COLUMN IF EXISTS agent_type;
-- DROP INDEX IF EXISTS idx_chat_sections_user_agent;
-- DROP INDEX IF EXISTS idx_chat_sections_agent_user;
-- ALTER TABLE chat_sections DROP COLUMN IF EXISTS agent_instance_id;
-- ALTER TABLE chat_sections DROP COLUMN IF EXISTS agent_type;
-- ALTER TABLE chat_sections DROP COLUMN IF EXISTS user_id;
-- DROP INDEX IF EXISTS idx_chat_sessions_user_agent;
-- DROP INDEX IF EXISTS idx_chat_sessions_agent_user;
-- ALTER TABLE chat_sessions DROP COLUMN IF EXISTS agent_instance_id;
-- ALTER TABLE chat_sessions DROP COLUMN IF EXISTS agent_type;
