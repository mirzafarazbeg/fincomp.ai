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


def check_parent_child_linkage(records: list[RawRecord]) -> list[Finding]:
    order_keys: set[tuple[str, str]] = set()
    for r in records:
        if r.parse_error:
            continue
        order_id, order_key_date = r.fields.get('orderID'), r.fields.get('orderKeyDate')
        if order_id and order_key_date:
            order_keys.add((order_id, order_key_date))

    findings = []
    for r in records:
        if r.parse_error or r.event_type not in CHILD_ORDER_EVENTS:
            continue
        parent_id = r.fields.get('parentOrderID')
        parent_key_date = r.fields.get('parentOrderKeyDate')
        if not parent_id or not parent_key_date:
            continue  # presence for Required fields is already checked by rules.py
        if (parent_id, parent_key_date) not in order_keys:
            findings.append(Finding(
                r.line_no, r.event_type, 'parentOrderID', PARENT_NOT_FOUND_CODE, 'Error',
                f'parentOrderID "{parent_id}" / parentOrderKeyDate "{parent_key_date}" '
                f'does not match any orderID/orderKeyDate reported in this file',
            ))
    return findings
