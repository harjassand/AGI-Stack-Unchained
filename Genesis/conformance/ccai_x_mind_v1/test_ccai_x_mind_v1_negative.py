import io
import json
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = ROOT / "tools"
VEC_DIR = ROOT / "test_vectors" / "ccai_x_mind_v1"

sys.path.insert(0, str(TOOLS_DIR))

from ccai_x_mind_v1.canonical_json import to_gcj1_bytes  # noqa: E402
from ccai_x_mind_v1.efe_recompute import recompute_efe_report  # noqa: E402
from ccai_x_mind_v1.hashes import (  # noqa: E402
    ZERO_HASH,
    candidate_id_from_tar,
    do_payload_hash,
    workspace_state_hash,
)
from ccai_x_mind_v1.validate_instance import (  # noqa: E402
    CcaiXValidationError,
    ERR_WORKSPACE_MARGINAL_LENGTH_MISMATCH,
    load_json_strict,
    validate_json_bytes,
)


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_expected(name: str) -> str:
    return (VEC_DIR / name).read_text(encoding="utf-8").strip()


def assert_do_payload_hash_matches(obj, expected_hash: str) -> None:
    computed = do_payload_hash(obj["entries"][0]["do_payload"])
    if computed != expected_hash:
        raise AssertionError("do_payload_hash mismatch")


def compute_residual_fp(belief_a: list[int], belief_b: list[int]) -> int:
    return sum(abs(int(a) - int(b)) for a, b in zip(belief_a, belief_b))


class TestCcaiXMindV1Negative(unittest.TestCase):
    def test_float_rejection(self) -> None:
        data = (VEC_DIR / "workspace_state.json").read_text(encoding="utf-8")
        mutated = data.replace("1000", "1.5", 1).encode("utf-8")
        with self.assertRaises(Exception):
            validate_json_bytes(mutated)

    def test_unsorted_list_rejection(self) -> None:
        capsule = load_json(VEC_DIR / "preference_capsule.json")
        capsule["metrics"] = list(reversed(capsule["metrics"]))
        mutated = to_gcj1_bytes(capsule)
        with self.assertRaises(Exception):
            validate_json_bytes(mutated)

    def test_program_instruction_out_of_set(self) -> None:
        program = load_json(VEC_DIR / "inference_kernel_program.json")
        program["program"][0]["op"] = "BAD_OP"
        mutated = to_gcj1_bytes(program)
        with self.assertRaises(Exception):
            validate_json_bytes(mutated)

    def test_workspace_hash_chain_break(self) -> None:
        raw = (VEC_DIR / "workspace_state.jsonl").read_bytes()
        lines = raw.splitlines()
        self.assertGreaterEqual(len(lines), 2)
        second = load_json_strict(lines[1].decode("utf-8"))
        second["prev_state_hash"] = ZERO_HASH
        recomputed = workspace_state_hash(ZERO_HASH, second["beliefs"])
        self.assertNotEqual(recomputed, second["state_hash"])

    def test_efe_mismatch_vs_recompute(self) -> None:
        efe_report = load_json(VEC_DIR / "efe_report.json")
        recomputed = recompute_efe_report(efe_report)
        self.assertEqual(to_gcj1_bytes(recomputed), to_gcj1_bytes(efe_report))

        mutated = json.loads(json.dumps(efe_report))
        mutated["policies"][0]["risk_fp"] += 1
        recomputed2 = recompute_efe_report(mutated)
        self.assertNotEqual(to_gcj1_bytes(recomputed2), to_gcj1_bytes(mutated))

    def test_coherence_residual_bound(self) -> None:
        operator = load_json(VEC_DIR / "coherence_operator.json")
        residual_bound = int(operator["residual_bound_fp"])
        belief_a = [0, 1000]
        belief_b = [1000, 0]
        residual = compute_residual_fp(belief_a, belief_b)
        self.assertGreater(residual, residual_bound)

    def test_candidate_tar_missing_entry(self) -> None:
        original_tar = VEC_DIR / "ccai_x_mind_patch_candidate_mind_v1.tar"
        with tarfile.open(original_tar, "r") as tar:
            members = [m for m in tar.getmembers() if m.name != "policy_prior.json"]
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_tar_path = Path(tmpdir) / "missing.tar"
                with tarfile.open(tmp_tar_path, "w", format=tarfile.USTAR_FORMAT) as out_tar:
                    for member in members:
                        fileobj = tar.extractfile(member)
                        if fileobj is None:
                            continue
                        data = fileobj.read()
                        info = tarfile.TarInfo(name=member.name)
                        info.size = len(data)
                        info.mtime = 0
                        info.uid = 0
                        info.gid = 0
                        info.uname = ""
                        info.gname = ""
                        info.mode = 0o644
                        out_tar.addfile(info, io.BytesIO(data))

                with self.assertRaises(Exception):
                    candidate_id_from_tar(str(tmp_tar_path))

    def test_workspace_state_prob_fp_length_mismatch_fails(self) -> None:
        workspace = load_json(VEC_DIR / "workspace_state.json")
        marginal = workspace["beliefs"]["variable_marginals"][0]
        marginal["prob_fp"] = marginal["prob_fp"][:-1]
        mutated = to_gcj1_bytes(workspace)
        with self.assertRaises(CcaiXValidationError) as ctx:
            validate_json_bytes(mutated)
        self.assertEqual(ctx.exception.code, ERR_WORKSPACE_MARGINAL_LENGTH_MISMATCH)
        self.assertEqual(ctx.exception.details, "")


if __name__ == "__main__":
    raise SystemExit(unittest.main())
