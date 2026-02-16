import io
import tarfile
from pathlib import Path

from .canonical_json import assert_no_floats, to_gcj1_bytes
from .hashes import REQUIRED_TAR_ENTRIES, candidate_id_from_components, sha256_hex
from .validate_instance import load_json_strict


def _load_json_bytes(path: Path) -> bytes:
    obj = load_json_strict(path.read_text(encoding="utf-8"))
    assert_no_floats(obj)
    return to_gcj1_bytes(obj)


def build_candidate_tar(out_path: Path, artifact_dir: Path) -> str:
    artifacts: dict[str, bytes] = {}
    for name in REQUIRED_TAR_ENTRIES[1:]:
        path = artifact_dir / name
        if not path.exists():
            raise FileNotFoundError(f"missing artifact: {path}")
        artifacts[name] = _load_json_bytes(path)

    manifest_obj = {
        "format": "ccai_x_mind_patch_candidate_mind_v1",
        "schema_version": "1",
        "task_id": "ccai_x_mind_v1",
        "candidate_id": "0" * 64,
        "artifacts": [
            {
                "path": name,
                "sha256": sha256_hex(artifacts[name]),
                "bytes_len": len(artifacts[name]),
            }
            for name in sorted(artifacts.keys())
        ],
    }

    candidate_id = candidate_id_from_components(manifest_obj, {"manifest.json": b"", **artifacts})
    manifest_obj["candidate_id"] = candidate_id
    artifacts["manifest.json"] = to_gcj1_bytes(manifest_obj)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(out_path, "w", format=tarfile.USTAR_FORMAT) as tar:
        for name in REQUIRED_TAR_ENTRIES:
            data = artifacts[name]
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            info.mtime = 0
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            info.mode = 0o644
            tar.addfile(info, io.BytesIO(data))

    return candidate_id
