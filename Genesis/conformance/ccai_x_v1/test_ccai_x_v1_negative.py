import io
import json
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = ROOT / "tools"
VEC_DIR = ROOT / "test_vectors" / "ccai_x_v1"

sys.path.insert(0, str(TOOLS_DIR))

from ccai_x_v1.canonical_json import to_gcj1_bytes  # noqa: E402
from ccai_x_v1.hashes import candidate_id_from_tar, do_payload_hash  # noqa: E402
from ccai_x_v1.validate_instance import (  # noqa: E402
    CcaiXValidationError,
    ERR_WORKSPACE_MARGINAL_LENGTH_MISMATCH,
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


class TestCcaiXV1Negative(unittest.TestCase):
    def test_float_rejection(self) -> None:
        data = (VEC_DIR / "workspace_state.json").read_text(encoding="utf-8")
        mutated = data.replace("4294967296", "1.0", 1).encode("utf-8")
        with self.assertRaises(Exception):
            validate_json_bytes(mutated)

    def test_unsorted_list_rejection(self) -> None:
        registry = load_json(VEC_DIR / "mechanism_registry.json")
        registry["variables"] = list(reversed(registry["variables"]))
        mutated = to_gcj1_bytes(registry)
        with self.assertRaises(Exception):
            validate_json_bytes(mutated)

    def test_hash_mismatch_rejection(self) -> None:
        do_map = load_json(VEC_DIR / "do_map.json")
        do_map["entries"][0]["do_payload"]["value_int"] = 2
        expected = read_expected("expected_do_payload_hash.txt")
        with self.assertRaises(AssertionError):
            assert_do_payload_hash_matches(do_map, expected)

    def test_candidate_tar_missing_entry(self) -> None:
        original_tar = VEC_DIR / "ccai_x_mind_patch_candidate_v1.tar"
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

    def test_candidate_manifest_mismatch(self) -> None:
        original_tar = VEC_DIR / "ccai_x_mind_patch_candidate_v1.tar"
        with tarfile.open(original_tar, "r") as tar:
            members = tar.getmembers()
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_tar_path = Path(tmpdir) / "bad_manifest.tar"
                with tarfile.open(tmp_tar_path, "w", format=tarfile.USTAR_FORMAT) as out_tar:
                    for member in members:
                        fileobj = tar.extractfile(member)
                        if fileobj is None:
                            continue
                        data = fileobj.read()
                        if member.name == "manifest.json":
                            manifest = json.loads(data.decode("utf-8"))
                            manifest["candidate_id"] = "0" * 64
                            data = to_gcj1_bytes(manifest)
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
