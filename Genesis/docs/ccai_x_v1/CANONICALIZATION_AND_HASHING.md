# Canonicalization and Hashing (CCAI-X v1)

## 1. GCJ-1 canonical JSON

All CCAI-X v1 JSON objects must be serialized using GCJ-1 canonical JSON:

- UTF-8 encoding, LF line endings.
- Object keys sorted lexicographically (bytewise).
- No insignificant whitespace.
- Integers only (no decimal points, no exponent notation).

## 2. `sha256_hex(bytes)`

`sha256_hex(bytes)` is SHA-256 over raw bytes, returned as lowercase hexadecimal.

## 3. `do_payload_hash`

`do_payload_hash = sha256_hex(canonical_json_bytes(do_payload))`

Where `canonical_json_bytes` is GCJ-1 canonical JSON byte encoding of the `do_payload` object.

## 4. `mechanism_hash`

`mechanism_hash = sha256_hex(canonical_json_bytes(mechanism_object))`

Where `mechanism_object` is the exact JSON object stored in `causal_mechanism_registry_v1.mechanisms[]`.

## 5. Intervention log hash chain

Initialization:

- `prev_link_hash` for the first entry is 64 zero hex characters.

Per-entry hashing:

- `link_hash = sha256( prev_link_hash_bytes || canonical_json_line_bytes_without_link_hash_field )`
- `prev_link_hash_bytes` is the raw 32 bytes decoded from `prev_link_hash` hex.
- `canonical_json_line_bytes_without_link_hash_field` is GCJ-1 canonical JSON for the entry with `link_hash` temporarily set to 64 zeros before canonicalization.

## 6. `candidate_id`

Candidate IDs are derived from the exact tar entry bytes (no re-serialization) for all artifacts, with a self-reference resolution step for the manifest:

- `m = sha256(manifest_bytes_for_hash)`
- `r = sha256(mechanism_registry_bytes)`
- `p = sha256(policy_prior_bytes)`
- `pref = sha256(preference_capsule_bytes)`
- `isa = sha256(inference_kernel_isa_bytes)`
- `blanket = sha256(markov_blanket_spec_bytes)`
- `d = sha256(do_map_bytes)`

Then:

`candidate_id = sha256_hex( b"ccai_x_mind_patch_candidate_v1\n" || m || r || p || pref || isa || blanket || d )`

Where `||` is raw byte concatenation and each SHA-256 output is raw 32 bytes.

### Candidate ID self-reference resolution

To avoid a fixed-point when the manifest includes `candidate_id`, compute the manifest hash component `m` using a zeroed candidate_id:

1. Parse `manifest.json` into object `M`.
2. Create `M0 = M` but set `M0["candidate_id"] = "0000000000000000000000000000000000000000000000000000000000000000"`.
3. `manifest_bytes_for_hash = GCJ1(M0)`.
4. `m = sha256_raw(manifest_bytes_for_hash)`.

Then compute:

`candidate_id = sha256_hex( b"ccai_x_mind_patch_candidate_v1\n" || m || r || p || pref || isa || blanket || d )`

Finally, require that the manifest's stored `candidate_id` equals the computed `candidate_id`; otherwise FAIL.

## Common pitfalls

- Hashing parsed JSON rather than the exact file bytes.
- Allowing timestamps, UUIDs, or other nondeterministic fields.
- Non-deterministic ordering in arrays that must be sorted.
- Floats sneaking in via Python math or JSON parsing.
