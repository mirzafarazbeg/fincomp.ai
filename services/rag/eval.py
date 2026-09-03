#!/usr/bin/env python3
"""Retrieval regression check: for each question in data/eval/questions.json,
verify that a chunk matching the expected citation shows up in the top-k
results. Doesn't require an LLM (checks retrieval quality only) so it can run
without a GPU/Ollama - useful as a fast sanity check before/after changing
the chunker, embedding model, or ingested sources.

Usage:
    python3 -m services.rag.eval
"""
from __future__ import annotations

import json
import sys

from services.api.app.rag_client import retrieve

QUESTIONS_PATH = 'data/eval/questions.json'


def matches(chunk: dict, expect: dict) -> bool:
    if 'document_title' in expect and expect['document_title'] not in chunk['document_title']:
        return False
    if 'section_ref' in expect and chunk['section_ref'] != expect['section_ref']:
        return False
    if 'text_contains' in expect and expect['text_contains'].lower() not in chunk['text'].lower():
        return False
    return True


def main() -> None:
    cases = json.load(open(QUESTIONS_PATH))
    top_k = 5
    passed = 0
    for case in cases:
        chunks = retrieve(case['question'], top_k=top_k)
        hit = any(matches(c, case['expect']) for c in chunks)
        status = 'PASS' if hit else 'FAIL'
        if hit:
            passed += 1
        print(f"[{status}] {case['question']}")
        if not hit:
            print(f"         expected: {case['expect']}")
            print(f"         got: {[c['citation'] for c in chunks]}")
    print(f"\n{passed}/{len(cases)} passed")
    if passed < len(cases):
        sys.exit(1)


if __name__ == '__main__':
    main()
