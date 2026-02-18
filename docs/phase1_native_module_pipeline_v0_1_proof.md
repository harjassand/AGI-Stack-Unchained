# Phase 1 Native Module Pipeline v0.1 Proof (Real Hotpath)

This repo contains a Phase 1 native module pipeline that:

- Builds a Rust `cdylib` implementing a fixed ABI (`BLOBLIST_V1`) for a selected `op_id`.
- Produces content-addressed artifacts + receipts (hotspot/source/vendor/build/health/bench/binary).
- Promotes + activates the module and installs the binary into a content-addressed runtime cache.
- Routes a **real kernel hotpath** through the generic native router during normal ticks:
  - `op_id = omega_kernel_canon_bytes_v1` (canonical JSON bytes).
- Emits deterministic, ledger-linked runtime stats proving the native path executed.
- Remains replay-deterministic (`verify_rsi_omega_daemon_v1` returns `VALID`).

## One-Command Run (v19)

```bash
bash scripts/run_phase1_native_modules_v19_two_ticks.sh
```

This runs 2 ticks:

- Tick 1: produces + verifies + promotes + activates `omega_kernel_canon_bytes_v1`.
- Tick 2: normal tick execution hits the canonicalization hotpath and routes through native; the router emits runtime stats.

The script prints the run directory under `runs/` and where to find tick2 stats.

## Inspect Evidence (Promotion/Activation)

Given `RUN_DIR=runs/<your_run_id>`:

```bash
DISPATCH_DIR="${RUN_DIR}/tick_0001/daemon/rsi_omega_daemon_v19_0/state/dispatch"
ls "${DISPATCH_DIR}"

# Substitute the dispatch id dir printed by ls
D="${DISPATCH_DIR}/<dispatch_id>"

jq '.result' "${D}/verifier/"*.omega_subverifier_receipt_v1.json
jq '{status:.result.status,native_module}' "${D}/promotion/"*.omega_promotion_receipt_v1.json
jq '{activation_success,native_activation_gate_result,native_gate_reason,native_module}' "${D}/activation/"*.omega_activation_receipt_v1.json
```

Expected:

- subverifier `result.status == "VALID"`
- promotion `result.status == "PROMOTED"` and `native_module.op_id == "omega_kernel_canon_bytes_v1"`
- activation `activation_success == true` and native gate `PASS`

## Inspect Evidence (Native Hotpath Executed During Tick 2)

```bash
STATS_DIR="${RUN_DIR}/tick_0002/daemon/rsi_omega_daemon_v19_0/state/ledger/native"
ls "${STATS_DIR}"

jq '.ops[] | select(.op_id=="omega_kernel_canon_bytes_v1")' \
  "${STATS_DIR}/"*.omega_native_runtime_stats_v1.json
```

Expected:

- `native_returned_u64 > 0`
- `py_returned_u64 == 0` (for the canon-bytes op once native is active)
- `shadow_mismatch_u64 == 0` (for the Phase 1 workload)

The runtime stats are also linked into the tick’s trace/ledger:

```bash
LEDGER="${RUN_DIR}/tick_0002/daemon/rsi_omega_daemon_v19_0/state/ledger/omega_ledger_v1.jsonl"
rg "NATIVE_RUNTIME_STATS" "${LEDGER}"
```

## Replay Determinism Check (v19)

```bash
export PYTHONPATH="$(pwd)/CDEL-v2:$(pwd)"
python3 -m cdel.v19_0.verify_rsi_omega_daemon_v1 --mode full \
  --state_dir "${RUN_DIR}/tick_0001/daemon/rsi_omega_daemon_v19_0/state"
python3 -m cdel.v19_0.verify_rsi_omega_daemon_v1 --mode full \
  --state_dir "${RUN_DIR}/tick_0002/daemon/rsi_omega_daemon_v19_0/state"
```

Expected: both print `VALID` (no `INVALID:NONDETERMINISTIC`).

## macOS Reproducibility Notes (Verifier-Stable)

The reproducible build gate is: build twice with isolated target dirs and require identical `sha256`.

On macOS, **do not** use `-Wl,-no_uuid`: it can produce dylibs missing `LC_UUID`, which `dyld` refuses to load (`dlopen` fails). The pipeline keeps `LC_UUID` and relies on:

- pinned toolchain (cargo + rustc sha256)
- `-C debuginfo=0`
- `-C strip=symbols`
- `--remap-path-prefix <abs_build_root>=/omega_src`
- stable `install_name` for the dylib

This combination passes:

- producer double-build determinism
- verifier rebuild-twice determinism
- activation healthcheck `dlopen` + vectors

