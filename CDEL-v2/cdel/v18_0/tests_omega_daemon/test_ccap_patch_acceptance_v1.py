from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from cdel.v18_0.authority.authority_hash_v1 import auth_hash, load_authority_pins
from cdel.v18_0.ccap_runtime_v1 import ccap_payload_id
from cdel.v18_0.omega_allowlists_v1 import load_allowlists
from cdel.v18_0.omega_common_v1 import canon_hash_obj
from cdel.v18_0.omega_promoter_v1 import run_promotion
from cdel.v18_0.verify_ccap_v1 import verify
from cdel.v1_7r.canon import load_canon_json, write_canon_json


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _make_patch(repo_root: Path, relpath: str, marker: str) -> bytes:
    del repo_root
    content = (
        "from __future__ import annotations\n\n"
        f"MARKER = 'ccap_acceptance_v1:{marker}'\n"
        "def test_ccap_acceptance_marker_v1() -> None:\n"
        "    assert MARKER.startswith('ccap_acceptance_v1:')\n"
    )
    lines = content.splitlines()
    patch_rows = [
        f"diff --git a/{relpath} b/{relpath}",
        "new file mode 100644",
        "index 0000000..1111111",
        "--- /dev/null",
        f"+++ b/{relpath}",
        f"@@ -0,0 +1,{len(lines)} @@",
    ]
    patch_rows.extend("+" + row for row in lines)
    return ("\n".join(patch_rows) + "\n").encode("utf-8")


def _allowlists(repo_root: Path) -> dict:
    path = repo_root / "campaigns" / "rsi_omega_daemon_v18_0" / "omega_allowlists_v1.json"
    return load_allowlists(path)[0]


def _minimal_materializer(repo_root: Path, target_relpath: str):
    def _inner(_repo: Path, out_dir: Path) -> None:
        del _repo
        if out_dir.exists():
            shutil.rmtree(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

    return _inner


def _patch_meta_core(monkeypatch, tmp_path: Path) -> None:
    def _fake_build_promo(*, out_dir: Path, campaign_id: str, source_bundle_hash: str) -> Path:
        del out_dir, campaign_id, source_bundle_hash
        path = tmp_path / "meta_core_promo_bundle"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _fake_verify(*, out_dir: Path, bundle_dir: Path):
        del out_dir, bundle_dir
        return (
            {
                "schema_version": "meta_core_promo_verify_receipt_v1",
                "return_code": 0,
                "stdout_hash": "sha256:" + ("0" * 64),
                "stderr_hash": "sha256:" + ("0" * 64),
                "verifier_out_hash": "sha256:" + ("0" * 64),
                "pass": True,
            },
            True,
        )

    def _fake_build_activation(*, out_dir: Path, binding_payload: dict, binding_hash_hex8: str):
        del out_dir, binding_payload, binding_hash_hex8
        path = tmp_path / "meta_core_activation_bundle"
        path.mkdir(parents=True, exist_ok=True)
        return path, "sha256:" + ("a" * 64)

    monkeypatch.setattr("cdel.v18_0.omega_promoter_v1._build_meta_core_promotion_bundle", _fake_build_promo)
    monkeypatch.setattr("cdel.v18_0.omega_promoter_v1._run_meta_core_promo_verify", _fake_verify)
    monkeypatch.setattr("cdel.v18_0.omega_promoter_v1._build_meta_core_activation_bundle", _fake_build_activation)
    monkeypatch.setattr("cdel.v18_0.omega_promoter_v1._read_active_binding", lambda _root: None)


def _setup_ccap_artifacts(
    *,
    tmp_path: Path,
    repo_root: Path,
    base_tree_id: str,
    patch_bytes: bytes,
    recipe_id: str,
) -> tuple[Path, Path, dict[str, object], str]:
    run_root = tmp_path / "runs" / "ccap_acceptance"
    state_root = run_root / "daemon" / "rsi_omega_daemon_v18_0" / "state"
    dispatch_dir = state_root / "dispatch" / "a01"
    verifier_dir = dispatch_dir / "verifier"
    subrun_root = state_root / "subruns" / "a01_ccap"
    (subrun_root / "ccap" / "blobs").mkdir(parents=True, exist_ok=True)
    verifier_dir.mkdir(parents=True, exist_ok=True)

    pins = load_authority_pins(repo_root)
    ccap = {
        "meta": {
            "ccap_version": 1,
            "base_tree_id": base_tree_id,
            "auth_hash": auth_hash(pins),
            "dsbx_profile_id": str(pins["active_dsbx_profile_ids"][0]),
            "env_contract_id": str(pins["env_contract_id"]),
            "toolchain_root_id": str(pins["toolchain_root_id"]),
            "ek_id": str(pins["active_ek_id"]),
            "op_pool_id": str(pins["active_op_pool_ids"][0]),
            "canon_version_ids": dict(pins["canon_version_ids"]),
        },
        "payload": {
            "kind": "PATCH",
            "patch_blob_id": "sha256:" + hashlib.sha256(patch_bytes).hexdigest(),
        },
        "build": {
            "build_recipe_id": recipe_id,
            "build_targets": [],
            "artifact_bindings": {},
        },
        "eval": {
            "stages": [
                {"stage_name": "REALIZE"},
                {"stage_name": "SCORE"},
                {"stage_name": "FINAL_AUDIT"},
            ],
            "final_suite_id": "sha256:" + ("2" * 64),
        },
        "budgets": {
            "cpu_ms_max": 5000,
            "wall_ms_max": 5000,
            "mem_mb_max": 2048,
            "disk_mb_max": 256,
            "fds_max": 128,
            "procs_max": 64,
            "threads_max": 128,
            "net": "forbidden",
        },
    }
    ccap_id = ccap_payload_id(ccap)
    ccap_rel = f"ccap/sha256_{ccap_id.split(':', 1)[1]}.ccap_v1.json"
    patch_rel = f"ccap/blobs/sha256_{ccap['payload']['patch_blob_id'].split(':', 1)[1]}.patch"
    write_canon_json(subrun_root / ccap_rel, ccap)
    (subrun_root / patch_rel).write_bytes(patch_bytes)

    bundle = {
        "schema_version": "omega_promotion_bundle_ccap_v1",
        "ccap_id": ccap_id,
        "ccap_relpath": ccap_rel,
        "patch_relpath": patch_rel,
        "touched_paths": [ccap_rel, patch_rel],
        "activation_key": "ccap_patch_acceptance_v1",
    }
    bundle_hash = canon_hash_obj(bundle)
    write_canon_json(subrun_root / f"sha256_{bundle_hash.split(':', 1)[1]}.omega_promotion_bundle_ccap_v1.json", bundle)
    return subrun_root, verifier_dir, bundle, ccap_rel


def _dispatch_ctx(state_root: Path, subrun_root: Path) -> dict[str, object]:
    dispatch_dir = state_root / "dispatch" / "a01"
    return {
        "dispatch_dir": dispatch_dir,
        "state_root": state_root,
        "subrun_root_abs": subrun_root,
        "campaign_entry": {
            "campaign_id": "mock_ccap_campaign",
            "capability_id": "MOCK_CCAP",
            "promotion_bundle_rel": "sha256_*.omega_promotion_bundle_ccap_v1.json",
        },
    }


def test_ccap_patch_smoke_verify_promote_and_promoter_accepts(tmp_path: Path, monkeypatch) -> None:
    repo_root = _repo_root()
    target_relpath = "tools/omega/ccap_acceptance_generated_smoke.py"
    base_tree_id = "sha256:" + ("1" * 64)
    recipe_id = "sha256:" + ("9" * 64)
    patch_bytes = _make_patch(repo_root, target_relpath, "smoke")
    subrun_root, verifier_dir, _bundle, ccap_rel = _setup_ccap_artifacts(
        tmp_path=tmp_path,
        repo_root=repo_root,
        base_tree_id=base_tree_id,
        patch_bytes=patch_bytes,
        recipe_id=recipe_id,
    )

    monkeypatch.setattr("cdel.v18_0.verify_ccap_v1.compute_repo_base_tree_id", lambda _root: base_tree_id)
    monkeypatch.setattr("cdel.v18_0.ek.ek_runner_v1.materialize_repo_snapshot", _minimal_materializer(repo_root, target_relpath))
    monkeypatch.setattr(
        "cdel.v18_0.realize.repo_harness_v1._load_build_recipes",
        lambda _repo_root: {
            recipe_id: {
                "recipe_id": recipe_id,
                "commands": [["python3", "-c", "import pathlib; pathlib.Path('out_marker.txt').write_text('ok', encoding='utf-8')"]],
                "env_allowlist": ["PYTHONPATH"],
                "cwd_policy": "repo_root",
                "out_capture_policy": {"mode": "copy_glob", "patterns": ["out_marker.txt"]},
            }
        },
    )
    monkeypatch.setattr(
        "cdel.v18_0.ek.ek_runner_v1._load_active_ek",
        lambda _repo_root, _expected_ek_id: {
            "schema_version": "evaluation_kernel_v1",
            "stages": [
                {"stage_name": "REALIZE"},
                {"stage_name": "SCORE"},
                {"stage_name": "FINAL_AUDIT"},
            ],
            "scoring_impl": {"code_ref": {"path": "tools/omega/omega_benchmark_suite_v1.py"}},
        },
    )
    monkeypatch.setattr(
        "cdel.v18_0.ek.ek_runner_v1._run_score_stage",
        lambda **_kwargs: {
            "ok": True,
            "score_run_root": tmp_path / "score_run",
            "score_run_hash": "sha256:" + ("8" * 64),
        },
    )

    receipt, code = verify(
        subrun_root=subrun_root,
        repo_root=repo_root,
        ccap_relpath=ccap_rel,
        receipt_out_dir=verifier_dir,
    )
    assert code is None
    assert receipt["determinism_check"] == "PASS"
    assert receipt["eval_status"] == "PASS"
    assert receipt["decision"] == "PROMOTE"

    realized_plain = subrun_root / "ccap" / "realized" / "realized_capsule_receipt_v1.json"
    assert realized_plain.exists()
    realized = load_canon_json(realized_plain)
    assert realized["determinism_check"] == "PASS"

    state_root = subrun_root.parents[1]
    _patch_meta_core(monkeypatch, tmp_path)
    monkeypatch.setattr("cdel.v18_0.omega_promoter_v1._verify_ccap_apply_matches_receipt", lambda **_: True)
    promo_receipt, _ = run_promotion(
        tick_u64=1,
        dispatch_ctx=_dispatch_ctx(state_root, subrun_root),
        subverifier_receipt={"result": {"status": "VALID", "reason_code": None}},
        allowlists=_allowlists(repo_root),
    )
    assert promo_receipt is not None
    assert promo_receipt["result"]["status"] == "PROMOTED"


def test_ccap_patch_no_improvement_refutes_with_receipt(tmp_path: Path, monkeypatch) -> None:
    repo_root = _repo_root()
    target_relpath = "tools/omega/ccap_acceptance_generated_no_improvement.py"
    base_tree_id = "sha256:" + ("6" * 64)
    recipe_id = "sha256:" + ("7" * 64)
    patch_bytes = _make_patch(repo_root, target_relpath, "no_improvement")
    subrun_root, verifier_dir, _bundle, ccap_rel = _setup_ccap_artifacts(
        tmp_path=tmp_path,
        repo_root=repo_root,
        base_tree_id=base_tree_id,
        patch_bytes=patch_bytes,
        recipe_id=recipe_id,
    )

    monkeypatch.setattr("cdel.v18_0.verify_ccap_v1.compute_repo_base_tree_id", lambda _root: base_tree_id)
    monkeypatch.setattr("cdel.v18_0.ek.ek_runner_v1.materialize_repo_snapshot", _minimal_materializer(repo_root, target_relpath))
    monkeypatch.setattr(
        "cdel.v18_0.realize.repo_harness_v1._load_build_recipes",
        lambda _repo_root: {
            recipe_id: {
                "recipe_id": recipe_id,
                "commands": [["python3", "-c", "print('realize ok')"]],
                "env_allowlist": ["PYTHONPATH"],
                "cwd_policy": "repo_root",
                "out_capture_policy": {"mode": "none"},
            }
        },
    )
    monkeypatch.setattr(
        "cdel.v18_0.ek.ek_runner_v1._load_active_ek",
        lambda _repo_root, _expected_ek_id: {
            "schema_version": "evaluation_kernel_v1",
            "stages": [
                {"stage_name": "REALIZE"},
                {"stage_name": "SCORE"},
                {"stage_name": "FINAL_AUDIT"},
            ],
            "scoring_impl": {"code_ref": {"path": "tools/omega/omega_benchmark_suite_v1.py"}},
        },
    )
    monkeypatch.setattr(
        "cdel.v18_0.ek.ek_runner_v1._run_score_stage",
        lambda **_kwargs: {
            "ok": False,
            "refutation": {"code": "NO_IMPROVEMENT", "detail": "candidate score did not improve"},
        },
    )

    receipt, code = verify(
        subrun_root=subrun_root,
        repo_root=repo_root,
        ccap_relpath=ccap_rel,
        receipt_out_dir=verifier_dir,
    )
    assert code == "NO_IMPROVEMENT"
    assert receipt["determinism_check"] == "PASS"
    assert receipt["eval_status"] == "FAIL"
    assert receipt["decision"] == "REJECT"

    plain_receipt_path = verifier_dir / "ccap_receipt_v1.json"
    assert plain_receipt_path.exists()
    plain_receipt = load_canon_json(plain_receipt_path)
    assert plain_receipt["decision"] == "REJECT"

    cert_paths = sorted((subrun_root / "ccap" / "refutations").glob("sha256_*.ccap_refutation_cert_v1.json"))
    assert cert_paths
    cert = load_canon_json(cert_paths[-1])
    assert cert["refutation_code"] == "NO_IMPROVEMENT"


def test_ccap_patch_nondeterminism_is_accepted_and_promoter_allows(tmp_path: Path, monkeypatch) -> None:
    repo_root = _repo_root()
    target_relpath = "tools/omega/ccap_acceptance_generated_nondet.py"
    base_tree_id = "sha256:" + ("3" * 64)
    recipe_id = "sha256:" + ("4" * 64)
    patch_bytes = _make_patch(repo_root, target_relpath, "nondeterministic")
    subrun_root, verifier_dir, _bundle, ccap_rel = _setup_ccap_artifacts(
        tmp_path=tmp_path,
        repo_root=repo_root,
        base_tree_id=base_tree_id,
        patch_bytes=patch_bytes,
        recipe_id=recipe_id,
    )

    monkeypatch.setattr("cdel.v18_0.verify_ccap_v1.compute_repo_base_tree_id", lambda _root: base_tree_id)
    monkeypatch.setattr("cdel.v18_0.ek.ek_runner_v1.materialize_repo_snapshot", _minimal_materializer(repo_root, target_relpath))
    monkeypatch.setattr(
        "cdel.v18_0.realize.repo_harness_v1._load_build_recipes",
        lambda _repo_root: {
            recipe_id: {
                "recipe_id": recipe_id,
                "commands": [["python3", "-c", "import time; print(time.time_ns())"]],
                "env_allowlist": ["PYTHONPATH"],
                "cwd_policy": "repo_root",
                "out_capture_policy": {"mode": "none"},
            }
        },
    )
    monkeypatch.setattr(
        "cdel.v18_0.ek.ek_runner_v1._load_active_ek",
        lambda _repo_root, _expected_ek_id: {
            "schema_version": "evaluation_kernel_v1",
            "stages": [
                {"stage_name": "REALIZE"},
                {"stage_name": "SCORE"},
                {"stage_name": "FINAL_AUDIT"},
            ],
            "scoring_impl": {"code_ref": {"path": "tools/omega/omega_benchmark_suite_v1.py"}},
        },
    )
    monkeypatch.setattr(
        "cdel.v18_0.ek.ek_runner_v1._run_score_stage",
        lambda **_kwargs: {
            "ok": True,
            "score_run_root": tmp_path / "score_run",
            "score_run_hash": "sha256:" + ("5" * 64),
        },
    )

    receipt, _ = verify(
        subrun_root=subrun_root,
        repo_root=repo_root,
        ccap_relpath=ccap_rel,
        receipt_out_dir=verifier_dir,
    )
    assert receipt["determinism_check"] == "PASS"
    assert receipt["eval_status"] == "PASS"
    assert receipt["decision"] == "PROMOTE"

    cert_paths = sorted((subrun_root / "ccap" / "refutations").glob("sha256_*.ccap_refutation_cert_v1.json"))
    assert not cert_paths

    state_root = subrun_root.parents[1]
    _patch_meta_core(monkeypatch, tmp_path)
    monkeypatch.setattr("cdel.v18_0.omega_promoter_v1._verify_ccap_apply_matches_receipt", lambda **_: True)
    promo_receipt, _ = run_promotion(
        tick_u64=1,
        dispatch_ctx=_dispatch_ctx(state_root, subrun_root),
        subverifier_receipt={"result": {"status": "VALID", "reason_code": None}},
        allowlists=_allowlists(repo_root),
    )
    assert promo_receipt is not None
    assert promo_receipt["result"]["status"] == "PROMOTED"
