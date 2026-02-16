# Sealed Signing Canonicalization

This document specifies the canonicalization contract for signed sealed payloads
(e.g., `stat_cert` certificates).

## Canonicalization contract

Signed payloads use RFC 8785 JSON Canonicalization Scheme (JCS) semantics with
an explicit, bounded value set.

### Encoding and structure

- UTF-8 encoding for the final bytes.
- JSON objects sorted by Unicode code point order of keys.
- Arrays preserve order.
- No extra whitespace (`,`, `:` separators only).
- Strings are not Unicode-normalized (NFC/NFD differences remain distinct).

### Numbers and allowed types

Only the following JSON types are allowed in signed payloads:

- object (dict with string keys)
- array (list)
- string
- integer
- boolean
- null

Float values are **not** allowed. This disallows non-finite numbers
(`NaN`, `Infinity`, `-Infinity`) and avoids platform-specific formatting.

All non-integer numeric values (e.g., `alpha_i`, `evalue_threshold`) must be
encoded as strings to avoid formatting ambiguity (scientific notation, trailing
zeros).

E-values are encoded as a compact scientific form:

```json
{"mantissa":"1.234567890123456789000000","exponent10":42}
```

- `mantissa` is a fixed-precision decimal string with a single digit before the
  decimal point (24 significant digits total; JCS preserves the string verbatim).
- `exponent10` is an integer power of 10.
The certificate also carries `evalue_schema_version` (must be `2`) to avoid
legacy ambiguity.

### Determinism

Canonicalization rejects:

- floats of any kind
- non-string object keys
- unsupported JSON types

This ensures stable, cross-platform signature bytes for the sealed worker and
verifier.
