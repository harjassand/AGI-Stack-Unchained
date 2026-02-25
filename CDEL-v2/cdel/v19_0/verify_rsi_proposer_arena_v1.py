"""Fail-closed verifier for RSI proposer arena v1 artifacts."""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path
from typing import Any

from ..v18_0.ccap_runtime_v1 import ccap_payload_id
from ..v18_0.omega_common_v1 import OmegaV18Error, canon_hash_obj, load_canon_dict, validate_schema as validate_schema_v18
from .common_v1 import validate_schema as validate_schema_v19


_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_Q_REASON_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^HOLDOUT_"),
    re.compile(r"^PHASE1_PUBLIC_ONLY_VIOLATION"),
    re.compile(r"^SANDBOX_REQUIRED_BUT_NOT_ENFORCED"),
    re.compile(r"^ALLOWLIST_VIOLATION$"),
)
_RISK_RANK = {"LOW": 0, "MED": 1, "HIGH": 2, "FRONTIER_HEAVY": 3}
_DEFAULT_BACKLOG_MAX_U32 = 128


def _fail(reason: str) -> None:
    message = str(reason).strip() or "UNKNOWN"
    if not message.startswith("INVALID:"):
        message = f"INVALID:{message}"
    raise OmegaV18Error(message)


def _ensure_sha256(value: Any) -> str:
    text = str(value).strip()
    if _SHA256_RE.fullmatch(text) is None:
        _fail("SCHEMA_FAIL")
    return text


def _resolve_state_root(path: Path) -> Path:
    root = path.resolve()
    candidates = [
        root / "daemon" / "rsi_proposer_arena_v1" / "state",
        root,
    ]
    for candidate in candidates:
        if (candidate / "arena").exists() and (candidate / "promotion").exists():
            return candidate
    _fail("SCHEMA_FAIL")
    return root


def _hash_from_filename(path: Path, suffix: str) -> str:
    name = path.name
    if not name.startswith("sha256_") or not name.endswith(suffix):
        _fail("SCHEMA_FAIL")
    digest = name[len("sha256_") : -len(suffix)]
    if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        _fail("SCHEMA_FAIL")
    return f"sha256:{digest}"


def _latest(path: Path, pattern: str) -> Path | None:
    rows = sorted(path.glob(pattern), key=lambda row: row.as_posix())
    return rows[-1] if rows else None


def _selection_sort_key(row: dict[str, Any]) -> tuple[int, int, int, str]:
    risk = str(row.get("risk_class", "")).strip().upper()
    return (
        -int(row.get("score_q32", 0)),
        int(_RISK_RANK.get(risk, 99)),
        int(row.get("cost_q32", 0)),
        str(row.get("candidate_id", "")),
    )


def _configured_backlog_max_u32() -> int:
    repo_root = Path(__file__).resolve().parents[3]
    pack_path = repo_root / "campaigns" / "rsi_proposer_arena_v1" / "rsi_proposer_arena_pack_v1.json"
    if not pack_path.exists() or not pack_path.is_file():
        return int(_DEFAULT_BACKLOG_MAX_U32)
    try:
        pack_payload = load_canon_dict(pack_path)
        validate_schema_v19(pack_payload, "rsi_proposer_arena_pack_v1")
        budgets = pack_payload.get("budgets")
        if isinstance(budgets, dict):
            return int(max(1, int(budgets.get("backlog_max_u32", _DEFAULT_BACKLOG_MAX_U32))))
    except Exception:
        return int(_DEFAULT_BACKLOG_MAX_U32)
    return int(_DEFAULT_BACKLOG_MAX_U32)


def _candidate_material_id(*, candidate_payload: dict[str, Any], payload_hashes: dict[str, str]) -> str:
    material = {
        "schema_version": "arena_candidate_material_v1",
        "agent_id": str(candidate_payload.get("agent_id", "")).strip(),
        "candidate_kind": str(candidate_payload.get("candidate_kind", "")).strip(),
        "declared_touched_paths": sorted(str(row) for row in list(candidate_payload.get("declared_touched_paths") or [])),
        "derived_touched_paths": sorted(str(row) for row in list(candidate_payload.get("derived_touched_paths") or [])),
        "base_tree_id": str(candidate_payload.get("base_tree_id", "")).strip(),
        "nontriviality_cert_id": candidate_payload.get("nontriviality_cert_id"),
        "oracle_trace_id": candidate_payload.get("oracle_trace_id"),
        "payload_hashes": dict(payload_hashes),
    }
    return canon_hash_obj(material)


def _load_winner_payload_hashes(*, state_root: Path, winner_kind: str) -> dict[str, str]:
    promotion_dir = state_root / "promotion"
    if winner_kind == "PATCH":
        bundle_path = _latest(promotion_dir, "sha256_*.omega_promotion_bundle_ccap_v1.json")
        if bundle_path is None:
            _fail("MISSING_STATE_INPUT")
        bundle_payload = load_canon_dict(bundle_path)
        validate_schema_v18(bundle_payload, "omega_promotion_bundle_ccap_v1")
        bundle_hash = _hash_from_filename(bundle_path, ".omega_promotion_bundle_ccap_v1.json")
        if canon_hash_obj(bundle_payload) != bundle_hash:
            _fail("NONDETERMINISTIC")
        ccap_rel = str(bundle_payload.get("ccap_relpath", "")).strip()
        patch_rel = str(bundle_payload.get("patch_relpath", "")).strip()
        ccap_path = (promotion_dir / ccap_rel).resolve()
        patch_path = (promotion_dir / patch_rel).resolve()
        if not ccap_path.exists() or not patch_path.exists():
            _fail("MISSING_STATE_INPUT")
        ccap_payload = load_canon_dict(ccap_path)
        validate_schema_v18(ccap_payload, "ccap_v1")
        ccap_id = _ensure_sha256(bundle_payload.get("ccap_id"))
        if ccap_payload_id(ccap_payload) != ccap_id:
            _fail("NONDETERMINISTIC")
        patch_blob_id = _ensure_sha256((ccap_payload.get("payload") or {}).get("patch_blob_id"))
        if patch_blob_id != f"sha256:{__import__('hashlib').sha256(patch_path.read_bytes()).hexdigest()}":
            _fail("NONDETERMINISTIC")
        return {"patch_blob_id": patch_blob_id}

    if winner_kind == "KERNEL_EXT_PROPOSAL":
        ext_path = _latest(promotion_dir, "sha256_*.kernel_extension_spec_v1.json")
        manifest_path = _latest(promotion_dir, "sha256_*.benchmark_suite_manifest_v1.json")
        suite_set_path = _latest(promotion_dir, "sha256_*.benchmark_suite_set_v1.json")
        if ext_path is None or manifest_path is None or suite_set_path is None:
            _fail("MISSING_STATE_INPUT")
        ext_payload = load_canon_dict(ext_path)
        suite_manifest = load_canon_dict(manifest_path)
        suite_set = load_canon_dict(suite_set_path)
        validate_schema_v19(ext_payload, "kernel_extension_spec_v1")
        validate_schema_v19(suite_manifest, "benchmark_suite_manifest_v1")
        validate_schema_v19(suite_set, "benchmark_suite_set_v1")
        ext_hash = _hash_from_filename(ext_path, ".kernel_extension_spec_v1.json")
        manifest_hash = _hash_from_filename(manifest_path, ".benchmark_suite_manifest_v1.json")
        set_hash = _hash_from_filename(suite_set_path, ".benchmark_suite_set_v1.json")
        if canon_hash_obj(ext_payload) != ext_hash:
            _fail("NONDETERMINISTIC")
        if canon_hash_obj(suite_manifest) != manifest_hash:
            _fail("NONDETERMINISTIC")
        if canon_hash_obj(suite_set) != set_hash:
            _fail("NONDETERMINISTIC")
        return {
            "extension_spec_id": _ensure_sha256(ext_payload.get("extension_spec_id")),
            "suite_manifest_id": _ensure_sha256(suite_manifest.get("suite_id")),
            "suite_set_id": _ensure_sha256(suite_set.get("suite_set_id")),
        }

    _fail("SCHEMA_FAIL")
    return {}


def _validate_quarantine_rules(*, state_root: Path, arena_state: dict[str, Any]) -> None:
    daemon_state_root_raw = str(os.environ.get("OMEGA_DAEMON_STATE_ROOT", "")).strip()
    if not daemon_state_root_raw:
        return
    daemon_state_root = Path(daemon_state_root_raw).resolve()
    promo_path = _latest(daemon_state_root / "dispatch", "*/promotion/sha256_*.omega_promotion_receipt_v1.json")
    if promo_path is None:
        return
    promo_payload = load_canon_dict(promo_path)
    validate_schema_v18(promo_payload, "omega_promotion_receipt_v1")
    reason_code = str((promo_payload.get("result") or {}).get("reason_code", "")).strip().upper()
    if not any(pattern.match(reason_code) for pattern in _Q_REASON_PATTERNS):
        return
    agent_states = arena_state.get("agent_states")
    if not isinstance(agent_states, list):
        _fail("SCHEMA_FAIL")
    quarantined_rows = [row for row in agent_states if isinstance(row, dict) and bool(row.get("quarantined_b", False))]
    if not quarantined_rows:
        _fail("NONDETERMINISTIC")
    for row in quarantined_rows:
        cooldown = int(max(0, int(row.get("cooldown_until_tick_u64", 0))))
        tick_u64 = int(max(0, int(arena_state.get("tick_u64", 0))))
        expected = int(tick_u64 + 10_000)
        if cooldown != expected:
            _fail("NONDETERMINISTIC")


def verify(state_dir: Path, *, mode: str = "full") -> str:
    if mode != "full":
        _fail("MODE_UNSUPPORTED")

    state_root = _resolve_state_root(state_dir)
    arena_dir = state_root / "arena"
    candidates_dir = state_root / "candidates"

    selection_path = _latest(arena_dir, "sha256_*.arena_selection_receipt_v1.json")
    run_path = _latest(arena_dir, "sha256_*.proposer_arena_run_receipt_v1.json")
    arena_state_path = _latest(arena_dir, "sha256_*.proposer_arena_state_v1.json")
    if selection_path is None or run_path is None or arena_state_path is None:
        _fail("MISSING_STATE_INPUT")

    selection_payload = load_canon_dict(selection_path)
    run_payload = load_canon_dict(run_path)
    arena_state_payload = load_canon_dict(arena_state_path)

    validate_schema_v19(selection_payload, "arena_selection_receipt_v1")
    validate_schema_v19(run_payload, "proposer_arena_run_receipt_v1")
    validate_schema_v19(arena_state_payload, "proposer_arena_state_v1")

    if canon_hash_obj(selection_payload) != _hash_from_filename(selection_path, ".arena_selection_receipt_v1.json"):
        _fail("NONDETERMINISTIC")
    if canon_hash_obj(run_payload) != _hash_from_filename(run_path, ".proposer_arena_run_receipt_v1.json"):
        _fail("NONDETERMINISTIC")
    if canon_hash_obj(arena_state_payload) != _hash_from_filename(arena_state_path, ".proposer_arena_state_v1.json"):
        _fail("NONDETERMINISTIC")

    if int(run_payload.get("n_considered_u64", -1)) <= 0:
        _fail("SCHEMA_FAIL")
    if int(run_payload.get("n_admitted_u64", -1)) < 0:
        _fail("SCHEMA_FAIL")

    winner_candidate_id = _ensure_sha256(run_payload.get("winner_candidate_id"))
    winner_kind = str(run_payload.get("winner_kind", "")).strip()
    if winner_kind not in {"PATCH", "KERNEL_EXT_PROPOSAL"}:
        _fail("SCHEMA_FAIL")
    if _ensure_sha256(selection_payload.get("winner_candidate_id")) != winner_candidate_id:
        _fail("NONDETERMINISTIC")

    considered = selection_payload.get("candidates_considered")
    ranked_ids = selection_payload.get("ranked_candidate_ids")
    if not isinstance(considered, list) or not considered:
        _fail("SCHEMA_FAIL")
    if not isinstance(ranked_ids, list) or len(ranked_ids) != len(considered):
        _fail("SCHEMA_FAIL")
    if int(run_payload.get("n_considered_u64", -1)) != len(considered):
        _fail("NONDETERMINISTIC")

    recomputed = sorted(considered, key=_selection_sort_key)
    recomputed_ids = [_ensure_sha256(row.get("candidate_id")) for row in recomputed]
    ranked_ids_norm = [_ensure_sha256(row) for row in ranked_ids]
    if recomputed_ids != ranked_ids_norm:
        _fail("NONDETERMINISTIC")
    if ranked_ids_norm[0] != winner_candidate_id:
        _fail("NONDETERMINISTIC")

    backlog = arena_state_payload.get("candidate_backlog")
    if not isinstance(backlog, list):
        _fail("SCHEMA_FAIL")
    if int(run_payload.get("n_backlogged_u64", -1)) != len(backlog):
        _fail("NONDETERMINISTIC")
    if len(backlog) > int(_configured_backlog_max_u32()):
        _fail("NONDETERMINISTIC")

    candidate_rows = sorted(candidates_dir.glob("sha256_*.arena_candidate_v1.json"), key=lambda row: row.as_posix())
    by_id: dict[str, dict[str, Any]] = {}
    for path in candidate_rows:
        payload = load_canon_dict(path)
        validate_schema_v19(payload, "arena_candidate_v1")
        digest = _hash_from_filename(path, ".arena_candidate_v1.json")
        if canon_hash_obj(payload) != digest:
            _fail("NONDETERMINISTIC")
        by_id[_ensure_sha256(payload.get("candidate_id"))] = payload
    if winner_candidate_id not in by_id:
        _fail("MISSING_STATE_INPUT")

    winner_payload = by_id[winner_candidate_id]
    payload_hashes = _load_winner_payload_hashes(state_root=state_root, winner_kind=winner_kind)
    if _candidate_material_id(candidate_payload=winner_payload, payload_hashes=payload_hashes) != winner_candidate_id:
        _fail("NONDETERMINISTIC")

    _validate_quarantine_rules(state_root=state_root, arena_state=arena_state_payload)
    return "VALID"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="verify_rsi_proposer_arena_v1")
    parser.add_argument("--mode", default="full")
    parser.add_argument("--state_dir", required=True)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    try:
        print(verify(Path(args.state_dir).resolve(), mode=str(args.mode)))
    except OmegaV18Error as exc:
        msg = str(exc)
        if not msg.startswith("INVALID:"):
            msg = f"INVALID:{msg}"
        print(msg)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
