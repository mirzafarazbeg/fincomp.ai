"""Loads the official CAT Industry Member schema (docs/specs/cat_im_schema_v4.2.0.json)
into lookup structures the parser and rules engine use.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache

SCHEMA_PATH = 'docs/specs/cat_im_schema_v4.2.0.json'
ERROR_FIELD_MAP_PATH = 'data/cat_reference/error_code_field_map.json'
ERROR_CODES_PATH = 'data/cat_reference/cat_error_codes.json'

TYPE_NAME_RE = re.compile(r'^([A-Za-z /]+?)(?:\s*\((\d+)(?:,(\d+))?\))?$')


@dataclass(frozen=True)
class TypeOption:
    """One acceptable data type for a field. A few fields (destination,
    senderIMID, receiverIMID) accept more than one type (e.g. either an
    Industry Member ID or an Exchange ID) - a value is valid if it satisfies
    ANY of a field's TypeOptions."""
    base_type: str
    # Inline size annotation from this type option, e.g. (64) on "Text (64)"
    # or (6,4) on "Numeric (6,4)". Meaning depends on base_type - maxLength
    # for Text/Alphanumeric, precision/scale for Numeric-family types. None
    # for types whose size comes from the canonical schema.data_types()
    # table instead (Symbol, CAT Reporter IMID, Price, etc).
    size1: int | None
    size2: int | None


@dataclass(frozen=True)
class FieldDef:
    name: str
    data_type: str  # raw string from the schema, e.g. "Text (64)" or "['Industry Member ID', 'Exchange ID']"
    types: list[TypeOption]
    json_data_type: object
    required: str  # "Required" | "Conditional" | "Optional"
    position: int


@dataclass(frozen=True)
class EventDef:
    name: str
    fields: list[FieldDef]  # in CSV position order

    def field(self, name: str) -> FieldDef | None:
        for f in self.fields:
            if f.name == name:
                return f
        return None


def _split_type(data_type: str) -> tuple[str, int | None, int | None]:
    m = TYPE_NAME_RE.match(data_type.strip())
    if not m:
        return data_type.strip(), None, None
    base = m.group(1).strip()
    a = int(m.group(2)) if m.group(2) else None
    b = int(m.group(3)) if m.group(3) else None
    return base, a, b


@lru_cache(maxsize=1)
def load() -> dict:
    return json.load(open(SCHEMA_PATH))


@lru_cache(maxsize=1)
def data_types() -> dict[str, dict]:
    return {dt['dataType']: dt for dt in load()['dataTypes']}


@lru_cache(maxsize=1)
def choices() -> dict[str, list]:
    return load()['choices']


@lru_cache(maxsize=1)
def name_value_pair_defs() -> dict[str, dict]:
    return {d['nameValuePair']: {f['name']: f for f in d['fields']} for d in load()['nameValuePairDefinitions']}


@lru_cache(maxsize=1)
def events() -> dict[str, EventDef]:
    result = {}
    for e in load()['eventDefinitions']:
        fields = []
        for f in e['fields']:
            raw_types = f['dataType'] if isinstance(f['dataType'], list) else [f['dataType']]
            types = [TypeOption(*_split_type(t)) for t in raw_types]
            fields.append(FieldDef(
                name=f['name'],
                data_type=str(f['dataType']),
                types=types,
                json_data_type=f['JSONDataType'],
                required=f['required'],
                position=int(f['position']),
            ))
        fields.sort(key=lambda f: f.position)
        result[e['eventName']] = EventDef(name=e['eventName'], fields=fields)
    return result


@lru_cache(maxsize=1)
def error_code_field_map() -> dict[str, list[str]]:
    """code -> [field names]. See scripts/build_error_code_field_map.py."""
    try:
        return json.load(open(ERROR_FIELD_MAP_PATH))
    except FileNotFoundError:
        return {}


@lru_cache(maxsize=1)
def error_codes_by_code() -> dict[str, dict]:
    return {e['code']: e for e in json.load(open(ERROR_CODES_PATH))}


@lru_cache(maxsize=1)
def field_error_codes() -> dict[str, list[str]]:
    """field name -> [error codes], using only each code's PRIMARY field (the
    first/leftmost field name matched in its text, which is reliably the
    field the error is actually about - see build_error_code_field_map.py).
    Using every field mentioned anywhere in a code's text (including
    incidental ones in combination-check explanations) would make most
    fields ambiguous."""
    inv: dict[str, list[str]] = {}
    for code, field_list in error_code_field_map().items():
        if field_list:
            inv.setdefault(field_list[0], []).append(code)
    return inv
