from __future__ import annotations

from services.cat_validator import linkage, parser, report, rules, store
from services.rag import db


def validate_and_store(file_path: str, filename: str) -> dict:
    records = parser.parse_file(file_path)
    findings = rules.validate_records(records) + linkage.check_parent_child_linkage(records)

    conn = db.get_connection()
    try:
        store.init_schema(conn)
        submission_id = store.create_submission(conn, filename, len(records))
        store.save_findings(conn, submission_id, findings)
    finally:
        conn.close()

    error_count = sum(1 for f in findings if f.severity == 'Error')
    warning_count = sum(1 for f in findings if f.severity == 'Warning')
    return {
        'submission_id': submission_id,
        'filename': filename,
        'record_count': len(records),
        'error_count': error_count,
        'warning_count': warning_count,
        'findings': report.to_dicts(findings),
    }
