from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def load(p: Path) -> dict[str, Any]:
    return json.loads(p.read_text(encoding="utf-8"))


def read_jsonl(p: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        out.append(json.loads(line))
    return out


def epochs_sorted(epochs_dir: Path) -> list[Path]:
    eps = [p for p in epochs_dir.iterdir() if p.is_dir()]
    return sorted(eps, key=lambda x: x.name)


def epoch_local(diag: Path) -> tuple[set[str], dict[str, dict[str, Any]], int]:
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


def main() -> None:
    out_root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("runs/v1_5r_ignition_r5_2")
    run0 = out_root / "run_0"
    ports = [p for p in run0.iterdir() if p.is_dir()]

    STRESS_EPOCH_INDEX = 3  # epoch_4
    K_RECOVER = 1           # recover by epoch_5
    MAX_DROP_FRAC = 0.50

    all_ok = True

    for port in sorted(ports, key=lambda x: x.name):
        print("\n====================", port.name, "====================")
        epochs = epochs_sorted(port / "epochs")
        if len(epochs) < 5:
            print("FAIL: expected 5 epochs")
            all_ok = False
            continue

        ir = load(epochs[-1] / "diagnostics" / "rsi_ignition_report_v1.json")
        if not ir.get("ignition"):
            print("FAIL: prereq ignition false")
            all_ok = False
            continue

        sets: list[set[str]] = []
        deltas: list[int] = []
        composed_used: list[set[str]] = []

        for ep in epochs:
            mids, meta, d = epoch_local(ep / "diagnostics")
            sets.append(mids)
            deltas.append(d)
            comp = {mid for mid, mm in meta.items() if bool(mm.get("is_composed")) and int(mm.get("delta_tokens_token_space_est", 0)) > 0}
            composed_used.append(comp)

        pre = max(1, deltas[STRESS_EPOCH_INDEX - 1])
        post = deltas[STRESS_EPOCH_INDEX]
        if post < int(pre * (1.0 - MAX_DROP_FRAC)):
            print("FAIL: compression collapse exceeds bound at stress boundary")
            print(" pre_delta:", pre, "post_delta:", post)
            all_ok = False
            continue

        ok_rec = True
        for i in range(STRESS_EPOCH_INDEX, min(len(deltas) - 1, STRESS_EPOCH_INDEX + K_RECOVER)):
            if deltas[i + 1] < deltas[i]:
                ok_rec = False
                break
        if not ok_rec:
            print("FAIL: not monotone recovery after stress")
            print(" epoch_local_deltas:", deltas)
            all_ok = False
            continue

        ledger = read_jsonl(port / "current" / "macro_ledger_v1.jsonl")
        deact = [l for l in ledger if l.get("event") == "DEACTIVATE" and l.get("epoch_id") == f"{port.name}_epoch_4"]
        if not deact:
            print("FAIL: no DEACTIVATE ledger events at stress epoch")
            all_ok = False
            continue

        early = set.union(sets[0], sets[1], sets[2])
        late = set.union(sets[3], sets[4])
        disappeared = sorted(list(early - late))
        appeared = sorted(list(late - early))
        if not disappeared or not appeared:
            print("FAIL: could not detect disappearance->replacement around stress")
            print(" disappeared:", disappeared)
            print(" appeared:", appeared)
            all_ok = False
            continue

        comp_after = set.union(*composed_used[STRESS_EPOCH_INDEX + 1 :])
        comp_before = set.union(*composed_used[: STRESS_EPOCH_INDEX])
        new_comp = sorted(list(comp_after - comp_before))
        if not new_comp:
            print("FAIL: no NEW composed macro used after stress")
            all_ok = False
            continue

        print("PASS: RSI-L5")
        print(" stress_epoch: epoch_4")
        print(" deactivated:", [l.get("macro_id") for l in deact])
        print(" new_composed_used_after_stress:", new_comp)
        print(" epoch_local_deltas:", deltas)

    print("\n==================== OVERALL ====================")
    print("OVERALL:", "PASS (RSI-L5)" if all_ok else "FAIL")
    sys.exit(0 if all_ok else 2)


if __name__ == "__main__":
    main()
