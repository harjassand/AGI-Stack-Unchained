# Level-1 RC Manifest

spec_version: 1.0.1
schema_version: 1.0.0
git_ref: v1.0.0
git_ref_type: annotated_tag
resolution_rule: git rev-parse <git_ref>

## Normative Schemas

- `schema/capsule.schema.json`
- `schema/receipt.schema.json`

## Examples

- `examples/algorithm.capsule.json`
- `examples/world_model.capsule.json`
- `examples/causal_model.capsule.json`
- `examples/policy.capsule.json`
- `examples/experiment.capsule.json`
- `receipt_examples/pass_receipt.json`

## Normative Docs

- `docs/evaluate_protocol.md`
- `docs/canonicalization.md`
- `docs/enums.md`
- `docs/verify_receipt.md`
- `docs/alpha_ledger.md`
- `docs/privacy_ledger.md`
- `docs/compute_ledger.md`
- `docs/contract_taxonomy.md`
- `docs/contract_calculus.md`
- `docs/robustness_spec.md`
- `docs/assumptions_spec.md`
- `docs/determinism_attestation.md`
- `docs/tcb_boundary.md`
- `docs/shadow_cdel.md`
- `docs/genesis_interfaces.md`
- `docs/promotion_policy.md`
- `docs/experiment_capsule.md`

## Tools

- `tools/run_checks.sh`
- `run_checks.sh`
- `tools/validate_schema.py`
- `tools/validate_receipt.py`
- `tools/verify_receipt.py`
- `tools/canonicalize.py`
- `tools/check_links.py`
- `tools/consistency_check.py`

## Test Vectors

- `test_vectors/capsule_minimal.json`
- `test_vectors/capsule_minimal.hash.txt`
- `test_vectors/receipt_minimal.json`
- `test_vectors/receipt_minimal.hash.txt`

## Ledger Simulators

- `ledger_sim/alpha_ledger_sim.py`
- `ledger_sim/privacy_ledger_sim.py`
- `ledger_sim/compute_ledger_sim.py`

## How to Run Checks

```bash
python3 -m pip install -r requirements-dev.txt
./run_checks.sh
```
