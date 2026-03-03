# apfsc

> Path: `baremetal_lgp/src/apfsc`

## Mission

Bare-metal Rust runtime components, services, and performance-critical execution surfaces.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- `archive/`: component subtree.
- `ingress/`: component subtree.
- `lanes/`: component subtree.
- `prod/`: component subtree.
- `scir/`: component subtree.

## Key Files

- `active.rs`: Rust source module.
- `afferent.rs`: Rust source module.
- `artifacts.rs`: Rust source module.
- `bank.rs`: Rust source module.
- `bridge.rs`: Rust source module.
- `bytecoder.rs`: Rust source module.
- `canary.rs`: Rust source module.
- `candidate.rs`: Rust source module.
- `challenge_scheduler.rs`: Rust source module.
- `challenge_stub.rs`: Rust source module.
- `config.rs`: Rust source module.
- `constants.rs`: Rust source module.
- `constellation.rs`: Rust source module.
- `credit.rs`: Rust source module.
- `dependency_pack.rs`: Rust source module.
- `emission.rs`: Rust source module.
- `errors.rs`: Rust source module.
- `formal_policy.rs`: Rust source module.
- `fresh_contact.rs`: Rust source module.
- `hardware_oracle.rs`: Rust source module.
- `headpack.rs`: Rust source module.
- `judge.rs`: Rust source module.
- `law_archive.rs`: Rust source module.
- `law_tokens.rs`: Rust source module.
- `macro_lib.rs`: Rust source module.
- ... and 24 more files.

## File-Type Surface

- `rs`: 49 files

## Operational Checks

```bash
ls -la baremetal_lgp/src/apfsc
find baremetal_lgp/src/apfsc -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files baremetal_lgp/src/apfsc | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
