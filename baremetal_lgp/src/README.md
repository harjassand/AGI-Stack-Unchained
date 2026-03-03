# src

> Path: `baremetal_lgp/src`

## Mission

Bare-metal Rust runtime components, services, and performance-critical execution surfaces.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- `accel/`: component subtree.
- `agent_b/`: component subtree.
- `apf3/`: component subtree.
- `apfsc/`: component subtree.
- `bin/`: component subtree.
- `bytecode/`: component subtree.
- `cfg/`: component subtree.
- `contracts/`: component subtree.
- `isa/`: component subtree.
- `jit/`: component subtree.
- `jit2/`: component subtree.
- `library/`: component subtree.
- `oracle/`: component subtree.
- `oracle3/`: component subtree.
- `outer_loop/`: component subtree.
- `search/`: component subtree.
- `telemetry/`: component subtree.
- `vm/`: component subtree.

## Key Files

- `.DS_Store`: project artifact.
- `abi.rs`: Rust source module.
- `lib.rs`: Rust source module.
- `types.rs`: Rust source module.

## File-Type Surface

- `rs`: 3 files
- `DS_Store`: 1 files

## Operational Checks

```bash
ls -la baremetal_lgp/src
find baremetal_lgp/src -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files baremetal_lgp/src | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
