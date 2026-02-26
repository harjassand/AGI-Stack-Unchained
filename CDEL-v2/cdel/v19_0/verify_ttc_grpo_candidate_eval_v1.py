"""Structural verifier for TTC-GRPO candidate eval artifacts (v1)."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

from ..v18_0.omega_common_v1 import OmegaV18Error, canon_hash_obj, load_canon_dict
from .common_v1 import validate_schema as validate_schema_v19
from ..v18_0.omega_common_v1 import validate_schema as validate_schema_v18

_SHA_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def _fail(reason: str) -> None:
    text = str(reason).strip() or "SCHEMA_FAIL"
    if not text.startswith("INVALID:"):
        text = f"INVALID:{text}"
    raise OmegaV18Error(text)


def _ensure_sha(value: Any, *, field: str) -> str:
    text = str(value).strip()
    if _SHA_RE.fullmatch(text) is None:
        _fail(f"SCHEMA_FAIL:{field}")
    return text


def _resolve_state_root(path: Path) -> Path:
    root = path.resolve()
    candidates = [
        root / "daemon" / "rsi_proposer_arena_grpo_ttc_v1" / "state" / "ttc_grpo",
        root / "ttc_grpo",
        root,
    ]
    for candidate in candidates:
        if (candidate / "candidate_eval").exists():
            return candidate
    _fail("MISSING_STATE_INPUT")
    return root


def _find_one(root: Path, pattern: str) -> Path | None:
    rows = sorted(root.glob(pattern), key=lambda p: p.as_posix())
    return rows[-1] if rows else None


def _find_by_hash(root: Path, *, digest: str, suffix: str) -> Path:
    needle = f"sha256_{digest.split(':', 1)[1]}.{suffix}"
    matches = sorted(root.rglob(needle), key=lambda p: p.as_posix())
    if len(matches) != 1:
        _fail("MISSING_STATE_INPUT")
    return matches[0]


def verify(state_dir: Path, *, mode: str = "full", candidate_eval_hash: str | None = None) -> str:
    if mode != "full":
        _fail("MODE_UNSUPPORTED")

    state_root = _resolve_state_root(state_dir)

    if candidate_eval_hash is None:
        eval_path = _find_one(state_root / "candidate_eval", "sha256_*.ttc_grpo_candidate_eval_v1.json")
        if eval_path is None:
            _fail("MISSING_STATE_INPUT")
    else:
        eval_hash = _ensure_sha(candidate_eval_hash, field="candidate_eval_hash")
        eval_path = _find_by_hash(state_root / "candidate_eval", digest=eval_hash, suffix="ttc_grpo_candidate_eval_v1.json")

    eval_obj = load_canon_dict(eval_path)
    validate_schema_v19(eval_obj, "ttc_grpo_candidate_eval_v1")

    eval_id = _ensure_sha(eval_obj.get("id"), field="id")
    if canon_hash_obj({k: v for k, v in eval_obj.items() if k != "id"}) != eval_id:
        _fail("ID_MISMATCH")

    valid_ir = bool(eval_obj.get("valid_ir_b", False))
    ir_hash = eval_obj.get("candidate_ir_hash")
    plan_hash = eval_obj.get("dmpl_plan_result_hash")
    cac_hash = eval_obj.get("cac_hash")
    if not valid_ir:
        if ir_hash is not None or plan_hash is not None or cac_hash is not None:
            _fail("NONDETERMINISTIC")
        return "VALID"

    ir_digest = _ensure_sha(ir_hash, field="candidate_ir_hash")
    _find_by_hash(state_root / "ir", digest=ir_digest, suffix="polymath_restricted_ir_v1.json")

    if plan_hash is not None:
        _find_by_hash(state_root / "dmpl" / "plan", digest=_ensure_sha(plan_hash, field="dmpl_plan_result_hash"), suffix="dmpl_action_receipt_v1.json")

    if cac_hash is not None:
        cac_path = _find_by_hash(state_root / "dmpl" / "cac", digest=_ensure_sha(cac_hash, field="cac_hash"), suffix="cac_v1.json")
        cac_obj = load_canon_dict(cac_path)
        validate_schema_v18(cac_obj, "cac_v1")
        if str(cac_obj.get("candidate_ir_hash", "")).strip() != ir_digest:
            _fail("NONDETERMINISTIC")
        if plan_hash is not None and str(cac_obj.get("dmpl_plan_result_hash", "")).strip() != str(plan_hash):
            _fail("NONDETERMINISTIC")

    return "VALID"


def main() -> None:
    parser = argparse.ArgumentParser(prog="verify_ttc_grpo_candidate_eval_v1")
    parser.add_argument("--mode", required=True)
    parser.add_argument("--state_dir", required=True)
    parser.add_argument("--candidate_eval_hash", required=False)
    args = parser.parse_args()
    try:
        print(
            verify(
                Path(args.state_dir),
                mode=str(args.mode),
                candidate_eval_hash=(str(args.candidate_eval_hash).strip() if args.candidate_eval_hash else None),
            )
        )
    except OmegaV18Error as exc:
        print(str(exc))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
