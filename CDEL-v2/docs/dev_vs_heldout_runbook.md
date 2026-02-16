# Dev vs Heldout Runbook

## Configs

- `configs/sealed_suite_dev.toml`
- `configs/sealed_suite_heldout.toml`

Both configs pin:

- `sealed.eval_harness_id = "suite-harness-v1"`
- `sealed.eval_harness_hash = "suite-harness-hash"`
- `sealed.eval_suite_hash = "<hash>"`
- `sealed.episodes = <N>`

## Suite locations

Dev suite lives in the repo:

```
sealed_suites/<dev_hash>.jsonl
```

Heldout suite stays outside the repo and is mounted at runtime:

```
export CDEL_SUITES_DIR=/secure/heldout_suites
ls $CDEL_SUITES_DIR/<heldout_hash>.jsonl
```

## Promotion script

```bash
export CDEL_SUITES_DIR=/secure/heldout_suites
export CDEL_SEALED_PRIVKEY="..."

python3 scripts/promote_candidate_dev_vs_heldout.py \
  --concept <concept> \
  --baseline <baseline_symbol> \
  --candidate <candidate_symbol> \
  --oracle <oracle_symbol> \
  --dev-config configs/sealed_suite_dev.toml \
  --heldout-config configs/sealed_suite_heldout.toml \
  --seed-key "sealed-seed" \
  --min-dev-diff-sum 5 \
  --request-out /tmp/stat_cert_request.json \
  --signed-cert-out /tmp/stat_cert_signed.json \
  --module-out /tmp/module.json \
  --candidate-module /tmp/candidate_defs.json
```

The script:

- evaluates on the dev suite first
- refuses to proceed if dev diff_sum is below the threshold
- issues and checks a heldout stat_cert
- commits and adopts only if heldout passes the threshold

## Rotate heldout suite

1. Generate a new JSONL suite.
2. Compute the hash: `cdel sealed suite-hash --path <suite.jsonl>`.
3. Copy to the heldout suites directory as `<hash>.jsonl`.
4. Update `configs/sealed_suite_heldout.toml` with the new hash.
