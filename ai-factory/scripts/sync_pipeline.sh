#!/bin/bash
# 
# PM-agent 数据同步流水线
# 功能：自动同步 all_sessions.md → entries → entry_embeddings
# 
# 运行方式：
#   手动: ./scripts/sync_pipeline.sh
#   定时: crontab -e 添加: */15 * * * * /root/ai-factory/scripts/sync_pipeline.sh

set -e  # 遇到错误退出

cd /root/ai-factory
LOG_FILE="logs/sync_pipeline.log"
mkdir -p logs

echo "========================================" | tee -a $LOG_FILE
echo "🔄 PM-agent 数据同步流水线 - $(date)" | tee -a $LOG_FILE
echo "========================================" | tee -a $LOG_FILE

# 步骤1: 检查数据库连接
echo -e "\n📊 步骤1: 检查数据库连接..." | tee -a $LOG_FILE
python3 -c "
import sys
sys.path.insert(0, '.')
from ai_factory.db.pgvector_client import get_connection
try:
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute('SELECT COUNT(*) FROM entries;')
        count = cur.fetchone()[0]
        print(f'✅ 数据库连接正常，entries: {count}')
    conn.close()
except Exception as e:
    print(f'❌ 数据库连接失败: {e}')
    sys.exit(1)
" | tee -a $LOG_FILE

# 步骤2: 同步 all_sessions.md → entries
echo -e "\n📥 步骤2: 同步 all_sessions.md → entries..." | tee -a $LOG_FILE
python3 scripts/sync_all_sessions_to_entries.py 2>&1 | tee -a $LOG_FILE

# 步骤3: 补齐向量化（如果有未向量化的记录）
echo -e "\n🔍 步骤3: 检查并补齐向量化..." | tee -a $LOG_FILE
python3 -c "
import sys
sys.path.insert(0, '.')
from ai_factory.db.pgvector_client import get_connection
conn = get_connection()
with conn.cursor() as cur:
    cur.execute('''
        SELECT COUNT(*) 
        FROM entries e
        LEFT JOIN entry_embeddings em ON e.entry_id = em.entry_id
        WHERE em.entry_id IS NULL
    ''')
    missing = cur.fetchone()[0]
    print(f'未向量化记录: {missing}')
conn.close()
" | tee -a $LOG_FILE

# 步骤4: 如果存在未向量化的记录，运行向量化脚本
MISSING=$(python3 -c "
import sys
sys.path.insert(0, '.')
from ai_factory.db.pgvector_client import get_connection
conn = get_connection()
with conn.cursor() as cur:
    cur.execute('SELECT COUNT(*) FROM entries e LEFT JOIN entry_embeddings em ON e.entry_id = em.entry_id WHERE em.entry_id IS NULL')
    count = cur.fetchone()[0]
    print(count)
conn.close()
" 2>/dev/null)

if [ "$MISSING" -gt 0 ]; then
    echo "🔄 运行向量化补齐（$MISSING 条记录）..." | tee -a $LOG_FILE
    # 使用 DashScope 进行向量化（默认）
    python3 ai_factory/vectorize_entries_with_dashscope.py --max-batches 5 2>&1 | tee -a $LOG_FILE || true
else
    echo "✅ 所有记录都已向量化" | tee -a $LOG_FILE
fi

# 步骤5: 生成最终报告
echo -e "\n📋 步骤5: 生成同步报告..." | tee -a $LOG_FILE
python3 -c "
import sys
sys.path.insert(0, '.')
from ai_factory.db.pgvector_client import get_connection
conn = get_connection()
with conn.cursor() as cur:
    cur.execute('SELECT COUNT(*) FROM entries;')
    entries = cur.fetchone()[0]
    cur.execute('SELECT COUNT(*) FROM entry_embeddings;')
    embeddings = cur.fetchone()[0]
    cur.execute('''
        SELECT COUNT(*) FROM entries e 
        LEFT JOIN entry_embeddings em ON e.entry_id = em.entry_id 
        WHERE em.entry_id IS NULL
    ''')
    missing = cur.fetchone()[0]
    
    print('')
    print('=' * 50)
    print('📊 同步完成报告')
    print('=' * 50)
    print(f'entries 总数:      {entries}')
    print(f'已向量化:          {embeddings}')
    print(f'未向量化:          {missing}')
    print(f'向量化率:          {embeddings/entries*100:.1f}%' if entries > 0 else 'N/A')
    print('=' * 50)
conn.close()
" | tee -a $LOG_FILE

echo -e "\n✅ 同步流水线完成 - $(date)\n" | tee -a $LOG_FILE
