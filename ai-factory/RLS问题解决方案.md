# PostgreSQL RLS 配置问题解决方案

## 问题描述

在使用数据库版API时遇到错误：
```
unrecognized configuration parameter "app.current_user_id"
```

这是因为PostgreSQL的Row Level Security (RLS)策略使用了自定义参数，但数据库未授权普通用户设置这些参数。

## 技术背景

### RLS使用的自定义参数
系统使用以下三个自定义参数进行数据隔离：
- `app.current_user_id` - 用户ID
- `app.current_agent_type` - Agent类型
- `app.current_agent_instance_id` - Agent实例ID

### 涉及的表
RLS策略已应用于以下表：
- `chat_sessions` - 会话表
- `chat_messages` - 消息表
- `chat_sections` - 段落表
- `qa_cache` - 问答缓存表

## 解决方案

### 方案1：使用超级用户连接（推荐）

**优点**：最简单，无需修改数据库或代码
**缺点**：需要知道超级用户密码

#### 步骤：

1. **修改.env配置文件**
```bash
# 编辑 /root/ai-factory/.env
AI_PG_USER=postgres  # 使用超级用户
AI_PG_PASSWORD=your_postgres_password  # 超级用户密码
```

2. **重启API服务**
```bash
cd /root/ai-factory
pkill -f "agent_memory_api.py"
nohup python3 ai_factory/web/agent_memory_api.py > /tmp/api.log 2>&1 &
```

3. **验证连接**
```bash
curl http://localhost:8001/api/memory/health
```

### 方案2：DBA授权自定义参数（生产环境推荐）

**优点**：安全，符合最小权限原则
**缺点**：需要DBA操作

#### DBA执行步骤：

以 `postgres` 超级用户登录数据库：

```sql
-- 1. 创建自定义参数（如果尚未创建）
ALTER DATABASE rag_db SET app.current_user_id TO '';
ALTER DATABASE rag_db SET app.current_agent_type TO '';
ALTER DATABASE rag_db SET app.current_agent_instance_id TO '';

-- 2. 授权给普通用户设置这些参数
-- 替换 'rag_user' 为实际的数据库用户名
ALTER USER rag_user SET app.current_user_id TO '';
ALTER USER rag_user SET app.current_agent_type TO '';
ALTER USER rag_user SET app.current_agent_instance_id TO '';

-- 3. 验证配置
\c rag_db rag_user  -- 以普通用户连接
SET app.current_user_id = 'user_001';
SET app.current_agent_type = 'assistant';
SET app.current_agent_instance_id = 'assistant_001';
SHOW app.current_user_id;  -- 应该显示 'user_001'
```

#### 或者使用SQL脚本：

创建文件 `/tmp/grant_rls_params.sql`：
```sql
-- 授权RLS参数给rag_user
GRANT ALL ON DATABASE rag_db TO rag_user;

-- 设置默认值
ALTER DATABASE rag_db SET app.current_user_id TO '';
ALTER DATABASE rag_db SET app.current_agent_type TO '';
ALTER DATABASE rag_db SET app.current_agent_instance_id TO '';

-- 授权用户设置这些参数
ALTER USER rag_user SET app.current_user_id TO '';
ALTER USER rag_user SET app.current_agent_type TO '';
ALTER USER rag_user SET app.current_agent_instance_id TO '';
```

执行：
```bash
sudo -u postgres psql -d rag_db -f /tmp/grant_rls_params.sql
```

### 方案3：修改RLS策略（灵活但复杂）

**优点**：无需修改用户权限
**缺点**：需要修改所有表的RLS策略

#### 修改RLS策略示例：

```sql
-- 修改 chat_sessions 表的策略
DROP POLICY IF EXISTS user_agent_isolation ON chat_sessions;
CREATE POLICY user_agent_isolation ON chat_sessions FOR ALL
USING (
    user_id = current_setting('app.current_user_id', true) 
    OR current_setting('app.current_user_id', true) IS NULL
    OR current_setting('app.current_user_id', true) = ''
);

-- 修改 chat_messages 表的策略
DROP POLICY IF EXISTS user_agent_isolation ON chat_messages;
CREATE POLICY user_agent_isolation ON chat_messages FOR ALL
USING (
    user_id = current_setting('app.current_user_id', true) 
    OR current_setting('app.current_user_id', true) IS NULL
    OR current_setting('app.current_user_id', true) = ''
);

-- 对其他表执行类似操作...
```

### 方案4：代码层容错（已部分实现）

**优点**：无需DBA介入
**缺点**：RLS实际上未生效，数据隔离失效

代码中已经实现了部分容错：

```python
# 在 session_service.py 中
try:
    cur.execute("SET LOCAL app.current_user_id = %s", (user_id,))
    cur.execute("SET LOCAL app.current_agent_type = %s", (agent_type or "",))
    cur.execute("SET LOCAL app.current_agent_instance_id = %s", (agent_instance_id or "",))
except Exception as e:
    # 如果设置失败，记录警告但继续执行
    logger.warning(f"Failed to set RLS parameters: {e}, continuing anyway")
```

**注意**：这种方式虽然不会报错，但RLS策略会使用NULL值，可能导致数据隔离失效。

## 快速测试脚本

使用以下脚本测试RLS配置：

```bash
cd /root/ai-factory
cat > /tmp/test_rls.py << 'EOF'
#!/usr/bin/env python3
import psycopg2
import os
from ai_factory.db.pgvector_client import _get_dsn

def test_rls():
    dsn = _get_dsn()
    print(f"DSN: {dsn}")
    
    try:
        conn = psycopg2.connect(dsn)
        cur = conn.cursor()
        
        # 尝试设置RLS参数
        print("\n测试设置RLS参数...")
        try:
            cur.execute("SET LOCAL app.current_user_id = %s", ("user_001",))
            cur.execute("SET LOCAL app.current_agent_type = %s", ("assistant",))
            cur.execute("SET LOCAL app.current_agent_instance_id = %s", ("assistant_001",))
            print("✅ 设置成功！")
        except Exception as e:
            print(f"❌ 设置失败: {e}")
            return False
        
        # 验证参数值
        print("\n验证参数值...")
        cur.execute("SHOW app.current_user_id")
        user_id = cur.fetchone()[0]
        print(f"app.current_user_id = {user_id}")
        
        cur.execute("SHOW app.current_agent_type")
        agent_type = cur.fetchone()[0]
        print(f"app.current_agent_type = {agent_type}")
        
        cur.execute("SHOW app.current_agent_instance_id")
        agent_instance_id = cur.fetchone()[0]
        print(f"app.current_agent_instance_id = {agent_instance_id}")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"连接失败: {e}")
        return False

if __name__ == "__main__":
    success = test_rls()
    print(f"\n{'='*50}")
    if success:
        print("✅ RLS配置正常，可以使用数据库版API")
    else:
        print("❌ RLS配置有问题，请使用方案1或联系DBA")
EOF

python3 /tmp/test_rls.py
```

## 推荐选择

| 场景 | 推荐方案 | 原因 |
|------|---------|------|
| 开发/测试环境 | 方案1（超级用户） | 简单快速 |
| 生产环境（有DBA） | 方案2（DBA授权） | 安全规范 |
| 生产环境（无DBA） | 方案4（代码容错） | 无需权限修改 |
| 需要灵活配置 | 方案3（修改RLS） | 策略可控 |

## 验证数据库版API

配置完成后，验证数据库版API：

```bash
# 1. 停止内存版服务
pkill -f "agent_memory_api_memory.py"

# 2. 启动数据库版服务
cd /root/ai-factory
nohup python3 ai_factory/web/agent_memory_api.py > /tmp/api.log 2>&1 &

# 3. 等待启动
sleep 3

# 4. 检查健康状态
curl http://localhost:8001/api/memory/health

# 5. 在浏览器中测试
# 打开 http://localhost:8080/agent_memory_debug.html
```

## 联系DBA的邮件模板

如果无法自行解决，可以使用以下模板联系DBA：

---
**主题**: 请求配置PostgreSQL自定义参数 - Agent记忆系统

**正文**:
Hi DBA团队，

我们的应用（Agent记忆系统）需要配置PostgreSQL自定义参数以支持Row Level Security (RLS)数据隔离。

**需求**：
- 数据库：rag_db
- 用户：rag_user（或.env中配置的用户）
- 需要配置的参数：
  * app.current_user_id
  * app.current_agent_type
  * app.current_agent_instance_id

**配置方式（任选一种）**：
1. 授予用户设置这些参数的权限（推荐）
2. 或使用超级用户连接（简单但权限较大）

请协助配置，谢谢！

附件：
- RLS问题解决方案.md（详细技术文档）
- test_rls.py（测试脚本）
---

## 总结

RLS配置问题的本质是PostgreSQL的权限控制。根据你的权限和环境，选择最适合的方案即可。对于快速验证和开发，推荐使用**方案1**；对于生产环境，推荐**方案2**配合DBA操作。
