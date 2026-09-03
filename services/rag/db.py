"""Postgres + pgvector access for the RAG knowledge base.

Schema matches docs/ARCHITECTURE.md's `documents` / `document_chunks` tables.
"""
from __future__ import annotations

import os

import psycopg
from pgvector.psycopg import register_vector

EMBEDDING_DIM = 384  # all-MiniLM-L6-v2

SCHEMA_SQL = f"""
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS documents (
    id BIGSERIAL PRIMARY KEY,
    source_path TEXT NOT NULL,
    title TEXT NOT NULL,
    version TEXT,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source_path, version)
);

CREATE TABLE IF NOT EXISTS document_chunks (
    id BIGSERIAL PRIMARY KEY,
    document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    section_ref TEXT,
    section_title TEXT,
    page_no INT,
    text TEXT NOT NULL,
    embedding VECTOR({EMBEDDING_DIM})
);

CREATE INDEX IF NOT EXISTS document_chunks_document_id_idx ON document_chunks(document_id);
"""


def get_dsn() -> str:
    return os.environ.get(
        'DATABASE_URL',
        'postgresql://compliancegpt:devpassword@localhost:5432/compliancegpt',
    )


def get_connection() -> psycopg.Connection:
    conn = psycopg.connect(get_dsn(), autocommit=True)
    register_vector(conn)
    return conn


def init_schema(conn: psycopg.Connection | None = None) -> None:
    owns_conn = conn is None
    conn = conn or get_connection()
    try:
        conn.execute(SCHEMA_SQL)
    finally:
        if owns_conn:
            conn.close()


def upsert_document(conn: psycopg.Connection, source_path: str, title: str, version: str | None) -> int:
    row = conn.execute(
        """
        INSERT INTO documents (source_path, title, version)
        VALUES (%s, %s, %s)
        ON CONFLICT (source_path, version) DO UPDATE SET title = EXCLUDED.title, ingested_at = now()
        RETURNING id
        """,
        (source_path, title, version),
    ).fetchone()
    return row[0]


def replace_document_chunks(conn: psycopg.Connection, document_id: int, chunks: list[dict]) -> None:
    """Delete existing chunks for a document and insert the new set (re-ingestion is idempotent)."""
    conn.execute('DELETE FROM document_chunks WHERE document_id = %s', (document_id,))
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO document_chunks (document_id, section_ref, section_title, page_no, text, embedding)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            [
                (document_id, c['section_ref'], c['section_title'], c['page_no'], c['text'], c['embedding'])
                for c in chunks
            ],
        )


def search(conn: psycopg.Connection, query_embedding, top_k: int = 5) -> list[dict]:
    rows = conn.execute(
        """
        SELECT dc.text, dc.section_ref, dc.section_title, dc.page_no, d.title AS document_title,
               dc.embedding <=> %s::vector AS distance
        FROM document_chunks dc
        JOIN documents d ON d.id = dc.document_id
        ORDER BY dc.embedding <=> %s::vector
        LIMIT %s
        """,
        (query_embedding, query_embedding, top_k),
    ).fetchall()
    cols = ['text', 'section_ref', 'section_title', 'page_no', 'document_title', 'distance']
    return [dict(zip(cols, row)) for row in rows]
