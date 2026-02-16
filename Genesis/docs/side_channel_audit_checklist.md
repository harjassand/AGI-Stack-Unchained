# Side-Channel Audit Checklist (Normative)

## Threat Model
Evaluate is a binary-only boundary. Any variation in response content, timing, or error handling can leak information. This checklist defines required audit tests and acceptance criteria.

## Checklist
1. Response Shape Consistency
   - Requirement: PASS responses include only the receipt; FAIL responses include only {"result":"FAIL"}.
   - Test: send a fixed set of FAIL cases (schema invalid, protocol cap hit, non-triviality fail) and verify identical JSON structure.
   - Acceptance: byte-identical FAIL responses.

2. Response Size Stability
   - Requirement: FAIL response size MUST be within a single allowed length set.
   - Test: measure response byte lengths over multiple FAIL cases.
   - Acceptance: lengths belong to an explicit small whitelist.

3. Stage Leakage Elimination
   - Requirement: No stage identifiers, no structured failure reasons, no trace snippets in responses.
   - Test: inspect responses for any extra fields or error strings.
   - Acceptance: only the allowed fields are present.

4. Timing Buckets (Coarse)
   - Requirement: responses may be delayed to coarse buckets, but no stage-specific timing is exposed.
   - Test: repeat identical FAILs and confirm durations fall within configured buckets.
   - Acceptance: durations fall within declared bucket windows.

5. Error Hygiene
   - Requirement: stderr MUST be empty for non-malformed inputs; malformed inputs may emit a short, generic error.
   - Test: run malformed input and a normal FAIL; capture stderr.
   - Acceptance: stderr empty for normal FAIL; malformed input stderr is generic.

6. Protocol Cap Refusal
   - Requirement: protocol cap refusal returns FAIL with spend=0 and identical format.
   - Test: exhaust caps and trigger refusal.
   - Acceptance: FAIL response identical to other FAILs.
