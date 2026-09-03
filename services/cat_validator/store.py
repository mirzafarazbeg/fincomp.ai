"""Persists CAT file validation runs (submissions + findings) to the same
Postgres instance the RAG knowledge base uses, so the chat layer can answer
follow-up questions grounded in a specific validation run.

Schema matches docs/ARCHITECTURE.md's cat_submissions / cat_findings tables
(cat_records is not implemented yet - findings reference line numbers into
the original file rather than a separate parsed-record table, which is
enough for narration but not yet for structured per-record queries).
"""
from __future__ import annotations

import psycopg

from services.cat_validator.rules import Finding

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS cat_submissions (
    id BIGSERIAL PRIMARY KEY,
    filename TEXT NOT NULL,
    record_count INT NOT NULL,
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS cat_findings (
    id BIGSERIAL PRIMARY KEY,
    submission_id BIGINT NOT NULL REFERENCES cat_submissions(id) ON DELETE CASCADE,
    line_no INT NOT NULL,
    event_type TEXT,
    field TEXT,
    error_code TEXT,
    severity TEXT,
    message TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS cat_findings_submission_id_idx ON cat_findings(submission_id);
"""


def init_schema(conn: psycopg.Connection) -> None:
    conn.execute(SCHEMA_SQL)


def create_submission(conn: psycopg.Connection, filename: str, record_count: int) -> int:
    row = conn.execute(
        'INSERT INTO cat_submissions (filename, record_count) VALUES (%s, %s) RETURNING id',
        (filename, record_count),
    ).fetchone()
    return row[0]


def save_findings(conn: psycopg.Connection, submission_id: int, findings: list[Finding]) -> None:
    if not findings:
        return
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO cat_findings (submission_id, line_no, event_type, field, error_code, severity, message)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            [
                (submission_id, f.line_no, f.event_type, f.field, f.error_code, f.severity, f.message)
                for f in findings
            ],
        )


def get_submission(conn: psycopg.Connection, submission_id: int) -> dict | None:
    row = conn.execute(
        'SELECT id, filename, record_count, submitted_at FROM cat_submissions WHERE id = %s',
        (submission_id,),
    ).fetchone()
    if row is None:
        return None
    return dict(zip(['id', 'filename', 'record_count', 'submitted_at'], row))


def get_findings(conn: psycopg.Connection, submission_id: int, line_no: int | None = None) -> list[dict]:
    if line_no is not None:
        rows = conn.execute(
            """
            SELECT line_no, event_type, field, error_code, severity, message
            FROM cat_findings WHERE submission_id = %s AND line_no = %s
            ORDER BY line_no
            """,
            (submission_id, line_no),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT line_no, event_type, field, error_code, severity, message
            FROM cat_findings WHERE submission_id = %s
            ORDER BY (severity = 'Error') DESC, line_no
            """,
            (submission_id,),
        ).fetchall()
    cols = ['line_no', 'event_type', 'field', 'error_code', 'severity', 'message']
    return [dict(zip(cols, row)) for row in rows]
