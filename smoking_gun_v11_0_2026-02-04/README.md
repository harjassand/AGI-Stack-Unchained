# SAS v11.0 Smoking Gun Evidence Pack (2026-02-04)

Canonical evidence pack for a valid SAS v11.0 smoking-gun run.

## Contents

- `state/`: Captured runtime state from a validated v11.0 run.
- `arch_synthesis_toolchain_manifest_v1.json`: Toolchain manifest bound to this evidence pack.
- `README.md`: Reproduction and integrity notes.

## Canonical Root Caveat

If your local repository path has a trailing space (for example `/Users/harjas/AGI-Stack-Clean `), canonical root resolution can fail because `CANON_ROOT_V1` strips the trailing space before `resolve()`.

Use a space-free symlink and point `AGI_ROOT` at that symlink:

```bash
ln -s "/Users/harjas/AGI-Stack-Clean " /Users/harjas/AGI-Stack-Clean-canon
```

## Reproduction Steps

Run the exact sequence below:

1. `export AGI_ROOT="/Users/harjas/AGI-Stack-Clean-canon"`
2. `scripts/demo_sas_smoking_gun.sh`
3. `PYTHONPATH="$AGI_ROOT/CDEL-v2" python3 -m cdel.v11_0.verify_rsi_arch_synthesis_v1 --sas_state_dir "$AGI_ROOT/daemon/rsi_arch_synthesis_v11_0/state" --mode full`

## Determinism Note

From a clean starting state, repeated runs should yield identical `arch_id` and `weights_bundle_id`.
Ledger head hashes may differ because ledger entries include timestamped events.

## Integrity Check

Tarball digest is recorded in the sibling checksum file:

- `smoking_gun_v11_0_2026-02-04.tar.gz.sha256`
