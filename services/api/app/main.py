from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from services.api.app import llm, rag_client

app = FastAPI(title='ComplianceGPT API')

STATIC_DIR = Path(__file__).resolve().parent.parent / 'static'
if STATIC_DIR.exists():
    app.mount('/static', StaticFiles(directory=str(STATIC_DIR)), name='static')


class QueryRequest(BaseModel):
    question: str
    top_k: int = 5


class QueryResponse(BaseModel):
    answer: str | None
    chunks: list[dict]
    generated: bool


@app.get('/health')
def health():
    return {'status': 'ok'}


@app.get('/')
def index():
    index_path = STATIC_DIR / 'index.html'
    if index_path.exists():
        return FileResponse(index_path)
    return {'message': 'ComplianceGPT API. POST /query {"question": "..."}'}


@app.post('/query', response_model=QueryResponse)
def query(req: QueryRequest):
    chunks = rag_client.retrieve(req.question, top_k=req.top_k)
    if llm.is_configured():
        answer = llm.generate(req.question, chunks)
        generated = True
    else:
        answer = None
        generated = False
    return QueryResponse(answer=answer, chunks=chunks, generated=generated)
