#!/usr/bin/env python3
"""Extract the CAT error code catalog (Appendix E) from the CAT Reporting
Technical Specifications PDF into structured JSON.

Requires the `pdftotext` CLI (poppler-utils) on PATH.

Usage:
    python3 scripts/extract_cat_error_codes.py \
        docs/specs/06.26.26_CAT_Reporting_Technical_Specifications_for_Industry_Members_v4.2.0r1_CLEAN.pdf \
        data/cat_reference/cat_error_codes.json
"""
import json
import re
import subprocess
import sys

SECTION_RE = re.compile(r'^E\.(\d)\s+(.*)')
CODE_START_RE = re.compile(r'^ ?(\d{3,4})\s+(\S.*)$')
SEV_END_RE = re.compile(r'\s+(Error|Warning)\s*$')
SKIP_PREFIXES = (
    'Version 4.2.0r1', 'Table ', 'The table below', 'The tables below',
    'Error', 'Code', 'Warnings are not required', 'be repaired',
    'files and filenames.', 'specific fields within an event.',
    'Codes are separated by Linkage type.',
)
SKIP_EXACT = (
    'Description              Explanation',
    'Code    Error Code Description        Explanation',
    'Warning',
)


def extract_appendix_e_text(pdf_path: str) -> str:
    raw = subprocess.run(
        ['pdftotext', '-layout', pdf_path, '-'],
        check=True, capture_output=True, text=True,
    ).stdout
    lines = raw.split('\n')
    start = next(i for i, l in enumerate(lines) if l.strip().startswith('E.1') and 'File Integrity' in l)
    end = next(i for i, l in enumerate(lines) if l.strip() == 'Appendix F: Glossary')
    return '\n'.join(lines[start:end])


def parse_error_codes(text: str) -> list[dict]:
    records = []
    cur = None
    section = section_name = None

    def flush():
        nonlocal cur
        if cur:
            body = ' '.join(w for w in cur['text_parts'] if w).strip()
            body = re.sub(r'\s+', ' ', body)
            records.append({
                'code': cur['code'],
                'section': cur['section'],
                'section_name': cur['section_name'],
                'severity': cur['severity'],
                'text': body,
            })
        cur = None

    for raw_line in text.split('\n'):
        line = raw_line.rstrip('\n')
        stripped = line.strip()
        if not stripped:
            continue
        m = SECTION_RE.match(stripped)
        if m:
            flush()
            section = 'E.' + m.group(1)
            section_name = m.group(2).strip()
            continue
        if stripped.startswith(SKIP_PREFIXES) or stripped in SKIP_EXACT:
            continue
        m2 = CODE_START_RE.match(line)
        if m2:
            flush()
            code, rest = m2.group(1), m2.group(2)
            sev = None
            sm = SEV_END_RE.search(rest)
            if sm:
                sev = sm.group(1)
                rest = rest[:sm.start()].rstrip()
            cur = {'code': code, 'section': section, 'section_name': section_name,
                   'severity': sev, 'text_parts': [rest]}
        elif cur:
            cur['text_parts'].append(stripped)
    flush()
    return records


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    pdf_path, out_path = sys.argv[1], sys.argv[2]
    text = extract_appendix_e_text(pdf_path)
    records = parse_error_codes(text)
    with open(out_path, 'w') as f:
        json.dump(records, f, indent=2)
    print(f'Extracted {len(records)} error codes to {out_path}')


if __name__ == '__main__':
    main()
