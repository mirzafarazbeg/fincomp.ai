"""Thin client for a local Ollama server. Not required for retrieval-only use —
if OLLAMA_URL / OLLAMA_MODEL aren't set, the API returns retrieved chunks
without a generated answer (useful for testing retrieval quality on its own,
and for running without a GPU at all).
"""
from __future__ import annotations

import os

import httpx

SYSTEM_PROMPT = (
    "You are a compliance assistant for broker-dealer CAT/SEC/FINRA reporting. "
    "Answer ONLY using the provided context chunks. Cite the section/error "
    "code/field referenced in each chunk you use (the citation is given with "
    "each chunk). If the context does not contain the answer, say so plainly "
    "instead of guessing — do not use outside knowledge for compliance-specific "
    "facts (rule numbers, error codes, field requirements).\n\n"
    "The context mixes two kinds of chunks, and you must not conflate them:\n"
    "- \"CAT Validation Finding\" chunks are the actual result for THIS "
    "specific uploaded file. A CAT error code number appears in a Validation "
    "Finding chunk's own text ONLY if the validator determined one "
    "unambiguously for that exact finding — e.g. \"Error [2041]: ...\".\n"
    "- \"CAT Error Code Catalog\" chunks are general reference material about "
    "what a given code means; they are retrieved because they're topically "
    "related, NOT because they necessarily apply to a specific finding.\n"
    "When explaining why a specific record/line failed: state the error code "
    "ONLY if it is written inside that finding's own chunk text. If a "
    "Validation Finding chunk has no bracketed code, say plainly that no "
    "official CAT error code was determined for it — never borrow a code "
    "number from a separate Error Code Catalog chunk just because it appears "
    "elsewhere in the context; that would misattribute it."
)


def is_configured() -> bool:
    return bool(os.environ.get('OLLAMA_URL') and os.environ.get('OLLAMA_MODEL'))


def generate(question: str, context_chunks: list[dict]) -> str:
    base_url = os.environ['OLLAMA_URL'].rstrip('/')
    model = os.environ['OLLAMA_MODEL']

    context = '\n\n'.join(
        f"[{i + 1}] {c['citation']}\n{c['text']}" for i, c in enumerate(context_chunks)
    )
    user_prompt = f"Context:\n{context}\n\nQuestion: {question}"

    resp = httpx.post(
        f'{base_url}/api/chat',
        json={
            'model': model,
            'messages': [
                {'role': 'system', 'content': SYSTEM_PROMPT},
                {'role': 'user', 'content': user_prompt},
            ],
            'stream': False,
        },
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()['message']['content']
