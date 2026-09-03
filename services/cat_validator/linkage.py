"""Cross-record linkage checks (CAT Tech Spec Appendix E.3, "Linkage
Discovery Errors") - as opposed to rules.py, which only validates a record
against itself.

v1 scope: parent -> child order linkage only. A Child Order event (equity
MECO, option MOCO, multi-leg MLCO) or Internal Route Accepted event (MEIR/
MOIR/MLIR) carries a parentOrderID/parentOrderKeyDate pointing at the order
it was generated from; that pair must match the orderID/orderKeyDate of some
other event actually present. This is exactly what CAT error code 3501
("Secondary Event ... references an Order Key ... that does not exist in
CAT") covers.

Known limitation: only checks linkage WITHIN the uploaded file. Real CAT
linkage discovery also checks across previously-submitted files (a parent
order reported yesterday, or later today in a different file) - a valid
cross-file parent reference will be flagged here as broken. Extending this
to check against cat_findings/other stored submissions in Postgres is the
natural next step if this proves too noisy in practice.
"""
from __future__ import annotations

from collections.abc import Iterable

from services.cat_validator.parser import RawRecord
from services.cat_validator.rules import Finding
from services.cat_validator.schema import events as schema_events

# Event types with a parentOrderID/parentOrderKeyDate field (schema-derived,
# not hardcoded - see services/cat_validator/README.md if this needs
# re-deriving after a schema update).
CHILD_ORDER_EVENTS = frozenset(
    name for name, ev in schema_events().items() if ev.field('parentOrderID')
)

PARENT_NOT_FOUND_CODE = '3501'

OrderKey = tuple[str, str]


def build_order_key_index(records: Iterable[RawRecord]) -> set[OrderKey]:
    """One (orderID, orderKeyDate) pair per record that has both - the
    lightweight index parent references get checked against. Takes any
    iterable, so it works equally over an in-memory list or a streaming
    parser.iter_records() generator (memory cost is O(distinct order keys),
    not O(record size) - each entry is two short strings, not a whole
    parsed record).
    """
    order_keys: set[OrderKey] = set()
    for r in records:
        if r.parse_error:
            continue
        order_id, order_key_date = r.fields.get('orderID'), r.fields.get('orderKeyDate')
        if order_id and order_key_date:
            order_keys.add((order_id, order_key_date))
    return order_keys


def check_record_linkage(r: RawRecord, order_keys: set[OrderKey]) -> list[Finding]:
    """Check a single record's parent reference against an already-built
    index. This is the streaming-friendly entry point - call once per
    record after build_order_key_index has been run over the whole file."""
    if r.parse_error or r.event_type not in CHILD_ORDER_EVENTS:
        return []
    parent_id = r.fields.get('parentOrderID')
    parent_key_date = r.fields.get('parentOrderKeyDate')
    if not parent_id or not parent_key_date:
        return []  # presence for Required fields is already checked by rules.py
    if (parent_id, parent_key_date) in order_keys:
        return []
    return [Finding(
        r.line_no, r.event_type, 'parentOrderID', PARENT_NOT_FOUND_CODE, 'Error',
        f'parentOrderID "{parent_id}" / parentOrderKeyDate "{parent_key_date}" '
        f'does not match any orderID/orderKeyDate reported in this file',
    )]


def check_parent_child_linkage(records: list[RawRecord]) -> list[Finding]:
    """Convenience wrapper for small in-memory record lists (tests,
    fixtures). For large files, build the index and call check_record_linkage
    per record while streaming instead - see cat_validator.engine.validate_file."""
    order_keys = build_order_key_index(records)
    findings = []
    for r in records:
        findings.extend(check_record_linkage(r, order_keys))
    return findings
