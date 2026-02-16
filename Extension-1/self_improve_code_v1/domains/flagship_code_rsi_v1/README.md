# Flagship Code RSI v1.1

This flagship domain proves a full RSI-style loop can compound improvements under the existing trust model:

Untrusted proposer -> deterministic repo patch candidates -> devscreen diagnostics -> sealed CDEL eval -> PASS receipts only -> deterministic learning update -> next epoch.

## What this proves
- End-to-end, deterministic candidate generation for `repo_patch_candidate_v1`.
- Baseline sealed-dev calibration selects an active ladder tier where baseline FAIL is observed (or reports baseline PASS across all tiers).
- Null control checks tier sensitivity and forces escalation if the tier is too easy.
- Devscreen diagnostics are dense but non-certifying.
- Sealed CDEL evaluation is the only certification gate (PASS receipts only).
- Replay/verify can reconstruct ranking and selection without hidden state.

## Commands

From the stack root (`/Users/harjas/AGI Stack`):
```
export PYTHONPATH="$(pwd)/Extension-1"
python3 - <<'PY'
import importlib
import sys
try:
    importlib.import_module("self_improve_code_v1.cli.flagship_code_rsi_v1_cli")
except Exception as exc:
    print("import preflight failed:", exc)
    sys.exit(1)
print("import preflight ok")
PY
```

Start CDEL Evaluate service (dev):
```
PYTHONPATH="$(pwd)/CDEL-v2" python3 -m cdel.evaluate_service.app \
  --root CDEL-v2 \
  --port 8000
```

Run flagship (dev, 10 epochs):
```
python3 -m self_improve_code_v1.cli.flagship_code_rsi_v1_cli \
  run_flagship \
  --config Extension-1/self_improve_code_v1/domains/flagship_code_rsi_v1/default_run_config.json \
  --epochs 10
```

Verify run output:
```
python3 -m self_improve_code_v1.cli.flagship_code_rsi_v1_cli \
  verify_flagship \
  --run_dir Extension-1/runs/self_improve_code_v1/<run_id>
```


Quick e2e smoke (<=3 minutes):
```
Extension-1/self_improve_code_v1/scripts/e2e_flagship_code_rsi_v1.sh
```

Real devscreen (best effort, <=30 minutes):
```
Extension-1/self_improve_code_v1/scripts/e2e_flagship_code_rsi_v1.sh real
```

## Heldout runs
- Mount heldout suites at runtime (do not commit them).
- For heldout evaluation, run with `--heldout` and ensure the Evaluate service is configured with sealed suites.

## Determinism contract
Runs are replayable from `run_config.json` + `seed` + baseline commit + suite IDs.
Determinism is invalidated by:
- Changing template library ordering or template logic.
- Changing selection ordering rules.
- Changing manifest schema or candidate ID derivation.
- Changing ladder tiers or eval plan IDs.
- Changing suitepacks or eval plans.

## Key artifacts
- `baseline/baseline_sealed_dev_result.json`: baseline sealed-dev result for the active tier.
- `epochs/*/controls/null_control_sealed_dev_result.json`: sensitivity control per epoch.
- `sanity.json`: baseline status, null control pass rate, noop-filter fraction.
- `improvement_curve.json`: per-epoch RSI signal (sealed passes + improvement credits).

## Candidate ID
Candidate IDs follow the repo patch spec: `sha256(domain_sep || manifest_hash || patch_hash || policy_hash)`.

## Notes
- Devscreen uses deterministic runner logic; sealed eval uses the CDEL CLI profile `repo_patch_eval_v1`.
- Outputs are written as canonical JSON and deterministic tar archives.
- Semantic no-op patches are filtered from sealed eval unless they are the explicit null control.
