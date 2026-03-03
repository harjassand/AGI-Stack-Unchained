# baremetal_lgp

Bare-metal Rust runtime for low-level AGI stack execution loops, APFSC services, search/oracle components, and native/JIT-adjacent tooling.

## Scope

- Provide high-performance runtime and service binaries implemented in Rust.
- Host APFSC production and ingestion binaries (`apfscd`, `apfscctl`, and related tools).
- Maintain lower-level contracts and runtime types used across binary entrypoints.

## Repository Layout

- `src/`: Core Rust implementation modules.
- `src/bin/`: Operational CLIs and daemons (APF3/APFSC, hotloop, architect, release verify).
- `config/`: Profile and schema configuration for runtime behavior.
- `fixtures/`: Deterministic fixtures for local/testing workflows.
- `tests/`: Integration and regression tests.
- `benches/`, `fuzz/`: Performance and fuzzing surfaces.
- `native_jit/`: Native/JIT support components.
- `ops/`: Runbooks, alerts, and dashboard collateral.
- `deploy/`: Deployment-oriented assets (including launchd configs).
- `runs/`: Local run outputs.

## Build And Test

```bash
cd baremetal_lgp
cargo build
cargo test
```

Optional release build:

```bash
cargo build --release
```

## Key Operational Binaries

- `apfscd`: APFSC daemon process.
- `apfscctl`: APFSC control-plane CLI.
- `apfsc_preflight`: Preflight validation tool.
- `apfsc_release_verify`: Release verification entrypoint.
- `apfsc_ingest_*`: Ingestion pipeline tools for external/formal/reality/substrate sources.

List all available binaries:

```bash
ls src/bin
```

## Contract And Safety Notes

1. Shared contracts in `src/contracts/` and core runtime types are treated as compatibility-sensitive surfaces.
2. Use additive versioning and new artifacts/directories instead of mutating historical evidence.
3. Keep operational state in runtime directories (`.apfsc/`, `runs/`) rather than in source modules.

## Development Workflow

1. Make code changes in `src/` and update tests under `tests/`.
2. Run `cargo test` locally before promoting changes.
3. Validate runtime behavior with targeted binaries from `src/bin/` using profile configs under `config/`.
