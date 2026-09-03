#!/usr/bin/env python3
"""Ingest all knowledge base sources into the Postgres+pgvector RAG index.

Usage:
    python3 -m services.rag.ingest

Reads DATABASE_URL from the environment (see services/rag/db.py for the
default). Safe to re-run: each source is upserted by (source_path, version)
and its chunks fully replaced.
"""
from __future__ import annotations

from services.rag import db
from services.rag.chunker import Chunk, chunk_pdf
from services.rag.embed import embed_texts
from services.rag.structured import chunks_from_data_dictionary, chunks_from_error_codes

SPEC_VERSION = 'v4.2.0r1 / v4.18'

SOURCES: list[dict] = [
    {
        'source_path': 'docs/specs/06.26.26_CAT_Reporting_Technical_Specifications_for_Industry_Members_v4.2.0r1_CLEAN.pdf',
        'title': 'CAT Tech Spec v4.2.0r1',
        'version': 'v4.2.0r1',
        'kind': 'pdf',
        'start_page': 38,  # skips cover/TOC/changelog front matter; see services/rag/chunker.py
    },
    {
        'source_path': 'docs/specs/07.31.26_Industry_Member_Tech_Specs_Reporting_Scenarios_v4.18_CLEAN.pdf',
        'title': 'CAT Reporting Scenarios v4.18',
        'version': 'v4.18',
        'kind': 'pdf',
        'start_page': 18,
    },
    {
        'source_path': 'data/cat_reference/cat_error_codes.json',
        'title': 'CAT Error Code Catalog (Appendix E)',
        'version': 'v4.2.0r1',
        'kind': 'error_codes',
    },
    {
        'source_path': 'data/cat_reference/cat_data_dictionary.json',
        'title': 'CAT Data Dictionary (Appendix G)',
        'version': 'v4.2.0r1',
        'kind': 'data_dictionary',
    },
]


def _load_chunks(source: dict) -> list[Chunk]:
    if source['kind'] == 'pdf':
        return chunk_pdf(source['source_path'], source['title'], start_page=source['start_page'])
    if source['kind'] == 'error_codes':
        return chunks_from_error_codes(source['source_path'])
    if source['kind'] == 'data_dictionary':
        return chunks_from_data_dictionary(source['source_path'])
    raise ValueError(f"unknown source kind: {source['kind']}")


def ingest_source(conn, source: dict) -> int:
    chunks = _load_chunks(source)
    embeddings = embed_texts([c.text for c in chunks])
    document_id = db.upsert_document(conn, source['source_path'], source['title'], source['version'])
    rows = [
        {
            'section_ref': c.section_ref,
            'section_title': c.section_title,
            'page_no': c.page_no,
            'text': c.text,
            'embedding': emb,
        }
        for c, emb in zip(chunks, embeddings)
    ]
    db.replace_document_chunks(conn, document_id, rows)
    return len(rows)


def main() -> None:
    db.init_schema()
    conn = db.get_connection()
    try:
        for source in SOURCES:
            n = ingest_source(conn, source)
            print(f"Ingested {n:>4} chunks from {source['title']}")
    finally:
        conn.close()


if __name__ == '__main__':
    main()
