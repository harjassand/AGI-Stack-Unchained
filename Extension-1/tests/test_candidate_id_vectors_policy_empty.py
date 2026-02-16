import hashlib

from self_improve_code_v1.package.candidate_hash_v1 import compute_candidate_id, set_candidate_id_backend
from self_improve_code_v1.canon.json_canon_v1 import canon_bytes


def test_candidate_id_policy_empty():
    set_candidate_id_backend({"backend": "stub_deterministic_v1"})
    patch_bytes = b"diff"
    manifest = {
        "candidate_id": "",
        "base": {"git_commit": "abc"},
        "eval_plan_id": "plan",
        "patch": {
            "sha256": "",
            "byte_length": len(patch_bytes),
            "files_changed": 1,
            "lines_added": 1,
            "lines_removed": 0,
        },
    }
    cand_id, _, _, _ = compute_candidate_id(manifest, patch_bytes)

    manifest_for_hash = dict(manifest)
    manifest_for_hash.pop("candidate_id", None)
    expected = hashlib.sha256(b"stub_candidate_id_v1\x00" + canon_bytes(manifest_for_hash) + patch_bytes).hexdigest()
    assert cand_id == expected
