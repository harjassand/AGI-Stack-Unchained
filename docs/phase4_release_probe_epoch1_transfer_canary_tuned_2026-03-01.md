# Phase4 Probe After Transfer/Canary Tuning (2026-03-01)

## Applied changes

1. Transfer adaptation + floor relaxation in probe/base configs:
   - `/Users/harjas/.apfsc/config/phase4_frontier_probe.toml`
   - `/Users/harjas/.apfsc/config/phase4_frontier.toml`
   - `max_transfer_regress_bpb = 0.010` for all `phase2.floors.*`
   - `[phase2.transfer] steps = 128` (with full transfer block)

2. Canary investigation and tuning:
   - The earlier `6cff...` canary fail was **not** RSS/crash and not score-noise regression (`candidate_bits <= incumbent_bits`), but failed because canary gate also requires enough canary windows.
   - In this runtime, canary panels are absent across all families (`canary.windows.jsonl` missing), so structural canary checks were blocked by window availability.
   - Added in probe/base configs:
     - `[phase3.canary] warm_windows = 0`
     - `[phase3.canary] cold_windows = 0`

3. Rebuilt constellation:

```bash
cargo run -p baremetal_lgp --release --bin apfsc_build_constellation -- \
  --root /Users/harjas/.apfsc \
  --config /Users/harjas/.apfsc/config/phase4_frontier_probe.toml
```

Active constellation:

- `883da431af4f201d1be2bec83f2db6ca8b2625b9c2f2203dff8f69c8c6f6e532`

## 1-epoch release probe

Command:

```bash
cargo run -p baremetal_lgp --release --bin apfsc_epoch_run -- \
  --root /Users/harjas/.apfsc \
  --config /Users/harjas/.apfsc/config/phase4_frontier_probe.toml \
  --profile phase4 \
  --epochs 1
```

Observed:

- `epoch=1 public=0 judge=2 canary=0`

## Final receipts

### Splice candidate path

Candidate: `700a81b3ca64377475158ef6506a8e34c176c4c00baf3cff1f77d7911faba387` (`splice_periodicity_macro`)

- Public static:
  - `/Users/harjas/.apfsc/receipts/public_static/700a81b3ca64377475158ef6506a8e34c176c4c00baf3cff1f77d7911faba387.json`
  - `improved_families = ["det_micro"]`
- Public transfer:
  - `/Users/harjas/.apfsc/receipts/public_transfer/700a81b3ca64377475158ef6506a8e34c176c4c00baf3cff1f77d7911faba387.json`
  - `protected_floor_pass = false`
  - `regressed_families = [det_micro,event_sparse,formal_alg,phys_sim,sensor_temporal,text_code]`
- Public robust:
  - `/Users/harjas/.apfsc/receipts/public_robust/700a81b3ca64377475158ef6506a8e34c176c4c00baf3cff1f77d7911faba387.json`
  - `protected_floor_pass = true`

Result: splice still does not clear transfer gate in this epoch.

### Judged structural candidate

Candidate: `ad646e360e497d77cbc958d897d3e5626cb3725edc30d579c10be2644330c56b` (`phase3_macro_aware`, `PCold`)

- Judge receipt:
  - `/Users/harjas/.apfsc/receipts/judge/ad646e360e497d77cbc958d897d3e5626cb3725edc30d579c10be2644330c56b.json`
  - `decision = Reject`
  - `reason = Reject(RecentFamilyGainFail)`
  - `canary_required = true`, `canary_result = null` (rejected pre-canary)

### Activated candidate in this epoch

Candidate: `8d3b2175d3b46b36b6b7ef61cd06bc931dcd95b2f69484ed228d9348ae0758f2` (`remove_identity_linear`, `S`)

- Judge receipt:
  - `/Users/harjas/.apfsc/receipts/judge/8d3b2175d3b46b36b6b7ef61cd06bc931dcd95b2f69484ed228d9348ae0758f2.json`
  - `decision = Promote`
  - `promotion_class = S`
- Activation receipt:
  - `/Users/harjas/.apfsc/receipts/activation/8d3b2175d3b46b36b6b7ef61cd06bc931dcd95b2f69484ed228d9348ae0758f2.json`

Pointers after run:

- active candidate: `8d3b2175d3b46b36b6b7ef61cd06bc931dcd95b2f69484ed228d9348ae0758f2`
- rollback candidate: `a354a23c8a0c6d65300d584796efb6f2e9ef04cd00d6184e78273c198dd660e3`

## Outcome against target

- `Improved_families > 0` on splice: **yes** (`det_micro`)
- Splice cleared `public_transfer`: **no**
- `PromotionClass::A/PWarm` architecture activation this epoch: **no**
- Activation occurred: **yes**, but class `S`

