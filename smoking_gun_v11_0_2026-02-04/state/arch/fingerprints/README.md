# fingerprints

> Path: `smoking_gun_v11_0_2026-02-04/state/arch/fingerprints`

## Mission

Evidence-pack artifacts and deterministic replay references for smoking-gun validation.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `sha256_49fe7da886f7505c95fa625a126b1a45676e73474c588495002bbc8926bf1029.sas_topology_fingerprint_v1.json`: JSON contract, config, or artifact.
- `sha256_776abfdad0a5f20989aa7b11f266c043dc2402be7d91a8e4eddc601e6510253a.sas_topology_fingerprint_v1.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 2 files

## Operational Checks

```bash
ls -la smoking_gun_v11_0_2026-02-04/state/arch/fingerprints
find smoking_gun_v11_0_2026-02-04/state/arch/fingerprints -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files smoking_gun_v11_0_2026-02-04/state/arch/fingerprints | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
