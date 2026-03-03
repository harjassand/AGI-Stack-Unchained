# Configs

Centralized static configuration inputs for mission execution, schema validation, and thermo fixtures.

## Files

- `mission_request_v1.json`: Mission request payload consumed by orchestration entrypoints.
- `mission_request_v1.jsonschema`: JSON Schema for validating mission requests.
- `omega_axis_gate_exemptions_v1.json`: Explicit relpath exemptions for axis gates.
- `sealed_thermo_fixture_v1.toml`: Fixture thermo target set.
- `sealed_thermo_grand_challenge_heldout.toml`: Heldout thermo target set.
- `sealed_thermo_live_capture_v1.toml`: Live-capture thermo target set.

## Operating Rules

1. Keep configs declarative and deterministic; no generated timestamps.
2. Treat schema files as API contracts between orchestration and verification layers.
3. When changing mission contracts, update both payload examples and schema together.

## Validation Workflow

```bash
python3 -m json.tool configs/mission_request_v1.json > /dev/null
python3 -m json.tool configs/omega_axis_gate_exemptions_v1.json > /dev/null
```

For schema-level validation, run the repository validator/test path that consumes `mission_request_v1.jsonschema`.
