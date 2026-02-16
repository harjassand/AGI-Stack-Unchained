# SAS v11.0 Smoking Gun Evidence Pack (2026-02-04)

This pack contains:
- `state/` from a VALID v11.0 SAS smoking-gun run
- `arch_synthesis_toolchain_manifest_v1.json`
- this README

## Canonical root note
If your repo path has a trailing space (for example: `/Users/harjas/AGI-Stack-Clean `), `CANON_ROOT_V1` will strip it and `resolve()` will fail. Create a symlink without the trailing space and set `AGI_ROOT` to the symlink.

Example:
`ln -s "/Users/harjas/AGI-Stack-Clean " /Users/harjas/AGI-Stack-Clean-canon`

## Reproduce (exact 3 commands)
1. `export AGI_ROOT="/Users/harjas/AGI-Stack-Clean-canon"`
2. `scripts/demo_sas_smoking_gun.sh`
3. `PYTHONPATH="$AGI_ROOT/CDEL-v2" python3 -m cdel.v11_0.verify_rsi_arch_synthesis_v1 --sas_state_dir "$AGI_ROOT/daemon/rsi_arch_synthesis_v11_0/state" --mode full`

## Determinism note
Running the demo twice from a clean state yields identical `arch_id` and `weights_bundle_id`. Ledger head hashes can differ due to timestamped ledger entries.

## Tarball SHA256
See the sibling file `smoking_gun_v11_0_2026-02-04.tar.gz.sha256` next to the tarball.
