from fastapi import FastAPI, HTTPException

from ai_factory.integrations.entries_ingest import entries_ingest
from ai_factory.integrations.rag_api import qa_answer_rag
from ai_factory.integrations.web_api import qa_answer_web


app = FastAPI(title="AI Factory API", version="1.0.0")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/entries/ingest")
async def entries_ingest_endpoint(payload: dict) -> dict:
    try:
        return entries_ingest(payload)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/qa/rag")
async def qa_rag_endpoint(payload: dict) -> dict:
    try:
        return qa_answer_rag(payload)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/qa/web")
async def qa_web_endpoint(payload: dict) -> dict:
    try:
        return qa_answer_web(payload)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
