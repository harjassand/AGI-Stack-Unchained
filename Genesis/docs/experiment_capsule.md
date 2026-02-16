# Experiment Capsules (Level-1)

Experiment capsules generate data or probes to discriminate hypotheses without touching private CDEL holdouts.

## Representation (Normative)

Experiments are represented as **EXPERIMENT** capsules with a required entrypoint:

```
entrypoint: run_experiment(input_spec) -> dataset_handle
```

## Allowed Effects

- `read_only` is REQUIRED.
- `filesystem_read` MAY be used to access sandboxed simulator handles.
- `network` and `filesystem_write` are FORBIDDEN.

## Required Contract Clauses

- **ResourceSpec:** strict caps on time, memory, and sample count.
- **FunctionalSpec:** output dataset handle schema and checksum format.
- **SafetySpec:** no side effects outside the sandbox.
- **StatisticalSpec:** optional; used when experiment quality is scored.
- **RobustnessSpec:** required only if experiment outputs are used for robustness claims.

## Dataset Handle Schema

An experiment MUST output a dataset handle with:

- `handle_id`
- `schema_id`
- `checksum`
- `provenance` (capsule hash + parameters)

## Selection Policy (Non-Private)

Genesis SHOULD prioritize experiments that maximize information gain or model disagreement, computed on public data only.

## Prohibited Inputs

Experiments MUST NOT access CDEL private holdouts or DP-protected evaluation data.
