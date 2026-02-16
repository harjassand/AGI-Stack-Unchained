# CDEL Prototype

Certified Definitional Extension Ledger (CDEL) prototype implementation.

## Quickstart (dev)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m compileall -q cdel tests
pytest -q
```

## Smoke tests

```bash
scripts/smoke_e2e.sh
scripts/smoke_rebuild.sh
scripts/smoke_statcert_adopt.sh
scripts/smoke_generalization_experiment.sh
```

## CLI examples

```bash
cdel init --budget 1000000
cdel run-tasks tasks/stream_min.jsonl --generator enum --out runs/min
cdel check-invariants
cdel eval --expr '{"tag":"app","fn":{"tag":"sym","name":"inc"},"args":[{"tag":"int","value":1}]}'
```

## Stat cert runbook

See `docs/stat_cert_runbook.md` for the sealed certificate + CAL adoption flow.

## Sealed signing

See `docs/sealed_signing.md` for the canonicalization contract used in sealed signatures.

## Learning claims

See `docs/learning_claims.md` for the learning definition, risk control, and non-interference statement.

## Generalization experiment

```bash
cdel run-generalization-experiment --out runs/generalization
```
