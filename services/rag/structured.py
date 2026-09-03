"""Turn the extracted CAT reference JSON (error codes, data dictionary) into
RAG chunks — one per code/field, as readable prose rather than raw JSON, so
retrieval on questions like "what does error 2019 mean" or "what type is
askPrice" hits a clean, citable chunk instead of a mangled table fragment
from the PDF appendix.
"""
from __future__ import annotations

import json

from services.rag.chunker import Chunk

ERROR_CODES_DOC = 'CAT Error Code Catalog (Appendix E)'
DATA_DICT_DOC = 'CAT Data Dictionary (Appendix G)'


def chunks_from_error_codes(json_path: str) -> list[Chunk]:
    records = json.load(open(json_path))
    chunks = []
    for r in records:
        severity = r['severity'] or 'Unknown'
        text = (
            f"CAT Error Code {r['code']} ({severity}) — {r['section_name']}.\n"
            f"{r['text']}"
        )
        chunks.append(Chunk(
            document=ERROR_CODES_DOC,
            page_no=0,
            section_ref=r['section'],
            section_title=f"Error Code {r['code']}: {r['section_name']}",
            text=text,
        ))
    return chunks


def chunks_from_data_dictionary(json_path: str) -> list[Chunk]:
    records = json.load(open(json_path))
    chunks = []
    for r in records:
        text = f"CAT field `{r['field']}` — Data Type: {r['data_type']}.\n{r['description']}"
        chunks.append(Chunk(
            document=DATA_DICT_DOC,
            page_no=0,
            section_ref=r['field'],
            section_title=f"Field: {r['field']} ({r['data_type']})",
            text=text,
        ))
    return chunks
