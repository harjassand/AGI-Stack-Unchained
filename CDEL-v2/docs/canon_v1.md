# CDEL Canonicalization v1

This document defines canonicalization and hashing for v1 payloads.

## Canonical JSON encoding

Use UTF-8 bytes of:

```
json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
```

No floats are permitted anywhere. Integers must be JSON ints (not booleans).

## Canonicalization of payload

Given a module `payload`:

1. Discard `meta` entirely (not hashed).
2. Sort lists:
   - `new_symbols` lexicographically
   - `declared_deps` lexicographically
   - `definitions` by `name`
   - `specs` by stable JSON of the canonicalized spec
   - `concepts` by (`concept`, `symbol`)
3. Canonicalize each definition and spec by alpha-normalization.

### Definition canonicalization (alpha-normalization)

- Parameter names are irrelevant to hashes.
- Rename params to `p0`, `p1`, ... in order.
- Convert the body to an internal form using de Bruijn indices and re-emit
  with canonical binder names.
- Match binders are renamed deterministically based on binder depth:
  `h{depth}` and `t{depth}`.
- Option match binders are renamed deterministically:
  `o{depth}`.

### Spec canonicalization

- Spec vars are renamed to `v0`, `v1`, ... in order.
- Domain `fun_symbols` are sorted lexicographically.
- `int_min`, `int_max`, `list_max_len` must be integers.
- Proof specs (`proof` / `proof_unbounded`) canonicalize the goal terms
  and the proof term (`missing` / `by_eval` / `refl` / `sym` / `trans`).
- Stat cert specs (`stat_cert`) are normalized field-by-field:
  - `eval` contains ints + bool + harness identifiers/hashes.
  - `risk` and `certificate` use decimal strings (no floats).
  - `alpha_schedule` is preserved with `name`, `exponent`, `coefficient`.
  - `concept` and `key_id` are canonicalized as strings.

## Hashing

- Hash algorithm: BLAKE3
- Input bytes: canonical JSON encoding of the canonicalized payload
- Output: lowercase hex digest

The payload hash is the content address for ledger storage.
