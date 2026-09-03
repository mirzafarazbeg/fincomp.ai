from __future__ import annotations

from services.rag import db
from services.rag.embed import embed_query


def retrieve(question: str, top_k: int = 5) -> list[dict]:
    query_vec = embed_query(question)
    conn = db.get_connection()
    try:
        rows = db.search(conn, query_vec, top_k=top_k)
    finally:
        conn.close()
    for r in rows:
        page = f' (p. {r["page_no"]})' if r['page_no'] else ''
        if r['section_ref'] and r['section_title']:
            r['citation'] = f'{r["document_title"]} §{r["section_ref"]} "{r["section_title"]}"{page}'
        else:
            r['citation'] = f'{r["document_title"]}{page}'
    return rows
