# Canonicalization & Hashing (v1)

## Canonical JSON bytes
All canonical JSON bytes are produced with:
- UTF-8 encoding
- Object keys sorted lexicographically
- Arrays preserved in-order (no sorting)
- No floats; only null, bool, int, string, array, object
- String keys only; no duplicate keys
- JSON separators: `,` and `:` (no extra whitespace)
- LF line endings (no CRLF)

The canonical JSON **bytes** are the UTF-8 encoding of this canonical JSON string.

## Patch bytes
`patch.diff` is hashed as **raw bytes** (no normalization). The patch SHOULD use LF
line endings for reproducibility. The patch SHA-256 is:

```
patch_sha256 = sha256(patch_bytes)
```

## Candidate ID (normative)
The candidate ID is defined as:

```
candidate_id = sha256( canonical_candidate_json_bytes || 0x0a || patch_bytes_sha256_hex )
```

Where:
- `canonical_candidate_json_bytes` is the canonical JSON bytes of the candidate **with
  `candidate_id` set to the empty string** (`""`).
- `patch_bytes_sha256_hex` is the lowercase hex string of `sha256(patch_bytes)`.
- `0x0a` is a single LF byte separating the JSON bytes and the patch hash hex.

## Candidate JSON hash
`candidate_json_sha256` (used in test vectors) is:

```
sha256(canonical_candidate_json_bytes_with_actual_candidate_id)
```

## Deterministic tar packaging
`candidate.tar` is constructed from:
- `candidate.json` (canonical JSON bytes with the actual `candidate_id`)
- `patch.diff` (raw patch bytes)
- `policy.json` (optional; canonical JSON bytes)

Deterministic tar rules:
- Entries sorted by name
- USTAR format
- `mtime = 0`
- `uid = 0`, `gid = 0`, `uname = ""`, `gname = ""`
- `mode = 0644`
- No timestamps in any hashed payload

The tar hash is:

```
candidate_tar_sha256 = sha256(candidate_tar_bytes)
```
