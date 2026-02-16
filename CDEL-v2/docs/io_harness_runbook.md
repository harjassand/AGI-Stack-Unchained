# IO Harness Runbook

This runbook covers the supervised I/O sealed harness (`io-harness-v1`).

## Suite format

Each line in the suite JSONL is:

```json
{"episode":0,"args":[{"tag":"int","value":0}],"target":{"tag":"bool","value":true}}
```

- `args` is a list of ValueJSON arguments.
- `target` is the expected ValueJSON output.

## Hashing

Compute the suite hash using:

```bash
python -m cdel.cli sealed suite-hash --path /path/to/suite.jsonl
```

Store the suite at `sealed_suites/<hash>.jsonl` for dev, and provide heldout suites via `CDEL_SUITES_DIR`.

## Config

Use a sealed config with:

```toml
[sealed]
eval_harness_id = "io-harness-v1"
eval_harness_hash = "io-harness-v1-hash"
eval_suite_hash = "<suite hash>"
episodes = <N>
```

## Notes

- The harness ignores `oracle_symbol` in the request (kept for schema compatibility).
- Baseline/candidate type checking still requires an oracle symbol to exist in the ledger.
