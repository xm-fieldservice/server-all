-- 001_add_scene_tags_to_entries.sql
-- 说明：为 AI 工厂的 entries 表新增 scene_tags 字段，用于支持场景标签查询。
-- 注意：请在连接到 AI 工厂使用的目标数据库后执行本脚本。

ALTER TABLE entries
ADD COLUMN IF NOT EXISTS scene_tags jsonb DEFAULT '{}'::jsonb;

-- 如需去掉默认值，可在确认新数据写入逻辑稳定后执行：
-- ALTER TABLE entries
-- ALTER COLUMN scene_tags DROP DEFAULT;
