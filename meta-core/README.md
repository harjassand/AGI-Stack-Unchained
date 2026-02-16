# meta-core

meta-core is the **RE1 TCB root** for constitutional upgrades in AGI-Stack.
It verifies and applies upgrade bundles only when constitutional constraints and kernel proofs are satisfied.

If any check fails, the operation is rejected; this is a deliberate fail-closed design.

## Position in the stack

- **RE1 (Trust root):** `meta-core`
  - Enforces constitutional constraints, verifies receipts, writes activation ledger, owns authoritative active state pointers.
- **RE2 (Verifier and promotion logic):** `CDEL-v2`
  - Generates candidate proofs and upgrade receipts for `meta-core` to validate.
- **Below RE2:** orchestrators/campaign tooling that collect candidate bundles and invoke `meta-core`.

## What meta-core verifies

- Bundle integrity and declared hash consistency.
- Deterministic hash identities for every JSON-bound artifact.
- Constitutional predicates via Rust kernel policy (`kernel/verifier`).
- Parent-chain continuity (`parent_bundle_hash` links to an existing `store` bundle).
- Toolchain and specification binding via manifest fields.
- Replay safety and audit invariants.

## Repository structure

```text
meta-core/
├─ active/               # current and previous active bundle pointers + local lock/ledger work
├─ stage/                # staged bundle checkout during apply
├─ store/                # immutable history of committed bundles
├─ meta_constitution/v1/ # constitutional schema, hashes, policy, IR specs
├─ kernel/verifier/      # Rust verifier binary + tests + build integration
├─ engine/               # orchestration logic (stage/verify/canary/commit/rollback/audit)
├─ cli/                  # thin Python command wrappers
├─ scripts/              # build and smoke-test entry points
└─ tests_orchestration/  # behavior tests and atomicity/failure-mode tests
```

## Deterministic foundation

All JSON used for hashing/identities is **GCJ-1 canonical**:

- No floats (signed 64-bit integers only)
- Sorted object keys (Unicode codepoint order)
- No whitespace
- Standard UTF-8 string escaping rules
- Raw bytes hashed as-is unless explicitly wrapped by `gcj1`

`meta-core` and `kernel/verifier` use this as the authoritative canonicalization for digest and receipt operations.

## Canonical bundle hashes

### Manifest hash

For `constitution.manifest.json`, `manifest_for_hash` blanks these fields before hashing:

- `bundle_hash`
- `manifest_hash`

Then:

`manifest_hash = sha256( GCJ1(manifest_for_hash(manifest)) )`

### Ruleset hash


a = gcj1(accept.ir.json)
b = gcj1(costvec.ir.json)
c = gcj1(migrate.ir.json)

`ruleset_hash = sha256( a || 0x00 || b || 0x00 || c )`

### Proof-bundle hash

`proof_bundle_hash = sha256( GCJ1(proofs/proof_bundle.manifest.json) )`

### Migration and schema binding

- `migration_hash = sha256( GCJ1(ruleset/migrate.ir.json) )`
- `state_schema_hash = sha256( raw_bytes(meta_constitution/v1/schemas/migration.schema.json) )`

### Toolchain Merkle root

A deterministic manifest over fixed toolchain files is built and hashed (file paths are sorted):

- `kernel/verifier/toolchain.lock`
- `kernel/verifier/Cargo.lock`
- `kernel/verifier/KERNEL_HASH`
- `kernel/verifier/build.sh`
- `meta_constitution/v1/META_HASH`
- `meta_constitution/v1/build_meta_hash.sh`
- `scripts/build.sh`

`toolchain_merkle_root = sha256( gcj1({"version":1,"files":[...sorted_by_path...]}) )`

### Bundle hash

`bundle_hash = sha256( manifest_hash || 0x00 || ruleset_hash || 0x00 || proof_bundle_hash || 0x00 || migration_hash || 0x00 || state_schema_hash || 0x00 || toolchain_merkle_root )`

Every piece is interpreted as 32-byte raw hex-decoded bytes in this formula.

## Bundle contract (`constitution.manifest.json`)

A valid upgrade bundle in `stage`/`store` must satisfy:

- All hash fields in manifest match computed values.
- `parent_bundle_hash` is either empty (genesis lineage) or a known 64-hex hash.
- `meta_hash` equals current `meta_constitution/v1/META_HASH`.
- `kernel_hash` equals `kernel/verifier/KERNEL_HASH`.
- `ruleset` files and proofs are present and structurally complete.

Core required keys observed in active bundles:

- `format`
- `schema_version`
- `bundle_hash`
- `parent_bundle_hash`
- `manifest_hash`
- `ruleset_hash`
- `proofs.proof_bundle_hash`
- `migration_hash`
- `state_schema_hash`
- `toolchain_merkle_root`
- `meta_hash`
- `kernel_hash`

Exact schema details are in:

- `meta_constitution/v1/schemas/constitution_manifest.schema.json`
- `kernel/verifier/tests/fixtures/*/constitution.manifest.json`

## File layout at runtime

- `active/ACTIVE_BUNDLE`
  - 64-hex active bundle hash with trailing newline
- `active/PREV_ACTIVE_BUNDLE`
  - previous active pointer
- `active/LOCK`
  - advisory lock for activation serialization
- `active/ledger/ledger.log`
  - append-only hash chain of COMMIT/ROLLBACK actions
- `active/work/`
  - staging temp area used during stage/verify/canary/commit
- `stage/bundles/<bundle_hash>/`
  - copied staged bundle content
- `store/bundles/<bundle_hash>/`
  - immutable committed bundles with `kernel_receipt.json`

## Runtime lifecycle

### 1) Stage

`cli/meta_core_stage.py` runs `activation.stage_bundle`.

- Loads manifest and recomputes all relevant hashes.
- Validates manifest declarations against recomputed values.
- Verifies `meta_hash` and `kernel_hash` from local root files.
- Copies bundle to `stage/bundles/<bundle_hash>/`.
- Emits a stage descriptor JSON (`meta_core_stage_v1`) to `--work-dir/stage.json`.

Return value: `{"verdict":"STAGED", "stage_path": <path>, "bundle_hash": <hash>}` on success.

### 2) Verify staged bundle

`cli/meta_core_verify.py` runs `activation.verify_staged`.

- Reads stage descriptor from `--stage`.
- Loads staged bundle and resolves parent from `parent_bundle_hash` if non-empty.
- Invokes Rust verifier (or builds it lazily).
- Writes receipt to `--receipt-out` and checks `receipt.bundle_hash` against staged hash.

Return value: `{"verdict":"VERIFIED", "receipt_out": <path>}` on success.

### 3) Canary

`cli/meta_core_canary.py` runs `activation.canary_staged`.

- Recomputes all bundle hashes from disk in staged copy.
- Re-runs kernel verifier against parent and candidate.
- Confirms determinism/replay consistency.

Return value: `{"verdict":"CANARY_OK"}` on success.

### 4) Commit

`cli/meta_core_commit.py` runs `activation.commit_staged`.

- Re-reads stage descriptor and receipt.
- Enforces hash bindings and parent relation.
- Writes `store/bundles/<bundle_hash>/` (idempotent if already present) and persists receipt.
- Updates active pointers and ledger atomically.

Return value: `{"verdict":"COMMITTED", "active_bundle_hash": <hash>}` on success.

### 5) Apply (end-to-end)

`cli/meta_core_apply.py` runs the full pipeline:

- lock `active/LOCK`
- stage -> verify -> canary -> commit

Return value on success: `{"verdict":"APPLIED", "active_bundle_hash": <hash>}`.

### 6) Audit

`cli/meta_core_audit_active.py` runs `engine.audit_active`.

- Validates active pointer exists.
- Loads active bundle and its stored receipt.
- Re-runs verifier from parent relationship and compares receipt bytes hash.
- Validates active/ledger integrity.

Returns `verdict=OK` with active hashes/hashes snapshot, or `INVALID` / `INTERNAL_ERROR` with empty fields on mismatch.

### 7) Rollback

`cli/meta_core_rollback.py` reverses active pointer to `PREV_ACTIVE_BUNDLE` when present.

- Writes rollback ledger entry.

Return value: `{"verdict":"ROLLED_BACK", "active_bundle_hash": <hash>}`.

## CLI reference

All CLI scripts require absolute paths in practice because engine functions reject non-absolute inputs for roots and key stage/output files.

### Stage a bundle

```bash
python3 cli/meta_core_stage.py \
  --meta-core-root /abs/path/to/meta-core \
  --bundle-dir /abs/path/to/candidate/bundle \
  --work-dir /abs/path/to/meta-core/active/work \
  --out-json /abs/path/to/meta-core/active/work/stage_out.json
```

### Verify staged bundle

```bash
python3 cli/meta_core_verify.py \
  --meta-core-root /abs/path/to/meta-core \
  --stage /abs/path/to/meta-core/active/work/stage.json \
  --receipt-out /abs/path/to/meta-core/active/work/receipt.json \
  --out-json /abs/path/to/meta-core/active/work/verify_out.json
```

### Canary staged bundle

```bash
python3 cli/meta_core_canary.py \
  --meta-core-root /abs/path/to/meta-core \
  --stage /abs/path/to/meta-core/active/work/stage.json \
  --work-dir /abs/path/to/meta-core/active/work \
  --out-json /abs/path/to/meta-core/active/work/canary_out.json
```

### Commit staged bundle

```bash
python3 cli/meta_core_commit.py \
  --meta-core-root /abs/path/to/meta-core \
  --stage /abs/path/to/meta-core/active/work/stage.json \
  --receipt /abs/path/to/meta-core/active/work/receipt.json \
  --out-json /abs/path/to/meta-core/active/work/commit_out.json
```

### Apply directly

```bash
python3 cli/meta_core_apply.py \
  --meta-core-root /abs/path/to/meta-core \
  --bundle-dir /abs/path/to/candidate/bundle \
  --out-json /abs/path/to/meta-core/active/work/apply_out.json
```

### Audit active state

```bash
python3 cli/meta_core_audit_active.py \
  --meta-core-root /abs/path/to/meta-core \
  --out-json /abs/path/to/meta-core/active/work/audit_out.json
```

### Rollback

```bash
python3 cli/meta_core_rollback.py \
  --meta-core-root /abs/path/to/meta-core \
  --reason "post_incident" \
  --out-json /abs/path/to/meta-core/active/work/rollback_out.json
```

## Verifier binaries and receipts

Rust verifier entrypoints are in `kernel/verifier/target/release/verifier` after build:

- `verify`
  - promotion bundle verification
- `verify-promotion`
  - wrapper mode used for codeless promotion checks
- `immutable-core-verify`
  - immutable-core checks

Exit codes from verifier:

- `0` valid
- `2` invalid verdict
- `1` internal verifier error (receipt may still be emitted)

Receipt output is canonical JSON (`meta_core_receipt_v1`) with at least:
`format`, `schema_version`, `verdict`, `bundle_hash`, `meta_hash`, `kernel_hash`, `reason_code`, `details`.

## Ledger model

`active/ledger/ledger.log` is append-only JSON-lines:

- each entry has `seq` monotone sequence
- `entry_hash` = `sha256` over canonical entry body excluding `entry_hash`
- `prev_entry_hash` is previous entry hash (or all-zero for genesis)
- action is either `COMMIT` or `ROLLBACK`

## Integration touchpoints

- `CDEL-v2` uses `meta-core` outputs while promoting bundles and checking active hashes.
- `agi-orchestrator` daemons pass `meta_core_root` to campaign/verifier paths and rely on `ACTIVE_BUNDLE` + ledger/audit semantics.
- Campaign/proof tooling uses `kernel/verifier/tests/fixtures` style bundle examples.

## Security and failure semantics

- Fail-closed behavior: invalid input paths, malformed manifests, hash mismatches, verifier rejections, or replay mismatches all produce rejection.
- Parent mismatch or bad chain hash causes `INVALID`, not partial mutation.
- Atomicity failures intentionally leave deterministic evidence (ledger/pointers can be audited).
- Determinism: same candidate + same parent yields byte-identical outputs.

## Build and local smoke workflow

```bash
# meta_core build + constitution refresh + kernel + receipts
./scripts/build.sh

# run kernel unit smoke paths
cd kernel/verifier
./build.sh
../../scripts/smoke_test.sh

# run core orchestration smoke
./scripts/smoke_orchestration.sh
```

## Notes for operators

- Keep absolute roots consistent: environment/config references must point to the real active working tree.
- Treat `meta_constitution/v1/META_HASH` and `kernel/verifier/KERNEL_HASH` as root-trust anchors.
- Never mutate files under `meta-core` through tooling not reviewed via constitutional paths.

## Version history

- `meta-core` tracks evolving RE1 semantics per root hash anchors and kernel upgrades.
- Always verify `kernel/verifier/KERNEL_HASH`, `meta_constitution/v1/META_HASH`, and current `ledger.log` before trust decisions.

