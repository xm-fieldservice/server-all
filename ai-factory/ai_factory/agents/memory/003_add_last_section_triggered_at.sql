-- 添加 last_section_triggered_at 字段到 chat_sessions 表
-- 用于 Section 触发的冷却时间窗控制

-- 添加 last_section_triggered_at 字段
ALTER TABLE chat_sessions
ADD COLUMN IF NOT EXISTS last_section_triggered_at TIMESTAMP WITH TIME ZONE;

-- 创建索引以提高查询性能
CREATE INDEX IF NOT EXISTS idx_chat_sessions_last_section_triggered_at
ON chat_sessions(last_section_triggered_at);

-- 添加注释
COMMENT ON COLUMN chat_sessions.last_section_triggered_at IS '最后一次触发 Section 整理的时间，用于冷却时间窗控制';
