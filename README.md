# fincomp.ai — ComplianceGPT

An AI-assisted compliance system for broker-dealer CAT/SEC/FINRA reporting.
See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full build plan.
Implemented so far: Phase 1 (Document Intelligence / RAG Q&A) and Phase 2 v1
(CAT File Validator), wired together — upload a CAT file and ask follow-up
questions grounded in the actual validation findings.

## Quick start (Docker Compose)

```bash
docker compose up -d postgres ollama
docker compose exec ollama ollama pull qwen2.5:7b-instruct-q4_K_M
docker compose run --rm api python3 -m services.rag.ingest
docker compose up -d api
```

Then open http://localhost:8001.

## Local dev (no Docker)

Requires Postgres 16 with the `pgvector` extension, and `pdftotext`
(poppler-utils) on PATH.

```bash
pip install -r requirements.txt
cp .env.example .env   # adjust DATABASE_URL / OLLAMA_* as needed
export $(cat .env | xargs)

python3 -m services.rag.ingest        # chunk + embed + load the knowledge base
python3 -m services.rag.eval          # retrieval regression check (no LLM needed)
python3 -m uvicorn services.api.app.main:app --port 8001
```

Without `OLLAMA_URL`/`OLLAMA_MODEL` set, `/query` runs in retrieval-only
mode — it returns the matched source chunks without a generated answer.
Useful for checking retrieval quality without a GPU.

`POST /validate` (multipart file upload) parses and validates a CAT Data
File and returns a `submission_id`; pass that as `submission_id` on a
`/query` call (the chat UI does this automatically after an upload) to
ground the answer in that run's findings — e.g. "why did record 45 fail?".
`python3 -m services.cat_validator.selftest` is the validator's own
regression check (no DB/LLM needed).

## Layout

- `docs/specs/` — source FINRA CAT spec PDFs
- `docs/ARCHITECTURE.md` — build plan and data model
- `data/cat_reference/` — structured CAT error codes + field data dictionary,
  extracted from the specs (`scripts/extract_cat_*.py`)
- `data/eval/questions.json` — retrieval regression test cases
- `services/rag/` — chunking, embedding, Postgres+pgvector storage, ingestion,
  eval (no FastAPI/HTTP dependency — usable standalone)
- `services/api/` — FastAPI app (`/query`) + minimal chat UI
