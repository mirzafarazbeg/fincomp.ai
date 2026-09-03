"""Parses a CAT Data File (CSV or JSON, per Tech Spec Section 6.1.2) into raw
records: the event type plus a dict of populated field name -> raw string
value. Does not itself validate anything - that's rules.py.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from services.cat_validator import schema

TYPE_CSV_POSITION = 4  # confirmed constant across all 88 event definitions


@dataclass
class RawRecord:
    line_no: int
    raw_line: str
    event_type: str | None  # None if the type field itself couldn't be determined
    fields: dict[str, str]  # populated fields only; value is the raw string as submitted
    parse_error: str | None = None  # set if the record couldn't be parsed at all


def _detect_format(first_nonblank_line: str) -> str:
    return 'json' if first_nonblank_line.lstrip().startswith('{') else 'csv'


def parse_json_line(line_no: int, line: str) -> RawRecord:
    try:
        obj = json.loads(line)
    except json.JSONDecodeError as e:
        return RawRecord(line_no, line, None, {}, parse_error=f'Invalid JSON: {e}')
    event_type = obj.get('type')
    fields = {k: v for k, v in obj.items()}
    return RawRecord(line_no, line, event_type, fields)


def parse_csv_line(line_no: int, line: str) -> RawRecord:
    # Per spec: comma-delimited, no escaping needed since delimiter chars
    # cannot appear within a field value.
    values = line.split(',')
    if len(values) < TYPE_CSV_POSITION:
        return RawRecord(line_no, line, None, {}, parse_error='Line too short to contain a type field')
    event_type = values[TYPE_CSV_POSITION - 1].strip() or None
    if event_type is None:
        return RawRecord(line_no, line, None, {}, parse_error='Missing type field')

    event_def = schema.events().get(event_type)
    if event_def is None:
        return RawRecord(line_no, line, event_type, {}, parse_error=f'Unknown event type "{event_type}"')

    fields: dict[str, str] = {}
    for field_def in event_def.fields:
        idx = field_def.position - 1
        if idx >= len(values):
            break
        raw = values[idx].strip()
        if raw != '':
            fields[field_def.name] = raw
    return RawRecord(line_no, line, event_type, fields)


def parse_file(path: str) -> list[RawRecord]:
    records = []
    fmt = None
    with open(path, encoding='utf-8') as f:
        for line_no, raw_line in enumerate(f, start=1):
            line = raw_line.rstrip('\r\n')
            if not line.strip():
                continue
            if fmt is None:
                fmt = _detect_format(line)
            record = parse_json_line(line_no, line) if fmt == 'json' else parse_csv_line(line_no, line)
            records.append(record)
    return records
