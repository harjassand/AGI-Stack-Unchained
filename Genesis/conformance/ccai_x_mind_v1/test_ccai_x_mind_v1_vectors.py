import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = ROOT / "tools"
VEC_DIR = ROOT / "test_vectors" / "ccai_x_mind_v1"

sys.path.insert(0, str(TOOLS_DIR))

from ccai_x_mind_v1.canonical_json import assert_no_floats, to_gcj1_bytes  # noqa: E402
from ccai_x_mind_v1.hashes import (  # noqa: E402
    ZERO_HASH,
    candidate_id_from_tar,
    do_payload_hash,
    intervention_log_link_hash,
    mechanism_hash,
    sha256_hex,
    workspace_state_hash,
)
from ccai_x_mind_v1.validate_instance import load_json_strict, validate_path  # noqa: E402


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_expected(name: str) -> str:
    return (VEC_DIR / name).read_text(encoding="utf-8").strip()


def compute_final_link_hash(jsonl_path: Path) -> str:
    raw = jsonl_path.read_bytes()
    if not raw.endswith(b"\n"):
        raise AssertionError("JSONL file must end with LF")
    lines = raw.split(b"\n")[:-1]
    prev = ZERO_HASH
    for idx, line in enumerate(lines):
        if not line:
            raise AssertionError(f"empty JSONL line {idx}")
        obj = load_json_strict(line.decode("utf-8"))
        assert_no_floats(obj)
        if obj.get("prev_link_hash") != prev:
            raise AssertionError(f"prev_link_hash mismatch at line {idx}")
        computed = intervention_log_link_hash(prev, obj)
        if obj.get("link_hash") != computed:
            raise AssertionError(f"link_hash mismatch at line {idx}")
        prev = computed
    return prev


class TestCcaiXMindV1Vectors(unittest.TestCase):
    def test_validate_instances(self) -> None:
        for name in (
            "markov_blanket_spec.json",
            "do_map.json",
            "causal_mechanism_registry.json",
            "policy_prior.json",
            "preference_capsule.json",
            "inference_kernel_isa.json",
            "inference_kernel_program.json",
            "coherence_operator.json",
            "workspace_state.json",
            "efe_report.json",
            "affordance_latent.json",
            "intervention_log.jsonl",
            "workspace_state.jsonl",
            "efe_report.jsonl",
        ):
            validate_path(VEC_DIR / name)

    def test_transcript_jsonl_is_canonical(self) -> None:
        raw = (VEC_DIR / "transcript.jsonl").read_bytes()
        self.assertTrue(raw.endswith(b"\n"))
        for line in raw.split(b"\n")[:-1]:
            obj = load_json_strict(line.decode("utf-8"))
            assert_no_floats(obj)
            self.assertEqual(to_gcj1_bytes(obj), line)

    def test_hashes(self) -> None:
        do_map = load_json(VEC_DIR / "do_map.json")
        expected_do_payload_hash = read_expected("expected_do_payload_hash.txt")
        do_payload = do_map["entries"][0]["do_payload"]
        self.assertEqual(do_payload_hash(do_payload), expected_do_payload_hash)
        self.assertEqual(do_map["entries"][0]["do_payload_hash"], expected_do_payload_hash)

        registry = load_json(VEC_DIR / "causal_mechanism_registry.json")
        mechanism = registry["mechanisms"][0]
        expected_mechanism_hash = read_expected("expected_mechanism_hash.txt")
        self.assertEqual(mechanism_hash(mechanism), expected_mechanism_hash)
        self.assertEqual(
            do_map["entries"][0]["expected_mech_hash_before"], expected_mechanism_hash
        )

        # Workspace state hash chain
        expected_workspace_state_hash = read_expected("expected_workspace_state_hash.txt")
        workspace_states = [
            load_json_strict(line.decode("utf-8"))
            for line in (VEC_DIR / "workspace_state.jsonl").read_bytes().splitlines()
            if line
        ]
        prev = ZERO_HASH
        last_hash = ""
        for state in workspace_states:
            computed = workspace_state_hash(prev, state["beliefs"])
            self.assertEqual(computed, state["state_hash"])
            prev = state["state_hash"]
            last_hash = state["state_hash"]
        self.assertEqual(last_hash, expected_workspace_state_hash)

        expected_log_hash = read_expected("expected_intervention_log_final_link_hash.txt")
        final_hash = compute_final_link_hash(VEC_DIR / "intervention_log.jsonl")
        self.assertEqual(final_hash, expected_log_hash)

        expected_candidate_id = read_expected("expected_candidate_id.txt")
        candidate_id = candidate_id_from_tar(str(VEC_DIR / "ccai_x_mind_patch_candidate_mind_v1.tar"))
        self.assertEqual(candidate_id, expected_candidate_id)

        efe_report = load_json(VEC_DIR / "efe_report.json")
        self.assertEqual(efe_report["candidate_id"], expected_candidate_id)

        expected_digest = read_expected("expected_efe_report_digest.txt")
        self.assertEqual(sha256_hex(to_gcj1_bytes(efe_report)), expected_digest)


if __name__ == "__main__":
    raise SystemExit(unittest.main())
