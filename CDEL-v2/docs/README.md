# docs

> Path: `CDEL-v2/docs`

## Mission

Local component subtree within the AGI stack; maintain deterministic, contract-safe changes.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `AUDIT_INTERFACE.md`: documentation artifact.
- `EVIDENCE_MANIFEST_phase10_03daacd.txt`: text output or trace artifact.
- `EVIDENCE_MANIFEST_phase11_9295362.txt`: text output or trace artifact.
- `EVIDENCE_MANIFEST_phase12_183817a.txt`: text output or trace artifact.
- `EVIDENCE_MANIFEST_phase13_bba40ca.txt`: text output or trace artifact.
- `EVIDENCE_MANIFEST_phase14_657e550.txt`: text output or trace artifact.
- `EVIDENCE_MANIFEST_trackA_9282820.txt`: text output or trace artifact.
- `EVIDENCE_MANIFEST_trackB_0295f31.txt`: text output or trace artifact.
- `EVIDENCE_MANIFEST_v0.1-hypothesis-core.txt`: text output or trace artifact.
- `EVIDENCE_MANIFEST_v0.2-trackA-suite_f885989.txt`: text output or trace artifact.
- `EVIDENCE_MANIFEST_v0.6-templates-and-reuse_183817a.txt`: text output or trace artifact.
- `INSTALL.md`: documentation artifact.
- `OUTPUT_SCHEMAS.md`: documentation artifact.
- `RC_SIGNOFF_v1.0-rc1.md`: documentation artifact.
- `REVIEW_PACKET.md`: documentation artifact.
- `RUN_CONTRACT.md`: documentation artifact.
- `SOLVE_LOOP.md`: documentation artifact.
- `cache_contract.md`: documentation artifact.
- `canon_v1.md`: documentation artifact.
- `dev_vs_heldout_runbook.md`: documentation artifact.
- `hygiene_metric.md`: documentation artifact.
- `io_harness_runbook.md`: documentation artifact.
- `learning_claims.md`: documentation artifact.
- `pyut_sandbox_runbook.md`: documentation artifact.
- `reuse_metric.md`: documentation artifact.
- ... and 6 more files.

## File-Type Surface

- `md`: 21 files
- `txt`: 10 files

## Operational Checks

```bash
ls -la CDEL-v2/docs
find CDEL-v2/docs -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/docs | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
