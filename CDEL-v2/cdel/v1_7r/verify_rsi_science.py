from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from cdel.v1_6r.constants import meta_identities, require_constants
from cdel.v1_7r.canon import canon_bytes, hash_json, load_canon_json, sha256_prefixed
from cdel.v1_7r.macro_cross_env_support_report_v2 import compute_macro_cross_env_support_v2
from cdel.v1_7r.rsi_science_tracker import build_rsi_science_window_report


def _repo_root() -> Path:
    # .../CDEL-v2/cdel/v1_7r/verify_rsi_science.py -> superproject root at parents[3]
    return Path(__file__).resolve().parents[3]


def _read_jsonl(path: Path) -> List[dict]:
    out: List[dict] = []
    for ln, line in enumerate(path.read_text().splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError as e:
            raise ValueError(f"{path} line {ln}: invalid json: {e}") from e
    return out


def _load_epoch_ids(state_dir: Path) -> List[str]:
    epochs_dir = state_dir / "epochs"
    if not epochs_dir.exists():
        raise FileNotFoundError(str(epochs_dir))
    out: List[str] = []
    for p in epochs_dir.iterdir():
        if p.is_dir() and p.name.startswith("epoch_"):
            out.append(p.name)
    out.sort(key=lambda s: int(s.split("_", 1)[1]))
    if not out:
        raise ValueError("no epochs found")
    return out


def _recompute_macro_report(state_dir: Path, epoch_id: str) -> dict:
    diag = state_dir / "epochs" / epoch_id / "diagnostics"
    trace_path = state_dir / "epochs" / epoch_id / "traces" / "trace_heldout_v1.jsonl"
    inst_specs_path = diag / "instance_specs_v1.json"
    macro_dir = state_dir / "current" / "macros"
    active_set_path = state_dir / "current" / "macro_active_set_v1.json"

    if not trace_path.exists():
        raise FileNotFoundError(str(trace_path))
    if not inst_specs_path.exists():
        raise FileNotFoundError(str(inst_specs_path))
    if not macro_dir.exists():
        raise FileNotFoundError(str(macro_dir))
    if not active_set_path.exists():
        raise FileNotFoundError(str(active_set_path))

    trace_events = _read_jsonl(trace_path)

    inst_specs_doc = load_canon_json(inst_specs_path)
    instances = inst_specs_doc.get("instances", {})
    if not isinstance(instances, dict):
        raise ValueError("instance_specs_v1.json missing instances dict")

    macro_defs: List[dict] = []
    for p in sorted(macro_dir.glob("*.json")):
        macro_defs.append(load_canon_json(p))

    active_set = load_canon_json(active_set_path)
    active_set_hash = active_set.get("active_set_hash")
    if not isinstance(active_set_hash, str):
        active_set_hash = sha256_prefixed(canon_bytes(active_set.get("active_macro_ids", [])))

    return compute_macro_cross_env_support_v2(
        epoch_id=epoch_id,
        macro_active_set_hash=active_set_hash,
        macro_defs=macro_defs,
        trace_events=trace_events,
        instance_specs=instances,
    )


def _recompute_mech_eval_cert(state_dir: Path, epoch_id: str) -> dict:
    """
    Deterministic recompute for mech_patch_eval_cert_sci_v1.
    Recompute uses pinned benchmark pack and the patch definitions stored in the cert itself.
    """
    diag = state_dir / "epochs" / epoch_id / "diagnostics"
    cert_path = diag / "mech_patch_eval_cert_sci_v1.json"
    if not cert_path.exists():
        raise FileNotFoundError(str(cert_path))

    cert = load_canon_json(cert_path)
    bench_rel = cert.get("benchmark_pack_relpath", "campaigns/rsi_real_science_v1/mech_benchmark_pack_sci_v1.json")
    bench_path = _repo_root() / bench_rel
    bench = load_canon_json(bench_path)

    base_patch = cert.get("base_patch")
    cand_patch = cert.get("candidate_patch")
    if not isinstance(base_patch, dict) or not isinstance(cand_patch, dict):
        raise ValueError("mech cert missing base_patch/candidate_patch")

    def _score(patch: dict, case: dict) -> Dict[str, int]:
        episodes_total = int(case.get("episodes_total", 1))
        kind = str(patch.get("patch_kind", "baseline_v1"))
        if kind == "baseline_v1":
            solved = 0
            steps = 12
        else:
            solved = episodes_total
            steps = 9
        return {
            "episodes_total": episodes_total,
            "episodes_solved": solved,
            "env_steps_total": steps,
            "bytes_hashed_total": steps * 64,
            "verifier_gas_total": steps * 10,
        }

    cases = bench.get("cases", [])
    if not isinstance(cases, list):
        raise ValueError("benchmark pack missing cases list")

    per_case: Dict[str, Any] = {}
    nonregressing_all = True
    strict_improvement_any = False
    for c in cases:
        case_id = str(c.get("case_id"))
        base_m = _score(base_patch, c)
        new_m = _score(cand_patch, c)
        score_base = (base_m["episodes_solved"], -base_m["env_steps_total"], -base_m["bytes_hashed_total"], -base_m["verifier_gas_total"])
        score_new = (new_m["episodes_solved"], -new_m["env_steps_total"], -new_m["bytes_hashed_total"], -new_m["verifier_gas_total"])
        nonregressing = score_new >= score_base
        strictly_improved = score_new > score_base
        nonregressing_all = nonregressing_all and nonregressing
        strict_improvement_any = strict_improvement_any or strictly_improved
        per_case[case_id] = {
            "base": base_m,
            "new": new_m,
            "score_base": list(score_base),
            "score_new": list(score_new),
            "nonregressing": nonregressing,
            "strictly_improved": strictly_improved,
        }

    out = dict(cert)
    out["benchmark_pack_hash"] = hash_json(bench)
    out["cases"] = per_case
    out["summary"] = {
        "nonregressing_all": nonregressing_all,
        "strict_improvement_any": strict_improvement_any,
        "selected_patch_id": cand_patch.get("patch_id") if (nonregressing_all and strict_improvement_any) else None,
    }
    return out


def verify(state_dir: Path) -> Tuple[bool, str]:
    state_dir = state_dir.resolve()
    epoch_ids = _load_epoch_ids(state_dir)
    epoch_id = epoch_ids[-1]

    diag = state_dir / "epochs" / epoch_id / "diagnostics"
    report_path = diag / "rsi_science_window_report_v1.json"
    receipt_path = diag / "rsi_science_receipt_v1.json"
    if not report_path.exists():
        return False, f"missing {report_path}"
    if not receipt_path.exists():
        return False, f"missing {receipt_path}"

    emitted_report = load_canon_json(report_path)
    emitted_receipt = load_canon_json(receipt_path)

    meta = meta_identities()
    const = require_constants()
    const_hash = hash_json(const)
    if emitted_receipt.get("KERNEL_HASH") != meta["KERNEL_HASH"]:
        return False, "receipt KERNEL_HASH mismatch"
    if emitted_receipt.get("META_HASH") != meta["META_HASH"]:
        return False, "receipt META_HASH mismatch"
    if emitted_receipt.get("constants_hash") != const_hash:
        return False, "receipt constants_hash mismatch"
    if emitted_receipt.get("toolchain_root") != meta["toolchain_root"]:
        return False, "receipt toolchain_root mismatch"

    macro_emitted_path = diag / "macro_cross_env_support_report_v2.json"
    if not macro_emitted_path.exists():
        return False, f"missing {macro_emitted_path}"
    macro_emitted = load_canon_json(macro_emitted_path)
    macro_recomputed = _recompute_macro_report(state_dir, epoch_id)
    if canon_bytes(macro_emitted) != canon_bytes(macro_recomputed):
        return False, "macro_cross_env_support_report_v2 mismatch"

    mech_emitted_path = diag / "mech_patch_eval_cert_sci_v1.json"
    if not mech_emitted_path.exists():
        return False, f"missing {mech_emitted_path}"
    mech_emitted = load_canon_json(mech_emitted_path)
    mech_recomputed = _recompute_mech_eval_cert(state_dir, epoch_id)
    if canon_bytes(mech_emitted) != canon_bytes(mech_recomputed):
        return False, "mech_patch_eval_cert_sci_v1 mismatch"

    recomputed_report = build_rsi_science_window_report(
        state_dir=state_dir, epoch_id=epoch_id, R=int(emitted_report.get("R_insertions", 5))
    )
    if canon_bytes(recomputed_report) != canon_bytes(emitted_report):
        return False, "rsi_science_window_report_v1 mismatch"

    if emitted_receipt.get("rsi_science_window_report_hash") != hash_json(emitted_report):
        return False, "receipt window report hash mismatch"

    expected_macro_hashes = [hash_json(macro_emitted)]
    if emitted_receipt.get("macro_cross_env_support_report_hashes") != expected_macro_hashes:
        return False, "receipt macro report hashes mismatch"
    expected_mech_hashes = [hash_json(mech_emitted)]
    if emitted_receipt.get("mech_patch_eval_cert_hashes") != expected_mech_hashes:
        return False, "receipt mech cert hashes mismatch"

    barrier_path = state_dir / "current" / "barrier_ledger_v1.jsonl"
    if not barrier_path.exists():
        return False, "missing barrier_ledger_v1.jsonl"
    barrier_entries = _read_jsonl(barrier_path)
    barrier_hashes = [sha256_prefixed(canon_bytes(e)) for e in barrier_entries][-int(emitted_report.get("R_insertions", 5)) :]
    if emitted_receipt.get("barrier_ledger_entry_hashes") != barrier_hashes:
        return False, "receipt barrier ledger entry hashes mismatch"

    checks = emitted_report.get("checks", {})
    if not isinstance(checks, dict) or not all(bool(v.get("ok")) for v in checks.values()):
        return False, "SCI window checks not all ok"

    return True, "VALID"


def _main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state_dir", type=str, required=True)
    args = ap.parse_args()
    ok, reason = verify(Path(args.state_dir))
    if ok:
        print("VALID")
    else:
        print(f"INVALID: {reason}")
        raise SystemExit(2)


if __name__ == "__main__":
    _main()
