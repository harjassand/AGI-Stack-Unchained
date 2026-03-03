# ccai_x_mind_v1

> Path: `CDEL-v2/proof/ccai_x_mind_v1`

## Mission

Local component subtree within the AGI stack; maintain deterministic, contract-safe changes.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- `fixtures/`: deterministic fixture data.

## Key Files

- `EXPECTED_FAIL_CODES.md`: documentation artifact.
- `PROOF_REPORT.md`: documentation artifact.
- `expected_failures.json`: JSON contract, config, or artifact.
- `proof_manifest_v1.py`: Python module or executable script.
- `prove_ccai_x_mind_v1.sh`: shell automation script.
- `verify_ccai_x_mind_v1.py`: Python module or executable script.

## File-Type Surface

- `py`: 2 files
- `md`: 2 files
- `sh`: 1 files
- `json`: 1 files

## Operational Checks

```bash
ls -la CDEL-v2/proof/ccai_x_mind_v1
find CDEL-v2/proof/ccai_x_mind_v1 -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/proof/ccai_x_mind_v1 | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
