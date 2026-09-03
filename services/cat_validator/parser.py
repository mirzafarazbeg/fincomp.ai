"""Parses a CAT Data File (CSV or JSON, per Tech Spec Section 6.1.2) into raw
records: the event type plus a dict of populated field name -> raw string
value. Does not itself validate anything - that's rules.py.

`iter_records` streams one record at a time and is the memory-efficient path
for large files - `parse_file` (kept for convenience/tests on small fixtures)
just materializes it into a list, which is exactly the pattern that turned
out not to scale: see services/cat_validator/README.md's "Scale" section.
"""
from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass

from services.cat_validator import schema

TYPE_CSV_POSITION = 4  # confirmed constant across all 88 event definitions


@dataclass
class RawRecord:
    line_no: int
    event_type: str | None  # None if the type field itself couldn't be determined
    fields: dict[str, str]  # populated fields only; value is the raw string as submitted
    parse_error: str | None = None  # set if the record couldn't be parsed at all


def _detect_format(first_nonblank_line: str) -> str:
    return 'json' if first_nonblank_line.lstrip().startswith('{') else 'csv'


def parse_json_line(line_no: int, line: str) -> RawRecord:
    try:
        obj = json.loads(line)
    except json.JSONDecodeError as e:
        return RawRecord(line_no, None, {}, parse_error=f'Invalid JSON: {e}')
    event_type = obj.get('type')
    fields = {k: v for k, v in obj.items()}
    return RawRecord(line_no, event_type, fields)


def parse_csv_line(line_no: int, line: str) -> RawRecord:
    # Per spec: comma-delimited, no escaping needed since delimiter chars
    # cannot appear within a field value.
    values = line.split(',')
    if len(values) < TYPE_CSV_POSITION:
        return RawRecord(line_no, None, {}, parse_error='Line too short to contain a type field')
    event_type = values[TYPE_CSV_POSITION - 1].strip() or None
    if event_type is None:
        return RawRecord(line_no, None, {}, parse_error='Missing type field')

    event_def = schema.events().get(event_type)
    if event_def is None:
        return RawRecord(line_no, event_type, {}, parse_error=f'Unknown event type "{event_type}"')

    fields: dict[str, str] = {}
    for field_def in event_def.fields:
        idx = field_def.position - 1
        if idx >= len(values):
            break
        raw = values[idx].strip()
        if raw != '':
            fields[field_def.name] = raw
    return RawRecord(line_no, event_type, fields)


def iter_records(path: str) -> Iterator[RawRecord]:
    """Stream records one at a time - O(1) memory regardless of file size
    (aside from the line itself and whatever the caller does with each
    RawRecord). Prefer this over parse_file for anything beyond small
    fixtures/tests."""
    fmt = None
    with open(path, encoding='utf-8') as f:
        for line_no, raw_line in enumerate(f, start=1):
            line = raw_line.rstrip('\r\n')
            if not line.strip():
                continue
            if fmt is None:
                fmt = _detect_format(line)
            yield parse_json_line(line_no, line) if fmt == 'json' else parse_csv_line(line_no, line)


def parse_file(path: str) -> list[RawRecord]:
    """Convenience wrapper for small files/tests. Materializes every record
    in memory at once - see iter_records for the streaming alternative."""
    return list(iter_records(path))
