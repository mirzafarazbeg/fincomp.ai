"""Memory-efficient orchestration for validating a whole file: two streaming
passes over the file (never materializing all records at once) instead of
parser.parse_file's "load everything into a list" convenience path.

Pass 1 builds the linkage index (parentOrderID lookups need to see the whole
file first). Pass 2 re-reads the file and runs both per-record field
validation and the linkage check against that index, one record at a time.

Why two file reads instead of one: linkage checking is inherently two-phase
(you can't know if a parent order exists until you've seen the whole file),
but a record's own field validation doesn't depend on any other record. Re-
reading the file is cheap (sequential I/O, OS page cache does the rest);
holding every record in memory at once is what actually didn't scale - see
services/cat_validator/README.md's "Scale" section for real numbers.
"""
from __future__ import annotations

from services.cat_validator import linkage, parser, rules
from services.cat_validator.rules import Finding


def validate_file(path: str) -> tuple[list[Finding], int]:
    """Returns (findings, record_count)."""
    order_keys = linkage.build_order_key_index(parser.iter_records(path))

    findings: list[Finding] = []
    record_count = 0
    for record in parser.iter_records(path):
        record_count += 1
        findings.extend(rules.validate_record(record))
        findings.extend(linkage.check_record_linkage(record, order_keys))
    return findings, record_count
