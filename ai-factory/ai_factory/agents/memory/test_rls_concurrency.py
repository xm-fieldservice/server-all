import threading
import time
import uuid
import random
from typing import List, Dict, Any
from ai_factory.db.pgvector_client import connection_scope
from ai_factory.agents.memory.entry_service import EntryService
from ai_factory.agents.memory.api.client import MemoryClient
import logging

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(threadName)s - %(message)s')
logger = logging.getLogger(__name__)

class RLSTester:
    def __init__(self, num_users: int = 5, iterations: int = 20):
        self.num_users = num_users
        self.iterations = iterations
        self.entry_service = EntryService()
        self.users = [
            {
                "user_id": f"user_{i}",
                "agent_type": f"type_{i}",
                "agent_instance_id": f"inst_{i}",
                "data_content": f"Secret data for user {i}"
            }
            for i in range(num_users)
        ]
        self.errors = []
        self.lock = threading.Lock()

    def run_user_session(self, user_info: Dict[str, Any]):
        user_id = user_info["user_id"]
        a_type = user_info["agent_type"]
        a_inst = user_info["agent_instance_id"]
        content = user_info["data_content"]
        
        try:
            for i in range(self.iterations):
                # 随机延迟模拟真实并发
                time.sleep(random.uniform(0.01, 0.1))
                
                with connection_scope() as conn:
                    # 1. 设置 RLS 上下文
                    self.entry_service.set_rls_context(user_id, a_type, a_inst, conn=conn)
                    
                    # 2. 写入数据
                    entry_id = f"test_{user_id}_{i}_{uuid.uuid4().hex[:8]}"
                    with conn.cursor() as cur:
                        cur.execute("""
                            INSERT INTO entries (entry_id, title, content, user_id, agent_type, agent_instance_id)
                            VALUES (%s, %s, %s, %s, %s, %s)
                        """, (entry_id, f"Title {i}", content, user_id, a_type, a_inst))
                    
                    # 3. 立即查询，验证隔离
                    with conn.cursor() as cur:
                        # 尝试查询不属于自己的数据（理论上应该查不到）
                        # 即使不加 WHERE user_id = ...，RLS 也应该起作用
                        cur.execute("SELECT content FROM entries")
                        rows = cur.fetchall()
                        
                        for row in rows:
                            if row[0] != content:
                                raise ValueError(f"RLS LEAK! User {user_id} saw data: {row[0]}")
                        
                        # 验证至少能查到自己刚才插入的数据
                        cur.execute("SELECT COUNT(*) FROM entries WHERE entry_id = %s", (entry_id,))
                        count = cur.fetchone()[0]
                        if count == 0:
                            raise ValueError(f"RLS BLOCK! User {user_id} cannot see their own data {entry_id}")

                if i % 5 == 0:
                    logger.info(f"User {user_id} iteration {i} successful")

        except Exception as e:
            with self.lock:
                self.errors.append(f"Error for {user_id}: {str(e)}")
                logger.error(f"Error for {user_id}: {str(e)}")

    def cleanup(self):
        logger.info("Cleaning up test data...")
        with connection_scope() as conn:
            with conn.cursor() as cur:
                # 绕过 RLS 清理（或者使用 admin 权限）
                # 这里我们假设当前连接有权清理 test_ 开头的数据
                cur.execute("DELETE FROM entries WHERE entry_id LIKE 'test_user_%'")
        logger.info("Cleanup done.")

    def run(self):
        logger.info(f"Starting RLS Concurrency Test with {self.num_users} users, {self.iterations} iterations each")
        threads = []
        for user in self.users:
            t = threading.Thread(target=self.run_user_session, args=(user,), name=f"Thread-{user['user_id']}")
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        if self.errors:
            logger.error(f"Test FAILED with {len(self.errors)} errors")
            for err in self.errors:
                print(err)
        else:
            logger.info("Test PASSED! No RLS leaks detected.")
        
        self.cleanup()

if __name__ == "__main__":
    tester = RLSTester(num_users=10, iterations=50)
    tester.run()
