# Promotion Policy (Level-1)

Promotion policy governs when Genesis is allowed to call CDEL and how it selects budget bids.

## Promotion-Ready (Normative)

A candidate is promotion-ready only if all conditions hold:

1. PASS_shadow under the one-sided rule with margin `m`.
2. Stability across `k` independent Shadow runs (default k=3) with consistent PASS.
3. No unresolved counterexamples in the CEGIS queue.
4. Resource usage within the declared `resource_spec` caps.

## Per-Epoch CDEL Call Cap (Normative)

- `N_promote_max = 100` attempts per epoch (hard cap).
- Once the cap is reached, Genesis MUST refuse further CDEL calls.

## Bid Selection

- **Grade:** Default to ResearchGrade unless the candidate is explicitly marked for deployment.
- **Alpha bid:** Use the ledger-allocated amount for the current attempt (`alpha_i`).
- **Privacy bid:** Minimal DP spend required by the evaluation mechanism; never exceed ledger residual.
- **Compute bid:** Must be <= `resource_spec` caps and <= ledger residual.

## Refusal Rules

Genesis MUST refuse promotion if any of the following hold:

- Ledger residuals are insufficient for the minimum bid.
- Ledger residuals fall below 2x the minimum bid for any ledger (reserve buffer).
- The candidate has already been evaluated in the current epoch (same capsule hash).
- Promotion attempt budget for the epoch is exhausted.

## Anti-Overfitting Controls

- Cap promotion attempts per epoch: `N_promote_max = 100` (hard cap).
- Enforce a minimum spacing between attempts (`min_promote_interval` in wall time or attempt count).
- Disallow adaptive retries on the same capsule hash.

## CDEL Feedback Boundary

Genesis MUST treat CDEL as binary-only: PASS/FAIL. A receipt is returned only on PASS and MUST be verified before use.

## Audit Hooks

Genesis MUST record all promotion attempts with:

- capsule hash
- chosen bid
- Shadow-CDEL summary (PASS/FAIL + margins)
- ledger residuals at decision time
