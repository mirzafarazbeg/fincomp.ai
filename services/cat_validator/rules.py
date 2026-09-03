"""Field-level validation rules, driven entirely by the official CAT schema
(docs/specs/cat_im_schema_v4.2.0.json) - no hardcoded per-event knowledge.

Deliberately conservative about what it claims to check: known limitations
(compound/array field types not deeply validated, Conditional field presence
not evaluated since the schema doesn't encode *when* a Conditional field is
required) are documented in services/cat_validator/README.md, not silently
glossed over.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from services.cat_validator import schema
from services.cat_validator.parser import RawRecord

TIMESTAMP_STRING_RE = re.compile(
    r'^\d{8}[T ]\d{6}(\.\d{1,9})?$'
)
TIMESTAMP_NUMBER_RE = re.compile(r'^\d{1,20}$')

# Base types whose values must not be negative (per their Table 3 definitions
# in the Tech Spec - Whole/Real Quantity and Unsigned are explicitly
# non-negative; Date is an 8-digit YYYYMMDD integer).
NON_NEGATIVE_TYPES = {'Whole Quantity', 'Real Quantity', 'Unsigned', 'Date'}

# Compound/array/nested types not deeply validated in this version - see
# services/cat_validator/README.md. Presence (Required-field-missing) is
# still checked; internal structure/format is not.
UNVALIDATED_COMPOUND_TYPES = {
    'Aggregated Orders', 'Aggregated Order Details', 'Trade Side Details',
    'Fulfillment Side Details', 'Leg Details', 'Multi-Dimensional Array',
    'Array', 'Name/Value Pairs',
}


@dataclass
class Finding:
    line_no: int
    event_type: str | None
    field: str | None
    error_code: str | None
    severity: str | None  # "Error" | "Warning" | None (no matching CAT code found)
    message: str


def _lookup_code(field_name: str) -> tuple[str | None, str | None]:
    """Best-effort: field name -> (error_code, severity), via the
    code<->field map built from Appendix E (data/cat_reference/error_code_field_map.json).
    Returns (None, None) if no single unambiguous code maps to this field.
    """
    codes = schema.field_error_codes().get(field_name)
    if not codes or len(codes) != 1:
        return None, None
    entry = schema.error_codes_by_code().get(codes[0])
    return codes[0], (entry['severity'] if entry else None)


def _check_numeric(value: str, max_int_digits: int | None, scale: int | None, allow_negative: bool) -> bool:
    """`max_int_digits`/`scale` follow the CAT spec's own Numeric(a,b) convention
    (Tech Spec Section 2.5.1): a = max digits BEFORE the decimal point, b = max
    digits after - NOT the SQL NUMERIC(precision,scale) convention where
    precision is the *total* digit count. Mixing these up rejects any value
    with more integer digits than (a - b), which is wrong - e.g. it would
    reject "135.00" against Price's (10,8) even though 135 is nowhere near
    the spec's stated max of 9999999999.
    """
    v = value
    if allow_negative and v.startswith('-'):
        v = v[1:]
    if not allow_negative and v.startswith('-'):
        return False
    if scale and scale > 0:
        if '.' not in v:
            int_part, frac_part = v, ''
        else:
            int_part, frac_part = v.split('.', 1)
        if not int_part.isdigit() or not (frac_part == '' or frac_part.isdigit()):
            return False
        if max_int_digits and len(int_part) > max_int_digits:
            return False
        if len(frac_part) > scale:
            return False
    else:
        if '.' in v:
            return False
        if not v.isdigit():
            return False
        if max_int_digits and len(v) > max_int_digits:
            return False
    return True


def _check_value(field_def: 'schema.FieldDef', value: str) -> str | None:
    """Returns an error description if `value` is invalid for every type
    option on `field_def` (most fields have exactly one; a few - destination,
    senderIMID, receiverIMID - accept any of several), else None."""
    errors = []
    for type_option in field_def.types:
        error = _check_type_option(field_def.name, type_option, value)
        if error is None:
            return None
        errors.append(error)
    return '; or '.join(errors)


def _check_type_option(field_name: str, type_option: 'schema.TypeOption', value) -> str | None:
    base = type_option.base_type

    # JSON submissions carry native types (NUMBER, BOOLEAN, OBJECT/ARRAY for
    # compound fields); CSV is always strings. Coerce scalars to strings so
    # the checks below are format-agnostic. Compound values (dict/list, for
    # the Name/Value Pairs & Aggregated Orders-style types) are left as-is -
    # they're never inspected since UNVALIDATED_COMPOUND_TYPES returns before
    # any string operation would run on them.
    if not isinstance(value, (dict, list)):
        value = str(value)

    if base == 'Choice':
        allowed = schema.choices().get(field_name)
        if allowed is not None and value not in allowed:
            return f'"{value}" is not an allowed value (expected one of {allowed})'
        return None

    if base == 'Boolean':
        if value.lower() not in ('true', 'false'):
            return f'"{value}" is not a valid Boolean (expected true/false)'
        return None

    if base == 'Timestamp':
        if TIMESTAMP_STRING_RE.match(value) or TIMESTAMP_NUMBER_RE.match(value):
            return None
        return f'"{value}" is not a valid Timestamp (expected YYYYMMDDTHHMMSS[.ffffff...] or nanosecond epoch)'

    if base in ('Text', 'Alphanumeric'):
        max_len = type_option.size1
        if max_len is not None and len(value) > max_len:
            return f'value exceeds max length {max_len} ({len(value)} chars)'
        if base == 'Alphanumeric' and not re.match(r'^[A-Za-z0-9]*$', value):
            return 'Alphanumeric field must contain only letters and digits'
        return None

    if base == 'Numeric':
        if not _check_numeric(value, type_option.size1, type_option.size2, allow_negative=True):
            return f'"{value}" does not match Numeric ({type_option.size1},{type_option.size2})'
        return None

    canonical = schema.data_types().get(base)
    if canonical and canonical.get('JSONDataType') == 'NUMBER':
        precision = canonical.get('precision')
        scale = canonical.get('scale', 0)
        allow_negative = base not in NON_NEGATIVE_TYPES
        if not _check_numeric(value, precision, scale, allow_negative):
            return f'"{value}" does not match {base} (precision {precision}, scale {scale})'
        return None

    if canonical and 'allowedValues' in canonical:
        if value not in canonical['allowedValues']:
            return f'"{value}" is not an allowed value for {base}'
        return None

    if canonical and canonical.get('JSONDataType') == 'STRING':
        max_len = canonical.get('maxLength')
        if max_len is not None and len(value) > max_len:
            return f'value exceeds max length {max_len} ({len(value)} chars)'
        return None

    if base in UNVALIDATED_COMPOUND_TYPES:
        return None  # presence-only, see module docstring

    return None  # unknown/unhandled type - don't fail closed on something we don't model


def validate_record(record: RawRecord) -> list[Finding]:
    findings: list[Finding] = []

    if record.parse_error:
        findings.append(Finding(record.line_no, record.event_type, None, None, 'Error', record.parse_error))
        return findings

    event_def = schema.events().get(record.event_type)
    if event_def is None:
        findings.append(Finding(
            record.line_no, record.event_type, None, None, 'Error',
            f'Unknown event type "{record.event_type}"',
        ))
        return findings

    for field_def in event_def.fields:
        value = record.fields.get(field_def.name)
        if value is None:
            if field_def.required == 'Required':
                code, severity = _lookup_code(field_def.name)
                findings.append(Finding(
                    record.line_no, record.event_type, field_def.name, code,
                    severity or 'Error',
                    f'Missing required field "{field_def.name}"',
                ))
            continue
        error = _check_value(field_def, value)
        if error:
            code, severity = _lookup_code(field_def.name)
            findings.append(Finding(
                record.line_no, record.event_type, field_def.name, code,
                severity or 'Error',
                f'Field "{field_def.name}": {error}',
            ))

    return findings


def validate_records(records: list[RawRecord]) -> list[Finding]:
    findings = []
    for r in records:
        findings.extend(validate_record(r))
    return findings
