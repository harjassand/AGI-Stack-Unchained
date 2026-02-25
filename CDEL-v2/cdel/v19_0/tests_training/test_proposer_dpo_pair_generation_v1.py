from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

EK_ID = "sha256:" + ("5" * 64)
LEDGER_ID = "sha256:" + ("6" * 64)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _canon_bytes(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha256_prefixed(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _sha_text(text: str) -> str:
    return _sha256_prefixed(text.encode("utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")


def _write_hashed_json(out_dir: Path, suffix: str, payload: dict[str, Any]) -> tuple[Path, str]:
    digest = hashlib.sha256(_canon_bytes(payload)).hexdigest()
    path = out_dir / f"sha256_{digest}.{suffix}"
    _write_json(path, payload)
    return path, f"sha256:{digest}"


def _patch_text(idx: int) -> str:
    relpath = "campaigns/pair_test.py"
    return (
        f"diff --git a/{relpath} b/{relpath}\n"
        f"--- a/{relpath}\n"
        f"+++ b/{relpath}\n"
        "@@ -1 +1 @@\n"
        f"-pair_{idx}\n"
        f"+pair_{idx + 1}\n"
    )


def _make_tick(*, runs_root: Path, run_name: str, idx: int, promoted: bool) -> None:
    run_dir = runs_root / run_name
    dispatch_id = f"d{idx:02d}"
    subrun_root = run_dir / "state" / "subruns" / f"{dispatch_id}_rsi_proposer_arena_v1"
    state_dir = subrun_root / "daemon" / "rsi_proposer_arena_v1" / "state"
    arena_dir = state_dir / "arena"
    candidates_dir = state_dir / "candidates"
    promotion_dir = state_dir / "promotion"
    bench_dir = subrun_root / "bench" / "trial_01"
    dispatch_promo_dir = run_dir / "state" / "dispatch" / dispatch_id / "promotion"

    for path in [arena_dir, candidates_dir, promotion_dir, bench_dir, dispatch_promo_dir]:
        path.mkdir(parents=True, exist_ok=True)

    candidate_id = _sha_text(f"candidate|{run_name}|{idx}")
    patch = _patch_text(idx)
    patch_blob_id = _sha256_prefixed(patch.encode("utf-8"))

    candidate_payload = {
        "schema_version": "arena_candidate_v1",
        "candidate_id": candidate_id,
        "agent_id": "agent_patch_v1",
        "candidate_kind": "PATCH",
        "declared_touched_paths": ["campaigns/pair_test.py"],
        "derived_touched_paths": ["campaigns/pair_test.py"],
        "base_tree_id": _sha_text("base"),
        "nontriviality_cert_id": None,
        "candidate_precheck_receipt_id": _sha_text("precheck"),
        "oracle_trace_id": None,
        "surrogate_eval_receipt_id": None,
    }
    _write_hashed_json(candidates_dir, "arena_candidate_v1.json", candidate_payload)

    run_payload = {
        "schema_version": "proposer_arena_run_receipt_v1",
        "receipt_id": _sha_text(f"run|{run_name}|{idx}"),
        "tick_u64": idx,
        "arena_state_out_id": _sha_text(f"state|{run_name}|{idx}"),
        "n_generated_u64": 1,
        "n_admitted_u64": 1,
        "n_backlogged_u64": 0,
        "n_considered_u64": 1,
        "winner_kind": "PATCH",
        "winner_candidate_id": candidate_id,
        "winner_agent_id": "agent_patch_v1",
        "drop_reason_histogram": {},
    }
    _write_hashed_json(arena_dir, "proposer_arena_run_receipt_v1.json", run_payload)

    selection_payload = {
        "schema_version": "arena_selection_receipt_v1",
        "receipt_id": _sha_text(f"selection|{run_name}|{idx}"),
        "inputs_descriptor_id": _sha_text(f"inputs|{run_name}|{idx}"),
        "arena_state_in_id": _sha_text(f"in|{run_name}|{idx}"),
        "candidates_considered": [{"candidate_id": candidate_id, "score_q32": 1, "cost_q32": 1, "risk_class": "LOW"}],
        "ranked_candidate_ids": [candidate_id],
        "winner_candidate_id": candidate_id,
        "tie_break_proof": {"seed": _sha_text(f"seed|{run_name}|{idx}"), "ordered_candidate_ids": [candidate_id], "chosen_candidate_id": candidate_id},
        "selection_reason_codes": ["ARENA_SELECT:WINNER_FROM_BACKLOG"],
    }
    _write_hashed_json(arena_dir, "arena_selection_receipt_v1.json", selection_payload)

    patch_relpath = f"patches/sha256_{patch_blob_id.split(':', 1)[1]}.patch"
    (promotion_dir / patch_relpath).parent.mkdir(parents=True, exist_ok=True)
    (promotion_dir / patch_relpath).write_text(patch, encoding="utf-8")

    ccap_payload = {
        "meta": {
            "ccap_version": 1,
            "base_tree_id": _sha_text("base-tree"),
            "auth_hash": _sha_text("auth"),
            "dsbx_profile_id": _sha_text("sandbox"),
            "env_contract_id": _sha_text("env"),
            "toolchain_root_id": _sha_text("toolchain"),
            "ek_id": EK_ID,
            "op_pool_id": _sha_text("op"),
            "canon_version_ids": {},
        },
        "payload": {"kind": "PATCH", "patch_blob_id": patch_blob_id},
        "build": {"build_recipe_id": _sha_text("recipe"), "build_targets": [], "artifact_bindings": {}},
        "eval": {"stages": [], "final_suite_id": _sha_text("suite")},
        "budgets": {
            "cpu_ms_max": 1,
            "wall_ms_max": 1,
            "mem_mb_max": 1,
            "disk_mb_max": 1,
            "fds_max": 1,
            "procs_max": 1,
            "threads_max": 1,
            "net": "forbidden",
        },
    }
    ccap_id = _sha256_prefixed(_canon_bytes(ccap_payload))
    ccap_relpath = f"ccap/sha256_{ccap_id.split(':', 1)[1]}.ccap_v1.json"
    _write_json(promotion_dir / ccap_relpath, ccap_payload)

    bundle_payload = {
        "schema_version": "omega_promotion_bundle_ccap_v1",
        "ccap_id": ccap_id,
        "ccap_relpath": ccap_relpath,
        "patch_relpath": patch_relpath,
        "touched_paths": ["campaigns/pair_test.py"],
        "activation_key": candidate_id,
    }
    _bundle_path, bundle_hash = _write_hashed_json(promotion_dir, "omega_promotion_bundle_ccap_v1.json", bundle_payload)

    promotion_receipt = {
        "schema_version": "omega_promotion_receipt_v1",
        "receipt_id": _sha_text(f"promo|{run_name}|{idx}"),
        "tick_u64": idx,
        "promotion_bundle_hash": bundle_hash,
        "meta_core_verifier_fingerprint": {"constitution_meta_hash": _sha_text("const"), "binary_hash_or_build_id": _sha_text("bin")},
        "result": {
            "status": "PROMOTED" if promoted else "REJECTED",
            "reason_code": None if promoted else "NO_BUNDLE_BENCH_FAIL",
            "route": "ACTIVE",
        },
        "active_manifest_hash_after": _sha_text("active"),
        "declared_class": "BASELINE_CORE",
        "effect_class": "EFFECT_BASELINE_CORE_OK",
    }
    _write_hashed_json(dispatch_promo_dir, "omega_promotion_receipt_v1.json", promotion_receipt)

    bench_payload = {
        "schema_version": "benchmark_run_receipt_v2",
        "receipt_id": _sha_text(f"bench|{run_name}|{idx}"),
        "ek_id": EK_ID,
        "anchor_suite_set_id": _sha_text("anchor"),
        "extensions_ledger_id": LEDGER_ID,
        "suite_runner_id": _sha_text("runner"),
        "executed_suites": [{"suite_id": _sha_text(f"suite-row|{run_name}|{idx}"), "suite_outcome": "PASS", "metrics": {}, "gate_results": [], "budget_outcome": {"within_budget_b": True, "cpu_ms_u64": 1, "wall_ms_u64": 1}}],
        "aggregate_metrics": {},
        "gate_results": [],
        "budget_outcome": {"within_budget_b": True, "cpu_ms_u64": 1, "wall_ms_u64": 1},
    }
    _write_hashed_json(bench_dir, "benchmark_run_receipt_v2.json", bench_payload)


def _run_builder(*, runs_root: Path, out_root: Path) -> None:
    cmd = [
        "python3",
        str(_repo_root() / "tools" / "training" / "proposer_corpus_builder_v1.py"),
        "--runs_root",
        str(runs_root),
        "--out_root",
        str(out_root),
        "--ek_id",
        EK_ID,
        "--kernel_ledger_id",
        LEDGER_ID,
        "--max_runs_u64",
        "5000",
        "--seed_u64",
        "0",
    ]
    run = subprocess.run(cmd, cwd=str(_repo_root()), capture_output=True, text=True, check=False)
    assert run.returncode == 0, run.stdout + run.stderr


def _load_manifest(out_root: Path) -> dict[str, Any]:
    manifests = sorted((out_root / "manifests").glob("sha256_*.proposer_training_corpus_manifest_v1.json"), key=lambda p: p.as_posix())
    assert len(manifests) == 1
    return json.loads(manifests[0].read_text(encoding="utf-8"))


def _read_jsonl_rows(out_root: Path, blob_id: str) -> list[dict[str, Any]]:
    digest = blob_id.split(":", 1)[1]
    paths = sorted((out_root / "blobs" / "sha256").glob(f"sha256_{digest}.*.jsonl"), key=lambda p: p.as_posix())
    assert len(paths) == 1
    rows: list[dict[str, Any]] = []
    for line in paths[0].read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rows.append(json.loads(line))
    return rows


def test_proposer_dpo_pair_generation_v1(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    out_root = tmp_path / "out" / "daemon" / "proposer_models" / "datasets"

    _make_tick(runs_root=runs_root, run_name="run_promoted_1", idx=1, promoted=True)
    _make_tick(runs_root=runs_root, run_name="run_promoted_2", idx=2, promoted=True)
    _make_tick(runs_root=runs_root, run_name="run_rejected_1", idx=3, promoted=False)
    _make_tick(runs_root=runs_root, run_name="run_rejected_2", idx=4, promoted=False)
    _make_tick(runs_root=runs_root, run_name="run_rejected_3", idx=5, promoted=False)
    _make_tick(runs_root=runs_root, run_name="run_rejected_4", idx=6, promoted=False)
    _make_tick(runs_root=runs_root, run_name="run_rejected_5", idx=7, promoted=False)

    _run_builder(runs_root=runs_root, out_root=out_root)
    manifest = _load_manifest(out_root)

    dpo_rows = _read_jsonl_rows(out_root, manifest["dpo_pairs_blob_id"])
    assert len(dpo_rows) == 8
