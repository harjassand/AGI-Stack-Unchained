# Canonicalization & Hashing (v1.1)

## Canonical JSON bytes (normative)
Canonical JSON bytes are produced exactly with:

```
json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
```

- The canonical JSON bytes are the UTF-8 encoding of the produced string.
- Lists preserve order as provided (no sorting).
- No NaN/Infinity floats are allowed anywhere.

## Ontology hash (self-referential)
To compute `ontology_hash`:
1. Take the ontology object.
2. Set its `ontology_hash` field to `"0"*64`.
3. Compute `sha256_hex(canonical_json_bytes(obj_with_zeroed_hash))`.
4. The stored `ontology_hash` MUST equal the computed value.

## Candidate ID (self-referential)
To compute `candidate_id`:
1. Take `manifest.json`.
2. Set its `candidate_id` field to `"0"*64`.
3. Let `manifest_bytes = canonical_json_bytes(zeroed_manifest)`.
4. Let:
   - `patch_hash_bytes = bytes.fromhex(sha256_hex(canonical_json_bytes(ontology_patch_json)))`
   - `mech_diff_hash_bytes = bytes.fromhex(sha256_hex(canonical_json_bytes(mechanism_registry_diff_json)))`
   - `programs_hash_bytes = bytes.fromhex(sha256_hex(concat_program_bytes_sorted_by_path))`
5. Compute:

```
candidate_id = sha256_hex(manifest_bytes || patch_hash_bytes || mech_diff_hash_bytes || programs_hash_bytes)
```

Where `concat_program_bytes_sorted_by_path` is the byte concatenation of program bytes ordered by their path.
