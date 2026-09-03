#!/usr/bin/env python3
"""Regression check for the CAT file validator against the fixtures in
data/eval/cat_validator/. No LLM/GPU/DB needed - pure logic, runs anywhere.

Usage:
    python3 -m services.cat_validator.selftest
"""
from __future__ import annotations

import sys

from services.cat_validator import linkage, parser, rules

FIXTURES_DIR = 'data/eval/cat_validator'

CASES = [
    ('valid_meno.csv', lambda findings: len(findings) == 0),
    ('valid_meno.json', lambda findings: len(findings) == 0),
    (
        'missing_required.csv',
        lambda findings: any(f.field == 'firmROEID' and 'Missing required' in f.message for f in findings),
    ),
    (
        'invalid_choice.csv',
        lambda findings: any(f.field == 'side' and 'not an allowed value' in f.message for f in findings),
    ),
    (
        'invalid_boolean.csv',
        lambda findings: any(
            f.field == 'manualFlag' and f.error_code == '2041' and 'not a valid Boolean' in f.message
            for f in findings
        ),
    ),
    (
        'invalid_timestamp.csv',
        lambda findings: any(f.field == 'eventTimestamp' and 'not a valid Timestamp' in f.message for f in findings),
    ),
    (
        # Regression guard: Numeric(a,b) in the CAT spec means "max a digits
        # before the decimal, max b after" (Tech Spec Section 2.5.1) - not
        # SQL NUMERIC(precision,scale) where precision is the total digit
        # count. A price like 135.0000 against Price's (10,8) must pass;
        # this caught a real bug (153K false positives on a ~600K-record
        # real-world file) where it was being rejected.
        'multi_digit_price.csv',
        lambda findings: len(findings) == 0,
    ),
    (
        'unknown_event_type.csv',
        lambda findings: any('Unknown event type' in f.message for f in findings),
    ),
    (
        'child_order_orphan.csv',
        lambda findings: any(
            f.field == 'parentOrderID' and f.error_code == '3501' and 'does not match any orderID' in f.message
            for f in findings
        ),
    ),
    (
        'child_order_linked.csv',
        lambda findings: len(findings) == 0,
    ),
]


def main() -> None:
    passed = 0
    for filename, check in CASES:
        path = f'{FIXTURES_DIR}/{filename}'
        records = parser.parse_file(path)
        findings = rules.validate_records(records) + linkage.check_parent_child_linkage(records)
        ok = check(findings)
        status = 'PASS' if ok else 'FAIL'
        print(f'[{status}] {filename}')
        if ok:
            passed += 1
        else:
            for f in findings:
                print(f'         got: line={f.line_no} field={f.field} code={f.error_code} msg={f.message}')
    print(f'\n{passed}/{len(CASES)} passed')
    if passed < len(CASES):
        sys.exit(1)


if __name__ == '__main__':
    main()
