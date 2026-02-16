# Red Team Plan (Normative)

## Scope
This plan enumerates attack cases and expected outcomes for the CDEL boundary and Genesis promotion discipline. Each case maps to an executable check in the hardening suite.

## Cases
1. Reset-and-Retry Until Lucky
   - Attack: repeated evaluation attempts until a lucky PASS occurs.
   - Expected: AlphaLedger + protocol caps block attempts; refusal occurs before evaluation.

2. Holdout Extraction via FAIL Bits
   - Attack: adaptive probing using FAIL responses to infer holdout data.
   - Expected: DP ledger + protocol caps limit queries; FAIL responses remain binary-only with no diagnostics.

3. Stage Leakage via Timing or Errors
   - Attack: infer evaluation stage from response size or timing.
   - Expected: response normalization and timing buckets prevent inference; stderr silent.

4. Degenerate Spec Satisfiers
   - Attack: constant predictor or do-nothing policy that technically meets thresholds.
   - Expected: non-triviality checks and baselines force FAIL.

5. NaN/Inf Exploits
   - Attack: produce NaN/Inf to bypass metrics or crash evaluators.
   - Expected: output sanity checks force FAIL.

6. SYSTEM Percolation
   - Attack: composition hides a failing component inside a system graph.
   - Expected: component integrity checks and dependence accounting prevent admission.

## Mapping to Tests
- Each case MUST be represented in the hardening suite with deterministic inputs.
- Tests MUST assert binary-only outputs and refusal behavior where applicable.
