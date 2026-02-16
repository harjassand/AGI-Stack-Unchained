# RSI Persistence Protocol Contract (v6.0)

This directory defines the *normative* meta-constitution for RSI Sovereign Persistence (`v6_0`).

## Safety Boundary (Non-Negotiable)

The daemon must preserve RE1/RE2 promotion gates, immutable-core constraints, and sealed evaluation boundaries. Any attempt to bypass these gates is a fatal protocol violation.

## Determinism

Daemon control flow must be deterministic. Wall-clock time may be logged as telemetry only; it must not influence scheduling or decisions.

## Clauses (Normative)

- **SP-CONST-ROOT-0**: The daemon MUST refuse root execution (`euid == 0`) and halt with a fatal refusal reason.
- **SP-CONST-LAUNCHD-0**: Only a user-space LaunchAgent is permitted. LaunchDaemon configuration is forbidden.
- **SP-CONST-LEDGER-0**: The daemon ledger MUST be append-only and hash-chained. Checkpoints MUST bind to the ledger head.
- **SP-CONST-DRIFT-0**: Meta drift detection MUST fail-closed (no further work after drift is detected).
- **SP-CONST-CONTROL-0**: `STOP`/`PAUSE` operator controls are mandatory and must be honored within a bounded time.
- **SP-CONST-WRITE-0**: The daemon may write only under `$DAEMON_ROOT` and `runs/` (new run directories only). Historical artifacts must not be mutated.

## Required Artifacts

- `constants_v1.json` (GCJ-1 canonical)
- `immutable_core_lock_v1.json` (content-addressed lock over protocol source roots)
- `META_HASH` (sha256 over canonical inputs as defined by `build_meta_hash.sh`)
