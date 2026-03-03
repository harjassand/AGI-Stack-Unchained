# v1_6r

> Path: `CDEL-v2/cdel/v1_6r`

## Mission

Core verifier/runtime implementation for CDEL protocol versions and shared primitives.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- `adversary/`: component subtree.
- `campaign/`: component subtree.
- `cmeta/`: component subtree.
- `ctime/`: component subtree.
- `diagnostics/`: component subtree.
- `family_dsl/`: component subtree.
- `ontology_v2/`: component subtree.
- `portfolio/`: component subtree.
- `proposals/`: component subtree.
- `proposers/`: component subtree.
- `sr_cegar/`: component subtree.
- `suites/`: component subtree.
- `tests/`: tests and validation assets.
- `tools/`: tooling and helper binaries.

## Key Files

- `__init__.py`: Python module or executable script.
- `barrier.py`: Python module or executable script.
- `bundle.py`: Python module or executable script.
- `canon.py`: Python module or executable script.
- `cli.py`: Python module or executable script.
- `constants.py`: Python module or executable script.
- `epoch.py`: Python module or executable script.
- `eval_runner.py`: Python module or executable script.
- `family_semantics.py`: Python module or executable script.
- `mech_patch_eval.py`: Python module or executable script.
- `phi_core.py`: Python module or executable script.
- `pi0.py`: Python module or executable script.
- `pi0_gate_eval.py`: Python module or executable script.
- `promotion.py`: Python module or executable script.
- `rsi.py`: Python module or executable script.
- `rsi_integrity_tracker.py`: Python module or executable script.
- `rsi_portfolio_tracker.py`: Python module or executable script.
- `rsi_tracker.py`: Python module or executable script.
- `rsi_transfer_tracker.py`: Python module or executable script.
- `run_rsi_campaign.py`: Python module or executable script.
- `suite_eval.py`: Python module or executable script.
- `verify_rsi_ignition.py`: Python module or executable script.
- `verify_rsi_integrity.py`: Python module or executable script.
- `verify_rsi_ontology_v2.py`: Python module or executable script.
- `verify_rsi_portfolio.py`: Python module or executable script.
- ... and 3 more files.

## File-Type Surface

- `py`: 28 files

## Operational Checks

```bash
ls -la CDEL-v2/cdel/v1_6r
find CDEL-v2/cdel/v1_6r -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/cdel/v1_6r | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
