from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def load(p: Path) -> dict[str, Any]:
    return json.loads(p.read_text(encoding="utf-8"))


def find_epochs(epochs_dir: Path) -> list[Path]:
    eps = [p for p in epochs_dir.iterdir() if p.is_dir()]
    return sorted(eps, key=lambda x: x.name)


def macros_in_epoch_local_report(diag: Path) -> tuple[set[str], int]:
    p = diag / "macro_tokenization_report_heldout_admitted_only_epoch_v1.json"
    if not p.exists():
        return set(), 0
    o = load(p)
    mids = set()
    for m in o.get("macros", []):
        if isinstance(m, dict) and isinstance(m.get("macro_id"), str):
            mids.add(m["macro_id"])
    delta = int(o.get("delta_tokens_total", 0))
    return mids, delta


def turnover_check(epoch_macros: list[set[str]]) -> tuple[bool, int, str, str]:
    # Find boundary t where some macro disappears and another appears.
    # Return (ok, boundary_index, old_macro, new_macro)
    if len(epoch_macros) < 3:
        return False, -1, "", ""
    early = set.union(*epoch_macros[:2]) if len(epoch_macros) >= 2 else set()
    late = set.union(*epoch_macros[-2:]) if len(epoch_macros) >= 2 else set()
    disappeared = sorted(list(early - late))
    appeared = sorted(list(late - early))
    if not disappeared or not appeared:
        return False, -1, "", ""
    # boundary: first epoch where old absent and new present
    old = disappeared[0]
    new = appeared[0]
    for t in range(len(epoch_macros) - 1):
        if old in epoch_macros[t] and old not in epoch_macros[t + 1] and new not in epoch_macros[t] and new in epoch_macros[t + 1]:
            return True, t + 1, old, new
    # fallback: allow new to appear within 1 epoch after disappearance
    for t in range(len(epoch_macros) - 2):
        if old in epoch_macros[t] and old not in epoch_macros[t + 1] and new in epoch_macros[t + 2]:
            return True, t + 1, old, new
    return False, -1, old, new


def bounded_drop_and_recovery(deltas: list[int], boundary: int, max_drop_frac: float = 0.50) -> bool:
    if boundary <= 0 or boundary >= len(deltas):
        return False
    pre = max(1, deltas[boundary - 1])
    post = deltas[boundary]
    # bounded drop
    if post < int(pre * (1.0 - max_drop_frac)):
        return False
    # monotone recovery after boundary
    for i in range(boundary, len(deltas) - 1):
        if deltas[i + 1] < deltas[i]:
            return False
    return True


def audit_portfolio(portfolio_dir: Path) -> bool:
    epochs_dir = portfolio_dir / "epochs"
    eps = find_epochs(epochs_dir)
    if not eps:
        print("FAIL: no epochs")
        return False

    # Prereq: ignition true and rho_non_decreasing true at final epoch (cumulative admitted-only already)
    final_diag = eps[-1] / "diagnostics"
    irp = final_diag / "rsi_ignition_report_v1.json"
    if not irp.exists():
        print("FAIL: missing ignition report")
        return False
    ir = load(irp)
    if not ir.get("ignition") or not ir.get("rho_non_decreasing"):
        print("FAIL: prereq ignition/rho_non_decreasing")
        return False

    # Build epoch-local macro sets + deltas
    epoch_sets: list[set[str]] = []
    deltas: list[int] = []
    for ep in eps:
        diag = ep / "diagnostics"
        mids, d = macros_in_epoch_local_report(diag)
        epoch_sets.append(mids)
        deltas.append(d)

    ok, boundary, old, new = turnover_check(epoch_sets)
    if not ok:
        print("FAIL: no disappearance->replacement detected")
        return False

    if not bounded_drop_and_recovery(deltas, boundary, max_drop_frac=0.50):
        print("FAIL: compression collapse or no monotone recovery at turnover boundary")
        print("deltas:", deltas, "boundary:", boundary)
        return False

    print("PASS: RSI-L4 turnover detected")
    print(" boundary_epoch_index:", boundary + 1)
    print(" old_macro:", old)
    print(" new_macro:", new)
    print(" epoch_local_deltas:", deltas)
    return True


def main() -> None:
    out_root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("runs/v1_5r_ignition_r5_2")
    run0 = out_root / "run_0"
    ports = [p for p in run0.iterdir() if p.is_dir()]

    all_ok = True
    for p in sorted(ports, key=lambda x: x.name):
        print("\n====================", p.name, "====================")
        all_ok = audit_portfolio(p) and all_ok

    print("\n==================== OVERALL ====================")
    print("OVERALL:", "PASS (RSI-L4)" if all_ok else "FAIL")
    sys.exit(0 if all_ok else 2)


if __name__ == "__main__":
    main()
