# Stat Cert + CAL Runbook

This runbook exercises the sealed certificate flow end-to-end:
keygen → stat cert → CDEL commit → CAL adopt → resolve.

For signing/canonicalization details, see `docs/sealed_signing.md`.

## Install + test

```bash
python3 -m pip install -e ".[dev]"
python3 -m compileall -q cdel tests
pytest -q
```

Run commands from the repo root; do not rely on installed `*.egg-info` metadata.

## Smoke script

```bash
scripts/smoke_statcert_adopt.sh
```

## Initialize ledger

```bash
cdel init --budget 1000000
```

## Generate keys

```bash
cdel sealed keygen --out sealed_keypair.json
# deterministic keygen: add --seed "fixed-seed"
```

Add the public key + key_id to `config.toml` under `[sealed]`:

```
public_key = "<base64>"
key_id = "<id>"
alpha_total = "1e-4"
eval_harness_id = "toy-harness-v1"
eval_harness_hash = "harness-hash"
eval_suite_hash = "suite-hash"
[sealed.alpha_schedule]
name = "p_series"
exponent = 2
coefficient = "0.60792710185402662866"
```

## Create and sign a stat cert

Prepare candidate definitions for the sealed worker (so it can evaluate the new symbol):

```bash
cat > candidate_defs.json <<'JSON'
{
  "new_symbols": ["inc_v2"],
  "definitions": [
    {
      "name": "inc_v2",
      "params": [{"name": "n", "type": {"tag": "int"}}],
      "ret_type": {"tag": "int"},
      "body": {"tag": "prim", "op": "add", "args": [{"tag": "var", "name": "n"}, {"tag": "int", "value": 1}]},
      "termination": {"kind": "structural", "decreases_param": null}
    }
  ],
  "declared_deps": ["inc"],
  "specs": [],
  "concepts": [{"concept": "increment", "symbol": "inc_v2"}]
}
JSON
```

Create a stat cert request (set a low threshold for the toy example):

```bash
cat > stat_cert.json <<'JSON'
{
  "kind": "stat_cert",
  "concept": "increment",
  "metric": "accuracy",
  "null": "no_improvement",
  "baseline_symbol": "inc",
  "candidate_symbol": "inc_v2",
  "eval": {"episodes": 4, "max_steps": 50, "paired_seeds": true, "oracle_symbol": "inc"},
  "risk": {"evalue_threshold": "1e-6"}
}
JSON
```

```bash
cdel sealed worker --request stat_cert.json --out stat_cert_signed.json \
  --private-key "$(jq -r .private_key sealed_keypair.json)" \
  --seed-key "sealed-seed" \
  --candidate-module candidate_defs.json
```

The signed certificate can now be embedded into a module `specs` entry.

Optional: write audit artifacts (per-episode outcomes) alongside the cert:

```bash
cdel sealed worker --request stat_cert.json --out stat_cert_signed.json \
  --private-key "$(jq -r .private_key sealed_keypair.json)" \
  --seed-key "sealed-seed" \
  --artifact-dir sealed/artifacts
```

Artifacts are keyed by `transcript_hash` and reproducible with the same harness/suite/seed.

## Commit + adopt

```bash
cdel verify module.json
cdel commit module.json
cdel adopt adoption.json
```

## Revert adoption (append-only)

```bash
cdel adopt revert --concept is_even --to is_even_v1 --cert cert.json
```

Reverts require a certificate that matches the target and current baseline.

## Resolve

```bash
cdel resolve --concept is_even
```
