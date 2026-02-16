# Code Patch Candidate v1

Purpose
- Define a governed, deterministic candidate type for repo patches.
- Enable replayable evaluation, archive storage, and lineage across iterations.

Threat model
- Proposer is untrusted and may attempt to smuggle unsafe changes, nondeterminism, or malformed metadata.
- Certifier is trusted and enforces schema validation, canonicalization, and policy constraints before acceptance.

Required invariants
- Candidate JSON conforms to the schema in `schemas/code_patch_candidate_v1.json`.
- `candidate_id` matches the normative hash definition in `CANONICALIZATION.md`.
- Patch is `unified_diff_v1` and parsed deterministically to compute touched paths and line deltas.
- `touched_paths` equals the diff-derived sorted path list.
- Constraints (`max_files_changed`, `max_lines_changed`, `max_patch_bytes`, `forbid_binary`) are enforced.
- No timestamps appear in hashed payloads; timestamps belong only in archive event logs.
- Packaging into `candidate.tar` is deterministic and hash-stable.

Evaluation attachment
- CDEL evaluation receipts/evidence are stored in the archive as idempotent attachments.
- Attachments never alter candidate hashes; they only update archive status.
