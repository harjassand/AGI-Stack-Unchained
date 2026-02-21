from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from cdel.v19_0.epistemic.type_registry_v1 import validate_registry_transition
from tools.omega.epistemics.common_v1 import hash_file
from tools.omega.epistemics.re0_capture_audio_window_v1 import run as run_audio_window
from tools.omega.epistemics.re0_capture_camera_live_v1 import run as run_camera_live
from tools.omega.epistemics.re0_capture_video_pinned_decode_v1 import run as run_video_decode
from tools.omega.epistemics.re0_capture_vision_fixed_cadence_v1 import run as run_vision_capture
from tools.omega.epistemics.re0_chunk_bytestream_rabin_v1 import run as run_rabin
from tools.omega.epistemics.re0_fetch_web_live_v1 import run as run_fetch_web_live
from tools.omega.epistemics.re0_segment_html_live_v1 import run as run_segment_html_live


Q32_ONE = 1 << 32


def _canon(obj: dict) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _h(obj: dict) -> str:
    return "sha256:" + hashlib.sha256(_canon(obj)).hexdigest()


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canon(payload) + b"\n")


def _fetch_contract(path: Path) -> dict:
    payload = {
        "schema_version": "epistemic_fetch_contract_v1",
        "fetch_contract_id": "sha256:" + ("0" * 64),
        "nonce_mode": "DETERMINISTIC_FROM_BYTES",
        "timeout_ms_u32": 1000,
        "user_agent": "fixture-agent",
        "header_allowlist": ["content-type", "etag", "last-modified"],
    }
    payload["fetch_contract_id"] = _h({k: v for k, v in payload.items() if k != "fetch_contract_id"})
    _write(path, payload)
    return payload


def _segment_contract(path: Path, *, impl_rel: str, impl_sha: str, max_segment_len_u32: int = 64) -> dict:
    payload = {
        "schema_version": "epistemic_segment_contract_v1",
        "segment_contract_id": "sha256:" + ("0" * 64),
        "parser_family": "HTML_READER",
        "parser_version_pin": "v1-fixture",
        "segmenter_impl_relpath": impl_rel,
        "segmenter_impl_sha256": impl_sha,
        "algorithm_id": "HTML_SENTENCE_SPLIT_V1",
        "ordering_rule": "INPUT_BLOB_ID_ASC",
        "max_segment_len_u32": int(max_segment_len_u32),
    }
    payload["segment_contract_id"] = _h({k: v for k, v in payload.items() if k != "segment_contract_id"})
    _write(path, payload)
    return payload


def _vision_chunk_contract(path: Path, *, source_kind: str) -> dict:
    payload = {
        "schema_version": "epistemic_chunk_contract_v1",
        "chunk_contract_id": "sha256:" + ("0" * 64),
        "sensor_kind": "VISION_FRAME",
        "source_kind": source_kind,
        "cadence_frames_u64": 1,
        "ordering_rule": "LEXICOGRAPHIC_PATH_ASC",
        "decoder_contract_id": _h({"k": "decoder"}),
        "max_frames_u64": 8,
    }
    payload["chunk_contract_id"] = _h({k: v for k, v in payload.items() if k != "chunk_contract_id"})
    _write(path, payload)
    return payload


def _audio_chunk_contract(path: Path) -> dict:
    payload = {
        "schema_version": "epistemic_chunk_contract_v1",
        "chunk_contract_id": "sha256:" + ("0" * 64),
        "sensor_kind": "AUDIO_WINDOW",
        "source_kind": "AUDIO_FILE",
        "ordering_rule": "INDEX_ASC",
        "audio_window_ms_u32": 10,
        "audio_overlap_ms_u32": 5,
        "audio_decode_contract_id": _h({"k": "audio_decode"}),
    }
    payload["chunk_contract_id"] = _h({k: v for k, v in payload.items() if k != "chunk_contract_id"})
    _write(path, payload)
    return payload


def _rabin_chunk_contract(path: Path) -> dict:
    payload = {
        "schema_version": "epistemic_chunk_contract_v1",
        "chunk_contract_id": "sha256:" + ("0" * 64),
        "sensor_kind": "BYTE_STREAM_RABIN",
        "source_kind": "BYTE_STREAM_FILE",
        "ordering_rule": "RABIN_BOUNDARY_ASC",
        "rabin_polynomial_u64": 257,
        "rabin_window_bytes_u32": 16,
        "rabin_mask_u64": 1023,
        "min_chunk_bytes_u32": 32,
        "max_chunk_bytes_u32": 128,
    }
    payload["chunk_contract_id"] = _h({k: v for k, v in payload.items() if k != "chunk_contract_id"})
    _write(path, payload)
    return payload


def _decoder_contract(path: Path, *, ffmpeg_path: Path, ffmpeg_sha: str, threads_u32: int = 1) -> dict:
    payload = {
        "schema_version": "epistemic_decoder_contract_v1",
        "decoder_contract_id": "sha256:" + ("0" * 64),
        "ffmpeg_exe_path": str(ffmpeg_path),
        "ffmpeg_exe_sha256": ffmpeg_sha,
        "threads_u32": int(threads_u32),
        "hwaccel_mode": "none",
        "pixel_format": "rgb24",
        "vf_filter": "scale=2:2",
        "frame_selection_mode": "FRAME_INDEX_STRIDE",
        "frame_stride_u32": 1,
    }
    payload["decoder_contract_id"] = _h({k: v for k, v in payload.items() if k != "decoder_contract_id"})
    _write(path, payload)
    return payload


def _fake_ffmpeg(path: Path) -> None:
    code = '''#!/usr/bin/env python3
import os
import sys
from pathlib import Path

out_pattern = sys.argv[-1]
if "%010d" not in out_pattern:
    raise SystemExit(2)
base = b"frame"
if os.environ.get("FAKE_FFMPEG_NONDET") == "1":
    base = ("frame-" + str(os.getpid())).encode("utf-8")
for i in range(1, 4):
    out = Path(out_pattern.replace("%010d", f"{i:010d}"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(base + b"-" + str(i).encode("ascii"))
raise SystemExit(0)
'''
    path.write_text(code, encoding="utf-8")
    path.chmod(0o755)


def _registry(*, epoch: int, parent: str | None, allowed: list[str], defs: dict[str, str]) -> dict:
    payload = {
        "schema_version": "epistemic_type_registry_v1",
        "registry_id": "sha256:" + ("0" * 64),
        "registry_epoch_u64": int(epoch),
        "parent_registry_id": parent,
        "evolution_rule": "APPEND_ONLY",
        "provisional_namespace_prefix": "PROVISIONAL/",
        "allowed_type_ids": list(allowed),
        "type_definitions": dict(defs),
    }
    payload["registry_id"] = _h({k: v for k, v in payload.items() if k != "registry_id"})
    return payload


def test_fetch_live_fixture_backed_deterministic(tmp_path: Path) -> None:
    outbox_root = tmp_path / ".omega_cache" / "epistemic_outbox"
    contract = _fetch_contract(tmp_path / "fetch_contract.json")
    body = b"<html><body>fixture-live-web</body></html>"
    body_path = tmp_path / "body.bin"
    body_path.write_bytes(body)
    headers_path = tmp_path / "headers.json"
    _write(headers_path, {"content-type": "text/html", "etag": "abc"})

    episode_id = _h({"episode": "fetch"})
    a = run_fetch_web_live(
        url="https://fixture.example/x",
        outbox_root=outbox_root,
        episode_id=episode_id,
        fetch_contract_path=tmp_path / "fetch_contract.json",
        fixture_body_path=body_path,
        fixture_headers_path=headers_path,
        fixture_status_code=200,
    )
    b = run_fetch_web_live(
        url="https://fixture.example/x",
        outbox_root=outbox_root,
        episode_id=episode_id,
        fetch_contract_path=tmp_path / "fetch_contract.json",
        fixture_body_path=body_path,
        fixture_headers_path=headers_path,
        fixture_status_code=200,
    )
    assert a["raw_blob_id"] == b["raw_blob_id"]
    assert a["fetch_receipt_id"] == b["fetch_receipt_id"]
    assert a["fetch_contract_id"] == str(contract["fetch_contract_id"])


def test_segmenter_impl_hash_enforced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    outbox_root = tmp_path / ".omega_cache" / "epistemic_outbox"
    raw = b"<html><body><p>alpha.</p><p>beta!</p></body></html>"
    raw_blob_id = "sha256:" + hashlib.sha256(raw).hexdigest()
    raw_path = outbox_root / "blobs" / "sha256" / raw_blob_id.split(":", 1)[1]
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_bytes(raw)

    impl = tmp_path / "impl.py"
    impl.write_text("# segmenter impl fixture\n", encoding="utf-8")
    contract = _segment_contract(
        tmp_path / "segment_contract.json",
        impl_rel="impl.py",
        impl_sha=hash_file(impl),
    )

    episode_id = _h({"episode": "segment"})
    a = run_segment_html_live(
        outbox_root=outbox_root,
        episode_id=episode_id,
        input_blob_ids=[raw_blob_id],
        segment_contract_path=tmp_path / "segment_contract.json",
    )
    b = run_segment_html_live(
        outbox_root=outbox_root,
        episode_id=episode_id,
        input_blob_ids=[raw_blob_id],
        segment_contract_path=tmp_path / "segment_contract.json",
    )
    assert a["segment_receipt_id"] == b["segment_receipt_id"]
    assert a["output_blob_ids"] == b["output_blob_ids"]
    assert a["segment_contract_id"] == str(contract["segment_contract_id"])

    bad_contract = _segment_contract(
        tmp_path / "segment_contract_bad.json",
        impl_rel="impl.py",
        impl_sha="sha256:" + ("0" * 64),
    )
    assert bad_contract["segmenter_impl_sha256"] != contract["segmenter_impl_sha256"]
    with pytest.raises(Exception, match="PIN_HASH_MISMATCH"):
        run_segment_html_live(
            outbox_root=outbox_root,
            episode_id=episode_id,
            input_blob_ids=[raw_blob_id],
            segment_contract_path=tmp_path / "segment_contract_bad.json",
        )


def test_decoder_pin_and_repro_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    outbox_root = tmp_path / ".omega_cache" / "epistemic_outbox"
    video_path = tmp_path / "video.bin"
    video_path.write_bytes(b"fixture-video")
    ffmpeg = tmp_path / "fake_ffmpeg.py"
    _fake_ffmpeg(ffmpeg)
    exe_sha = hash_file(ffmpeg)

    _decoder_contract(tmp_path / "decoder_contract.json", ffmpeg_path=ffmpeg, ffmpeg_sha=exe_sha)
    episode_id = _h({"episode": "video"})
    fetch_contract_id = _h({"fetch": 1})

    ok = run_video_decode(
        outbox_root=outbox_root,
        episode_id=episode_id,
        video_path=video_path,
        decoder_contract_path=tmp_path / "decoder_contract.json",
        fetch_contract_id=fetch_contract_id,
    )
    assert ok["raw_blob_ids"]
    assert str(ok["decoder_repro_receipt_id"]).startswith("sha256:")

    _decoder_contract(
        tmp_path / "decoder_contract_bad_hash.json",
        ffmpeg_path=ffmpeg,
        ffmpeg_sha="sha256:" + ("f" * 64),
    )
    with pytest.raises(Exception, match="PIN_HASH_MISMATCH"):
        run_video_decode(
            outbox_root=outbox_root,
            episode_id=episode_id,
            video_path=video_path,
            decoder_contract_path=tmp_path / "decoder_contract_bad_hash.json",
            fetch_contract_id=fetch_contract_id,
        )

    _decoder_contract(
        tmp_path / "decoder_contract_bad_args.json",
        ffmpeg_path=ffmpeg,
        ffmpeg_sha=exe_sha,
        threads_u32=2,
    )
    with pytest.raises(Exception, match="DECODE_ARGS_MISMATCH"):
        run_video_decode(
            outbox_root=outbox_root,
            episode_id=episode_id,
            video_path=video_path,
            decoder_contract_path=tmp_path / "decoder_contract_bad_args.json",
            fetch_contract_id=fetch_contract_id,
        )

    monkeypatch.setenv("FAKE_FFMPEG_NONDET", "1")
    with pytest.raises(Exception, match="DECODER_REPRO_FAIL"):
        run_video_decode(
            outbox_root=outbox_root,
            episode_id=episode_id,
            video_path=video_path,
            decoder_contract_path=tmp_path / "decoder_contract.json",
            fetch_contract_id=fetch_contract_id,
        )


def test_video_capture_requires_pinned_decoder_contract(tmp_path: Path) -> None:
    outbox_root = tmp_path / ".omega_cache" / "epistemic_outbox"
    contract_path = tmp_path / "vision_chunk.json"
    _vision_chunk_contract(contract_path, source_kind="VIDEO_FILE")
    episode_id = _h({"episode": "vision-video"})
    with pytest.raises(Exception, match="VIDEO_SOURCE_DISABLED_UNTIL_DECODE_CONTRACT"):
        run_vision_capture(
            outbox_root=outbox_root,
            episode_id=episode_id,
            chunk_contract_path=contract_path,
            source_kind="VIDEO_FILE",
            input_glob=None,
            video_path=tmp_path / "video.bin",
            decoder_contract_path=None,
            fetch_contract_id=_h({"fetch": "vision-video"}),
            capture_nonce_u64=0,
        )


def test_camera_audio_rabin_fixture_determinism(tmp_path: Path) -> None:
    outbox_root = tmp_path / ".omega_cache" / "epistemic_outbox"
    fetch_contract_id = _h({"fetch": "fixtures"})

    frames_dir = tmp_path / "camera"
    frames_dir.mkdir(parents=True, exist_ok=True)
    for i in range(4):
        (frames_dir / f"{i:04d}.bin").write_bytes(f"frame-{i}".encode("utf-8"))
    cam_contract = _vision_chunk_contract(tmp_path / "camera_chunk.json", source_kind="LIVE_CAMERA")
    cam_ep = _h({"episode": "camera"})
    cam_a = run_camera_live(
        outbox_root=outbox_root,
        episode_id=cam_ep,
        chunk_contract_path=tmp_path / "camera_chunk.json",
        frame_glob=str(frames_dir / "*.bin"),
        fetch_contract_id=fetch_contract_id,
    )
    cam_b = run_camera_live(
        outbox_root=outbox_root,
        episode_id=cam_ep,
        chunk_contract_path=tmp_path / "camera_chunk.json",
        frame_glob=str(frames_dir / "*.bin"),
        fetch_contract_id=fetch_contract_id,
    )
    assert cam_a["raw_blob_ids"] == cam_b["raw_blob_ids"]
    assert cam_a["fetch_receipt_ids"] == cam_b["fetch_receipt_ids"]
    assert cam_a["chunk_contract_id"] == str(cam_contract["chunk_contract_id"])

    audio_contract = _audio_chunk_contract(tmp_path / "audio_chunk.json")
    audio_path = tmp_path / "audio.pcm"
    audio_path.write_bytes((b"\x01\x02" * 4096))
    audio_ep = _h({"episode": "audio"})
    aud_a = run_audio_window(
        outbox_root=outbox_root,
        episode_id=audio_ep,
        chunk_contract_path=tmp_path / "audio_chunk.json",
        audio_path=audio_path,
        fetch_contract_id=fetch_contract_id,
    )
    aud_b = run_audio_window(
        outbox_root=outbox_root,
        episode_id=audio_ep,
        chunk_contract_path=tmp_path / "audio_chunk.json",
        audio_path=audio_path,
        fetch_contract_id=fetch_contract_id,
    )
    assert aud_a["pinset_id"] == aud_b["pinset_id"]
    assert aud_a["raw_blob_ids"] == aud_b["raw_blob_ids"]
    assert aud_a["chunk_contract_id"] == str(audio_contract["chunk_contract_id"])

    rabin_contract = _rabin_chunk_contract(tmp_path / "rabin_chunk.json")
    stream_path = tmp_path / "stream.bin"
    stream_path.write_bytes((b"0123456789abcdef" * 64))
    rabin_ep = _h({"episode": "rabin"})
    rab_a = run_rabin(
        outbox_root=outbox_root,
        episode_id=rabin_ep,
        chunk_contract_path=tmp_path / "rabin_chunk.json",
        input_path=stream_path,
    )
    rab_b = run_rabin(
        outbox_root=outbox_root,
        episode_id=rabin_ep,
        chunk_contract_path=tmp_path / "rabin_chunk.json",
        input_path=stream_path,
    )
    assert rab_a["pinset_id"] == rab_b["pinset_id"]
    assert rab_a["raw_blob_ids"] == rab_b["raw_blob_ids"]
    assert rab_a["chunk_contract_id"] == str(rabin_contract["chunk_contract_id"])


def test_type_registry_append_only_transition_rules() -> None:
    claim_def = _h({"type": "CLAIM", "v": 1})
    novel_def = _h({"type": "NOVEL", "v": 1})
    parent = _registry(
        epoch=1,
        parent=None,
        allowed=["CLAIM"],
        defs={"CLAIM": claim_def},
    )
    child = _registry(
        epoch=2,
        parent=str(parent["registry_id"]),
        allowed=["CLAIM", "NOVEL"],
        defs={"CLAIM": claim_def, "NOVEL": novel_def},
    )
    ok = validate_registry_transition(parent=parent, child=child)
    assert ok["legacy_registry_b"] is False

    bad_delete = _registry(
        epoch=2,
        parent=str(parent["registry_id"]),
        allowed=["NOVEL"],
        defs={"NOVEL": novel_def},
    )
    with pytest.raises(Exception):
        validate_registry_transition(parent=parent, child=bad_delete)

    bad_mutate = _registry(
        epoch=2,
        parent=str(parent["registry_id"]),
        allowed=["CLAIM", "NOVEL"],
        defs={"CLAIM": _h({"type": "CLAIM", "v": 2}), "NOVEL": novel_def},
    )
    with pytest.raises(Exception):
        validate_registry_transition(parent=parent, child=bad_mutate)
