# Suite growth and rotation

This document describes how ladder suites evolve while preserving dev/heldout
separation and reproducibility.

## Dev suite pointer

- Canonical dev suites are tracked in `suites/*_dev_current.json`.
- Current ladder pointers include:
  - `suites/io_dev_current.json`
  - `suites/env_dev_current.json`
  - `suites/pyut_dev_current.json`
  - `suites/tooluse_dev_current.json`
  - `suites/agent_reliability_dev_current.json`
  - `suites/pyut_transfer_dev_current.json`
- The JSON points to a hash-addressed JSONL in `sealed_suites/<hash>.jsonl`.
- Updates must go through `scripts/update_pyut_dev_suite_pointer.py` and a PR.

### Dev update flow

1) Mine new dev cases (manual-only):

```
./scripts/mine_and_augment_pyut_dev_suite.py \
  --run-dir runs/<run_id> \
  --suite-path sealed_suites/<old_hash>.jsonl \
  --out-dir sealed_suites \
  --max-episodes 50
```

2) Update the pointer + dev config:

```
./scripts/update_pyut_dev_suite_pointer.py \
  --suite-hash <new_hash> \
  --suites-dir sealed_suites \
  --dev-config /path/to/CDEL/configs/sealed_pyut_dev.toml \
  --updated-at YYYY-MM-DD \
  --source mined \
  --notes "mined from run <run_id>"
```

3) Open a PR containing:
- new `sealed_suites/<new_hash>.jsonl`
- updated `suites/pyut_dev_current.json`
- updated dev config hash
 - include `scripts/suite_diff.py --old <old_hash> --new <new_hash>` output in the PR description

## Heldout rotation (explicit only)

Heldout suites are never written to the repo. Rotation is deliberate and
recorded by a manifest.

### Rotation flow

1) Generate a candidate heldout suite (manual workflow):
- run the "heldout rotation" workflow or run locally:

```
./scripts/generate_pyut_heldout_candidate_suite.py \
  --pool /path/to/pool.jsonl \
  --out-dir /tmp/heldout_rotation \
  --seed <seed> \
  --target-size <N> \
  --stratify
```

2) Review `heldout_rotation_manifest.json` and the candidate JSONL.
3) Deploy suite bytes to the sealed environment via `CDEL_SUITES_DIR`.
4) Update the heldout config hash **only** via PR:

```
./scripts/update_pyut_heldout_config_hash.py \
  --heldout-hash <hash> \
  --heldout-config /path/to/CDEL/configs/sealed_pyut_heldout.toml
```

## Cooldown policy

- Mined cases must remain in dev for at least one full rotation cycle
  (or 30 days, whichever is longer).
- Heldout rotation requires a PR and manifest review; it cannot be triggered
  automatically.
