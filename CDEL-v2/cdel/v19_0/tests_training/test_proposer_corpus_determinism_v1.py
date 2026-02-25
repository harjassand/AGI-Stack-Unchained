from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

EK_ID = "sha256:" + ("1" * 64)
LEDGER_ID = "sha256:" + ("2" * 64)


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


def _patch_text(idx: int, relpath: str = "campaigns/test_file.py") -> str:
    return (
        f"diff --git a/{relpath} b/{relpath}\n"
        f"--- a/{relpath}\n"
        f"+++ b/{relpath}\n"
        "@@ -1 +1 @@\n"
        f"-value_{idx}\n"
        f"+value_{idx + 1}\n"
    )


def _make_tick(
    *,
    runs_root: Path,
    run_name: str,
    idx: int,
    outcome: str,
    reason_code: str | None,
    derived_touched_paths: list[str],
) -> None:
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

    candidate_id = _sha_text(f"{run_name}|{dispatch_id}|candidate")
    patch = _patch_text(idx)
    patch_blob_id = _sha256_prefixed(patch.encode("utf-8"))

    candidate_payload = {
        "schema_version": "arena_candidate_v1",
        "candidate_id": candidate_id,
        "agent_id": "agent_patch_v1",
        "candidate_kind": "PATCH",
        "declared_touched_paths": list(derived_touched_paths),
        "derived_touched_paths": list(derived_touched_paths),
        "base_tree_id": _sha_text(f"base|{run_name}|{idx}"),
        "nontriviality_cert_id": None,
        "candidate_precheck_receipt_id": _sha_text(f"precheck|{run_name}|{idx}"),
        "oracle_trace_id": None,
        "surrogate_eval_receipt_id": None,
    }
    _write_hashed_json(candidates_dir, "arena_candidate_v1.json", candidate_payload)

    run_payload = {
        "schema_version": "proposer_arena_run_receipt_v1",
        "receipt_id": _sha_text(f"run-receipt|{run_name}|{idx}"),
        "tick_u64": idx,
        "arena_state_out_id": _sha_text(f"arena-state|{run_name}|{idx}"),
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
        "arena_state_in_id": _sha_text(f"arena-in|{run_name}|{idx}"),
        "candidates_considered": [
            {
                "candidate_id": candidate_id,
                "score_q32": 1,
                "cost_q32": 1,
                "risk_class": "LOW",
            }
        ],
        "ranked_candidate_ids": [candidate_id],
        "winner_candidate_id": candidate_id,
        "tie_break_proof": {
            "seed": _sha_text(f"seed|{run_name}|{idx}"),
            "ordered_candidate_ids": [candidate_id],
            "chosen_candidate_id": candidate_id,
        },
        "selection_reason_codes": ["ARENA_SELECT:WINNER_FROM_BACKLOG"],
    }
    _write_hashed_json(arena_dir, "arena_selection_receipt_v1.json", selection_payload)

    patch_relpath = f"patches/sha256_{patch_blob_id.split(':', 1)[1]}.patch"
    patch_path = promotion_dir / patch_relpath
    patch_path.parent.mkdir(parents=True, exist_ok=True)
    patch_path.write_text(patch, encoding="utf-8")

    ccap_payload = {
        "meta": {
            "ccap_version": 1,
            "base_tree_id": _sha_text(f"base-tree|{run_name}|{idx}"),
            "auth_hash": _sha_text(f"auth|{run_name}|{idx}"),
            "dsbx_profile_id": _sha_text(f"sandbox|{run_name}|{idx}"),
            "env_contract_id": _sha_text(f"env|{run_name}|{idx}"),
            "toolchain_root_id": _sha_text(f"toolchain|{run_name}|{idx}"),
            "ek_id": EK_ID,
            "op_pool_id": _sha_text(f"op|{run_name}|{idx}"),
            "canon_version_ids": {},
        },
        "payload": {
            "kind": "PATCH",
            "patch_blob_id": patch_blob_id,
        },
        "build": {
            "build_recipe_id": _sha_text(f"recipe|{run_name}|{idx}"),
            "build_targets": [],
            "artifact_bindings": {},
        },
        "eval": {
            "stages": [],
            "final_suite_id": _sha_text(f"suite|{run_name}|{idx}"),
        },
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
        "touched_paths": list(derived_touched_paths),
        "activation_key": candidate_id,
    }
    _bundle_path, bundle_hash = _write_hashed_json(promotion_dir, "omega_promotion_bundle_ccap_v1.json", bundle_payload)

    promotion_receipt = {
        "schema_version": "omega_promotion_receipt_v1",
        "receipt_id": _sha_text(f"promo|{run_name}|{idx}"),
        "tick_u64": idx,
        "promotion_bundle_hash": bundle_hash,
        "meta_core_verifier_fingerprint": {
            "constitution_meta_hash": _sha_text(f"const|{run_name}|{idx}"),
            "binary_hash_or_build_id": _sha_text(f"bin|{run_name}|{idx}"),
        },
        "result": {
            "status": outcome,
            "reason_code": reason_code,
            "route": "ACTIVE",
        },
        "active_manifest_hash_after": _sha_text(f"active|{run_name}|{idx}"),
        "declared_class": "BASELINE_CORE",
        "effect_class": "EFFECT_BASELINE_CORE_OK",
    }
    _write_hashed_json(dispatch_promo_dir, "omega_promotion_receipt_v1.json", promotion_receipt)

    bench_payload = {
        "schema_version": "benchmark_run_receipt_v2",
        "receipt_id": _sha_text(f"bench|{run_name}|{idx}"),
        "ek_id": EK_ID,
        "anchor_suite_set_id": _sha_text("anchor-suite"),
        "extensions_ledger_id": LEDGER_ID,
        "suite_runner_id": _sha_text("suite-runner"),
        "executed_suites": [
            {
                "suite_id": _sha_text(f"suite-row|{run_name}|{idx}"),
                "suite_outcome": "PASS",
                "metrics": {},
                "gate_results": [],
                "budget_outcome": {
                    "within_budget_b": True,
                    "cpu_ms_u64": 1,
                    "wall_ms_u64": 1,
                },
            }
        ],
        "aggregate_metrics": {},
        "gate_results": [],
        "budget_outcome": {
            "within_budget_b": True,
            "cpu_ms_u64": 1,
            "wall_ms_u64": 1,
        },
    }
    _write_hashed_json(bench_dir, "benchmark_run_receipt_v2.json", bench_payload)


def _run_builder(*, runs_root: Path, out_root: Path, seed_u64: int) -> dict[str, Any]:
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
        str(seed_u64),
    ]
    run = subprocess.run(cmd, cwd=str(_repo_root()), capture_output=True, text=True, check=False)
    assert run.returncode == 0, run.stdout + run.stderr
    lines = [line.strip() for line in run.stdout.splitlines() if line.strip()]
    assert lines, run.stdout
    return json.loads(lines[-1])


def _load_manifest(out_root: Path) -> dict[str, Any]:
    manifests = sorted((out_root / "manifests").glob("sha256_*.proposer_training_corpus_manifest_v1.json"), key=lambda p: p.as_posix())
    assert len(manifests) == 1
    return json.loads(manifests[0].read_text(encoding="utf-8"))


def test_proposer_corpus_determinism_v1(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    out_root_a = tmp_path / "out_a" / "daemon" / "proposer_models" / "datasets"
    out_root_b = tmp_path / "out_b" / "daemon" / "proposer_models" / "datasets"

    _make_tick(
        runs_root=runs_root,
        run_name="run_alpha",
        idx=1,
        outcome="PROMOTED",
        reason_code=None,
        derived_touched_paths=["campaigns/test_file.py"],
    )
    _make_tick(
        runs_root=runs_root,
        run_name="run_beta",
        idx=2,
        outcome="REJECTED",
        reason_code="NO_BUNDLE_BENCH_FAIL",
        derived_touched_paths=["campaigns/test_file.py"],
    )

    _run_builder(runs_root=runs_root, out_root=out_root_a, seed_u64=7)
    _run_builder(runs_root=runs_root, out_root=out_root_b, seed_u64=7)

    manifest_a = _load_manifest(out_root_a)
    manifest_b = _load_manifest(out_root_b)

    assert manifest_a["corpus_id"] == manifest_b["corpus_id"]
    assert manifest_a["hashes"] == manifest_b["hashes"]
    assert manifest_a["sft_examples_blob_id"] == manifest_b["sft_examples_blob_id"]
    assert manifest_a["dpo_pairs_blob_id"] == manifest_b["dpo_pairs_blob_id"]
