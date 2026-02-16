# External Review Packet

This packet is the minimal entry point for third-party review.

Tag: `v0.1-hypothesis-core`

Quick reproduce:

```bash
python -m pip install -e ".[dev]"
./scripts/repro_quickstart.sh
```

Run all scripts from the repo root; do not rely on packaged metadata (e.g., `*.egg-info`).

Evidence manifest:

- `docs/EVIDENCE_MANIFEST_v0.1-hypothesis-core.txt`
- Verify hashes with `sha256sum` or `shasum -a 256`.

Track A evidence:

Tag: `v0.2-trackA-suite`

Manifest:

- `docs/EVIDENCE_MANIFEST_v0.2-trackA-suite_f885989.txt`
- Verify hashes with `sha256sum` or `shasum -a 256`.

Track B evidence:

Tag: `v0.3-trackB-solve`

Manifest:

- `docs/EVIDENCE_MANIFEST_trackB_0295f31.txt`
- Verify hashes with `sha256sum` or `shasum -a 256`.

Phase 10 evidence:

Tag: `v0.4-suite-solve`

Manifest:

- `docs/EVIDENCE_MANIFEST_phase10_03daacd.txt`
- Verify hashes with `sha256sum` or `shasum -a 256`.

Phase 11 evidence:

Tag: `v0.5-solve-ablations`

Manifest:

- `docs/EVIDENCE_MANIFEST_phase11_9295362.txt`
- Verify hashes with `sha256sum` or `shasum -a 256`.

Phase 12 evidence:

Tag: `v0.6-templates-and-reuse`

Manifest:

- `docs/EVIDENCE_MANIFEST_v0.6-templates-and-reuse_183817a.txt`
- `docs/EVIDENCE_MANIFEST_phase12_183817a.txt`
- Verify hashes with `sha256sum` or `shasum -a 256`.

Phase 13 evidence:

Tag: `v0.7-consolidation-and-growth`

Manifest:

- `docs/EVIDENCE_MANIFEST_phase13_bba40ca.txt`
- Verify hashes with `sha256sum` or `shasum -a 256`.

Phase 14 evidence:

Tag: `v1.0-rc1`

Manifest:

- `docs/EVIDENCE_MANIFEST_phase14_657e550.txt`
- Verify hashes with `sha256sum` or `shasum -a 256`.

Read these four documents, in order:

1) `docs/learning_claims.md`
2) `docs/AUDIT_INTERFACE.md`
3) `docs/sealed_signing.md`
4) `docs/stat_cert_runbook.md`

Track B reference:

- `docs/SOLVE_LOOP.md`
