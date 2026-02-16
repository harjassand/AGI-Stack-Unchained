# Suite Harness Runbook (v1)

## Suite JSONL format

Each line is a JSON object with an `args` array. Example:

```json
{"args":[{"tag":"int","value":3}]}
```

Supported ValueJSON tags:

- `{"tag":"int","value":3}`
- `{"tag":"bool","value":true}`
- `{"tag":"list","items":[...]}`
- `{"tag":"none"}`
- `{"tag":"some","value":...}`
- `{"tag":"pair","left":...,"right":...}`
- `{"tag":"fun","name":"symbol_name"}`

Each `args` list must match the oracle function arity.

## Suite file placement

Suites are content-addressed. Place the file at:

```
sealed_suites/<suite_hash>.jsonl
```

The harness resolves suites by `<project_root>/sealed_suites/<eval_suite_hash>.jsonl`.

## Compute suite hash

```bash
cdel sealed suite-hash --path sealed_suites/my_suite.jsonl
```

Use the returned hex hash as `sealed.eval_suite_hash`.

## Run suite smoke

```bash
scripts/smoke_statcert_adopt_suite.sh
```

## Rotate suites

1. Generate a new JSONL file.
2. Compute the hash with `cdel sealed suite-hash`.
3. Copy/rename to `sealed_suites/<new_hash>.jsonl`.
4. Update `configs/sealed_suite.toml` with the new hash.
