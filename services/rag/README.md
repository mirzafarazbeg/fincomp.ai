# RAG pipeline (Phase 1)

`chunker.py` → `embed.py` → `db.py`, tied together by `ingest.py`.
`structured.py` turns the extracted CAT error-code/data-dictionary JSON
(`data/cat_reference/`) into chunks too, formatted as prose rather than raw
JSON, so they read naturally alongside the PDF-derived chunks.

## Known limitations

- **Reporting Scenarios PDF heading detection**: this document's step-by-step
  tables ("# Step Reported Event Comments") have a numbered first column
  (1, 2, 3, ...) that occasionally gets misdetected as a section heading by
  the same regex that correctly finds real headings like "2.1.1 New
  Principal Order Routed...". When this happens, a chunk's `section_ref`/
  `section_title` citation can point at a table row instead of its parent
  scenario — the chunk's actual retrieved *text* is still correct and
  complete, only the citation label can drift. Worth revisiting if this
  turns out to matter for how often users click through citations vs. just
  reading the answer.
- **Embedding model requires internet access** (downloads
  `sentence-transformers/all-MiniLM-L6-v2` from Hugging Face on first run)
  — this couldn't be verified end-to-end in the sandboxed dev session this
  was built in (network policy blocks huggingface.co there); the DB/API
  plumbing was verified with a stubbed embedding function instead. Should
  work as-is on Colab / a normal dev machine with internet access — flag it
  if it doesn't.
- **Front matter skipped**: each PDF's cover/TOC/change-log pages are
  skipped via a hardcoded `start_page` in `ingest.py`'s `SOURCES` list. If a
  future spec revision changes page counts, re-check those offsets (or make
  this more robust by detecting "1. Introduction" / "1 Introduction"
  programmatically instead of hardcoding the page number).

## Running the eval

`python3 -m services.rag.eval` checks retrieval only (no LLM/GPU needed) —
for each question in `data/eval/questions.json`, it verifies a chunk
matching the expected citation appears in the top-k results. This hasn't
been run against real embeddings yet (see limitation above) — do that first
after setting up on a machine with internet access, before trusting the
retrieval quality.
