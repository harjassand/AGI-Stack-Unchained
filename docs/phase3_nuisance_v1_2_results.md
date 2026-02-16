# Phase-3 Nuisance Rate-Scale Solver v1.2 Results

Date: 2026-01-29

## Tests Run

1) Full suites (required)
- Command:
```
python3 -m pytest CDEL-v2/extensions/caoe_v1/tests -q
```
- Output:
```
.....................................                                    [100%]
37 passed in 2.57s
```

- Command:
```
python3 -m pytest Extension-1/caoe_v1/tests -q
```
- Output:
```
.................                                                        [100%]
17 passed in 1.25s
```

2) Determinism (guided order, run 1)
- Command:
```
python3 -m pytest Extension-1/caoe_v1/tests/test_guided_program_order_determinism_v1_2.py -q
```
- Output:
```
.                                                                        [100%]
1 passed in 0.00s
```

3) Determinism (guided order, run 2)
- Command:
```
python3 -m pytest Extension-1/caoe_v1/tests/test_guided_program_order_determinism_v1_2.py -q
```
- Output:
```
.                                                                        [100%]
1 passed in 0.00s
```

4) Candidate tar determinism
- Command:
```
python3 -m pytest Extension-1/caoe_v1/tests/test_candidate_tar_determinism_v1.py -q
```
- Output:
```
.                                                                        [100%]
1 passed in 0.03s
```

5) No-heldout-read
- Command:
```
python3 -m pytest Extension-1/caoe_v1/tests/test_no_heldout_read_v1.py -q
```
- Output:
```
.                                                                        [100%]
1 passed in 0.56s
```

6) Oracle tests
- Command:
```
python3 -m pytest Extension-1/caoe_v1/tests/test_oracles_nuisance_k2_v1_2.py -q
```
- Output:
```
.                                                                        [100%]
1 passed in 0.06s
```

7) Macro duration accounting
- Command:
```
python3 -m pytest Extension-1/caoe_v1/tests/test_macro_duration_accounting_v1_2.py -q
```
- Output:
```
.                                                                        [100%]
1 passed in 0.05s
```

## Full Epoch Run (epoch_16_phase3_nuisance_v1_2_full_v3)

Run command (redacted):
```
CDEL_SEALED_PRIVKEY=<REDACTED>
META_CORE_ROOT=/Users/harjas/AGI-Stack-Clean/runs/caoe_v1_1/meta_core_root
python3 Extension-1/caoe_v1/cli/caoe_proposer_cli_v1.py run-epoch --epoch_id epoch_16_phase3_nuisance_v1_2_full_v3 --base_ontology /Users/harjas/AGI-Stack-Clean/runs/caoe_v1_1/run_0/state_chain_v1/current/base_ontology.json --base_mech /Users/harjas/AGI-Stack-Clean/runs/caoe_v1_1/run_0/state_chain_v1/current/base_mech.json --suitepack_dev /Users/harjas/AGI-Stack-Clean/runs/caoe_v1_1/suitepacks/dev/suitepack.json --suitepack_heldout /Users/harjas/AGI-Stack-Clean/runs/caoe_v1_1/suitepacks/heldout/suitepack.json --heldout_suite_id caoe_switchboard_heldout_v1 --cdel_bin /Users/harjas/AGI-Stack-Clean/runs/caoe_v1_1/run_0/cdel_shim --state_dir /Users/harjas/AGI-Stack-Clean/runs/caoe_v1_1/run_0/state_chain_v1 --out_dir /Users/harjas/AGI-Stack-Clean/runs/caoe_v1_1/run_0/epochs/epoch_16_phase3_nuisance_v1_2_full_v3 --max_candidates 16 --eval_plan full --workers 1 --dev_oracle_sequence /Users/harjas/AGI-Stack-Clean/runs/caoe_v1_1/run_0/oracles_phase3_v1_2/nuisance_k2_00_sequence_h32.json --dev_oracle_memoryless /Users/harjas/AGI-Stack-Clean/runs/caoe_v1_1/run_0/oracles_phase3_v1_2/nuisance_k2_00_memoryless_h32.json
```

Base heldout nuisance summary (from success_matrix.json):
- nuisance_k2_00 = 0.0 (base fails)

Selected candidate:
- candidate_id = `b1b7e08d48fa447c04828e0d4abe2c179a901a9a2b5b2c9e1f3c566c1c4bf230`
- dev nuisance gate = PASS (3/3)
- contracts = C-INV PASS, C-MDL PASS, C-DO PASS, C-ANTI PASS, C-LIFE PASS
- heldout nuisance worst_case_success = 1.0

Verifiers:
- `python3 Extension-1/caoe_v1/tools/verify_epoch_consistency_v1_1.py /Users/harjas/AGI-Stack-Clean/runs/caoe_v1_1/run_0/epochs/epoch_16_phase3_nuisance_v1_2_full_v3` (exit 0)
- `python3 Extension-1/caoe_v1/tools/verify_failure_witness_index_v1_1.py .../candidate_0 --out .../diagnostics/failure_witness_consistency_candidate_0.json` (exit 0)
- `python3 Extension-1/caoe_v1/tools/verify_failure_witness_index_v1_1.py .../candidate_1 --out .../diagnostics/failure_witness_consistency_candidate_1.json` (exit 0)

## Post-Promotion Epoch (epoch_17_phase3_nuisance_v1_2_post_promotion)

Run command (redacted):
```
CDEL_SEALED_PRIVKEY=<REDACTED>
META_CORE_ROOT=/Users/harjas/AGI-Stack-Clean/runs/caoe_v1_1/meta_core_root
python3 Extension-1/caoe_v1/cli/caoe_proposer_cli_v1.py run-epoch --epoch_id epoch_17_phase3_nuisance_v1_2_post_promotion --base_ontology /Users/harjas/AGI-Stack-Clean/runs/caoe_v1_1/run_0/state_chain_v1/current/base_ontology.json --base_mech /Users/harjas/AGI-Stack-Clean/runs/caoe_v1_1/run_0/state_chain_v1/current/base_mech.json --suitepack_dev /Users/harjas/AGI-Stack-Clean/runs/caoe_v1_1/suitepacks/dev/suitepack.json --suitepack_heldout /Users/harjas/AGI-Stack-Clean/runs/caoe_v1_1/suitepacks/heldout/suitepack.json --heldout_suite_id caoe_switchboard_heldout_v1 --cdel_bin /Users/harjas/AGI-Stack-Clean/runs/caoe_v1_1/run_0/cdel_shim --state_dir /Users/harjas/AGI-Stack-Clean/runs/caoe_v1_1/run_0/state_chain_v1 --out_dir /Users/harjas/AGI-Stack-Clean/runs/caoe_v1_1/run_0/epochs/epoch_17_phase3_nuisance_v1_2_post_promotion --max_candidates 16 --eval_plan full --workers 1 --dev_oracle_sequence /Users/harjas/AGI-Stack-Clean/runs/caoe_v1_1/run_0/oracles_phase3_v1_2/nuisance_k2_00_sequence_h32.json --dev_oracle_memoryless /Users/harjas/AGI-Stack-Clean/runs/caoe_v1_1/run_0/oracles_phase3_v1_2/nuisance_k2_00_memoryless_h32.json
```

Base row (heldout):
- nuisance_k2_00 = 1.0
- nuisance_k3_01 = 1.0
- render_hold_00..07 = 1.0

Verifiers:
- `python3 Extension-1/caoe_v1/tools/verify_epoch_consistency_v1_1.py /Users/harjas/AGI-Stack-Clean/runs/caoe_v1_1/run_0/epochs/epoch_17_phase3_nuisance_v1_2_post_promotion` (exit 0)
- `python3 Extension-1/caoe_v1/tools/verify_failure_witness_index_v1_1.py .../candidate_0 --out .../diagnostics/failure_witness_consistency_candidate_0.json` (exit 0)

## SHA256 (Epoch 16)
- selection.json: `a6cb27042338e905243a02e6baa7c07af85870b88e92c23467b6b5adb86e7e19`
- candidate_decisions.json: `75e90387bf1b733871229e249a69d10faf073b8f246a965a207ee6b8d194a654`
- success_matrix.json: `74c76dfe9e75768e86322918b13e0b1cdaec8b5240a34d910e572c2f713e083f`
- per_regime_candidate_best.json: `4873d0993c0a7b86b1a6801c282884dc1243c0b8f914245b56a1ae09615b101d`
- epoch_summary.json: `026486339eceba72f89228678207573bf110f16e9ad08c5b0703e19edfcb1a9c`
- epoch_consistency_report.json: `ad92b2d9edd5d6b233063d529301a1a6a200d6bab7202e5d11bb853031320a67`
- mdl_breakdown.json: `a9fbc8291e5a10baa66bfbb36e715e07b6aa575fe67752d36d797b886c117bd7`
- failure_witness_index_candidate_0.json: `d41b8bd28c1391f7529846a740b396d2792ac8e8143b7e9f3f338659538c65e0`
- failure_witness_index_candidate_1.json: `e66d9fb645acfa8976f3917a1e47e8ffbf5ff86b6903f8602f3edfd11050ba1a`
- failure_witness_consistency_candidate_0.json: `04198d60348332985541f3db92240cd390cb19a2ddc6968ede11757af44c3a8c`
- failure_witness_consistency_candidate_1.json: `75747fe4921d3a72e2a80c80a4d4e30249796fcb254e8e6ae4e291554fa89b90`

## SHA256 (Epoch 17)
- selection.json: `d79f07483c7a2a93b5410cc6bce536668a20d2e1bac4affe215b8a3f5d116ff0`
- candidate_decisions.json: `4afc287df05415d96ad13c2d59ae5f5dae2ff7961eaf9c2e6a07d9cfa3c42cea`
- success_matrix.json: `cb6738e1ae64933cd7623b3a3a01e83859d483e23375a61a8deffcc8da0fc746`
- per_regime_candidate_best.json: `41129797156a064ba4c4c78407e5e25fdec6b17218729822623dbbe27e7e6767`
- epoch_summary.json: `bd6848774bde749fd1103f46b7282e869f41d8e0dc044566cc56fb20203ff553`
- epoch_consistency_report.json: `86db8fdf065ebc5549d264e5bcb81bd6b2aab9075ec66e4aceca596001e31f72`
- mdl_breakdown.json: `bd510e780b5518dc507bcc9182789102624c0ef46a42ff805de8b6e324e34d34`
- failure_witness_index_candidate_0.json: `9b37525fdc622154edd11e64ab72449b2bf7c112e4f3c617eeb3c11e46f62255`
- failure_witness_consistency_candidate_0.json: `4774766b2b57e05c50b54d7311ffebe76337d9501bc1d6e2e2dc8fd9c76e6456`

## SHA256 (Promotion + Lifecycle)
- promotion_record.json: `35392a3c4c95f696c9009e66057a62f708be151c26c81cb2b981c4164787b790`
- lifecycle.json: `fdb2624b688b9fe9813e3fd5e1645220810e2117c34d0bc8c8a8468bfe3d5b38`

## Proof Pack
- `caoe_v1_2_phase3_nuisance_proofpack.tar`: `24079fc719a371513fdf9e2f30e50abf99943e21f55cdbb42bd5146fbe0b9604`
