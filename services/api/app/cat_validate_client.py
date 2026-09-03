from __future__ import annotations

from services.cat_validator import engine, report, store
from services.rag import db


def validate_and_store(file_path: str, filename: str) -> dict:
    findings, record_count = engine.validate_file(file_path)

    conn = db.get_connection()
    try:
        store.init_schema(conn)
        submission_id = store.create_submission(conn, filename, record_count)
        store.save_findings(conn, submission_id, findings)
    finally:
        conn.close()

    error_count = sum(1 for f in findings if f.severity == 'Error')
    warning_count = sum(1 for f in findings if f.severity == 'Warning')
    return {
        'submission_id': submission_id,
        'filename': filename,
        'record_count': record_count,
        'error_count': error_count,
        'warning_count': warning_count,
        'findings': report.to_dicts(findings),
    }
