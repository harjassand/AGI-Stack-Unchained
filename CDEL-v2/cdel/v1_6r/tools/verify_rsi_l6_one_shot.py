from __future__ import annotations
import json
import sys
from pathlib import Path
from typing import Any

REQUIRED_CYCLES = 3
MAX_DROP_FRAC = 0.50

def load(p: Path) -> dict[str, Any]:
    return json.loads(p.read_text(encoding="utf-8"))

def read_jsonl(p: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out

def epochs_sorted(epochs_dir: Path) -> list[Path]:
    eps = [p for p in epochs_dir.iterdir() if p.is_dir()]
    return sorted(eps, key=lambda x: x.name)

def epoch_num_from_dirname(name: str) -> int | None:
    try:
        return int(name.split("_")[-1])
    except Exception:
        return None

def epoch_local_meta(diag: Path) -> tuple[set[str], dict[str, dict[str, Any]], int]:
    p = diag / "macro_tokenization_report_heldout_admitted_only_epoch_v1.json"
    if not p.exists():
        return set(), {}, 0
    o = load(p)
    mids = set()
    meta: dict[str, dict[str, Any]] = {}
    for m in o.get("macros", []):
        if isinstance(m, dict) and isinstance(m.get("macro_id"), str):
            mid = m["macro_id"]
            mids.add(mid)
            meta[mid] = m
    delta = int(o.get("delta_tokens_total", 0))
    return mids, meta, delta

def barrier_scalar(diag: Path) -> int:
    p = diag / "barrier_record_v1.json"
    if not p.exists():
        return 0
    o = load(p)
    return int(o.get("barrier_scalar_value", 0))

def composed_used(meta: dict[str, dict[str, Any]]) -> set[str]:
    out = set()
    for mid, m in meta.items():
        if bool(m.get("is_composed")) and int(m.get("delta_tokens_token_space_est", 0)) > 0:
            out.add(mid)
    return out

def main() -> None:
    out_root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("runs/v1_5r_ignition_r5_2")
    run0 = out_root / "run_0"
    ports = [p for p in run0.iterdir() if p.is_dir()]

    all_ok = True

    for port in sorted(ports, key=lambda x: x.name):
        print("\n====================", port.name, "====================")
        epochs_dir = port / "epochs"
        eps = epochs_sorted(epochs_dir)
        if len(eps) < 9:
            print("FAIL: need 9 epochs for 3 cycles; have", len(eps))
            all_ok = False
            continue

        # prereq ignition at final
        irp = eps[-1] / "diagnostics" / "rsi_ignition_report_v1.json"
        if not irp.exists():
            print("FAIL: missing ignition report")
            all_ok = False
            continue
        ir = load(irp)
        if not ir.get("ignition"):
            print("FAIL: prereq ignition false")
            all_ok = False
            continue

        # build per-epoch maps
        macro_sets = {}
        macro_meta = {}
        deltas = {}
        comp = {}
        barriers = {}
        epoch_nums = []

        for ep in eps:
            n = epoch_num_from_dirname(ep.name)
            if n is None:
                continue
            diag = ep / "diagnostics"
            mids, meta, d = epoch_local_meta(diag)
            macro_sets[n] = mids
            macro_meta[n] = meta
            deltas[n] = d
            comp[n] = composed_used(meta)
            barriers[n] = barrier_scalar(diag)
            epoch_nums.append(n)

        epoch_nums = sorted(set(epoch_nums))

        # ledger deactivations
        ledger = read_jsonl(port / "current" / "macro_ledger_v1.jsonl")
        deact_epochs = set()
        for l in ledger:
            if l.get("event") == "DEACTIVATE":
                eid = l.get("epoch_id")
                if isinstance(eid, str) and eid.startswith(port.name + "_epoch_"):
                    try:
                        deact_epochs.add(int(eid.split("_")[-1]))
                    except Exception:
                        pass

        # Stress epochs are ep%3==1: 1,4,7. Recovery are +1: 2,5,8. Pre are -1: 0,3,6 (we use 3,6 as pre for 4,7).
        stress_epochs = [1, 4, 7]
        ok_cycles = 0

        for stress_ep in stress_epochs:
            rec_ep = stress_ep + 1
            pre_ep = stress_ep - 1
            if pre_ep < 1:
                # for stress_ep=1, use pre_ep=1 itself as baseline (no prior epoch)
                pre_ep = 1

            if stress_ep not in epoch_nums or rec_ep not in epoch_nums or pre_ep not in epoch_nums:
                print("FAIL: missing epoch(s) for stress", stress_ep)
                all_ok = False
                break

            if stress_ep not in deact_epochs:
                print("FAIL: missing DEACTIVATE at stress epoch", stress_ep)
                all_ok = False
                break

            pre_set = set(macro_sets.get(pre_ep, set()))
            post_set = set(macro_sets.get(stress_ep, set())).union(macro_sets.get(rec_ep, set()))
            disappeared = sorted(list(pre_set - post_set))
            appeared = sorted(list(post_set - pre_set))
            if not disappeared or not appeared:
                print("FAIL: no disappearance->replacement detected around stress", stress_ep)
                all_ok = False
                break

            d0 = max(1, int(deltas.get(pre_ep, 0)))
            d1 = int(deltas.get(stress_ep, 0))
            drop_frac = (d0 - d1) / d0
            if drop_frac > MAX_DROP_FRAC:
                print("FAIL: drop too large at stress", stress_ep, "drop_frac", drop_frac)
                all_ok = False
                break

            d2 = int(deltas.get(rec_ep, 0))
            if d2 < d1:
                print("FAIL: no recovery at recovery epoch", rec_ep)
                all_ok = False
                break

            new_comp = sorted(list(comp.get(rec_ep, set()) - comp.get(pre_ep, set())))
            if not new_comp:
                print("FAIL: no NEW composed macro used on recovery epoch", rec_ep)
                all_ok = False
                break

            b0 = int(barriers.get(pre_ep, 0))
            b1 = int(barriers.get(stress_ep, 0))
            b2 = int(barriers.get(rec_ep, 0))
            if b1 > b0 or b2 > b0:
                print("FAIL: barrier regression around stress", stress_ep, "pre", b0, "stress", b1, "rec", b2)
                all_ok = False
                break

            ok_cycles += 1
            print("cycle PASS:", "stress", stress_ep, "recovery", rec_ep, "new_comp", new_comp[0])

        if all_ok and ok_cycles >= REQUIRED_CYCLES:
            print("PASS: RSI-L6 (", ok_cycles, "cycles )")
        else:
            all_ok = False

    print("\n==================== OVERALL ====================")
    print("OVERALL:", "PASS (RSI-L6)" if all_ok else "FAIL")
    sys.exit(0 if all_ok else 2)

if __name__ == "__main__":
    main()
