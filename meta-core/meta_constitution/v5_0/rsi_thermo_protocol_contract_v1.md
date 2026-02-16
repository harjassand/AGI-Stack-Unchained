# RSI Thermodynamic Integration Protocol (v5.0)

This directory defines the *normative* meta-constitution for RSI Thermodynamic Integration (`v5_0`).

## Safety Boundary (Non-Negotiable)

Any attempt to modify or bypass OS/hardware safety controls is a **fatal protocol violation**:

* `THERMO_SAFETY_GOVERNOR_TAMPER_FATAL`

The RE3 orchestrator must not run as root. Thermodynamic measurement is performed by a trusted RE2 worker that captures raw power + thermal logs and emits content-addressed receipts. Verification is deterministic from captured artifacts; the verifier does not re-measure.

## Determinism

Physical measurements are not bitwise deterministic. Determinism is achieved by:

* storing raw measurement outputs as immutable, content-addressed artifacts
* computing scores/decisions deterministically from those artifacts

## Required Artifacts

* `constants_v1.json` (GCJ-1 canonical)
* `immutable_core_lock_v1.json` (content-addressed lock over protocol source roots)
* `META_HASH` (sha256 over canonical inputs as defined by `build_meta_hash.sh`)

