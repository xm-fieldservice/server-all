from __future__ import annotations

from fastapi import FastAPI

from ai_factory.db.pgvector_client import test_connection


app = FastAPI(title="ai-factory-health", version="0.1.0")


@app.get("/health")
async def health() -> dict[str, str]:
    """基础健康检查：仅证明应用进程在运行。"""

    return {"status": "ok"}


@app.get("/db-test")
async def db_test() -> dict[str, bool]:
    """数据库连通性检查：调用 pgvector_client.test_connection。"""

    ok = test_connection()
    return {"db_ok": ok}
