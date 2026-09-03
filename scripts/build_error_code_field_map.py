#!/usr/bin/env python3
"""Cross-reference the CAT error code catalog (Appendix E, Data Ingestion
section) against known field names (from the official schema + data
dictionary) to build a code -> field name(s) map.

This lets the validator emit the exact CAT error code for a field-level
failure (e.g. missing `accountHolderType` -> error 2001) instead of a
locally-invented message, which is the whole point of extracting the
catalog in the first place.

Matching is done by searching each error's merged description/explanation
text for any known field name as a whole word. This isn't perfect - the
Appendix E text extraction merged two PDF table columns without preserving
their boundary (see data/cat_reference/README.md), so a few entries don't
match cleanly - but field names are distinctive camelCase identifiers, so
false positives are unlikely; coverage is checked and printed below.

Usage:
    python3 scripts/build_error_code_field_map.py
"""
import json
import re

ERROR_CODES_PATH = 'data/cat_reference/cat_error_codes.json'
SCHEMA_PATH = 'docs/specs/cat_im_schema_v4.2.0.json'
DATA_DICT_PATH = 'data/cat_reference/cat_data_dictionary.json'
OUT_PATH = 'data/cat_reference/error_code_field_map.json'


def load_field_names() -> set[str]:
    schema = json.load(open(SCHEMA_PATH))
    names = {f['name'] for e in schema['eventDefinitions'] for f in e['fields']}
    names |= {r['field'] for r in json.load(open(DATA_DICT_PATH))}
    return names


def main() -> None:
    errors = json.load(open(ERROR_CODES_PATH))
    field_names = load_field_names()
    # Longest-first so e.g. "askAggregatedOrders" matches before "askPrice"-like
    # partial overlaps could confuse a naive pattern (defensive; \b already helps).
    sorted_fields = sorted(field_names, key=len, reverse=True)
    pattern = re.compile(r'\b(' + '|'.join(re.escape(f) for f in sorted_fields) + r')\b')

    mapping: dict[str, list[str]] = {}
    ingestion_total = 0
    ingestion_mapped = 0
    for r in errors:
        if r['section'] != 'E.2':  # Data Ingestion Errors - the field-level ones
            continue
        ingestion_total += 1
        matches = pattern.findall(r['text'])
        if matches:
            ingestion_mapped += 1
            # dedupe, preserve first-seen order
            seen = []
            for m in matches:
                if m not in seen:
                    seen.append(m)
            mapping[r['code']] = seen

    with open(OUT_PATH, 'w') as f:
        json.dump(mapping, f, indent=2)

    print(f'Mapped {ingestion_mapped}/{ingestion_total} Data Ingestion error codes to field name(s)')
    print(f'Wrote {OUT_PATH}')


if __name__ == '__main__':
    main()
