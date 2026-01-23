#!/bin/bash
# ============================================================
# V3多租户架构快速升级脚本
# ============================================================
# 使用方法：
#   bash 快速升级指南.sh
# ============================================================

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "========================================"
echo "V3多租户架构快速升级"
echo "========================================"
echo ""

# 1. 检查依赖
echo -e "${YELLOW}1. 检查依赖...${NC}"
if ! command -v psql &> /dev/null; then
    echo -e "${RED}✗ psql 未安装${NC}"
    exit 1
fi
echo -e "${GREEN}✓ psql 已安装${NC}"
echo ""

# 2. 配置数据库连接
echo -e "${YELLOW}2. 配置数据库连接${NC}"
echo "请输入数据库管理员信息："
read -p "数据库主机 (默认: localhost): " DB_HOST
DB_HOST=${DB_HOST:-localhost}

read -p "数据库端口 (默认: 5433): " DB_PORT
DB_PORT=${DB_PORT:-5433}

read -p "数据库名称 (默认: rag_db): " DB_NAME
DB_NAME=${DB_NAME:-rag_db}

read -p "数据库用户 (默认: postgres): " DB_USER
DB_USER=${DB_USER:-postgres}

read -s -p "数据库密码: " DB_PASSWORD
echo ""
echo ""

# 3. 测试连接
echo -e "${YELLOW}3. 测试数据库连接...${NC}"
if PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -c "SELECT 1;" &> /dev/null; then
    echo -e "${GREEN}✓ 数据库连接成功${NC}"
else
    echo -e "${RED}✗ 数据库连接失败${NC}"
    echo "请检查："
    echo "  1. 数据库服务是否启动"
    echo "  2. 用户名和密码是否正确"
    echo "  3. 数据库是否存在"
    exit 1
fi
echo ""

# 4. 备份数据库（重要！）
echo -e "${YELLOW}4. 备份数据库...${NC}"
BACKUP_FILE="backup_$(date +%Y%m%d_%H%M%S).sql"
echo "备份文件: $BACKUP_FILE"

if PGPASSWORD=$DB_PASSWORD pg_dump -h $DB_HOST -p $DB_PORT -U $DB_USER $DB_NAME > $BACKUP_FILE; then
    echo -e "${GREEN}✓ 数据库备份成功${NC}"
    echo "备份文件大小: $(du -h $BACKUP_FILE | cut -f1)"
else
    echo -e "${RED}✗ 数据库备份失败${NC}"
    exit 1
fi
echo ""

# 5. 执行升级
echo -e "${YELLOW}5. 执行升级脚本...${NC}"
UPGRADE_SCRIPT="upgrade_v3_with_admin.sql"
if [ ! -f "$UPGRADE_SCRIPT" ]; then
    echo -e "${RED}✗ 升级脚本不存在: $UPGRADE_SCRIPT${NC}"
    exit 1
fi

echo "执行升级脚本: $UPGRADE_SCRIPT"
if PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -f $UPGRADE_SCRIPT; then
    echo -e "${GREEN}✓ 升级脚本执行成功${NC}"
else
    echo -e "${RED}✗ 升级脚本执行失败${NC}"
    echo ""
    echo "是否回滚？(y/n)"
    read -p "> " ROLLBACK
    if [ "$ROLLBACK" = "y" ]; then
        echo "回滚数据库..."
        PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME < $BACKUP_FILE
        echo -e "${GREEN}✓ 数据库已回滚${NC}"
    fi
    exit 1
fi
echo ""

# 6. 验证升级结果
echo -e "${YELLOW}6. 验证升级结果...${NC}"

# 检查表
echo "检查表："
for table in chat_sessions chat_sections qa_query_index entries; do
    if PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -c "\d $table" &> /dev/null; then
        echo -e "  ${GREEN}✓ $table${NC}"
    else
        echo -e "  ${RED}✗ $table${NC}"
    fi
done
echo ""

# 检查索引
echo "检查索引："
INDEXES=(
    "idx_entries_user_agent"
    "idx_entries_agent_type_user"
    "idx_entries_scene_tags"
    "idx_chat_sessions_user_agent"
    "idx_chat_sections_user_agent"
)

for index in "${INDEXES[@]}"; do
    if PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -c "SELECT indexname FROM pg_indexes WHERE indexname = '$index';" | grep -q $index; then
        echo -e "  ${GREEN}✓ $index${NC}"
    else
        echo -e "  ${RED}✗ $index${NC}"
    fi
done
echo ""

# 7. 完成
echo "========================================"
echo -e "${GREEN}✓ V3多租户架构升级完成！${NC}"
echo "========================================"
echo ""
echo "备份文件: $BACKUP_FILE"
echo "如需回滚，请使用："
echo "  PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME < $BACKUP_FILE"
echo ""
echo "下一步："
echo "  1. 检查应用层代码是否需要更新"
echo "  2. 运行应用测试"
echo "  3. 部署到生产环境"
