# APF-SC Production Model

This document summarizes the production runtime model implemented for APF-SC on a single Apple-silicon node.

## Core principles

- The judged protocol plane remains immutable.
- Interpreter holdout truth remains the only truth source.
- ControlDB is operational index state, not semantic truth.
- Every mutating control-plane action is authenticated, audited, and journaled.
- Activation pointers remain atomic file writes.

## Runtime components

- `apfscd`: long-running daemon that owns the control socket, ControlDB, recovery, maintenance, and telemetry.
- `apfscctl`: operator CLI for local authenticated mutations and status.
- `ControlDB` (SQLite WAL): run/job/lease/audit/maintenance index and history.
- File-based artifact plane: content-addressed objects, receipts, snapshots, and active pointers.

## Crash safety model

- Mutating jobs are written to a write-ahead journal before execution.
- Jobs are idempotent under `(command_type, profile, snapshot/entity hash, operator request id)`.
- Startup recovery reclassifies incomplete jobs into `Committed` or `RecoveryPending` based on journal evidence.

## Operational controls

- Local-only Unix socket transport.
- Role model: `Reader`, `Operator`, `ReleaseManager`.
- Hash-chained append-only audit stream mirrored into ControlDB.
- Preflight checks for path layout, secret/token permissions, and startup readiness.

## Release and qualification

- Release artifacts include manifest, SBOM, provenance, and signature bundle.
- `apfsc_release_verify` validates manifest and bundle integrity.
- `apfsc_qualify` emits deterministic JSON reports by qualification mode.

## Production fixtures

Production fixture packs for all ingress classes live under:

- `baremetal_lgp/fixtures/apfsc/prod/reality_seed`
- `baremetal_lgp/fixtures/apfsc/prod/prior_seed`
- `baremetal_lgp/fixtures/apfsc/prod/substrate_seed`
- `baremetal_lgp/fixtures/apfsc/prod/formal_seed`
- `baremetal_lgp/fixtures/apfsc/prod/tool_seed`

These are intended for deterministic production-control-plane smoke, migration, backup/restore, and qualification tests.
