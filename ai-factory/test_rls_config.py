#!/usr/bin/env python3
"""
RLS配置测试脚本
用于诊断PostgreSQL自定义参数配置问题
"""

import psycopg2
import os
import sys
from typing import Dict, Tuple, Optional

def get_connection_info() -> Dict[str, str]:
    """从环境变量获取数据库连接信息"""
    return {
        "host": os.getenv("AI_PG_HOST", "localhost"),
        "port": os.getenv("AI_PG_PORT", "5433"),
        "dbname": os.getenv("AI_PG_DB", "rag_db"),
        "user": os.getenv("AI_PG_USER", "rag_user"),
        "password": os.getenv("AI_PG_PASSWORD", "rag_password")
    }

def build_dsn(info: Dict[str, str]) -> str:
    """构建DSN字符串"""
    return f"dbname={info['dbname']} user={info['user']} password={info['password']} host={info['host']} port={info['port']}"

def test_connection(info: Dict[str, str]) -> Tuple[bool, Optional[str]]:
    """测试数据库连接"""
    try:
        dsn = build_dsn(info)
        conn = psycopg2.connect(dsn)
        conn.close()
        return True, None
    except Exception as e:
        return False, str(e)

def test_superuser(info: Dict[str, str]) -> Tuple[bool, Optional[str]]:
    """测试是否为超级用户"""
    try:
        dsn = build_dsn(info)
        conn = psycopg2.connect(dsn)
        cur = conn.cursor()
        cur.execute("SELECT usesuper FROM pg_user WHERE usename = current_user")
        is_superuser = cur.fetchone()[0]
        conn.close()
        return is_superuser, None
    except Exception as e:
        return False, str(e)

def test_custom_parameters(info: Dict[str, str]) -> Tuple[bool, Optional[str]]:
    """测试是否可以设置自定义参数"""
    try:
        dsn = build_dsn(info)
        conn = psycopg2.connect(dsn)
        cur = conn.cursor()
        
        # 尝试设置参数
        cur.execute("SET LOCAL app.current_user_id = %s", ("test_user_001",))
        cur.execute("SET LOCAL app.current_agent_type = %s", ("test_assistant",))
        cur.execute("SET LOCAL app.current_agent_instance_id = %s", ("test_instance_001",))
        
        # 验证参数值
        cur.execute("SHOW app.current_user_id")
        user_id = cur.fetchone()[0]
        
        conn.close()
        return True, None
    except Exception as e:
        return False, str(e)

def test_rls_policies(info: Dict[str, str]) -> Tuple[bool, Optional[str]]:
    """测试RLS策略是否存在"""
    try:
        dsn = build_dsn(info)
        conn = psycopg2.connect(dsn)
        cur = conn.cursor()
        
        # 检查RLS是否启用
        tables = ["chat_sessions", "chat_messages", "chat_sections", "qa_cache", "entries"]
        
        for table in tables:
            cur.execute(f"SELECT relrowsecurity FROM pg_class WHERE relname = %s", (table,))
            result = cur.fetchone()
            if result and result[0]:
                # 检查是否有策略
                cur.execute(f"SELECT COUNT(*) FROM pg_policies WHERE tablename = %s", (table,))
                policy_count = cur.fetchone()[0]
                if policy_count == 0:
                    conn.close()
                    return False, f"表 {table} 启用了RLS但没有策略"
        
        conn.close()
        return True, None
    except Exception as e:
        return False, str(e)

def show_rls_policy_details(info: Dict[str, str]):
    """显示RLS策略详情"""
    try:
        dsn = build_dsn(info)
        conn = psycopg2.connect(dsn)
        cur = conn.cursor()
        
        print("\n" + "="*60)
        print("RLS策略详情")
        print("="*60)
        
        cur.execute("""
            SELECT 
                tablename,
                policyname,
                permissive,
                roles,
                cmd,
                qual
            FROM pg_policies
            ORDER BY tablename, policyname
        """)
        
        policies = cur.fetchall()
        if policies:
            for policy in policies:
                print(f"\n表: {policy[0]}")
                print(f"  策略名: {policy[1]}")
                print(f"  类型: {'PERMISSIVE' if policy[2] else 'RESTRICTIVE'}")
                print(f"  适用角色: {policy[3]}")
                print(f"  命令: {policy[4]}")
                print(f"  条件: {policy[5][:100]}{'...' if len(policy[5]) > 100 else ''}")
        else:
            print("未找到RLS策略")
        
        conn.close()
    except Exception as e:
        print(f"获取RLS策略详情失败: {e}")

def main():
    """主测试流程"""
    print("="*60)
    print("PostgreSQL RLS配置诊断工具")
    print("="*60)
    
    # 获取连接信息
    info = get_connection_info()
    
    print(f"\n数据库连接信息:")
    print(f"  主机: {info['host']}:{info['port']}")
    print(f"  数据库: {info['dbname']}")
    print(f"  用户: {info['user']}")
    
    # 1. 测试连接
    print("\n[1/5] 测试数据库连接...")
    success, error = test_connection(info)
    if success:
        print("  ✅ 连接成功")
    else:
        print(f"  ❌ 连接失败: {error}")
        sys.exit(1)
    
    # 2. 测试超级用户
    print("\n[2/5] 测试用户权限...")
    success, error = test_superuser(info)
    if success:
        print("  ✅ 当前用户是超级用户")
    else:
        print("  ℹ️  当前用户不是超级用户（这是正常的）")
        if error:
            print(f"     错误: {error}")
    
    # 3. 测试自定义参数
    print("\n[3/5] 测试自定义参数设置...")
    success, error = test_custom_parameters(info)
    if success:
        print("  ✅ 可以设置自定义参数")
    else:
        print(f"  ❌ 无法设置自定义参数: {error}")
        print("\n  💡 解决方案:")
        print("     1. 使用超级用户连接（推荐用于开发）")
        print("     2. 联系DBA授权（推荐用于生产）")
        print("     3. 查看 RLS问题解决方案.md 获取详细说明")
    
    # 4. 测试RLS策略
    print("\n[4/5] 测试RLS策略...")
    success, error = test_rls_policies(info)
    if success:
        print("  ✅ RLS策略配置正常")
    else:
        print(f"  ⚠️  RLS策略问题: {error}")
        print("     可能需要执行数据库升级脚本")
    
    # 5. 显示RLS详情
    show_rls_policy_details(info)
    
    # 总结
    print("\n" + "="*60)
    print("诊断总结")
    print("="*60)
    
    param_success, _ = test_custom_parameters(info)
    superuser_success, _ = test_superuser(info)
    
    if param_success:
        print("✅ 配置正常，可以直接使用数据库版API")
        print("   启动命令: python3 ai_factory/web/agent_memory_api.py")
    elif superuser_success:
        print("✅ 当前是超级用户，可以直接使用数据库版API")
        print("   启动命令: python3 ai_factory/web/agent_memory_api.py")
    else:
        print("❌ 需要解决RLS配置问题")
        print("\n推荐方案:")
        print("1. 修改.env文件，使用超级用户连接")
        print("2. 运行: python3 /root/ai-factory/test_rls_config.py")
        print("3. 查看: /root/ai-factory/RLS问题解决方案.md")
        print("\n临时解决方案:")
        print("使用内存版API: python3 ai_factory/web/agent_memory_api_memory.py")

if __name__ == "__main__":
    # 检查依赖
    try:
        import psycopg2
    except ImportError:
        print("错误: 未安装 psycopg2")
        print("安装命令: pip install psycopg2-binary")
        sys.exit(1)
    
    main()
