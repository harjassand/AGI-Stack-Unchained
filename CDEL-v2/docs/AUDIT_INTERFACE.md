# Audit Interface

This document explains how to audit `stat_cert` records and interpret the
risk-control decision.

## Quick audit command

```bash
cdel audit stat-cert <module_hash>
```

This prints the key audit fields:

- `evalue_schema_version`
- `key_id`
- `eval_harness_id`, `eval_harness_hash`, `eval_suite_hash`
- `alpha_i`, `threshold` (computed as `1/alpha_i`)
- `evalue` (mantissa + exponent10)
- `decision` with rule `evalue * alpha_i >= 1`

## Manual audit checklist

For a module payload hash in the ledger:

1) Read the payload JSON and locate `specs[kind="stat_cert"]`.
2) Confirm the sealed config in `config.toml` matches the cert:
   - `key_id` in allowed keys
   - `eval_harness_id`, `eval_harness_hash`, `eval_suite_hash`
3) Verify the certificate fields:
   - `evalue_schema_version == 2`
   - `evalue.mantissa` and `evalue.exponent10` present
   - `alpha_i` matches the alpha schedule for the round
4) Apply the decision rule:
   - accept iff `evalue * alpha_i >= 1`

The verifier enforces these checks for commits; this guide is for independent
third-party audits.

## Alpha state audit

```bash
cdel audit alpha --limit 10
```

This prints the configured schedule, current round, alpha spent, and the most
recent acceptance decisions.
