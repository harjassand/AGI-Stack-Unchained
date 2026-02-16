# Canonicalization and Hashing (Level-1)

This document defines the normative canonical JSON encoding and hashing used for capsule and receipt commitments.

## Normative Default (MUST implement)

- **Canonicalization scheme:** GCJ-1 (Genesis Canonical JSON v1)
- **Hash algorithm:** SHA-256

Canonicalization ID: `gcj-1`

## GCJ-1 Canonicalization Rules

GCJ-1 is a deterministic JSON canonicalization profile suitable for cross-language hashing.

### Input

- Input JSON MUST be valid per RFC 8259.
- Input bytes MUST be UTF-8.

### Output

- Output is UTF-8 bytes of the canonical JSON text.
- No trailing newline or extra whitespace is permitted.

### Objects

- Keys MUST be sorted lexicographically by Unicode code point.
- Members are encoded as `{key:value}` with `,` separators and `:` between key and value.
- No extra whitespace is allowed.

### Arrays

- Element order is preserved.
- Elements are separated by `,` with no whitespace.

### Strings

- Strings are encoded with JSON escaping.
- Control characters MUST be escaped using `\u00XX` with lowercase hex.
- Non-ASCII characters MUST be encoded directly in UTF-8 (no `\u` escaping).

### Numbers

- Numbers MUST be finite (no NaN/Infinity).
- Canonical encoding is **decimal without exponent**.
- No leading `+` sign.
- `-0` is normalized to `0`.
- No leading zeros in the integer part (except zero itself).
- Fractional part MUST be minimal (remove trailing zeros). If the fractional part is empty, omit the decimal point.
- A leading zero MUST be present for numbers between -1 and 1 (e.g., `0.5`).

### Money-Like Quantities (Budgets)

To avoid cross-language float formatting drift, all money-like quantities MUST be encoded as **canonical decimal strings** (not JSON numbers) in hashed objects:

- Capsule `budget_bid.alpha_bid`
- Capsule `budget_bid.privacy_bid.epsilon`
- Capsule `budget_bid.privacy_bid.delta`
- Receipt `budgets_spent.alpha_spent`
- Receipt `budgets_spent.privacy_spent.epsilon_spent`
- Receipt `budgets_spent.privacy_spent.delta_spent`

These fields MUST be strings in the same canonical decimal form as the Number rules above (no exponent, no trailing zeros). JSON numbers in these fields are invalid.

### Literals

- `true`, `false`, and `null` are lowercase.

## Hashing Rules

### Capsule Hash

- Canonicalize the full capsule JSON using GCJ-1.
- Set `commitments.capsule_hash` to 64 zero hex during hash computation.
- Hash the canonical bytes with SHA-256.

### Receipt Hash

- Canonicalize the full receipt JSON using GCJ-1.
- Hash the canonical bytes with SHA-256.

## Extensions (MAY implement)

- Alternative hash algorithms (e.g., BLAKE3) MAY be added in a future spec epoch with explicit field identifiers.
