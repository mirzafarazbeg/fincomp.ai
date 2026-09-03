#!/usr/bin/env python3
"""Extract the CAT field Data Dictionary (Appendix G) from the CAT Reporting
Technical Specifications PDF into structured JSON.

Requires the `pdftotext` CLI (poppler-utils) on PATH.

Usage:
    python3 scripts/extract_cat_data_dictionary.py \
        docs/specs/06.26.26_CAT_Reporting_Technical_Specifications_for_Industry_Members_v4.2.0r1_CLEAN.pdf \
        data/cat_reference/cat_data_dictionary.json

Known limitation: when a field's Data Type name wraps across the PDF's two
physical lines (e.g. "Aggregated" on line 1, "Orders" on line 2, with
description text interleaved between them), the type name can't be
recovered by text order alone. A small manual override table
(TYPE_OVERRIDES below) fixes the ~19 fields this affects in v4.2.0r1; if a
future spec version changes, re-run and check for entries with
data_type == null.
"""
import json
import re
import subprocess
import sys

DATA_TYPES = [
    'Multi-Dimensional Array', 'Aggregated Order Details', 'Trade Side Details',
    'Fulfillment Side Details', 'Leg Details', 'Aggregated Orders',
    'Name/Value Pairs', 'Real Quantity', 'Whole Quantity', 'Message Type',
    'CAT Reporter IMID', 'CAT Submitter ID', 'Industry Member ID', 'Exchange ID',
    'Numeric', 'Alphanumeric', 'Timestamp', 'Boolean', 'Choice', 'Text',
    'Date', 'Integer', 'Unsigned', 'Price', 'Symbol', 'Array',
]
DATA_TYPES.sort(key=len, reverse=True)
TYPE_RE = re.compile(
    r'^(' + '|'.join(re.escape(t) for t in DATA_TYPES) + r')(\s*\(\d+(?:,\d+)?\))?\s*(.*)$'
)
FIELD_START_RE = re.compile(r'^ (\S+)\s{2,}(\S.*)$')
NOISE_EXACT_PREFIXES = ('Version 4.2.0r1',)
ALPHABET_ROW_RE = re.compile(r'^([A-Z]\s+){10,}[A-Z]$')

# Fields whose Data Type name wraps across a PDF line break, defeating
# in-order text matching. Values taken from the CAT Tech Spec Table 3 (Data
# Types) and Appendix G context for v4.2.0r1.
TYPE_OVERRIDES = {
    'aggregatedOrders': 'Aggregated Orders',
    'askAggregatedOrders': 'Aggregated Order Details',
    'bidAggregatedOrders': 'Aggregated Order Details',
    'buyDetails': 'Trade Side Details',
    'sellDetails': 'Trade Side Details',
    'clientDetails': 'Fulfillment Side Details',
    'firmDetails': 'Fulfillment Side Details',
    'counterparty': 'Industry Member ID',
    'destination': 'Industry Member ID',
    'receiverIMID': 'Industry Member ID',
    'senderIMID': 'Industry Member ID',
    'displayQty': 'Whole Quantity',
    'minQty': 'Whole Quantity',
    'nbbQty': 'Whole Quantity',
    'nboQty': 'Whole Quantity',
    'numberOfLegs': 'Whole Quantity',
    'handlingInstructions': 'Name/Value Pairs',
    'timeInForce': 'Name/Value Pairs',
    'originatingIMID': 'CAT Reporter IMID',
}


def is_noise(stripped: str) -> bool:
    if not stripped:
        return True
    if stripped.startswith(NOISE_EXACT_PREFIXES):
        return True
    if ALPHABET_ROW_RE.match(stripped):
        return True
    if re.match(r'^Field Name\s+Data Type\s+Description$', stripped):
        return True
    if stripped == 'Appendix G: Data Dictionary':
        return True
    return False


def extract_appendix_g_text(pdf_path: str) -> str:
    raw = subprocess.run(
        ['pdftotext', '-layout', pdf_path, '-'],
        check=True, capture_output=True, text=True,
    ).stdout
    lines = raw.split('\n')
    # "Appendix G: Data Dictionary" also appears as a plain cross-reference
    # earlier in the document (e.g. in the change-log summary), so anchor on
    # the occurrence immediately followed by the A-Z index row that only
    # appears at the top of the real appendix.
    candidates = [i for i, l in enumerate(lines) if l.strip() == 'Appendix G: Data Dictionary']
    start = next(i for i in candidates
                 if any(ALPHABET_ROW_RE.match(lines[j].strip()) for j in range(i, min(i + 5, len(lines)))))
    end = next(i for i in range(start, len(lines))
               if lines[i].strip().startswith('Appendix H: Processing Stages'))
    return '\n'.join(lines[start:end])


def parse_field_blocks(text: str) -> list[dict]:
    raw_records = []
    cur = None

    def flush():
        nonlocal cur
        if cur:
            raw_records.append(cur)
        cur = None

    for raw_line in text.split('\n'):
        line = raw_line.rstrip('\n')
        stripped = line.strip()
        if is_noise(stripped):
            continue
        m = FIELD_START_RE.match(line)
        is_field_start = bool(m and re.match(r'^[a-z][A-Za-z0-9]*$', m.group(1)))
        if is_field_start:
            flush()
            cur = {'field': m.group(1), 'parts': [m.group(2)]}
        elif cur is not None:
            cur['parts'].append(stripped)
    flush()

    # Merge consecutive blocks for the same field: the spec repeats
    # "fieldName (continued)" as a table header at each page break.
    merged = []
    for r in raw_records:
        if merged and merged[-1]['field'] == r['field']:
            merged[-1]['parts'].append('(continued)')
            merged[-1]['parts'].extend(r['parts'])
        else:
            merged.append({'field': r['field'], 'parts': list(r['parts'])})
    return merged


def resolve_types(blocks: list[dict]) -> list[dict]:
    records = []
    for r in blocks:
        joined = re.sub(r'\s+', ' ', ' '.join(w for w in r['parts'] if w)).strip()
        tm = TYPE_RE.match(joined)
        if tm:
            dtype = tm.group(1) + (tm.group(2) or '')
            desc = tm.group(3).strip()
            inferred = False
        elif r['field'] in TYPE_OVERRIDES:
            dtype = TYPE_OVERRIDES[r['field']]
            desc = joined
            inferred = True
        else:
            dtype = None
            desc = joined
            inferred = False
        rec = {'field': r['field'], 'data_type': dtype, 'description': desc}
        if inferred:
            rec['data_type_inferred'] = True
        records.append(rec)
    return records


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    pdf_path, out_path = sys.argv[1], sys.argv[2]
    text = extract_appendix_g_text(pdf_path)
    records = resolve_types(parse_field_blocks(text))
    unresolved = [r['field'] for r in records if r['data_type'] is None]
    with open(out_path, 'w') as f:
        json.dump(records, f, indent=2)
    print(f'Extracted {len(records)} fields to {out_path}')
    if unresolved:
        print(f'WARNING: {len(unresolved)} fields have no resolved data_type: {unresolved}')


if __name__ == '__main__':
    main()
