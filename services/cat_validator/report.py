"""Turns a list of Findings into a human/JSON report."""
from __future__ import annotations

import json

from services.cat_validator.rules import Finding


def to_dicts(findings: list[Finding]) -> list[dict]:
    return [
        {
            'line': f.line_no,
            'event_type': f.event_type,
            'field': f.field,
            'error_code': f.error_code,
            'severity': f.severity,
            'message': f.message,
        }
        for f in findings
    ]


def to_json(findings: list[Finding]) -> str:
    return json.dumps(to_dicts(findings), indent=2)


def to_text(findings: list[Finding]) -> str:
    if not findings:
        return 'No findings - all records passed validation.'
    lines = []
    for f in findings:
        code = f'[{f.error_code}]' if f.error_code else '[no CAT code]'
        sev = f.severity or 'Error'
        loc = f'line {f.line_no}'
        if f.event_type:
            loc += f' ({f.event_type})'
        lines.append(f'{sev:7} {code:10} {loc}: {f.message}')
    lines.append('')
    lines.append(f'{len(findings)} finding(s) across {len({f.line_no for f in findings})} record(s).')
    return '\n'.join(lines)
