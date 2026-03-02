# Phase4 1-Epoch Release Probe Report (2026-03-01)

## Run command and outcome

Command:

```bash
cargo run -p baremetal_lgp --release --bin apfsc_epoch_run -- \
  --root /Users/harjas/.apfsc \
  --config /Users/harjas/.apfsc/config/phase4_frontier_probe.toml \
  --profile phase4 \
  --epochs 1
```

Observed terminal summary:

- `epoch=1 public=0 judge=1 canary=0`
- wall time: ~31.43s
- peak RSS: ~18 MB

## Probe artifacts

- Raw probe analysis JSON: `/Users/harjas/AGI-Stack-Unchained/docs/phase4_release_probe_epoch1_analysis_2026-03-01.json`
- Probe config: `/Users/harjas/.apfsc/config/phase4_frontier_probe.toml`
- Copied config: `/Users/harjas/AGI-Stack-Unchained/docs/phase4_frontier_probe.toml`

## 1) Top-3 `public_static` receipts and MDL split

Top-3 by lowest `weighted_static_public_bpb` from touched receipts at `mtime=1772325237`:

1. `6cffc8ef0f8e32ea08767d620434dd18bb6fe0b30cef4483d78af9ba2f12aab3` (`incubator`, `phase3_macro_aware`)
   - `weighted_static_public_bpb = 417.60348361761027`
   - `code_penalty_bpb = 417.572265625`
   - panel component (`weighted_static_public_bpb - code_penalty_bpb`) = `0.03121799261026581`
   - `improved_families = []`

2. `a354a23c8a0c6d65300d584796efb6f2e9ef04cd00d6184e78273c198dd660e3` (`equivalence`, `remove_identity_linear`)
   - `weighted_static_public_bpb = 417.60543674261027`
   - `code_penalty_bpb = 417.57421875`
   - panel component = `0.03121799261026581`
   - `improved_families = []`

3. `d958da075aca2a2cdd9830a210635d7bdbc74df66e1c3427d171b3091a0cf6dc` (`truth`, `swap_simple_scan_medium`)
   - `weighted_static_public_bpb = 417.60543674261027`
   - `code_penalty_bpb = 417.57421875`
   - panel component = `0.03121799261026581`
   - `improved_families = []`

Interpretation:

- Code penalty dominates the objective (~99.9925% of weighted static for these top receipts).
- The top-3 all have identical panel term (`~0.031218 bpb`); ranking differences are mostly/entirely code-size penalty.
- This run does not show a predictive-NLL win signal (`improved_families` is empty and target subset fails).

Evidence files:

- `/Users/harjas/.apfsc/receipts/public_static/6cffc8ef0f8e32ea08767d620434dd18bb6fe0b30cef4483d78af9ba2f12aab3.json`
- `/Users/harjas/.apfsc/receipts/public_static/a354a23c8a0c6d65300d584796efb6f2e9ef04cd00d6184e78273c198dd660e3.json`
- `/Users/harjas/.apfsc/receipts/public_static/d958da075aca2a2cdd9830a210635d7bdbc74df66e1c3427d171b3091a0cf6dc.json`
- `/Users/harjas/.apfsc/candidates/<hash>/build_meta.json`

## 2) Zero-init / identity behavior check

### Equivalence lane

- Equivalence candidates clone incumbent packs (`head_pack`, `state_pack`, `schedule_pack`) and apply deterministic rewrites:
  - `/Users/harjas/AGI-Stack-Unchained/baremetal_lgp/src/apfsc/lanes/equivalence.rs` lines 16-92.
- Witness-equality filter keeps only candidates with near-identical output (`tol = 1e-6`):
  - `/Users/harjas/AGI-Stack-Unchained/baremetal_lgp/src/apfsc/lanes/equivalence.rs` lines 98-129.
- Inserted linear identity is explicit passthrough in interpreter when `!mutable && !bias && in_dim==out_dim`:
  - rewrite creation: `/Users/harjas/AGI-Stack-Unchained/baremetal_lgp/src/apfsc/scir/rewrite.rs` lines 4-35.
  - interpreter path: `/Users/harjas/AGI-Stack-Unchained/baremetal_lgp/src/apfsc/scir/interp.rs` lines 66-76.

Conclusion: equivalence lane is designed to be identity-preserving at initialization and filtered by witness equality.

### Truth lane

- Some structural mutations change program dimensions while reusing incumbent head pack unchanged:
  - `mutation_add_lag`: `/Users/harjas/AGI-Stack-Unchained/baremetal_lgp/src/apfsc/lanes/truth.rs` lines 106-134.
  - `mutation_scan_medium`: `/Users/harjas/AGI-Stack-Unchained/baremetal_lgp/src/apfsc/lanes/truth.rs` lines 136-161.
- During scoring, feature vectors are adapted to head input size by truncate/pad:
  - callsite: `/Users/harjas/AGI-Stack-Unchained/baremetal_lgp/src/apfsc/bytecoder.rs` line 65.
  - implementation: `/Users/harjas/AGI-Stack-Unchained/baremetal_lgp/src/apfsc/bytecoder.rs` lines 96-105.
- `mutation_add_feature_node` explicitly extends all heads with zero weights and zero residual entries:
  - `/Users/harjas/AGI-Stack-Unchained/baremetal_lgp/src/apfsc/lanes/truth.rs` lines 211-229.

Conclusion: no random init/noise injection is visible in Truth/Equivalence mutation paths; zero-init identity behavior exists for added channels, while some dimension-changing mutations rely on feature adaptation rather than full head resize.

## 3) Incubator utility / splice viability

- Splice admission requires `utility_bits > incubator_min_utility_bits`:
  - `/Users/harjas/AGI-Stack-Unchained/baremetal_lgp/src/apfsc/lanes/incubator.rs` lines 97-106.
- Default threshold is `8.0` bits if not overridden:
  - `/Users/harjas/AGI-Stack-Unchained/baremetal_lgp/src/apfsc/config.rs` lines 794-796.
- In this Phase4 run path, sidecar generation (`incubator::generate`) is not used; only `phase3_macro_aware_candidates` are used in Phase3/Phase4 candidate pools:
  - phase3 pool includes `phase3_macro_aware_candidates`: `/Users/harjas/AGI-Stack-Unchained/baremetal_lgp/src/apfsc/orchestrator.rs` lines 1088-1092.
  - phase4 expansion also includes `phase3_macro_aware_candidates`: `/Users/harjas/AGI-Stack-Unchained/baremetal_lgp/src/apfsc/orchestrator.rs` lines 1689-1694.
- Sidecar + splice path (`incubator::generate` + `materialize_splice_candidates`) appears in Phase1/Phase2 code paths:
  - `/Users/harjas/AGI-Stack-Unchained/baremetal_lgp/src/apfsc/orchestrator.rs` lines 101-103 and 432-435.

Conclusion: in this exact `profile=phase4` probe, incubator sidecars are effectively not evaluated for utility, so no splice candidates can clear threshold in this run mode.

## Additional gating evidence

Active constellation normalization in runtime remains strict/stale:

- `min_improved_families = 2`
- `require_target_subset_hit = true`
- `public_static_margin_bpb = 0.001`

Evidence:

- active pointer: `/Users/harjas/.apfsc/pointers/active_constellation`
- manifest: `/Users/harjas/.apfsc/constellations/11d667a61423788fa209a354d614ca5566f1d6aaa1f9054055172aa41a4a8489.json`

This explains why `phase4_frontier_probe.toml` relaxations did not take effect until constellation rebuild.

## Judge outcome

Latest judge receipt was incumbent-only fallback:

- `/Users/harjas/.apfsc/receipts/judge/d0e6c4004dfc653acbea70701c58fbbabd731cd9bf5c520acf0cced1819f575f.json`
- `candidate_hash == incumbent_hash`
- `decision = Reject`
- `reason = Reject(NoPublicMargin)`

