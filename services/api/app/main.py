from __future__ import annotations

import tempfile
from pathlib import Path

import httpx
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
    warning: str | None = None  # set if generation was attempted but failed (e.g. Ollama unreachable)


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
    answer, generated, warning = None, False, None
    if llm.is_configured():
        try:
            answer = llm.generate(req.question, chunks)
            generated = True
        except httpx.HTTPError as e:
            # Ollama unreachable/erroring - degrade to retrieval-only instead
            # of 500ing the whole request; the sources are still useful.
            warning = f'LLM generation failed ({e.__class__.__name__}: {e}); showing retrieved sources only.'
    return QueryResponse(answer=answer, chunks=chunks, generated=generated, warning=warning)


@app.post('/validate')
async def validate(file: UploadFile):
    # Stream the upload to disk in chunks rather than file.read()'ing the
    # whole thing into memory first - matters once files get into the
    # hundreds of MB / millions of records (see engine.py's docstring and
    # services/cat_validator/README.md's "Scale" section for why the actual
    # validation logic was rebuilt to stream too).
    with tempfile.NamedTemporaryFile(suffix='.dat', delete=False) as tmp:
        tmp_path = tmp.name
        while chunk := await file.read(1024 * 1024):
            tmp.write(chunk)
    try:
        return cat_validate_client.validate_and_store(tmp_path, file.filename or 'upload')
    finally:
        Path(tmp_path).unlink(missing_ok=True)
