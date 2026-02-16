import os

from self_improve_code_v1.canon.json_canon_v1 import canon_bytes
from self_improve_code_v1.canon.hash_v1 import sha256_hex
from self_improve_code_v1.package.candidate_hash_v1 import set_candidate_id_backend
from self_improve_code_v1.state.schema_state_v1 import make_state
from self_improve_code_v1.state.state_io_v1 import save_state
from self_improve_code_v1.state.state_update_v1 import apply_attempts
from self_improve_code_v1.state.attempt_log_v1 import append_attempt, init_history_seed
from self_improve_code_v1.patch.patch_stats_v1 import patch_stats
from self_improve_code_v1.package.manifest_v1 import build_manifest
from self_improve_code_v1.package.tar_deterministic_v1 import write_deterministic_tar
from self_improve_code_v1.run_manifest_v1 import build_run_manifest
from self_improve_code_v1.verify.verify_run_v1 import verify_run


def test_replay_no_exec_verifies_hashes(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "topk").mkdir()
    (run_dir / "selected").mkdir()

    run_config = {
        "baseline_commit": "abc",
        "eval_plan_id": "plan",
        "search": {"eta": 1},
        "candidate_id": {"backend": "stub_deterministic_v1"},
    }
    (run_dir / "run_config.json").write_bytes(canon_bytes(run_config))
    set_candidate_id_backend({"backend": "stub_deterministic_v1"})

    state_before = make_state(["arm1"])
    save_state(str(run_dir / "state_before.json"), state_before)

    patch_text = "--- a/x\n+++ b/x\n@@ -1 +1 @@\n-1\n+2\n"
    stats = patch_stats(patch_text)
    manifest = build_manifest("abc", "plan", patch_text, stats)
    patch_bytes = patch_text.encode("utf-8")

    tar_path = run_dir / "selected" / "selected_candidate.tar"
    write_deterministic_tar(str(tar_path), {"manifest.json": canon_bytes(manifest), "patch.diff": patch_bytes})

    attempt = {
        "attempt_index": 1,
        "arm_ids": ["arm1"],
        "value_choices": ["2"],
        "status": "OK",
        "m_bp": 10,
        "baseline_m_bp": 5,
        "reward": 5,
        "candidate_id": manifest["candidate_id"],
        "patch_sha256": manifest["patch"]["sha256"],
        "tar_sha256": sha256_hex(tar_path.read_bytes()),
    }

    attempts_path = run_dir / "attempts.jsonl"
    history = init_history_seed()
    history = append_attempt(str(attempts_path), attempt, history)

    state_after = apply_attempts(make_state(["arm1"]), [attempt], eta=1)
    save_state(str(run_dir / "state_after.json"), state_after)

    state_before_sha = sha256_hex(canon_bytes(state_before))
    state_after_sha = sha256_hex(canon_bytes(state_after))
    artifacts = {manifest["candidate_id"]: {"patch_sha256": attempt["patch_sha256"], "tar_sha256": attempt["tar_sha256"]}}
    run_manifest = build_run_manifest(run_config, [attempt], state_before_sha, state_after_sha, artifacts, manifest["candidate_id"])
    (run_dir / "run_manifest.json").write_bytes(canon_bytes(run_manifest))

    # topk artifacts
    (run_dir / "topk" / "1_patch.diff").write_bytes(patch_bytes)
    (run_dir / "topk" / "1_manifest.json").write_bytes(canon_bytes(manifest))
    (run_dir / "topk" / "1_candidate.tar").write_bytes(tar_path.read_bytes())
    (run_dir / "topk" / "1_devscreen_report.json").write_bytes(canon_bytes({"status": "OK"}))

    ok, errors = verify_run(str(run_dir))
    assert ok, errors
