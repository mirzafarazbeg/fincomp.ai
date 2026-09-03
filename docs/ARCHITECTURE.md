# ComplianceGPT — Architecture & Build Plan

## Goals

An AI-assisted compliance system for broker-dealer reporting, covering:
1. Q&A over the FINRA/SEC/CAT knowledge base (specs, rules, internal docs)
2. CAT file validation against the CAT Reporting Technical Specifications
3. Transaction surveillance (wash trades, spoofing, layering, front-running — rules TBD)
4. FIX protocol log analysis, interactively

Design principle throughout: **the LLM narrates, deterministic code decides.**
Validation, error detection, and surveillance flags come from rules engines and
parsers, not from asking an LLM to judge a file or a trade. The LLM's job is
retrieval-grounded Q&A and turning structured findings into plain English. This
keeps the system auditable — every flag traces to a specific rule and a specific
spec citation, not a model's opinion.

## Status

- [x] Specs committed (`docs/specs/`)
- [x] CAT Appendix E error code catalog extracted (`data/cat_reference/cat_error_codes.json`)
- [x] CAT Appendix G data dictionary extracted (`data/cat_reference/cat_data_dictionary.json`) — 132 fields, types + descriptions; Choice-field allowed values still need structuring (see `data/cat_reference/README.md`)
- [x] **Phase 1 (Document Intelligence) verified end-to-end on Colab (L4 GPU)**: chunker (`services/rag/chunker.py`), embedding (`services/rag/embed.py`), Postgres+pgvector storage (`services/rag/db.py`), ingestion (`services/rag/ingest.py`), FastAPI `/query` + chat UI (`services/api/`), hybrid exact-match short-circuit for ID lookups (`db.search_by_section_title_prefix`), retrieval eval harness (`services/rag/eval.py`, `data/eval/questions.json`) — **13/13 passing** with real embeddings (all-MiniLM-L6-v2) against all four ingested sources (1,751 chunks). Generation via Ollama (`qwen2.5:7b-instruct-q4_K_M`) confirmed working on the L4. Setup path: `docs/COLAB_SETUP.md` / `scripts/colab_setup.sh`.
- [x] **Phase 2 (CAT File Validator) v1**: schema-driven CSV/JSON parser and field-level rules engine (`services/cat_validator/`), built against the official CAT Industry Member schema (`docs/specs/cat_im_schema_v4.2.0.json`) rather than PDF-extracted tables. Emits real CAT error codes where unambiguous. 7/7 on its regression fixtures (`services/cat_validator/selftest.py`). Known gaps (Conditional-field presence, compound-field internals, cross-record linkage checks) documented in `services/cat_validator/README.md`.
- [x] **Phase 2 wired into chat/RAG**: `POST /validate` (file upload) parses+validates+persists a run (`services/cat_validator/store.py`); `POST /query` takes an optional `submission_id` and grounds the answer in that run's findings (plus the matching Appendix E error-code explanation for each finding, and the specific line if the question names one, e.g. "why did record 45 fail"). Chat UI has a file-upload control. Verified through the actual FastAPI app (not just the underlying functions) with a stubbed embedding.
- [ ] Everything after this (Conditional-field logic, cross-record linkage checks, Phase 4, Phase 3 - see gaps above)

## Build order

**Phase 1 (Document Intelligence) → Phase 2 (CAT Validator) → Phase 4 (FIX Log
Analysis) → Phase 3 (Transaction Surveillance).**

Phase 1 ships first: lowest risk, and its plumbing (chunking, embedding,
retrieval, the DB schema below) is reused by every later phase. Phase 3 is
last because it's blocked on you supplying the actual detection rules; Phase 4
doesn't depend on those and is self-contained, so it can move up if useful.

### Phase 0 — Foundations
- Extract Appendix G (Data Dictionary) from the CAT Tech Specs — field types,
  allowable values, required/conditional/optional rules. This is what the
  Phase 2 validator is actually built from.
- Chunk-index the Reporting Scenarios PDF for RAG (order-lifecycle narratives
  don't reduce to a clean table the way the error codes did).

### Phase 1 — Document Intelligence (Q&A)
1. Chunk PDFs/docs by section (respecting numbered headings, not blind token
   windows) so a retrieved chunk maps to a real citation like "CAT Tech Spec §2.6.1".
2. Embed chunks locally (`sentence-transformers`, e.g. `bge-small-en` or
   `all-MiniLM-L6-v2`) into pgvector.
3. FastAPI `/query` endpoint: retrieve top-k chunks → LLM with a strict
   "answer only from context, cite section" system prompt → answer + citations.
4. Minimal chat UI (vanilla JS + Tailwind CDN, per the original tech-stack scope).
5. Regression set: ~30 questions with known-correct answers (e.g. "what does
   error 2019 mean", "when is FDID required") — run on every change.

### Phase 2 — CAT File Validator
1. **Parser**: CAT submission file (pipe-delimited event records per spec) →
   structured records.
2. **Rules engine**: per-record field checks driven by the Appendix G data
   dictionary → on failure, emit the matching code from `cat_error_codes.json`
   verbatim, never a re-derived message.
3. **Linkage checks**: cross-record checks (Order ID lineage, route/trade
   sequencing) — driven by the Reporting Scenarios doc, built incrementally,
   one scenario at a time, each with a synthetic test fixture that should trip
   that exact rule.
4. Output: structured report (code, severity, record, field, message). LLM
   only summarizes/answers follow-ups ("why did record 45 fail") — never
   invents the verdict.
5. Validate against FINRA-published CAT test files if available, else
   hand-built fixtures per known scenario.

### Phase 4 — FIX Log Analysis
1. FIX parser (tag=value → named fields; QuickFIX dictionaries or a
   lightweight custom parser — protocol is fully specified, no LLM needed).
2. Session/order-state reconstruction (new order → acks → fills/cancels →
   reject reasons) into a timeline.
3. User asks "what happened to order X" / "why did the session drop at
   14:32" → retrieve the relevant timeline slice → LLM explains it. Same
   narrate-don't-decide pattern as Phase 2.

### Phase 3 — Transaction Surveillance
Blocked on you supplying rule definitions (wash trades, spoofing, layering,
front-running). Architecturally:
1. CSV/SQL dump → normalized trade/order event schema (reuse the CAT event
   model where it overlaps).
2. Each pattern = its own deterministic detector module (e.g. spoofing: large
   order placed and cancelled before execution, correlated with an opposite-
   side fill in a time window). Not an LLM prompt — LLMs are unreliable at
   "did a wash trade happen" and good at "explain why detector X flagged this".
3. Detectors are configurable (thresholds, lookback windows) — real rules are
   usually firm-specific tuning on a common shape.
4. LLM layer turns a list of flags into a plain-English narrative per
   account/desk.

## Data architecture

This was missing from the first pass of this plan — every phase produces
things that need to persist beyond a single request: parsed files, findings,
chat history, an audit trail of what was flagged and why. One Postgres
instance (with the pgvector extension) covers both the relational and vector
needs; no separate document/graph store for v1 (see "Why not Neo4j" below).

**Postgres + pgvector**, roughly:

```
documents            (id, source_path, title, version, ingested_at)
document_chunks       (id, document_id, section_ref, text, embedding vector, page_no)

cat_submissions       (id, filename, imid, submitted_at, status)
cat_records            (id, submission_id, event_type, raw_line, parsed jsonb, line_no)
cat_findings           (id, record_id, error_code, severity, field, message)
  [implemented in services/cat_validator/store.py as cat_submissions
   (id, filename, record_count, submitted_at) and cat_findings (id,
   submission_id, line_no, event_type, field, error_code, severity,
   message) - no separate cat_records table yet; findings reference the
   line number directly rather than a parsed-record row. Revisit if a
   later feature needs the full parsed record, not just the finding text.]

fix_sessions          (id, source_file, begin_string, sender_comp_id, target_comp_id, started_at, ended_at)
fix_events             (id, session_id, seq_num, msg_type, tags jsonb, ts)

surveillance_runs     (id, source_file, run_at, ruleset_version)
surveillance_flags     (id, run_id, pattern, severity, accounts jsonb, evidence jsonb)

chat_sessions         (id, user_id, created_at)
chat_messages          (id, session_id, role, content, citations jsonb, created_at)
```

Why this shape:
- **`document_chunks.embedding`** is the only vector column — Phase 1's RAG
  index. Everything else is plain relational data.
- **`cat_records.parsed`** and similar `jsonb` columns hold the full parsed
  record so the LLM narration layer can pull exact field values without a
  second parse pass, while `cat_findings` stays a thin, queryable table
  (filter by error code, severity, submission) for reporting/dashboards.
- Every finding/flag rows back to a source record — that's the audit trail:
  "why was this flagged" always resolves to a DB row, not a model response.
- **Redis** (optional, as in the original tech-stack scope) sits in front of
  this for session state and embedding cache, not as a system of record.

**Why not Neo4j for v1**: the original scope doc proposed a hybrid vector +
knowledge-graph search. Deferred — it's real added complexity (a second
database, graph modeling work, graph-aware retrieval logic) for marginal
gain until we know plain vector search actually falls short on relational
queries (e.g. "which rules amend 606(b)(2)"). If Phase 1's retrieval quality
proves that gap real, add it in Phase 2+ rather than building it speculatively
now.

## Model layer

- Self-hosted, quantized 7–8B instruct model (Qwen2.5-7B-Instruct or
  Llama-3.1-8B-Instruct, 4-bit) via Ollama or vLLM — fits comfortably on a
  24GB L4 with room for embeddings + KV cache, and scales down to a cheaper
  GPU later without a rewrite.
- Not fine-tuned for v1: RAG (Phase 1) + deterministic rules (Phases 2–4) cover
  the accuracy-critical paths. Revisit fine-tuning only if retrieval-grounded
  prompting proves insufficient for a specific recurring task.
- Local embeddings via `sentence-transformers`, no external API calls —
  matches the "privacy-first, no external API calls" requirement in the
  original scope doc.

## Deployment layer

- Docker + Docker Compose: `api` (FastAPI), `postgres` (+ pgvector), `ollama`
  (or vLLM), optional `redis`.
- Single Docker internal network, ports per the original tech-stack doc
  (Postgres :5432, FastAPI :8001).

## Testing / eval

Each phase ships with a fixture set with known-correct answers, run as part
of CI:
- Phase 1: ~30 spec Q&A pairs with expected citations.
- Phase 2: synthetic CAT files, one per known validation/linkage scenario,
  with expected error codes.
- Phase 3: synthetic trade sequences, one per surveillance pattern, with
  expected flags (once rules are provided).
- Phase 4: sample FIX logs with known session outcomes.

This is what lets us change the model, the rules, or the prompts later
without silently regressing something that used to work.
