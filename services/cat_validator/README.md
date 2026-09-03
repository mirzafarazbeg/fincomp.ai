# CAT File Validator (Phase 2)

Pure Python, no LLM dependency - parses a CAT Data File (CSV or JSON) and
validates it against the official CAT Industry Member schema
(`docs/specs/cat_im_schema_v4.2.0.json`), emitting the actual CAT error code
where one can be determined unambiguously.

```
python3 -m services.cat_validator.cli path/to/file.csv          # human-readable
python3 -m services.cat_validator.cli path/to/file.csv --json   # structured
python3 -m services.cat_validator.selftest                       # regression check
```

## How it works

- `schema.py` loads the official schema into lookups: per-event field lists
  (name, data type, required/conditional/optional, CSV position), the
  canonical data type table, Choice field allowed values, and a
  field-name -> CAT error code map (`data/cat_reference/error_code_field_map.json`,
  built by `scripts/build_error_code_field_map.py` by cross-referencing the
  Appendix E error catalog against known field names).
- `parser.py` reads a file line by line, detects CSV vs. JSON, and produces
  `RawRecord`s (event type + populated field name -> raw value). CSV field
  positions are read directly from the schema per event type - the `type`
  field itself is at a fixed CSV position 4 across all 88 event definitions,
  which is what makes it possible to identify the event before knowing its
  full field layout.
- `rules.py` validates each record's fields against the schema: presence for
  Required fields, and value format for whatever's populated (Choice
  membership, Boolean, Timestamp, Numeric-family precision/scale, Text/
  Alphanumeric length and charset, and the canonical ID/Symbol types).
- `report.py` / `cli.py` turn findings into text or JSON output, standalone
  (no DB needed) for command-line use.
- `store.py` persists a validation run (submission + findings) to the same
  Postgres instance the RAG knowledge base uses (`cat_submissions`,
  `cat_findings` - see `docs/ARCHITECTURE.md`'s data model), so the chat
  layer can answer follow-ups grounded in a specific run. Wired in via
  `services/api/app/cat_validate_client.py` (`POST /validate`, file upload)
  and `services/api/app/rag_client.py` (`retrieve(..., submission_id=...)`,
  used by `POST /query`) - a chat question with a `submission_id` gets that
  run's findings as priority context (capped at 10, or scoped to one line if
  the question names it, e.g. "why did record 45 fail"), plus the matching
  Appendix E error-code explanation for each finding with a code, on top of
  the normal spec retrieval. The chat UI (`services/api/static/index.html`)
  has a file-upload control that does this end to end.

## Design choice: emit real codes only when unambiguous

`schema.field_error_codes()` maps a field name to a CAT error code only when
exactly one Appendix E code is unambiguously "about" that field (its primary
subject, per the first field name mentioned in the code's description) - 99
of 135 mappable fields qualify. Where a field has multiple candidate codes
(e.g. `side` has 6, context-dependent per event/rule), the validator reports
`error_code: null` rather than guessing - a wrong code would be worse than
no code, in a compliance context.

## Known limitations

- **Conditional field presence isn't checked.** The schema marks a field
  "Conditional" but doesn't encode *when* it becomes required (that logic is
  scattered through the Tech Spec's prose, e.g. "required when X is
  populated"). Only `Required` fields are checked for presence; `Conditional`
  fields are validated for format if populated, but never flagged as
  missing. This is the biggest gap for a real validator - closing it means
  encoding each event's conditional-requirement rules, likely incrementally
  per event type as real usage surfaces which ones matter most.
- **Compound/array field types aren't deeply validated** - Aggregated
  Orders, Trade/Fulfillment Side Details, Leg Details, Name/Value Pairs
  (`handlingInstructions`, `timeInForce`), and generic Arrays are checked for
  presence only, not internal structure. `nameValuePairDefinitions` is
  already loaded in `schema.py` (`name_value_pair_defs()`) but not yet wired
  into `rules.py` - validating handlingInstructions/timeInForce sub-fields
  is the natural next slice of this.
- **No cross-record (linkage) checks yet** - Order ID lineage, route/trade
  event sequencing, the "Linkage Discovery" error class (Appendix E.3). This
  is explicitly Phase 2's harder half per `docs/ARCHITECTURE.md` and needs
  the Reporting Scenarios PDF's scenario logic, built incrementally per
  scenario with test fixtures - not attempted yet.
- **Only tested against MENO** (New Order Event) fixtures so far
  (`data/eval/cat_validator/`, `selftest.py`) - the other 87 event
  definitions load and should validate the same way since the logic is
  entirely schema-driven, but haven't been exercised with real or synthetic
  files yet. Worth building a fixture per event family (at least one Equity
  and one Option event beyond MENO) before trusting this broadly.
- **CSV delimiter edge cases**: the parser does a plain `line.split(',')`,
  which matches the spec's stated CSV rules (no delimiter chars are allowed
  inside field values, so no escaping/quoting to handle) - but hasn't been
  tested against a real-world CAT submission file, only spec-example-derived
  fixtures.
