# Phase4 Probe After Splice-Coupling + MDL/Gate Rebalance (2026-03-01)

## Applied changes

1. Splice coupling scale in incubator lane set to full strength:
   - `/Users/harjas/AGI-Stack-Unchained/baremetal_lgp/src/apfsc/lanes/incubator.rs` line 147
   - `Some((&item.shadow_head, 1.0))`

2. Probe config updated:
   - `/Users/harjas/.apfsc/config/phase4_frontier_probe.toml`
   - `phase2.min_nonprotected_improved_families = 0`
   - `phase2.normalization.codelen_ref_bytes = 67108864`

3. Constellation rebuilt from updated probe config:
   - `cargo run -p baremetal_lgp --release --bin apfsc_build_constellation -- --root /Users/harjas/.apfsc --config /Users/harjas/.apfsc/config/phase4_frontier_probe.toml`
   - new active constellation: `8771bc30ce3c1444e866aa9447aa755b083cb97fdcee1f4df90ccc7268b718d5`

## 1-epoch release probe

Command:

```bash
cargo run -p baremetal_lgp --release --bin apfsc_epoch_run -- \
  --root /Users/harjas/.apfsc \
  --config /Users/harjas/.apfsc/config/phase4_frontier_probe.toml \
  --profile phase4 \
  --epochs 1
```

Result:

- `epoch=1 public=0 judge=2 canary=1`

## Key evidence

### A) `improved_families > 0` occurred

Public static receipt:

- `/Users/harjas/.apfsc/receipts/public_static/182b4c58476047ba069e9c69fe429412f2378c7dfaba4b908bb4f0b667083fd4.json`
- build meta mutation: `splice_periodicity_macro`
- `improved_families = ["det_micro"]`

### B) First successful promotion occurred in this epoch

Judge/activation:

- promoted candidate: `a354a23c8a0c6d65300d584796efb6f2e9ef04cd00d6184e78273c198dd660e3`
- `/Users/harjas/.apfsc/receipts/judge/a354a23c8a0c6d65300d584796efb6f2e9ef04cd00d6184e78273c198dd660e3.json`
- decision: `Promote`
- `/Users/harjas/.apfsc/receipts/activation/a354a23c8a0c6d65300d584796efb6f2e9ef04cd00d6184e78273c198dd660e3.json`
- active pointer updated to `a354...`

### C) Architecture lane reached canary but failed

- candidate: `6cffc8ef0f8e32ea08767d620434dd18bb6fe0b30cef4483d78af9ba2f12aab3`
- class: `PCold`
- `/Users/harjas/.apfsc/receipts/judge/6cffc8ef0f8e32ea08767d620434dd18bb6fe0b30cef4483d78af9ba2f12aab3.json`
- decision: `Reject(CanaryFail)`
- `/Users/harjas/.apfsc/receipts/canary/6cffc8ef0f8e32ea08767d620434dd18bb6fe0b30cef4483d78af9ba2f12aab3.json`

### D) MDL balance now near 50/50 (no longer code-dominated)

Best public-static candidate in this run:

- `weighted_static_public_bpb = 0.0567035141`
- `code_penalty_bpb = 0.0254870653`
- panel component = `0.0312164488`

Approx split:

- code penalty ~44.95%
- panel term ~55.05%

## Note on splice admission bottleneck

The splice candidate that showed `improved_families=["det_micro"]` has transfer protection failure on public transfer:

- `/Users/harjas/.apfsc/receipts/public_transfer/182b4c58476047ba069e9c69fe429412f2378c7dfaba4b908bb4f0b667083fd4.json`
- `protected_floor_pass = false`
- regressed families include all six families

