from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "CDEL-v2") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "CDEL-v2"))

from cdel.v18_0.omega_common_v1 import OmegaV18Error  # noqa: E402
from orchestrator import rsi_coordinator_mutator_v1 as coord_mut  # noqa: E402


def _canon_write(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n", encoding="utf-8")


class _BackendStub:
    def __init__(self, response: str):
        self._response = response

    def generate(self, _prompt: str) -> str:
        return self._response


def _patch_json(diff_text: str) -> str:
    return json.dumps({"unified_diff": diff_text}, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _install_fastpath_stubs(monkeypatch: pytest.MonkeyPatch, *, target_relpath: str, diff_text: str) -> None:
    def _git_stub(repo_root: Path, args: list[str]) -> None:
        if args[:3] == ["worktree", "add", "--detach"] and len(args) >= 4:
            wt = Path(args[3])
            src = repo_root / target_relpath
            dst = wt / target_relpath
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
            return
        if args[:2] == ["worktree", "remove"]:
            return
        if args and args[0] == "apply":
            if "--check" in args:
                return
            patch_path = Path(args[-1])
            plus_rows = [
                row[1:]
                for row in patch_path.read_text(encoding="utf-8").splitlines()
                if row.startswith("+") and not row.startswith("+++")
            ]
            if plus_rows:
                dst = Path(repo_root) / target_relpath
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_text("\n".join(plus_rows) + "\n", encoding="utf-8")
            return

    monkeypatch.setattr(coord_mut, "_git", _git_stub)
    monkeypatch.setattr(coord_mut, "_git_out", lambda _root, _args: "")
    monkeypatch.setattr(coord_mut, "_canonical_patch_from_worktree", lambda **_kwargs: diff_text.encode("utf-8"))
    monkeypatch.setattr(coord_mut, "_run_python_gate", lambda **_kwargs: None)
    monkeypatch.setattr(
        coord_mut,
        "_micro_bench_gate",
        lambda **_kwargs: {
            "schema_version": "coordinator_mutator_micro_bench_receipt_v1",
            "baseline_median_q32": 0,
            "candidate_median_q32": 0,
            "improvement_frac_f64": "0.000000000000",
            "deterministic_timing_b": True,
        },
    )
    monkeypatch.setattr(
        coord_mut,
        "_verify_divergence_artifact_chain",
        lambda **_kwargs: {
            "schema_version": "phase3_divergence_artifact_receipt_v1",
            "native_runtime_stats_hash": "sha256:" + ("1" * 64),
            "native_runtime_stats_path_rel": "daemon/rsi_omega_daemon_v19_0/state/ledger/native/sha256_"
            + ("1" * 64)
            + ".omega_native_runtime_stats_v1.json",
            "phase3_receipt_hash": "sha256:" + ("2" * 64),
            "phase3_receipt_path_rel": "daemon/rsi_omega_daemon_v19_0/state/shadow/readiness/sha256_"
            + ("2" * 64)
            + ".shadow_regime_readiness_receipt_v1.json",
            "evidence_digest_match_b": True,
            "pass_b": True,
        },
    )


def test_phase3_coordinator_mutator_accepts_median_non_regression(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    out_dir = tmp_path / "out"
    repo_root.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(repo_root)
    monkeypatch.setenv("OMEGA_TICK_U64", "1")
    monkeypatch.setenv("OMEGA_RUN_SEED_U64", "424242")

    target_relpath = "orchestrator/omega_v19_0/coordinator_v1.py"
    target_path = repo_root / target_relpath
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text("print('baseline')\n", encoding="utf-8")

    pack_path = repo_root / "pack.json"
    _canon_write(
        pack_path,
        {
            "schema_version": "rsi_coordinator_mutator_pack_v1",
            "target_relpath": target_relpath,
            "bench_pack_rel": "campaigns/rsi_omega_daemon_v19_0_phase3_bench/rsi_omega_daemon_pack_v1.json",
            "benchmark": {
                "ticks_per_trial_u64": 15,
                "trials_u64": 5,
                "seed_base_u64": 424242,
                "accept_median_improvement_frac_f64": "0.0",
                "hard_reject_median_improvement_frac_f64": "-0.02",
                "metric": "median_stps_non_noop_q32",
                "alternate_order_b": True,
            },
            "structural_validator": {
                "enabled_b": True,
                "soak_ticks_u64": 120,
                "require_tree_hash_match_b": True,
                "max_disk_mb_u64": 2048,
                "max_fd_delta_u64": 50,
                "max_rss_delta_bytes_u64": 268435456,
            },
            "resource_caps": {"max_patch_bytes_u64": 200000, "max_prompt_chars_u64": 200000, "max_response_chars_u64": 400000},
            "require_replay_valid_b": True,
            "death_injection": {"enabled_b": False},
        },
    )

    diff = (
        "diff --git a/orchestrator/omega_v19_0/coordinator_v1.py b/orchestrator/omega_v19_0/coordinator_v1.py\n"
        "--- a/orchestrator/omega_v19_0/coordinator_v1.py\n"
        "+++ b/orchestrator/omega_v19_0/coordinator_v1.py\n"
        "@@ -1 +1 @@\n"
        "-print('baseline')\n"
        "+print('candidate')\n"
    )
    monkeypatch.setattr(coord_mut, "get_backend", lambda: _BackendStub(_patch_json(diff)))
    _install_fastpath_stubs(monkeypatch, target_relpath=target_relpath, diff_text=diff)
    monkeypatch.setattr(coord_mut, "_patch_nontrivial_reason", lambda **_kwargs: None)
    monkeypatch.setattr(coord_mut, "_bench_median_of_5", lambda **_kwargs: ([], 0.0))
    monkeypatch.setattr(
        coord_mut,
        "_structural_validate",
        lambda **_kwargs: ({"schema_version": "coordinator_mutator_structural_receipt_v1"}, tmp_path / "state"),
    )
    monkeypatch.setattr(coord_mut.v19_replay_verifier, "verify", lambda *_args, **_kwargs: "VALID")

    emitted: dict[str, str] = {}

    def _emit_stub(**_kwargs):
        emitted["ok"] = "1"
        return ("sha256:" + ("1" * 64), "ccap/x", "ccap/blobs/x", "sha256:" + ("2" * 64))

    monkeypatch.setattr(coord_mut, "_emit_ccap", _emit_stub)

    coord_mut.run(campaign_pack=pack_path, out_dir=out_dir)
    assert emitted.get("ok") == "1"


def test_phase3_coordinator_mutator_hard_rejects_negative_two_percent(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    out_dir = tmp_path / "out"
    repo_root.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(repo_root)

    target_relpath = "orchestrator/omega_v19_0/coordinator_v1.py"
    target_path = repo_root / target_relpath
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text("x\n", encoding="utf-8")

    pack_path = repo_root / "pack.json"
    _canon_write(
        pack_path,
        {
            "schema_version": "rsi_coordinator_mutator_pack_v1",
            "target_relpath": target_relpath,
            "bench_pack_rel": "campaigns/rsi_omega_daemon_v19_0_phase3_bench/rsi_omega_daemon_pack_v1.json",
            "benchmark": {
                "ticks_per_trial_u64": 15,
                "trials_u64": 5,
                "seed_base_u64": 424242,
                "accept_median_improvement_frac_f64": "0.0",
                "hard_reject_median_improvement_frac_f64": "-0.02",
                "metric": "median_stps_non_noop_q32",
                "alternate_order_b": True,
            },
            "structural_validator": {"enabled_b": True},
            "resource_caps": {"max_patch_bytes_u64": 200000, "max_prompt_chars_u64": 200000, "max_response_chars_u64": 400000},
            "require_replay_valid_b": True,
            "death_injection": {"enabled_b": False},
        },
    )

    diff = (
        "diff --git a/orchestrator/omega_v19_0/coordinator_v1.py b/orchestrator/omega_v19_0/coordinator_v1.py\n"
        "--- a/orchestrator/omega_v19_0/coordinator_v1.py\n"
        "+++ b/orchestrator/omega_v19_0/coordinator_v1.py\n"
        "@@ -1 +1 @@\n"
        "-x\n"
        "+y\n"
    )
    monkeypatch.setattr(coord_mut, "get_backend", lambda: _BackendStub(_patch_json(diff)))
    _install_fastpath_stubs(monkeypatch, target_relpath=target_relpath, diff_text=diff)
    monkeypatch.setattr(coord_mut, "_patch_nontrivial_reason", lambda **_kwargs: None)
    monkeypatch.setattr(coord_mut, "_bench_median_of_5", lambda **_kwargs: ([], -0.02))

    called = {"emit": 0}
    monkeypatch.setattr(coord_mut, "_emit_ccap", lambda **_kwargs: called.__setitem__("emit", called["emit"] + 1))

    coord_mut.run(campaign_pack=pack_path, out_dir=out_dir)
    assert called["emit"] == 0


def test_phase3_coordinator_mutator_requires_structural_before_emit(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    out_dir = tmp_path / "out"
    repo_root.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(repo_root)

    target_relpath = "orchestrator/omega_v19_0/coordinator_v1.py"
    target_path = repo_root / target_relpath
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text("x\n", encoding="utf-8")

    pack_path = repo_root / "pack.json"
    _canon_write(
        pack_path,
        {
            "schema_version": "rsi_coordinator_mutator_pack_v1",
            "target_relpath": target_relpath,
            "bench_pack_rel": "campaigns/rsi_omega_daemon_v19_0_phase3_bench/rsi_omega_daemon_pack_v1.json",
            "benchmark": {
                "ticks_per_trial_u64": 15,
                "trials_u64": 5,
                "seed_base_u64": 424242,
                "accept_median_improvement_frac_f64": "0.0",
                "hard_reject_median_improvement_frac_f64": "-0.02",
                "metric": "median_stps_non_noop_q32",
                "alternate_order_b": True,
            },
            "structural_validator": {"enabled_b": True, "max_fd_delta_u64": 50, "max_rss_delta_bytes_u64": 268435456},
            "resource_caps": {"max_patch_bytes_u64": 200000, "max_prompt_chars_u64": 200000, "max_response_chars_u64": 400000},
            "require_replay_valid_b": True,
            "death_injection": {"enabled_b": False},
        },
    )

    diff = (
        "diff --git a/orchestrator/omega_v19_0/coordinator_v1.py b/orchestrator/omega_v19_0/coordinator_v1.py\n"
        "--- a/orchestrator/omega_v19_0/coordinator_v1.py\n"
        "+++ b/orchestrator/omega_v19_0/coordinator_v1.py\n"
        "@@ -1 +1 @@\n"
        "-x\n"
        "+y\n"
    )
    monkeypatch.setattr(coord_mut, "get_backend", lambda: _BackendStub(_patch_json(diff)))
    _install_fastpath_stubs(monkeypatch, target_relpath=target_relpath, diff_text=diff)
    monkeypatch.setattr(coord_mut, "_patch_nontrivial_reason", lambda **_kwargs: None)
    monkeypatch.setattr(coord_mut, "_bench_median_of_5", lambda **_kwargs: ([], 0.0))
    monkeypatch.setattr(coord_mut.v19_replay_verifier, "verify", lambda *_args, **_kwargs: "VALID")

    def _structural_fail(**_kwargs):
        raise RuntimeError("STRUCTURAL_FAIL")

    monkeypatch.setattr(coord_mut, "_structural_validate", _structural_fail)

    called = {"emit": 0}

    def _emit_ccap(**_kwargs):
        called["emit"] += 1
        return ("sha256:" + ("1" * 64), "ccap/x", "ccap/blobs/x", "sha256:" + ("2" * 64))

    monkeypatch.setattr(coord_mut, "_emit_ccap", _emit_ccap)

    coord_mut.run(campaign_pack=pack_path, out_dir=out_dir)
    assert called["emit"] == 0


def test_phase3_coordinator_mutator_rejects_patch_touching_other_paths(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    out_dir = tmp_path / "out"
    repo_root.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(repo_root)

    target_relpath = "orchestrator/omega_v19_0/coordinator_v1.py"
    target_path = repo_root / target_relpath
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text("x\n", encoding="utf-8")

    pack_path = repo_root / "pack.json"
    _canon_write(pack_path, {"schema_version": "rsi_coordinator_mutator_pack_v1", "target_relpath": target_relpath})

    # Touches a second file.
    diff = (
        "diff --git a/orchestrator/omega_v19_0/coordinator_v1.py b/orchestrator/omega_v19_0/coordinator_v1.py\n"
        "--- a/orchestrator/omega_v19_0/coordinator_v1.py\n"
        "+++ b/orchestrator/omega_v19_0/coordinator_v1.py\n"
        "@@ -1 +1 @@\n"
        "-x\n"
        "+y\n"
        "diff --git a/orchestrator/omega_v19_0/other.py b/orchestrator/omega_v19_0/other.py\n"
        "--- a/orchestrator/omega_v19_0/other.py\n"
        "+++ b/orchestrator/omega_v19_0/other.py\n"
        "@@ -0,0 +1 @@\n"
        "+z\n"
    )
    monkeypatch.setattr(coord_mut, "get_backend", lambda: _BackendStub(_patch_json(diff)))
    monkeypatch.setattr(coord_mut, "_git", lambda _root, _args: None)
    monkeypatch.setattr(coord_mut, "_git_out", lambda _root, _args: "")
    monkeypatch.setattr(coord_mut, "_bench_median_of_5", lambda **_kwargs: ([], 0.0))
    monkeypatch.setattr(coord_mut, "_structural_validate", lambda **_kwargs: ({"schema_version": "x"}, tmp_path / "state"))
    monkeypatch.setattr(coord_mut.v19_replay_verifier, "verify", lambda *_args, **_kwargs: "VALID")
    monkeypatch.setattr(coord_mut, "_emit_ccap", lambda **_kwargs: ("x", "y", "z", "w"))

    coord_mut.run(campaign_pack=pack_path, out_dir=out_dir)
    failure = json.loads((out_dir / "coordinator_mutator_verify_failure_v1.json").read_text(encoding="utf-8"))
    assert failure["reason"] == "TOUCHED_PATHS_MISMATCH"
    assert "orchestrator/omega_v19_0/other.py" in failure.get("touched_paths", [])


def test_phase3_coordinator_mutator_death_injection_guard(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    out_dir = tmp_path / "out"
    repo_root.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(repo_root)

    target_relpath = "orchestrator/omega_v19_0/coordinator_v1.py"
    target_path = repo_root / target_relpath
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text("x\n", encoding="utf-8")

    pack_path = repo_root / "pack.json"
    _canon_write(
        pack_path,
        {"schema_version": "rsi_coordinator_mutator_pack_v1", "target_relpath": target_relpath, "death_injection": {"enabled_b": False}},
    )

    # Patch includes the death-injection env token, which should be rejected unless explicitly allowed.
    diff = (
        "diff --git a/orchestrator/omega_v19_0/coordinator_v1.py b/orchestrator/omega_v19_0/coordinator_v1.py\n"
        "--- a/orchestrator/omega_v19_0/coordinator_v1.py\n"
        "+++ b/orchestrator/omega_v19_0/coordinator_v1.py\n"
        "@@ -1 +1 @@\n"
        "-x\n"
        "+# OMEGA_DEV_DEATH_INJECTION_OK\n"
    )
    monkeypatch.setattr(coord_mut, "get_backend", lambda: _BackendStub(_patch_json(diff)))
    monkeypatch.setattr(coord_mut, "_git", lambda _root, _args: None)
    monkeypatch.setattr(coord_mut, "_git_out", lambda _root, _args: "")
    monkeypatch.setattr(coord_mut, "_bench_median_of_5", lambda **_kwargs: ([], 0.0))
    monkeypatch.setattr(coord_mut, "_structural_validate", lambda **_kwargs: ({"schema_version": "x"}, tmp_path / "state"))
    monkeypatch.setattr(coord_mut.v19_replay_verifier, "verify", lambda *_args, **_kwargs: "VALID")
    monkeypatch.setattr(coord_mut, "_emit_ccap", lambda **_kwargs: ("x", "y", "z", "w"))

    coord_mut.run(campaign_pack=pack_path, out_dir=out_dir)
    failure = json.loads((out_dir / "coordinator_mutator_verify_failure_v1.json").read_text(encoding="utf-8"))
    assert failure["reason"] == "DEATH_INJECTION_TOKEN_FORBIDDEN"
