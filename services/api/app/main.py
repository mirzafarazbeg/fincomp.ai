from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import FastAPI, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from services.api.app import cat_validate_client, llm, rag_client

app = FastAPI(title='ComplianceGPT API')

STATIC_DIR = Path(__file__).resolve().parent.parent / 'static'
if STATIC_DIR.exists():
    app.mount('/static', StaticFiles(directory=str(STATIC_DIR)), name='static')


class QueryRequest(BaseModel):
    question: str
    top_k: int = 5
    submission_id: int | None = None  # scopes the answer to a CAT file validation run


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
    chunks = rag_client.retrieve(req.question, top_k=req.top_k, submission_id=req.submission_id)
    if llm.is_configured():
        answer = llm.generate(req.question, chunks)
        generated = True
    else:
        answer = None
        generated = False
    return QueryResponse(answer=answer, chunks=chunks, generated=generated)


@app.post('/validate')
async def validate(file: UploadFile):
    with tempfile.NamedTemporaryFile(suffix='.dat', delete=False) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name
    try:
        return cat_validate_client.validate_and_store(tmp_path, file.filename or 'upload')
    finally:
        Path(tmp_path).unlink(missing_ok=True)
