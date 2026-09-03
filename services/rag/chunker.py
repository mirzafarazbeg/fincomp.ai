"""Section-aware chunking of the FINRA/SEC/CAT spec PDFs for the RAG index.

Splits a PDF into ~200-400 word chunks, each tagged with the nearest
preceding numbered heading (e.g. "2.6.1 CAT Linkage Keys") and the PDF page
number it came from, so retrieval results can cite a real spec location
instead of a blind token offset.

Requires the `pdftotext` CLI (poppler-utils) on PATH.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field

TARGET_WORDS = 300
MIN_WORDS = 60

HEADING_RE = re.compile(
    r'^\s{0,20}(\d+(?:\.\d+){0,4}\.?)\s{2,}(\S.*\S)$'
)
APPENDIX_HEADING_RE = re.compile(r'^Appendix [A-Z]: .+$')
APPENDIX_SUB_RE = re.compile(r'^\s{0,20}([A-Z]\.\d+)\.?\s{2,}(\S.*\S)$')
FOOTER_RE = re.compile(r'^(Version [\d.rR]+|CAT NMS Plan)\s')
DOT_LEADER_RE = re.compile(r'\.{4,}')


@dataclass
class Chunk:
    document: str
    page_no: int
    section_ref: str | None
    section_title: str | None
    text: str

    @property
    def citation(self) -> str:
        page = f' (p. {self.page_no})' if self.page_no else ''
        if self.section_ref and self.section_title:
            return f'{self.document} §{self.section_ref} "{self.section_title}"{page}'
        return f'{self.document}{page}'


def _is_heading(line: str) -> tuple[str, str] | None:
    """Return (ref, title) if `line` looks like a body heading, else None."""
    stripped = line.strip()
    if not stripped or DOT_LEADER_RE.search(stripped):
        return None
    if APPENDIX_HEADING_RE.match(stripped):
        head, _, title = stripped.partition(':')
        return head.strip(), title.strip()
    m = APPENDIX_SUB_RE.match(line)
    if m:
        return m.group(1), m.group(2)
    m = HEADING_RE.match(line)
    if m:
        ref, title = m.group(1).rstrip('.'), m.group(2)
        if len(title) > 100 or title[-1].isdigit():
            return None
        return ref, title
    return None


def _is_noise(stripped: str) -> bool:
    if not stripped:
        return True
    if FOOTER_RE.match(stripped):
        return True
    if DOT_LEADER_RE.search(stripped):
        return True
    return False


def _pdf_pages(pdf_path: str) -> list[str]:
    raw = subprocess.run(
        ['pdftotext', '-layout', pdf_path, '-'],
        check=True, capture_output=True, text=True,
    ).stdout
    return raw.split('\x0c')


def chunk_pdf(pdf_path: str, document_name: str, start_page: int = 1) -> list[Chunk]:
    """Chunk a PDF starting from `start_page` (1-based), skipping front matter/TOC."""
    pages = _pdf_pages(pdf_path)
    chunks: list[Chunk] = []

    cur_ref: str | None = None
    cur_title: str | None = None
    buf: list[str] = []
    buf_page: int | None = None

    def flush():
        nonlocal buf, buf_page
        text = '\n'.join(buf).strip()
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        if len(text.split()) >= MIN_WORDS or (text and not chunks):
            if text:
                chunks.append(Chunk(document_name, buf_page or 1, cur_ref, cur_title, text))
        elif text and chunks:
            # too short on its own - fold into the previous chunk
            chunks[-1] = Chunk(
                chunks[-1].document, chunks[-1].page_no,
                chunks[-1].section_ref, chunks[-1].section_title,
                (chunks[-1].text + '\n' + text).strip(),
            )
        buf = []
        buf_page = None

    for page_no, page_text in enumerate(pages, start=1):
        if page_no < start_page:
            continue
        for raw_line in page_text.split('\n'):
            line = raw_line.rstrip('\n')
            stripped = line.strip()
            heading = _is_heading(line)
            if heading:
                flush()
                cur_ref, cur_title = heading
                continue
            if _is_noise(stripped):
                continue
            if buf_page is None:
                buf_page = page_no
            buf.append(stripped)
            if sum(len(w.split()) for w in buf) >= TARGET_WORDS:
                flush()
    flush()
    return chunks
