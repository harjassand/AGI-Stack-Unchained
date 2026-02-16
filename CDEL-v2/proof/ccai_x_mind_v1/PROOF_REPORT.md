# CCAI-X Mind v1 Proof Report

This proof pack is reproducible via `prove_ccai_x_mind_v1.sh` and verified by `verify_ccai_x_mind_v1.py`. The canonical evidence hashes are in `proof_manifest_run1.json` and `proof_manifest_run2.json`.

## Contracts (C0–C5)

- **C0 (hermetic + allowlist)**: PASS in `runs/run1/pass_dev` and `runs/run1/pass_heldout` with `blanket_attestation.json`; FAIL fixtures `fail_c0_hermetic_required` and `fail_c0_env_not_allowlisted`; blanket leak is `fail_blanket_leak`.
- **C1 (do-semantics)**: PASS via intervention log + do-map consistency in PASS runs; FAIL fixture `fail_c1_do_mismatch`.
- **C2 (proof-carrying EFE)**: PASS via byte-identical EFE recompute in PASS runs (`efe_report.jsonl` vs `efe_recompute.jsonl`); FAIL fixture `fail_c2_efe_mismatch` (fault-injected).
- **C3 (admissibility / projection)**: PASS with forbidden tokens blocked in PASS runs; FAIL fixture `fail_c3_no_admissible_actions`.
- **C4 (heldout required)**: PASS in `pass_heldout`; FAIL fixture `fail_c4_heldout_dir_required`.
- **C5 (coherence bound)**: PASS residuals recorded in PASS runs; FAIL fixture `fail_c5_coherence_gate`.

## Selection pressures (suitepack IDs)

**Dev (PASS):**
- ψ-swap: `ccai_x_mind_dev_psi_swap_v1`
- ambiguity trap: `ccai_x_mind_dev_ambiguity_trap_v1`
- invariance battery: `ccai_x_mind_dev_invariance_v1`
- coherence suite: `ccai_x_mind_dev_coherence_v1`
- tamper/dark-room: `ccai_x_mind_dev_tamper_v1`

**Heldout (PASS):**
- ψ-swap: `ccai_x_mind_heldout_psi_swap_v1`
- ambiguity trap: `ccai_x_mind_heldout_ambiguity_trap_v1`
- invariance battery: `ccai_x_mind_heldout_invariance_v1`
- coherence suite: `ccai_x_mind_heldout_coherence_v1`
- tamper/dark-room: `ccai_x_mind_heldout_tamper_v1`

**Blanket leak (FAIL-closed):**
- `ccai_x_mind_fail_blanket_leak_v1` (expected FAIL with C0)

## Falsifiable predictions A–F (minimal evidence)

- **A (ψ-swap)**: `ccai_x_mind_dev_psi_swap_v1` and heldout ψ-swap suitepacks.
- **B (ambiguity trap)**: `ccai_x_mind_dev_ambiguity_trap_v1` and heldout ambiguity suitepacks.
- **C (invariance)**: `ccai_x_mind_dev_invariance_v1` and heldout invariance suitepacks.
- **D (coherence)**: `ccai_x_mind_dev_coherence_v1`, heldout coherence suitepacks, plus `fail_c5_coherence_gate`.
- **E (blanket leak)**: `fail_blanket_leak` (C0 fail-closed).
- **F (tamper / dark-room)**: `ccai_x_mind_dev_tamper_v1` and heldout tamper suitepacks; admissibility FAIL fixture `fail_c3_no_admissible_actions`.
