#!/usr/bin/env python3
"""Validate a CAT Data File (CSV or JSON, per Tech Spec Section 6.1.2).

Usage:
    python3 -m services.cat_validator.cli <file> [--json]
"""
from __future__ import annotations

import sys

from services.cat_validator import engine, report


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    path = sys.argv[1]
    as_json = '--json' in sys.argv[2:]

    findings, _record_count = engine.validate_file(path)

    print(report.to_json(findings) if as_json else report.to_text(findings))
    if any(f.severity == 'Error' for f in findings):
        sys.exit(1)


if __name__ == '__main__':
    main()
