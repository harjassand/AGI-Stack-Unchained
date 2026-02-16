# GCJ-1 Canonical JSON

GCJ-1 is the canonical JSON format used for all hash-bound artifacts in `meta-core`.

## GCJ-1 admissibility constraints

A JSON value is GCJ-1 admissible iff:

- Numbers are **signed 64-bit integers only** (no floats).
- Scientific notation is rejected.
- No `NaN` or `Infinity`.
- Strings are UTF-8.
- Objects contain only **unique keys**.
- Arrays preserve order.
- `null` is allowed (but discouraged) and must be preserved.
- No comments.

## Canonical encoding rules

The canonical byte representation is the UTF-8 encoding of the following serialization:

- Objects:
  - Keys are sorted by **Unicode codepoint lexicographic order**.
  - Key/value separators are exactly `:`.
  - Pair separators are exactly `,`.
- Arrays preserve order and use `[` `]` with `,` separators.
- No whitespace anywhere.
- Strings are escaped per the JSON standard **only when required**:
  - `"`, `\\`, `\b`, `\f`, `\n`, `\r`, `\t`, and `\u00XX` for control bytes `< 0x20`.
  - No optional escaping (e.g., `/` is not escaped).
- Integers are base-10 with optional leading `-`, no `+`, and no leading zeros unless the value is exactly `0`.

## Hash functions

- `H(x) = sha256(x)` where `x` is raw bytes.
- `hash_json(v) = sha256(GCJ1(v))`.
- `hash_file(path) = sha256(raw_file_bytes)` (only for blob hashing; manifests use GCJ-1).

GCJ-1 is the sole source of identity for JSON-bound artifacts.
