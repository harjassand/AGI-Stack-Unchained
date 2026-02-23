#!/usr/bin/env python3
"""Print a blocker histogram and sample failing substages for heavy CCAP attempts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


_HEAVY_DECLARED_CLASSES = {"FRONTIER_HEAVY", "CANARY_HEAVY"}
_CCAP_ACCEPT_DECISIONS = {"PROMOTE", "ACCEPT"}


def _load_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists() or not path.is_file():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        if isinstance(row, dict):
            out.append(row)
    return out


def _norm(value: Any, default: str) -> str:
    text = str(value).strip().upper()
    return text if text else default


def _present(value: Any) -> bool:
    if value is None:
        return False
    text = str(value).strip()
    return bool(text)


def _refutation_bucket_for_row(row: dict[str, Any]) -> str:
    code = _norm(row.get("ccap_refutation_code"), "NONE")
    if code != "PATCH_APPLY_FAILED":
        return code
    subcode = _norm(row.get("ccap_patch_apply_fail_code"), "OTHER_EXCEPTION")
    return f"PATCH_APPLY_FAILED/{subcode}"


def _is_heavy_row(row: dict[str, Any]) -> bool:
    declared_class = _norm(row.get("declared_class"), "UNCLASSIFIED")
    if declared_class in _HEAVY_DECLARED_CLASSES:
        return True
    if row.get("heavy_utility_ok_b") is True:
        return True
    if row.get("heavy_promoted_b") is True:
        return True
    return False


def _is_blocker_key(key: tuple[str, str, str, str]) -> bool:
    decision, eval_status, determinism_check, _refutation_code = key
    return not (
        decision in _CCAP_ACCEPT_DECISIONS
        and eval_status == "PASS"
        and determinism_check == "PASS"
    )


def _ccap_receipt_path_for_row(row: dict[str, Any]) -> Path | None:
    state_dir = Path(str(row.get("state_dir", "")).strip())
    if not state_dir.exists() or not state_dir.is_dir():
        return None
    receipt_hash = str(row.get("ccap_receipt_hash", "")).strip()
    if receipt_hash.startswith("sha256:") and len(receipt_hash) == 71:
        hexd = receipt_hash.split(":", 1)[1]
        rows = sorted(
            state_dir.glob(f"dispatch/*/verifier/sha256_{hexd}.ccap_receipt_v1.json"),
            key=lambda p: p.as_posix(),
        )
        if rows:
            return rows[-1]
    plain_rows = sorted(state_dir.glob("dispatch/*/verifier/ccap_receipt_v1.json"), key=lambda p: p.as_posix())
    if plain_rows:
        return plain_rows[-1]
    hashed_rows = sorted(state_dir.glob("dispatch/*/verifier/sha256_*.ccap_receipt_v1.json"), key=lambda p: p.as_posix())
    if hashed_rows:
        return hashed_rows[-1]
    return None


def _refutation_for_ccap_id(*, state_dir: Path, ccap_id: str) -> tuple[str | None, str | None]:
    if not ccap_id.startswith("sha256:") or len(ccap_id) != 71:
        return None, None
    rows = sorted(
        [
            *state_dir.glob("subruns/*/ccap/refutations/sha256_*.ccap_refutation_cert_v1.json"),
            *state_dir.glob("subruns/*/ccap/refutations/ccap_refutation_cert_v1.json"),
        ],
        key=lambda p: p.as_posix(),
    )
    for path in reversed(rows):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        if str(payload.get("ccap_id", "")).strip() != ccap_id:
            continue
        code = str(payload.get("refutation_code", "")).strip() or None
        detail = str(payload.get("detail", "")).strip() or None
        return code, detail
    return None, None


def _infer_substage(*, decision: str, eval_status: str, determinism_check: str, refutation_code: str) -> str:
    code = refutation_code.strip().upper()
    if code.startswith("PATCH_APPLY_FAILED/"):
        return "EK_REALIZE_PATCH_APPLICATION"
    if code == "PATCH_BASE_MISMATCH":
        return "EK_REALIZE_PATCH_APPLICATION"
    if code == "BUDGET_EXCEEDED":
        return "EK_COST_BUDGET_GATE"
    if code == "NO_IMPROVEMENT":
        return "EK_SCORE_ACCEPT_POLICY"
    if code in {"SITE_NOT_FOUND", "PATCH_HASH_MISMATCH", "PAYLOAD_KIND_UNSUPPORTED"}:
        return "EK_REALIZE_PATCH_APPLICATION"
    if determinism_check in {"REFUTED", "DIVERGED"}:
        return "EK_DETERMINISM_STAGE"
    if eval_status == "FAIL":
        return "EK_EVAL_STAGE"
    if eval_status == "REFUTED":
        return "CCAP_VERIFY_STAGE"
    if decision not in _CCAP_ACCEPT_DECISIONS:
        return "PROMOTION_GATE_CCAP_DECISION"
    return "NONE"


def _sample_for_key(key: tuple[str, str, str, str], rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    decision, eval_status, determinism_check, refutation_code = key
    for row in reversed(rows):
        row_key = (
            _norm(row.get("ccap_decision"), "NONE"),
            _norm(row.get("ccap_eval_status"), "NONE"),
            _norm(row.get("ccap_determinism_check"), "NONE"),
            _refutation_bucket_for_row(row),
        )
        if row_key != key:
            continue
        receipt_path = _ccap_receipt_path_for_row(row)
        receipt_payload: dict[str, Any] | None = None
        if receipt_path is not None and receipt_path.exists():
            try:
                loaded = json.loads(receipt_path.read_text(encoding="utf-8"))
            except Exception:
                loaded = None
            if isinstance(loaded, dict):
                receipt_payload = loaded
        ccap_id = str((receipt_payload or {}).get("ccap_id", "")).strip()
        state_dir = Path(str(row.get("state_dir", "")).strip())
        ref_code = refutation_code
        ref_code_base = ref_code.split("/", 1)[0] if "/" in ref_code else ref_code
        ref_detail = None
        if ref_code in {"", "NONE"}:
            cert_code, cert_detail = _refutation_for_ccap_id(state_dir=state_dir, ccap_id=ccap_id)
            if cert_code:
                ref_code = cert_code
            ref_detail = cert_detail
        else:
            cert_code, cert_detail = _refutation_for_ccap_id(state_dir=state_dir, ccap_id=ccap_id)
            if cert_code == ref_code_base and cert_detail:
                ref_detail = cert_detail
        return {
            "tick_u64": int(row.get("tick_u64", 0)),
            "state_dir": str(state_dir),
            "ccap_receipt_path": str(receipt_path) if receipt_path is not None else None,
            "ccap_id": ccap_id or None,
            "promotion_status": str(row.get("promotion_status", "")).strip() or None,
            "refutation_code": ref_code or None,
            "refutation_detail": ref_detail,
            "inferred_failing_substage": _infer_substage(
                decision=decision,
                eval_status=eval_status,
                determinism_check=determinism_check,
                refutation_code=ref_code,
            ),
        }
    return None


def main() -> None:
    ap = argparse.ArgumentParser(prog="miner_ccap_blockers_v1")
    ap.add_argument("--run_root", required=True, help="Run root containing index/long_run_tick_index_v1.jsonl")
    ap.add_argument("--last_n", type=int, default=200)
    ap.add_argument("--top_k", type=int, default=2)
    args = ap.parse_args()

    index_path = Path(args.run_root) / "index" / "long_run_tick_index_v1.jsonl"
    rows = _load_rows(index_path)
    last_n = max(1, int(args.last_n))
    top_k = max(1, int(args.top_k))
    scope_all = rows[-last_n:]
    scope_heavy = [row for row in scope_all if _is_heavy_row(row)]
    scope_heavy_ccap = [
        row
        for row in scope_heavy
        if _present(row.get("ccap_decision"))
    ]

    hist: dict[tuple[str, str, str, str], int] = {}
    for row in scope_heavy_ccap:
        key = (
            _norm(row.get("ccap_decision"), "NONE"),
            _norm(row.get("ccap_eval_status"), "NONE"),
            _norm(row.get("ccap_determinism_check"), "NONE"),
            _refutation_bucket_for_row(row),
        )
        hist[key] = int(hist.get(key, 0) + 1)

    sorted_items = sorted(hist.items(), key=lambda kv: (-int(kv[1]), kv[0]))
    top_blockers = [(key, count) for key, count in sorted_items if _is_blocker_key(key)][:top_k]
    blocker_rows: list[dict[str, Any]] = []
    for key, count in top_blockers:
        sample = _sample_for_key(key, scope_heavy_ccap)
        blocker_rows.append(
            {
                "decision": key[0],
                "eval_status": key[1],
                "determinism_check": key[2],
                "refutation_code": key[3],
                "count_u64": int(count),
                "sample": sample,
            }
        )

    payload = {
        "rows_scanned_u64": int(len(scope_all)),
        "rows_heavy_u64": int(len(scope_heavy)),
        "rows_heavy_ccap_u64": int(len(scope_heavy_ccap)),
        "histogram": [
            {
                "decision": key[0],
                "eval_status": key[1],
                "determinism_check": key[2],
                "refutation_code": key[3],
                "count_u64": int(count),
            }
            for key, count in sorted_items
        ],
        "top_blockers_v1": blocker_rows,
    }
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
