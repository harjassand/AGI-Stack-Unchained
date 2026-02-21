# Endgame Evidence Pack v1

## Pinned Contracts and Profiles
- Campaign pack: `campaigns/rsi_omega_daemon_v19_0_phase4d_epistemic_airlock/rsi_omega_daemon_pack_v1.json`
- `shadow_corpus_descriptor_id`: `sha256:2952d571676ddea1e5f0b3d4ed9bb23b60806d5bc615c59ed5dd4be801e33e42`
- `shadow_graph_invariance_contract_id`: `sha256:b097d3e4b2445464897c6eafc10b5ed9eac895cb172d1f9c0a8a9980dea7fd9a`
- `shadow_type_binding_invariance_contract_id`: `sha256:0597977540f82878921a3791e97e840096975560f605c4d7ad0d19b68cc5a39e`
- `shadow_cert_invariance_contract_id`: `sha256:d2dcbd5a6310bdae8787ca091075f3e47fba441c0598c657416e6d83f9d7e755`
- `shadow_instruction_strip_contract_id`: `sha256:29cdfb0d962508ec29bdaa772fc29e3b0c2b6ead068b71f0f7718c28e4bbb67b`
- `shadow_cert_profile_id`: `sha256:0aa48f4463696fe575a74342ff064dfe3f29af746ea4dd09dd4b2c2eeebf75f6`
- Comparator mode is pinned `ID_EQUAL` in `campaigns/rsi_omega_daemon_v19_0_phase4d_epistemic_airlock/cert_invariance_contract_v1.json`
- Retention non-destructive policy is pinned `deletion_mode=PLAN_ONLY` in `campaigns/rsi_epistemic_reduce_v1/epistemic_retention_policy_v1.json`

## Scripts to Run
- Closure:
```bash
python3 scripts/run_epistemic_airlock_closure_v1.py \
  --out-dir runs/epistemic_airlock_closure_v1_evidence \
  --tick-base 9300
```
- Phase4C drill (simulate):
```bash
python3 scripts/run_phase4c_real_swap_drill_v1.py \
  --simulate \
  --out-dir runs/phase4c_real_swap_drill_v1_evidence \
  --tick-base 8100
```
- Multi-tick canary (>=100):
```bash
python3 scripts/run_epistemic_airlock_closure_v1.py \
  --out-dir runs/epistemic_airlock_canary_v1_evidence \
  --tick-base 9500 \
  --ticks 100
```

## Phase4D Fixtures
- Root fixture pack: `campaigns/rsi_omega_daemon_v19_0_phase4d_epistemic_airlock`
- Corpus descriptor: `campaigns/rsi_omega_daemon_v19_0_phase4d_epistemic_airlock/corpus_descriptor_v1.json`
- Shadow entry manifests: `campaigns/rsi_omega_daemon_v19_0_phase4d_epistemic_airlock/entries`
- Regime proposal/profile/contracts:
  - `campaigns/rsi_omega_daemon_v19_0_phase4d_epistemic_airlock/shadow_regime_proposal_v1.json`
  - `campaigns/rsi_omega_daemon_v19_0_phase4d_epistemic_airlock/shadow_evaluation_tiers_v1.json`
  - `campaigns/rsi_omega_daemon_v19_0_phase4d_epistemic_airlock/witnessed_determinism_profile_v1.json`
  - `campaigns/rsi_omega_daemon_v19_0_phase4d_epistemic_airlock/graph_invariance_contract_v1.json`
  - `campaigns/rsi_omega_daemon_v19_0_phase4d_epistemic_airlock/type_binding_invariance_contract_v1.json`
  - `campaigns/rsi_omega_daemon_v19_0_phase4d_epistemic_airlock/cert_invariance_contract_v1.json`

## Merge Gates
- CI workflow now includes job `phase4c-epistemic-merge-gates` in `.github/workflows/ci.yml`
- Gate tests:
  - `CDEL-v2/cdel/v19_0/tests_omega_daemon/test_phase4c_real_swap_drill_v1.py`
  - `CDEL-v2/cdel/v19_0/tests_continuity/test_corpus_descriptor_v1.py`
  - `CDEL-v2/cdel/v19_0/tests_continuity/test_shadow_airlock_v1.py`
  - `CDEL-v2/cdel/v19_0/tests_omega_daemon/test_epistemic_airlock_v1.py`
- Branch protection on `main` now requires:
  - `CI / test`
  - `CI / phase4c-epistemic-merge-gates`
- Protection snapshot: `runs/validation_evidence/BRANCH_PROTECTION_MAIN_v1.json`

## DONE Definition
- `verify_rsi_omega_daemon_v1.log` is `VALID`
- retention verifier log is `VALID`
- drill verifier log is `VALID`
- cross-environment determinism spot-check passes:
  - invariance receipt IDs are equal (`ID_EQUAL`)
  - corpus descriptor and manifest pins match
  - ffmpeg pin enforcement remains fail-closed
- CI required checks are green.
