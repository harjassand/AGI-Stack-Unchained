"""Omega-dispatchable EUDRS-U producer: vision capture (Stage 0) v1.

This producer is untrusted (RE3). It MUST only emit content-addressed artifacts
and a promotion summary that points at additive registry outputs.

Stage-0 authoritative verification lives in RE2:
  cdel.v18_0.eudrs_u.verify_vision_stage0_v1
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path
from typing import Any

from cdel.v18_0.eudrs_u.eudrs_u_hash_v1 import gcj1_canon_bytes, gcj1_loads_strict, sha256_prefixed
from cdel.v18_0.eudrs_u.eudrs_u_merkle_v1 import merkle_fanout_v1
from cdel.v18_0.eudrs_u.verify_vision_stage0_v1 import verify_and_emit_receipt as verify_stage0_and_emit_receipt
from cdel.v18_0.eudrs_u.vision_frame_v1 import decode_vision_frame_v1, encode_vision_frame_v1
from cdel.v18_0.omega_common_v1 import fail, require_no_absolute_paths, validate_schema


_CAMPAIGN_ID = "rsi_eudrs_u_vision_capture_v1"


def _write_hashed_json(*, root: Path, rel_dir: str, artifact_type: str, payload: dict[str, Any]) -> dict[str, str]:
    require_no_absolute_paths(payload)
    raw = gcj1_canon_bytes(payload)
    digest = sha256_prefixed(raw)
    hex64 = digest.split(":", 1)[1]
    name = f"sha256_{hex64}.{artifact_type}.json"
    out_path = (root / rel_dir / name)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(raw)
    return {"artifact_id": digest, "artifact_relpath": out_path.relative_to(root).as_posix()}


def _write_hashed_bin(*, root: Path, rel_dir: str, artifact_type: str, data: bytes) -> dict[str, str]:
    digest = sha256_prefixed(bytes(data))
    hex64 = digest.split(":", 1)[1]
    name = f"sha256_{hex64}.{artifact_type}.bin"
    out_path = (root / rel_dir / name)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(bytes(data))
    return {"artifact_id": digest, "artifact_relpath": out_path.relative_to(root).as_posix()}


def _rgb8_to_gray8(*, rgb: bytes) -> bytes:
    raw = bytes(rgb)
    if len(raw) % 3 != 0:
        fail("SCHEMA_FAIL")
    out = bytearray(len(raw) // 3)
    j = 0
    for i in range(0, len(raw), 3):
        r = int(raw[i]) & 0xFF
        g = int(raw[i + 1]) & 0xFF
        b = int(raw[i + 2]) & 0xFF
        out[j] = (77 * r + 150 * g + 29 * b) >> 8
        j += 1
    return bytes(out)


def _resize_nn_gray8(*, in_w: int, in_h: int, pixels: bytes, out_w: int, out_h: int) -> bytes:
    iw = int(in_w)
    ih = int(in_h)
    ow = int(out_w)
    oh = int(out_h)
    raw = bytes(pixels)
    if iw < 1 or ih < 1 or ow < 1 or oh < 1:
        fail("SCHEMA_FAIL")
    if len(raw) != iw * ih:
        fail("SCHEMA_FAIL")
    if iw == ow and ih == oh:
        return raw

    out = bytearray(ow * oh)
    for yo in range(oh):
        yi = (yo * ih) // oh
        if yi < 0:
            yi = 0
        if yi >= ih:
            yi = ih - 1
        base_in = yi * iw
        base_out = yo * ow
        for xo in range(ow):
            xi = (xo * iw) // ow
            if xi < 0:
                xi = 0
            if xi >= iw:
                xi = iw - 1
            out[base_out + xo] = raw[base_in + xi]
    return bytes(out)


def _resize_nn_rgb8(*, in_w: int, in_h: int, pixels: bytes, out_w: int, out_h: int) -> bytes:
    iw = int(in_w)
    ih = int(in_h)
    ow = int(out_w)
    oh = int(out_h)
    raw = bytes(pixels)
    if iw < 1 or ih < 1 or ow < 1 or oh < 1:
        fail("SCHEMA_FAIL")
    if len(raw) != iw * ih * 3:
        fail("SCHEMA_FAIL")
    if iw == ow and ih == oh:
        return raw

    out = bytearray(ow * oh * 3)
    for yo in range(oh):
        yi = (yo * ih) // oh
        if yi < 0:
            yi = 0
        if yi >= ih:
            yi = ih - 1
        for xo in range(ow):
            xi = (xo * iw) // ow
            if xi < 0:
                xi = 0
            if xi >= iw:
                xi = iw - 1
            src = (yi * iw + xi) * 3
            dst = (yo * ow + xo) * 3
            out[dst : dst + 3] = raw[src : src + 3]
    return bytes(out)


def _load_capture_config(path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        fail("MISSING_STATE_INPUT")
    obj = gcj1_loads_strict(path.read_bytes())
    if not isinstance(obj, dict):
        fail("SCHEMA_FAIL")
    require_no_absolute_paths(obj)
    if str(obj.get("schema_id", "")).strip() != "vision_capture_config_v1":
        fail("SCHEMA_FAIL")
    try:
        validate_schema(obj, "vision_capture_config_v1")
    except Exception:  # noqa: BLE001
        fail("SCHEMA_FAIL")
    return dict(obj)


def _canonicalize_frame_bytes(*, in_bytes: bytes, cfg: dict[str, Any]) -> tuple[bytes, int, int, str]:
    """Return (vision_frame_v1.bin bytes, width, height, pixel_format_str)."""

    caps = cfg["caps"]
    canon = cfg["canonical_output"]
    max_w = int(caps["max_width_u32"])
    max_h = int(caps["max_height_u32"])
    tgt_fmt = str(canon["target_pixel_format"]).strip()
    tgt_w = int(canon["target_width_u32"])
    tgt_h = int(canon["target_height_u32"])

    decoded = decode_vision_frame_v1(in_bytes)
    iw = int(decoded.width_u32)
    ih = int(decoded.height_u32)
    if iw < 1 or ih < 1 or iw > max_w or ih > max_h:
        fail("SCHEMA_FAIL")

    if tgt_fmt == "GRAY8":
        if decoded.pixel_format_str == "GRAY8":
            gray = bytes(decoded.pixels)
        elif decoded.pixel_format_str == "RGB8":
            gray = _rgb8_to_gray8(rgb=decoded.pixels)
        else:
            fail("SCHEMA_FAIL")
        out_pix = _resize_nn_gray8(in_w=iw, in_h=ih, pixels=gray, out_w=tgt_w, out_h=tgt_h)
        out_bin = encode_vision_frame_v1(width_u32=tgt_w, height_u32=tgt_h, pixel_format="GRAY8", pixels=out_pix)
        return out_bin, int(tgt_w), int(tgt_h), "GRAY8"

    if tgt_fmt == "RGB8":
        if decoded.pixel_format_str != "RGB8":
            fail("SCHEMA_FAIL")
        rgb = bytes(decoded.pixels)
        out_pix = _resize_nn_rgb8(in_w=iw, in_h=ih, pixels=rgb, out_w=tgt_w, out_h=tgt_h)
        out_bin = encode_vision_frame_v1(width_u32=tgt_w, height_u32=tgt_h, pixel_format="RGB8", pixels=out_pix)
        return out_bin, int(tgt_w), int(tgt_h), "RGB8"

    fail("SCHEMA_FAIL")
    return b"", 0, 0, ""


def _emit(state_dir: Path, *, capture_config_path: Path, session_name: str, input_frames_dir: Path) -> dict[str, Any]:
    state_dir = Path(state_dir).resolve()
    state_dir.mkdir(parents=True, exist_ok=True)

    # Stage-0 inputs.
    cfg_obj = _load_capture_config(Path(capture_config_path).resolve())

    # Deterministic file adapter: read *.vision_frame_v1.bin from a directory in sorted order.
    in_dir = Path(input_frames_dir).resolve()
    if not in_dir.exists() or not in_dir.is_dir():
        fail("MISSING_STATE_INPUT")
    input_paths = sorted(in_dir.glob("*.vision_frame_v1.bin"), key=lambda p: p.as_posix())
    if not input_paths:
        fail("MISSING_STATE_INPUT")

    caps = cfg_obj["caps"]
    max_frames = int(caps["max_frames_per_session_u32"])
    if len(input_paths) > max_frames:
        fail("SCHEMA_FAIL")

    stage_root = state_dir / "eudrs_u" / "staged_registry_tree"

    # Write capture config artifact.
    capture_cfg_ref = _write_hashed_json(
        root=stage_root,
        rel_dir="polymath/registry/eudrs_u/vision/ingest/configs",
        artifact_type="vision_capture_config_v1",
        payload=cfg_obj,
    )

    # Emit canonical frames + manifests.
    frame_manifest_refs: list[dict[str, str]] = []
    frame_bin_ids: list[str] = []
    frame_bin_bytes: list[bytes] = []
    leaf32: list[bytes] = []

    for _idx, in_path in enumerate(input_paths):
        in_bytes = in_path.read_bytes()
        frame_bytes, w, h, fmt = _canonicalize_frame_bytes(in_bytes=in_bytes, cfg=cfg_obj)

        frame_ref = _write_hashed_bin(
            root=stage_root,
            rel_dir="polymath/registry/eudrs_u/vision/frames",
            artifact_type="vision_frame_v1",
            data=frame_bytes,
        )
        frame_bin_ids.append(str(frame_ref["artifact_id"]))
        frame_bin_bytes.append(bytes(frame_bytes))
        leaf32.append(bytes.fromhex(frame_ref["artifact_id"].split(":", 1)[1]))

        frame_manifest = {
            "schema_id": "vision_frame_manifest_v1",
            "frame_ref": {
                "artifact_id": frame_ref["artifact_id"],
                "artifact_relpath": frame_ref["artifact_relpath"],
            },
            "width_u32": int(w),
            "height_u32": int(h),
            "pixel_format": str(fmt),
            "timestamp_ns_u64": 0,
        }
        man_ref = _write_hashed_json(
            root=stage_root,
            rel_dir="polymath/registry/eudrs_u/vision/frames",
            artifact_type="vision_frame_manifest_v1",
            payload=frame_manifest,
        )
        frame_manifest_refs.append(man_ref)

    # Merkle root over session leaf list.
    fanout = int(cfg_obj["merkle"]["fanout_u32"])
    root32 = merkle_fanout_v1(leaf_hash32=leaf32, fanout_u32=fanout)
    frames_merkle_root32 = "sha256:" + bytes(root32).hex()

    # Clips: minimal policy supports a single full-session clip when enabled.
    clips: list[dict[str, Any]] = []
    if bool(cfg_obj["clip_policy"]["emit_full_session_clip_b"]):
        clip_manifest = {
            "schema_id": "vision_clip_manifest_v1",
            # Avoid a content-hash cycle: bind clips to the session's frame commitment (root32).
            "session_manifest_id": str(frames_merkle_root32),
            "clip_index_u32": 0,
            "frame_index_start_u32": 0,
            "frame_count_u32": int(len(frame_bin_ids)),
            "frames_merkle_fanout_u32": int(fanout),
            "frames_merkle_root32": str(frames_merkle_root32),
        }
        clip_manifest_ref = _write_hashed_json(
            root=stage_root,
            rel_dir="polymath/registry/eudrs_u/vision/clips",
            artifact_type="vision_clip_manifest_v1",
            payload=clip_manifest,
        )

        clip_blob_ref: dict[str, str] | None = None
        if bool(cfg_obj["clip_policy"]["emit_clip_blob_b"]):
            payload = b"".join(frame_bin_bytes)
            header = b"VCL1" + (1).to_bytes(2, "little") + (0).to_bytes(2, "little")
            header += (0).to_bytes(4, "little")  # clip_index_u32
            header += (len(frame_bin_bytes)).to_bytes(4, "little")
            header += (len(payload)).to_bytes(4, "little")
            clip_blob_bytes = header + payload
            clip_blob_ref = _write_hashed_bin(
                root=stage_root,
                rel_dir="polymath/registry/eudrs_u/vision/clips",
                artifact_type="vision_clip_v1",
                data=clip_blob_bytes,
            )

        clips.append(
            {
                "clip_index_u32": 0,
                "clip_manifest_ref": clip_manifest_ref,
                "clip_blob_ref": None if clip_blob_ref is None else clip_blob_ref,
            }
        )

    # Session manifest v2.
    session_manifest = {
        "schema_id": "vision_session_manifest_v2",
        "session_name": str(session_name),
        "capture_config_ref": capture_cfg_ref,
        "frame_count_u32": int(len(frame_manifest_refs)),
        "frames": [
            {
                "frame_index_u32": int(i),
                "frame_manifest_ref": ref,
            }
            for i, ref in enumerate(frame_manifest_refs)
        ],
        "clips": clips,
        "frames_merkle_fanout_u32": int(fanout),
        "frames_merkle_root32": str(frames_merkle_root32),
    }
    session_manifest_ref = _write_hashed_json(
        root=stage_root,
        rel_dir="polymath/registry/eudrs_u/vision/sessions",
        artifact_type="vision_session_manifest_v2",
        payload=session_manifest,
    )

    # Ingest run manifest.
    ingest_run_manifest = {
        "schema_id": "vision_ingest_run_manifest_v1",
        "capture_config_ref": capture_cfg_ref,
        "session_manifest_ref": session_manifest_ref,
        "frame_artifact_ids": list(frame_bin_ids),
        "frames_merkle_root32": str(frames_merkle_root32),
    }
    ingest_run_manifest_ref = _write_hashed_json(
        root=stage_root,
        rel_dir="polymath/registry/eudrs_u/vision/ingest/runs",
        artifact_type="vision_ingest_run_manifest_v1",
        payload=ingest_run_manifest,
    )

    # Stage-0 authoritative verification + receipt emission (content-addressed under staged tree).
    ingest_run_abs = stage_root / ingest_run_manifest_ref["artifact_relpath"]
    stage0_receipt_ref = verify_stage0_and_emit_receipt(state_dir, ingest_run_manifest_path=ingest_run_abs)

    # Run-local evidence stubs required by the promotion summary schema.
    evidence_dir_rel = "eudrs_u/evidence"
    producer_kind = "vision_capture"
    weights_ref = _write_hashed_json(root=state_dir, rel_dir=evidence_dir_rel, artifact_type="weights_manifest_v1", payload={"schema_id": "weights_manifest_v1", "producer_kind": producer_kind})
    ml_index_ref = _write_hashed_json(root=state_dir, rel_dir=evidence_dir_rel, artifact_type="ml_index_manifest_v1", payload={"schema_id": "ml_index_manifest_v1", "producer_kind": producer_kind})
    cac_ref = _write_hashed_json(root=state_dir, rel_dir=evidence_dir_rel, artifact_type="cac_v1", payload={"schema_id": "cac_v1", "producer_kind": producer_kind})
    ufc_ref = _write_hashed_json(root=state_dir, rel_dir=evidence_dir_rel, artifact_type="ufc_v1", payload={"schema_id": "ufc_v1", "producer_kind": producer_kind})
    cooldown_ref = _write_hashed_json(root=state_dir, rel_dir=evidence_dir_rel, artifact_type="cooldown_ledger_v1", payload={"schema_id": "cooldown_ledger_v1", "producer_kind": producer_kind})
    stability_ref = _write_hashed_json(root=state_dir, rel_dir=evidence_dir_rel, artifact_type="stability_metrics_v1", payload={"schema_id": "stability_metrics_v1", "producer_kind": producer_kind})
    det_cert_ref = _write_hashed_json(root=state_dir, rel_dir=evidence_dir_rel, artifact_type="determinism_cert_v1", payload={"schema_id": "determinism_cert_v1", "producer_kind": producer_kind})
    uni_cert_ref = _write_hashed_json(root=state_dir, rel_dir=evidence_dir_rel, artifact_type="universality_cert_v1", payload={"schema_id": "universality_cert_v1", "producer_kind": producer_kind})

    # Minimal staged root tuple + active pointer (schema-only; full promotion verification is handled elsewhere).
    epoch_u64 = 0
    opset_digest = sha256_prefixed(gcj1_canon_bytes({"schema_id": "eudrs_u_opset_stub_v1", "version_u64": 1}))
    opset_id = f"opset:eudrs_u_v1:{opset_digest}"

    def _manifest(schema_id: str) -> dict[str, Any]:
        return {"schema_id": schema_id, "epoch_u64": int(epoch_u64), "dc1_id": "dc1:q32_v1", "opset_id": opset_id}

    registry_prefix = "polymath/registry/eudrs_u"
    sroot = _write_hashed_json(root=stage_root, rel_dir=f"{registry_prefix}/manifests", artifact_type="qxwmr_world_model_manifest_v1", payload=_manifest("qxwmr_world_model_manifest_v1"))
    oroot = _write_hashed_json(root=stage_root, rel_dir=f"{registry_prefix}/ontology/concepts", artifact_type="concept_def_v1", payload=_manifest("concept_def_v1"))
    kroot = _write_hashed_json(root=stage_root, rel_dir=f"{registry_prefix}/manifests", artifact_type="strategy_vm_manifest_v1", payload=_manifest("strategy_vm_manifest_v1"))
    croot = _write_hashed_bin(root=stage_root, rel_dir=f"{registry_prefix}/capsules", artifact_type="urc_capsule_v1", data=b"\x00" * 16)
    mroot = _write_hashed_json(root=stage_root, rel_dir=f"{registry_prefix}/memory/compaction", artifact_type="memory_compaction_receipt_v1", payload=_manifest("memory_compaction_receipt_v1"))
    iroot = _write_hashed_json(root=stage_root, rel_dir=f"{registry_prefix}/manifests", artifact_type="ml_index_manifest_v1", payload=_manifest("ml_index_manifest_v1"))
    wroot = _write_hashed_json(root=stage_root, rel_dir=f"{registry_prefix}/weights", artifact_type="weights_manifest_v1", payload=_manifest("weights_manifest_v1"))
    stability_gate_bundle = _write_hashed_json(root=stage_root, rel_dir=f"{registry_prefix}/gates", artifact_type="stability_metrics_v1", payload=_manifest("stability_metrics_v1"))
    determinism_cert = _write_hashed_json(root=stage_root, rel_dir=f"{registry_prefix}/certs", artifact_type="determinism_cert_v1", payload=_manifest("determinism_cert_v1"))
    universality_cert = _write_hashed_json(root=stage_root, rel_dir=f"{registry_prefix}/certs", artifact_type="universality_cert_v1", payload=_manifest("universality_cert_v1"))

    # Root tuple requires a DMPL droot reference. Vision Stage-0 campaigns do
    # not run DMPL replay, so we emit a minimal schema-valid stub.
    zero_sha = "sha256:" + ("00" * 32)
    droot_payload = {
        "schema_id": "dmpl_droot_v1",
        "dc1_id": "dc1:q32_v1",
        "opset_id": opset_id,
        "dmpl_config_id": zero_sha,
        "froot": zero_sha,
        "vroot": zero_sha,
        "caps_digest": zero_sha,
        "opset_semantics_id": opset_id,
    }
    try:
        validate_schema(droot_payload, "dmpl_droot_v1")
    except Exception:  # noqa: BLE001
        fail("SCHEMA_FAIL")
    droot = _write_hashed_json(root=stage_root, rel_dir=f"{registry_prefix}/dmpl/roots", artifact_type="dmpl_droot_v1", payload=droot_payload)

    root_tuple_payload = {
        "schema_id": "eudrs_u_root_tuple_v1",
        "epoch_u64": int(epoch_u64),
        "dc1_id": "dc1:q32_v1",
        "opset_id": opset_id,
        "sroot": sroot,
        "oroot": oroot,
        "kroot": kroot,
        "croot": croot,
        "droot": droot,
        "mroot": mroot,
        "iroot": iroot,
        "wroot": wroot,
        "stability_gate_bundle": stability_gate_bundle,
        "determinism_cert": determinism_cert,
        "universality_cert": universality_cert,
    }
    try:
        validate_schema(root_tuple_payload, "eudrs_u_root_tuple_v1")
    except Exception:  # noqa: BLE001
        fail("SCHEMA_FAIL")
    root_tuple_ref = _write_hashed_json(
        root=stage_root,
        rel_dir=f"{registry_prefix}/roots",
        artifact_type="eudrs_u_root_tuple_v1",
        payload=root_tuple_payload,
    )

    active_pointer_payload = {
        "schema_id": "active_root_tuple_ref_v1",
        "active_root_tuple": {"artifact_id": root_tuple_ref["artifact_id"], "artifact_relpath": root_tuple_ref["artifact_relpath"]},
    }
    # Promotion verifier expects the staged active pointer at a fixed (non-hashed) relpath.
    active_pointer_path = stage_root / f"{registry_prefix}/active/active_root_tuple_ref_v1.json"
    active_pointer_path.parent.mkdir(parents=True, exist_ok=True)
    active_pointer_path.write_bytes(gcj1_canon_bytes(active_pointer_payload))

    # Promotion summary (required entrypoint).
    summary_payload = {
        "schema_id": "eudrs_u_promotion_summary_v1",
        "proposed_root_tuple_ref": {
            "artifact_id": root_tuple_ref["artifact_id"],
            "artifact_relpath": f"eudrs_u/staged_registry_tree/{root_tuple_ref['artifact_relpath']}",
        },
        "staged_registry_tree_relpath": "eudrs_u/staged_registry_tree",
        "evidence": {
            "weights_manifest_ref": weights_ref,
            "ml_index_manifest_ref": ml_index_ref,
            "cac_ref": cac_ref,
            "ufc_ref": ufc_ref,
            "cooldown_ledger_ref": cooldown_ref,
            "stability_metrics_ref": stability_ref,
            "determinism_cert_ref": det_cert_ref,
            "universality_cert_ref": uni_cert_ref,
            "vision_ingest_run_manifest_ref": {
                "artifact_id": ingest_run_manifest_ref["artifact_id"],
                "artifact_relpath": f"eudrs_u/staged_registry_tree/{ingest_run_manifest_ref['artifact_relpath']}",
            },
            "vision_stage0_verify_receipt_ref": {
                "artifact_id": stage0_receipt_ref["artifact_id"],
                "artifact_relpath": f"eudrs_u/staged_registry_tree/{stage0_receipt_ref['artifact_relpath']}",
            },
        },
    }
    require_no_absolute_paths(summary_payload)
    (state_dir / evidence_dir_rel).mkdir(parents=True, exist_ok=True)
    (state_dir / evidence_dir_rel / "eudrs_u_promotion_summary_v1.json").write_bytes(gcj1_canon_bytes(summary_payload))

    return {
        "status": "OK",
        "vision_ingest_run_manifest_id": ingest_run_manifest_ref["artifact_id"],
        "vision_stage0_receipt_id": stage0_receipt_ref["artifact_id"],
    }


def _load_pack(path: Path) -> dict[str, Any]:
    obj = gcj1_loads_strict(path.read_bytes())
    if not isinstance(obj, dict):
        fail("SCHEMA_FAIL")
    require_no_absolute_paths(obj)
    return dict(obj)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog=_CAMPAIGN_ID)
    parser.add_argument("--campaign_pack", required=True)
    parser.add_argument("--out_dir", required=True)
    parser.add_argument("--capture_config_path", required=True)
    parser.add_argument("--session_name", required=True)
    parser.add_argument("--input_frames_dir", required=True)
    args = parser.parse_args(argv)

    out_dir = Path(args.out_dir).resolve()
    _load_pack(Path(args.campaign_pack).resolve())

    state_dir = (out_dir / "daemon" / _CAMPAIGN_ID / "state").resolve()
    _emit(
        state_dir,
        capture_config_path=Path(args.capture_config_path),
        session_name=str(args.session_name),
        input_frames_dir=Path(args.input_frames_dir),
    )
    sys.stdout.write("OK\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
