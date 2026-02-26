#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any


class MetalToolchainError(RuntimeError):
    pass


class NonReproMetalBuildError(MetalToolchainError):
    def __init__(self, *, build1_metallib_hash: str, build2_metallib_hash: str) -> None:
        super().__init__("NONREPRO_BUILD:METAL")
        self.build1_metallib_hash = str(build1_metallib_hash)
        self.build2_metallib_hash = str(build2_metallib_hash)


def _fail(reason: str) -> None:
    raise MetalToolchainError(str(reason))


def _canon_bytes(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _canon_hash_obj(obj: Any) -> str:
    return "sha256:" + hashlib.sha256(_canon_bytes(obj)).hexdigest()


def _hash_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _tool_path_from_xcrun(*, xcrun: Path, tool_name: str) -> Path:
    rc = subprocess.run([str(xcrun), "--find", tool_name], capture_output=True, text=True, check=False)
    if rc.returncode != 0:
        _fail(f"MISSING_STATE_INPUT:{tool_name}")
    out = (rc.stdout or "").strip()
    p = Path(out)
    if not p.is_absolute() or not p.exists() or not p.is_file():
        _fail(f"MISSING_STATE_INPUT:{tool_name}")
    return p.resolve()


def build_toolchain_manifest() -> dict[str, Any]:
    xcrun_raw = shutil.which("xcrun")
    if not xcrun_raw:
        _fail("MISSING_STATE_INPUT:xcrun")
    xcrun = Path(xcrun_raw).resolve()
    metal = _tool_path_from_xcrun(xcrun=xcrun, tool_name="metal")
    metallib = _tool_path_from_xcrun(xcrun=xcrun, tool_name="metallib")

    host = platform.machine().strip().lower() + "-" + platform.system().strip().lower()
    payload = {
        "schema_version": "toolchain_manifest_metal_v1",
        "toolchain_id": "sha256:" + ("0" * 64),
        "checker_name": "metal_toolchain_v1",
        "xcrun_executable": str(xcrun),
        "xcrun_sha256": _hash_file(xcrun),
        "metal_executable": str(metal),
        "metal_sha256": _hash_file(metal),
        "metallib_executable": str(metallib),
        "metallib_sha256": _hash_file(metallib),
        "host_triple": host,
        "compile_invocation_template": [
            str(xcrun),
            "metal",
            "-std=metal3.0",
            "-fno-fast-math",
            "-c",
            "{src_metal}",
            "-o",
            "{out_air}",
        ],
        "link_invocation_template": [
            str(xcrun),
            "metallib",
            "{in_air}",
            "-o",
            "{out_metallib}",
        ],
    }
    payload["toolchain_id"] = _canon_hash_obj({k: v for k, v in payload.items() if k != "toolchain_id"})
    return payload


def _render(tokens: list[str], mapping: dict[str, str]) -> list[str]:
    out: list[str] = []
    for token in tokens:
        rendered = str(token)
        for key, value in mapping.items():
            rendered = rendered.replace("{" + key + "}", str(value))
        out.append(rendered)
    return out


def _compile_once(*, msl_src_path: Path, out_dir: Path, toolchain: dict[str, Any]) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    air_path = out_dir / "omega_kernel.air"
    lib_path = out_dir / "omega_kernel.metallib"

    compile_cmd = _render(
        list(toolchain.get("compile_invocation_template") or []),
        {
            "src_metal": str(msl_src_path.resolve()),
            "out_air": str(air_path.resolve()),
        },
    )
    link_cmd = _render(
        list(toolchain.get("link_invocation_template") or []),
        {
            "in_air": str(air_path.resolve()),
            "out_metallib": str(lib_path.resolve()),
        },
    )
    env = dict(os.environ)
    env.update(
        {
            "SOURCE_DATE_EPOCH": "0",
            "PYTHONHASHSEED": "0",
        }
    )

    rc1 = subprocess.run(compile_cmd, capture_output=True, text=True, check=False, env=env)
    if rc1.returncode != 0:
        _fail("VERIFY_ERROR:metal_compile_failed")
    rc2 = subprocess.run(link_cmd, capture_output=True, text=True, check=False, env=env)
    if rc2.returncode != 0:
        _fail("VERIFY_ERROR:metallib_link_failed")

    if not lib_path.exists() or not lib_path.is_file():
        _fail("VERIFY_ERROR:metallib_missing")
    return lib_path


def build_twice_repro(*, msl_src_path: Path, toolchain: dict[str, Any]) -> tuple[bytes, dict[str, Any]]:
    with tempfile.TemporaryDirectory(prefix="phase4b_metal_b1_") as t1, tempfile.TemporaryDirectory(prefix="phase4b_metal_b2_") as t2:
        out1 = _compile_once(msl_src_path=msl_src_path, out_dir=Path(t1), toolchain=toolchain)
        out2 = _compile_once(msl_src_path=msl_src_path, out_dir=Path(t2), toolchain=toolchain)
        h1 = _hash_file(out1)
        h2 = _hash_file(out2)
        if h1 != h2:
            raise NonReproMetalBuildError(build1_metallib_hash=h1, build2_metallib_hash=h2)

        proof = {
            "schema_id": "native_metal_build_proof_v1",
            "id": "sha256:" + ("0" * 64),
            "toolchain_manifest_hash": _canon_hash_obj(toolchain),
            "metal_src_merkle_hash": "",
            "output_metallib_hash": h1,
            "build_twice_repro_b": True,
            "created_at_utc": "",
            "build1_metallib_hash": h1,
            "build2_metallib_hash": h2,
        }
        proof["id"] = _canon_hash_obj({k: v for k, v in proof.items() if k != "id"})
        return out1.read_bytes(), proof


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="metal_toolchain_v1")
    ap.add_argument("--emit_manifest", default="")
    return ap.parse_args()


def main() -> None:
    args = _parse_args()
    manifest = build_toolchain_manifest()
    out = {"toolchain_manifest": manifest, "toolchain_manifest_hash": _canon_hash_obj(manifest)}
    if str(args.emit_manifest).strip():
        path = Path(str(args.emit_manifest)).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(_canon_bytes(manifest))
        out["manifest_path"] = path.as_posix()
    print(json.dumps(out, sort_keys=True, separators=(",", ":"), ensure_ascii=False))


if __name__ == "__main__":
    main()
