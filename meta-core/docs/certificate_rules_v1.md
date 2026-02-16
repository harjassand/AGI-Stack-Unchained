# Certificate Rules v1

This document defines how the Iron Kernel validates upgrade bundles.

## Bundle hashing (BUNDLE-V1.4)

A bundle is a directory containing `constitution.manifest.json` and referenced blobs.

1. `manifest_hash = sha256(GCJ1(manifest_for_hash(manifest)))` where:
   - `bundle_hash` is set to `""`
   - `manifest_hash` is set to `""` if present
   - `proofs.proof_bundle_hash` is **not** blanked
2. `proof_bundle_hash = sha256(GCJ1(proofs/proof_bundle.manifest.json))`
3. `migration_hash = sha256(GCJ1(ruleset/migrate.ir.json))`
4. `state_schema_hash = sha256(raw_bytes(meta_constitution/v1/schemas/migration.schema.json))`
5. `toolchain_merkle_root` is defined in `meta_constitution/v1/spec/toolchain_merkle_root_v1.md`
6. Compute:

```
bundle_hash = sha256(
  manifest_hash ||
  "\0" ||
  ruleset_hash ||
  "\0" ||
  proof_bundle_hash ||
  "\0" ||
  migration_hash ||
  "\0" ||
  state_schema_hash ||
  "\0" ||
  toolchain_merkle_root
)
```

`constitution.manifest.json` must include `bundle_hash` as lowercase hex.

## Ruleset hash (RULESET-V1)

Let `A`, `C`, `M` be GCJ-1 canonical bytes of:

- `ruleset/accept.ir.json`
- `ruleset/costvec.ir.json`
- `ruleset/migrate.ir.json`

Then:

```
ruleset_hash = sha256(A || "\0" || C || "\0" || M)
```

The null byte delimiter is mandatory and unambiguous because GCJ-1 JSON never contains raw `\0` bytes.

## SAFE(x, state)

`SAFE` is a kernel-built-in predicate (not IR) and is true iff:

- `x` is a map with keys `bundle_hash`, `ruleset_hash`, `meta_hash`.
- Each key is a lowercase hex string of length 64.
- `x.meta_hash == META_HASH`.
- `x.bundle_hash == computed_bundle_hash(bundle_dir)`.
- `x.ruleset_hash == computed_ruleset_hash(ruleset files)`.

## Required statements (v1)

1. `SOUNDNESS_BY_CONSTRUCTION_V1`
2. `TERMINATION_IR_TOTAL_V1`
3. `DOMINANCE_STRUCTURAL_OR_V1`
4. `STATE_MIGRATION_TOTAL_V1`
5. `SPEC_RUNTIME_HASH_BINDING_V1`

The proof bundle must list these exact statement IDs.

## Proof bundle hashing

`proofs.proof_bundle_hash` is computed as `sha256(GCJ1(proofs/proof_bundle.manifest.json))`.
`dominance_witness_sha256` inside the proof bundle manifest is `sha256(raw_bytes(dominance_witness.json))`.

## Soundness by construction

Acceptance IR must have the form:

```
Accept_B(x, state) = AND( SAFE(x, state), extra_conditions(x, state) )
```

The kernel enforces this by requiring the top-level node to be `And` with a direct `Safe` child.
`And` may contain **N ≥ 1** children as long as at least one direct child is `Safe`.

## Dominance (structural OR)

Let the parent accept be `Accept_A = SAFE AND CondA`.
The candidate must define:

```
Accept_B = SAFE AND (CondA OR CondExtra)
```

Rules:

1. `CondA` is extracted from the parent accept IR.
2. Candidate `CondA` must be byte-for-byte identical to the parent `CondA` under GCJ-1.
3. The candidate must carry `proofs/dominance_witness.json` with `x_star`, `state_a`,
   and `condextra_inputs` (including `blob_hashes`).
4. The kernel checks:
   - `CondA(x_star, state_a)` is **false**.
   - `CondExtra(x_star, condextra_inputs)` is **true**.

This provides inclusion (`CondA ⇒ CondA OR CondExtra`) and strictness via `x_star`.

## Migration totality

`ruleset/migrate.ir.json` must parse, pass static limits, and terminate on two canonical test
states: `tests/fixtures/state_small.json` and `tests/fixtures/state_edge.json`.
The output must pass the migration state schema. Any error ⇒ INVALID.

## Spec/runtime hash binding

The manifest must bind:

- `meta_hash == META_HASH`
- `kernel_hash == KERNEL_HASH`
- `ruleset_hash == computed ruleset hash`
- `migration_hash == computed migration hash`
- `state_schema_hash == computed state schema hash`
- `toolchain_merkle_root == computed toolchain merkle root`
- `bundle_hash == computed bundle hash`

Any mismatch ⇒ INVALID.
