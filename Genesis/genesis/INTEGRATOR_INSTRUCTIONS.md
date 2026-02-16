# Genesis Integrator Instructions (v1.2)

## Requirements

- Specpack v1.0.1
- CDEL Level-4.1 drop or newer (CLI + binary-only HTTP + healthz/server-info)

## Verify Specpack Lock

```bash
cd genesis
python3 -m pip install -r requirements-dev.txt
./run_checks.sh
```

## End-to-End Run

```bash
export CDEL_ROOT=<path-to-cdel>
./run_end_to_end_v1_2.sh
```

## Outputs

- `genesis_run_v1_2.jsonl` (authoritative run log)
- `genesis_archive.jsonl` (QD archive)
- `genesis_summary.json`
- `receipts_v1_2/` (PASS only)
- `release_packs_v1_2/` (release packs + manifests + eval bundles)
- `release_registry_v1_2.jsonl` (append-only registry)

Verification log:

- `GENESIS_END_TO_END_V1_2_VERIFICATION.txt`
