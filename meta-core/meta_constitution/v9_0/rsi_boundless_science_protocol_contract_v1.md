# v9.0 Boundless Science Expansion Protocol Contract (BS Protocol v1.1)

## Scope
This contract governs the v9.0 boundless science sandbox. All requirements are normative and fail-closed.

## Safety Boundary (MUST)
- No wet-lab action, physical actuation, device control, procurement, or operational deployment.
- No synthesis/culturing/procedural how-to outputs; outputs are numeric/model artifacts only.
- No network access.
- No execution of tasks outside pinned suitepacks.

## Triple-Gate Execution (MUST)
- Execution requires ENABLE_RESEARCH, ENABLE_BOUNDLESS_SCIENCE, and a domain enable file.
- Execution requires a valid science lease token.
- Execution requires a SUPEREGO_DECISION=ALLOW for the attempt.

## Hazard Model (MUST)
- Allowed hazards: H0/H1 only.
- H2 requires dual-key override.
- H3 always denied.

## Acceptance (MUST)
- DEV results never accepted.
- HELDOUT improvements only, with rational metrics and replication.

## Pinning + Drift (MUST)
- Toolchain/dataset/code/suitepacks are pinned by hash lock.
- Any drift pauses and invalidates runs.

## Write Fences (MUST)
- Writes allowed only under STATE_DIR/science/attempts, accepted, reports, ledger.
- Writes to control/env/leases are forbidden.

## Offline Enforcement (MUST)
- NETWORK_NONE only; any network use invalid.

