-- 审核验证SQL脚本

-- 1. 验证表创建
\echo '=== 1. 表验证 ==='
SELECT tablename, tableowner FROM pg_tables 
WHERE schemaname='public' 
ORDER BY tablename;

-- 2. 验证entries表字段
\echo ''
\echo '=== 2. entries表字段验证 ==='
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'entries' 
  AND column_name IN ('agent_type', 'agent_instance_id', 'user_id', 'title', 'summary_ai', 'content', 'scene_tags', 'extra_meta')
ORDER BY column_name;

-- 3. 验证索引
\echo ''
\echo '=== 3. 索引验证 ==='
SELECT schemaname, tablename, indexname 
FROM pg_indexes 
WHERE schemaname='public' 
  AND (indexname LIKE '%agent%' OR indexname LIKE '%user%' OR indexname LIKE '%scene%')
ORDER BY tablename, indexname;

-- 4. 验证RLS状态
\echo ''
\echo '=== 4. RLS状态验证 ==='
SELECT tablename, rowsecurity 
FROM pg_tables 
WHERE schemaname='public' 
ORDER BY tablename;

-- 5. 验证RLS策略
\echo ''
\echo '=== 5. RLS策略验证 ==='
SELECT schemaname, tablename, policyname, cmd, qual 
FROM pg_policies 
WHERE schemaname='public';
