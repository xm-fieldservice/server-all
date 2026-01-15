import os

print("=== 环境变量检查 (ai-factory venv) ===")
print("AI_PG_HOST =", os.getenv("AI_PG_HOST"))
print("AI_PG_PORT =", os.getenv("AI_PG_PORT"))
print("AI_PG_DB   =", os.getenv("AI_PG_DB"))
print("AI_PG_USER =", os.getenv("AI_PG_USER"))
print("RAG_DB_DSN =", os.getenv("RAG_DB_DSN"))

try:
    from ai_factory.db.pgvector_client import _get_dsn
    print("_get_dsn() =", _get_dsn())
except Exception as e:
    print("导入 ai_factory.db.pgvector_client 或调用 _get_dsn() 失败:", repr(e))
