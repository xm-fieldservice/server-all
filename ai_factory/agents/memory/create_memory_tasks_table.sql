-- Memory0 任务队列表
-- 用于异步处理 Memory0 记忆治理任务

CREATE TABLE IF NOT EXISTS memory_tasks (
    -- 主键
    task_id VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid(),

    -- 任务信息
    entry_id VARCHAR(36) NOT NULL,           -- 要处理的 entry_id
    task_type VARCHAR(50) NOT NULL DEFAULT 'memory0_process_entry',  -- 任务类型
    payload JSONB,                            -- 任务负载（JSON 格式）

    -- 任务状态
    status VARCHAR(20) NOT NULL DEFAULT 'pending',  -- pending, processing, completed, failed, dead
    attempts INTEGER NOT NULL DEFAULT 0,            -- 尝试次数
    max_attempts INTEGER NOT NULL DEFAULT 3,        -- 最大尝试次数

    -- 时间戳
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    started_at TIMESTAMP WITH TIME ZONE,             -- 开始处理时间
    completed_at TIMESTAMP WITH TIME ZONE,           -- 完成时间
    failed_at TIMESTAMP WITH TIME ZONE,             -- 失败时间
    dead_at TIMESTAMP WITH TIME ZONE,              -- 死信时间

    -- 错误信息
    last_error TEXT,

    -- 优先级（数字越小优先级越高）
    priority INTEGER NOT NULL DEFAULT 0,

    -- 预定执行时间（用于延迟重试）
    scheduled_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Worker 信息
    worker_id VARCHAR(100),                        -- 处理任务的 Worker ID
    worker_info JSONB                              -- Worker 元信息
);

-- 创建索引
-- 用于查询待处理的任务（按优先级和预定时间排序）
CREATE INDEX IF NOT EXISTS idx_memory_tasks_pending
    ON memory_tasks (status, priority, scheduled_at)
    WHERE status = 'pending';

-- 用于查询特定 entry 的任务
CREATE INDEX IF NOT EXISTS idx_memory_tasks_entry_id
    ON memory_tasks (entry_id);

-- 用于查询特定类型的任务
CREATE INDEX IF NOT EXISTS idx_memory_tasks_task_type
    ON memory_tasks (task_type);

-- 用于清理旧任务
CREATE INDEX IF NOT EXISTS idx_memory_tasks_created_at
    ON memory_tasks (created_at);

-- 用于 Worker 查询自己的任务
CREATE INDEX IF NOT EXISTS idx_memory_tasks_worker_id
    ON memory_tasks (worker_id);

-- 用于查询死信任务
CREATE INDEX IF NOT EXISTS idx_memory_tasks_dead
    ON memory_tasks (status, dead_at)
    WHERE status = 'dead';

-- 注释
COMMENT ON TABLE memory_tasks IS 'Memory0 任务队列表，用于异步处理记忆治理任务';
COMMENT ON COLUMN memory_tasks.task_id IS '任务唯一标识';
COMMENT ON COLUMN memory_tasks.entry_id IS '要处理的 entry_id';
COMMENT ON COLUMN memory_tasks.task_type IS '任务类型（memory0_process_entry 等）';
COMMENT ON COLUMN memory_tasks.payload IS '任务负载（JSON 格式）';
COMMENT ON COLUMN memory_tasks.status IS '任务状态：pending/processing/completed/failed/dead';
COMMENT ON COLUMN memory_tasks.attempts IS '当前尝试次数';
COMMENT ON COLUMN memory_tasks.max_attempts IS '最大尝试次数';
COMMENT ON COLUMN memory_tasks.scheduled_at IS '预定执行时间（用于延迟重试）';
COMMENT ON COLUMN memory_tasks.worker_id IS '处理任务的 Worker ID';
COMMENT ON COLUMN memory_tasks.last_error IS '最后一次错误信息';
COMMENT ON COLUMN memory_tasks.priority IS '优先级（数字越小优先级越高）';

-- 创建任务状态枚举类型（可选，用于更严格的数据验证）
-- CREATE TYPE memory_task_status AS ENUM ('pending', 'processing', 'completed', 'failed', 'dead');

-- 如果使用枚举类型，修改表结构：
-- ALTER TABLE memory_tasks ALTER COLUMN status TYPE memory_task_status USING status::memory_task_status;
-- ALTER TABLE memory_tasks ALTER COLUMN status SET DEFAULT 'pending'::memory_task_status;
-- ALTER TABLE memory_tasks ALTER COLUMN status SET NOT NULL;

-- 清理旧任务的函数（可选）
CREATE OR REPLACE FUNCTION cleanup_old_memory_tasks(days_to_keep INTEGER DEFAULT 7)
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM memory_tasks
    WHERE status IN ('completed', 'failed', 'dead')
      AND created_at < NOW() - INTERVAL '1 day' * days_to_keep;

    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION cleanup_old_memory_tasks IS '清理指定天数之前的已完成/失败/死信任务';
