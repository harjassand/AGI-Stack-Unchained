# Migration Totality v1 (D-BASE)

This document defines the v1.4 migration totality requirements.

## Requirements

The migration program MUST:

1. Execute in the kernel (MetaLang IR or other allowed artifact).
2. Be gas-bounded by the kernel limits.
3. Produce output that passes the state schema validation.
4. Succeed on the two deterministic test states:
   - `tests/fixtures/state_small.json`
   - `tests/fixtures/state_edge.json`

## State schema

The state schema is `meta_constitution/v1/schemas/migration.schema.json`.

For v1, the schema accepts any non-null JSON value that is an object, array,
string, integer, or boolean. `null` is not permitted.
