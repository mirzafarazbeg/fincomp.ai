from __future__ import annotations

import re

from services.rag import db
from services.rag.embed import embed_query

# Matches "error code 2019", "error 2019", "error code #2019", etc. Used to
# short-circuit to an exact lookup instead of relying on vector similarity,
# which is unreliable for exact numeric IDs - see db.search_by_section_title_prefix.
ERROR_CODE_RE = re.compile(r'\berror\s*(?:code)?\s*#?\s*(\d{3,4})\b', re.IGNORECASE)


def retrieve(question: str, top_k: int = 5) -> list[dict]:
    conn = db.get_connection()
    try:
        exact_rows = []
        m = ERROR_CODE_RE.search(question)
        if m:
            exact_rows = db.search_by_section_title_prefix(
                conn, f'Error Code {m.group(1)}:', limit=2
            )
        vector_rows = db.search(conn, embed_query(question), top_k=top_k)
    finally:
        conn.close()

    seen: set[str] = set()
    rows: list[dict] = []
    for r in exact_rows + vector_rows:
        if r['text'] in seen:
            continue
        seen.add(r['text'])
        rows.append(r)
    rows = rows[:top_k]

    for r in rows:
        page = f' (p. {r["page_no"]})' if r['page_no'] else ''
        if r['section_ref'] and r['section_title']:
            r['citation'] = f'{r["document_title"]} §{r["section_ref"]} "{r["section_title"]}"{page}'
        else:
            r['citation'] = f'{r["document_title"]}{page}'
    return rows
