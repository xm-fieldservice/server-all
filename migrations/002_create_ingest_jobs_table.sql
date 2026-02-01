-- 002_create_ingest_jobs_table.sql
-- 说明：为2号通道创建任务管理表，用于异步任务调度、状态追踪和幂等性去重。
-- 请在连接到 AI 工厂使用的目标数据库后执行本脚本。

CREATE TABLE IF NOT EXISTS ingest_jobs (
    job_id TEXT PRIMARY KEY,
    payload_hash TEXT UNIQUE,          -- 幂等键，用于去重
    raw_text TEXT NOT NULL,
    task_type TEXT NOT NULL,          -- 任务类型: note/rag/web
    status TEXT DEFAULT 'queued',      -- queued/running/succeeded/failed
    error_code TEXT,
    error_message TEXT,
    entry_id TEXT,                     -- 成功后写入的 entry_id（NOTE任务）
    result JSONB,                      -- 任务结果（RAG/Web任务返回的结果）
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 创建索引以优化查询
CREATE INDEX IF NOT EXISTS idx_ingest_jobs_status ON ingest_jobs(status);
CREATE INDEX IF NOT EXISTS idx_ingest_jobs_task_type ON ingest_jobs(task_type);
CREATE INDEX IF NOT EXISTS idx_ingest_jobs_created_at ON ingest_jobs(created_at DESC);

-- 添加注释
COMMENT ON TABLE ingest_jobs IS '2号通道任务管理表：记录异步任务的状态、结果和幂等性去重';
COMMENT ON COLUMN ingest_jobs.task_type IS '任务类型：note（笔记入库）/rag（RAG查询）/web（Web查询）';
COMMENT ON COLUMN ingest_jobs.payload_hash IS 'payload的SHA256 hash，用于幂等性去重';
COMMENT ON COLUMN ingest_jobs.entry_id IS '成功后写入的entry_id（仅NOTE任务）';
COMMENT ON COLUMN ingest_jobs.result IS '任务结果（JSON格式，RAG/Web任务返回的answer/citations/sources等）';
