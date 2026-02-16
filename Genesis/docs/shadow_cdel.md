# Shadow-CDEL One-Sided Screening (Level-1)

Shadow-CDEL is a conservative screening evaluator used during Genesis search. It MUST be one-sided: PASS_shadow implies a high-probability PASS under full CDEL, with an explicit bound `eta`.

## Normative Default (MUST implement)

- Use lower-confidence bounds (LCBs) or confidence sequences on non-private data.
- PASS only when the LCB clears the CDEL threshold with margin.

## Data Access Constraints (Normative)

Shadow-CDEL MAY use:

- Public or non-sensitive datasets.
- Simulator outputs and synthetic data.
- Genesis-generated experiment capsules.

Shadow-CDEL MUST NOT use:

- CDEL private holdouts or private evaluation sets.
- DP-protected evaluation data or reusable-holdout outputs.
- Any side-channel outputs from CDEL.

## Metrics

- Metrics MUST match the capsule `statistical_spec` definitions.
- Metrics computed by Shadow-CDEL are for screening only and do not count toward AlphaLedger or PrivacyLedger.

## One-Sided Acceptance Rule

Let `T` be the CDEL pass threshold for a metric (maximize direction). Let `LCB_t` be a time-uniform lower confidence bound computed from Shadow data. For minimize metrics, use an upper confidence bound `UCB_t`.

**PASS_shadow** if and only if:

- maximize: `LCB_t >= T + m`
- minimize: `UCB_t <= T - m`

where `m` is a nonnegative safety margin and `LCB_t` (or `UCB_t`) is constructed with failure probability `eta`.

`eta` MUST be specified in the epoch configuration. Default: `eta = 0.01` for single-metric screening; when multiple metrics are screened, `eta` MUST be divided by the number of metrics (union bound).

**Guarantee:** Under the Shadow data assumptions, `P(PASS_full | PASS_shadow) >= 1 - eta`.

## Diagnostics Returned to Genesis

Shadow-CDEL MAY return rich diagnostics internally to Genesis, including:

- Counterexample traces
- Failing slices (from public data)
- Gradient or sensitivity analyses

Shadow-CDEL MUST NOT return any diagnostics derived from private CDEL data.

## Worked Example (LCB Screen)

Clause: accuracy >= 0.9 (maximize). Choose `eta = 0.01`, margin `m = 0.01`, sample size `n = 5000`, and observed `p_hat = 0.94`.

```
LCB_n = p_hat - sqrt((log(2/eta)) / (2n))
      = 0.94 - sqrt(log(200) / 10000)
      = 0.94 - sqrt(0.0005298)
      = 0.94 - 0.0230
      = 0.9170
```

Since `LCB_n = 0.9170 >= 0.9 + 0.01 = 0.91`, Shadow-CDEL returns PASS_shadow.

## Extensions (MAY implement)

- E-value based screening with one-sided thresholds.
- Multiple-metric screening with union-bound adjustment of `eta`.
