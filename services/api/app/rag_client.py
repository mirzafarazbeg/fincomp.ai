from __future__ import annotations

import re

from services.cat_validator import store
from services.rag import db
from services.rag.embed import embed_query

# Matches "error code 2019", "error 2019", "error code #2019", etc. Used to
# short-circuit to an exact lookup instead of relying on vector similarity,
# which is unreliable for exact numeric IDs - see db.search_by_section_title_prefix.
ERROR_CODE_RE = re.compile(r'\berror\s*(?:code)?\s*#?\s*(\d{3,4})\b', re.IGNORECASE)

# Matches "record 45", "line 45", "row #45" - used to scope CAT validation
# findings to a specific line when a submission_id is given.
LINE_NO_RE = re.compile(r'\b(?:record|line|row)\s*#?\s*(\d+)\b', re.IGNORECASE)

MAX_FINDINGS_IN_CONTEXT = 10


def _to_row(text: str, document_title: str, section_ref: str | None, section_title: str | None) -> dict:
    return {
        'text': text, 'document_title': document_title, 'section_ref': section_ref,
        'section_title': section_title, 'page_no': None, 'distance': 0.0,
    }


def _finding_rows(conn, submission_id: int, question: str) -> list[dict]:
    """CAT validation findings for `submission_id`, plus the spec's own
    explanation for each distinct error code among them (reusing the same
    exact-match lookup used for direct error-code questions) - so the model
    can explain *why* a finding is wrong, not just repeat the finding text.
    """
    m = LINE_NO_RE.search(question)
    line_no = int(m.group(1)) if m else None
    findings = store.get_findings(conn, submission_id, line_no=line_no)
    findings = findings[:MAX_FINDINGS_IN_CONTEXT]

    rows = []
    for f in findings:
        code_part = f' [{f["error_code"]}]' if f['error_code'] else ''
        text = f'{f["severity"] or "Error"}{code_part}: {f["message"]}'
        rows.append(_to_row(text, 'CAT Validation Finding', f'line {f["line_no"]}', f['event_type']))

    codes = {f['error_code'] for f in findings if f['error_code']}
    for code in codes:
        rows.extend(db.search_by_section_title_prefix(conn, f'Error Code {code}:', limit=1))
    return rows


def retrieve(question: str, top_k: int = 5, submission_id: int | None = None) -> list[dict]:
    conn = db.get_connection()
    try:
        priority_rows = []
        m = ERROR_CODE_RE.search(question)
        if m:
            priority_rows += db.search_by_section_title_prefix(conn, f'Error Code {m.group(1)}:', limit=2)
        if submission_id is not None:
            priority_rows += _finding_rows(conn, submission_id, question)
        vector_rows = db.search(conn, embed_query(question), top_k=top_k)
    finally:
        conn.close()

    seen: set[str] = set()
    rows: list[dict] = []
    for r in priority_rows + vector_rows:
        if r['text'] in seen:
            continue
        seen.add(r['text'])
        rows.append(r)
    # priority_rows (findings + exact matches) are never trimmed for a
    # submission-scoped question - they're the point of asking; only the
    # supplementary vector-search rows are capped to top_k.
    rows = rows[:len(priority_rows) + top_k]

    for r in rows:
        page = f' (p. {r["page_no"]})' if r['page_no'] else ''
        if r['section_ref'] and r['section_title']:
            r['citation'] = f'{r["document_title"]} §{r["section_ref"]} "{r["section_title"]}"{page}'
        else:
            r['citation'] = f'{r["document_title"]}{page}'
    return rows
