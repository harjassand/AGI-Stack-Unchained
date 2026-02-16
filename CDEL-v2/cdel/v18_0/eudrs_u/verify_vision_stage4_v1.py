"""RE2 authoritative verifier for Vision Stage 4 (world model + DMPL integration, v1)."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..omega_common_v1 import OmegaV18Error, fail, require_no_absolute_paths, validate_schema
from .dmpl_train_trace_v1 import parse_lenpref_canonjson_stream_v1
from .dmpl_types_v1 import DMPLError
from .eudrs_u_artifact_refs_v1 import require_artifact_ref_v1, require_safe_relpath_v1, verify_artifact_ref_v1
from .eudrs_u_common_v1 import EUDRS_U_EVIDENCE_DIR_REL
from .eudrs_u_hash_v1 import gcj1_canon_bytes, gcj1_loads_and_verify_canonical, sha256_prefixed
from .verify_dmpl_certificates_v1 import _compute_holdout_mean_L1_pred_q32
from .verify_dmpl_train_replay_v1 import verify_dmpl_train_replay_v1
from .vision_state_to_dmpl_z_v1 import vision_state_to_dmpl_tensor_bytes_v1

REASON_VISION4_SCHEMA_INVALID = "EUDRSU_VISION4_SCHEMA_INVALID"
REASON_VISION4_BINDING_MISMATCH = "EUDRSU_VISION4_BINDING_MISMATCH"
REASON_VISION4_DMPL_REPLAY_FAIL = "EUDRSU_VISION4_DMPL_REPLAY_FAIL"
REASON_VISION4_THRESHOLD_FAIL = "EUDRSU_VISION4_THRESHOLD_FAIL"


class _Stage4Resolver:
    def __init__(self, *, state_root: Path, staged_root: Path) -> None:
        self.state_root = Path(state_root).resolve()
        self.roots = [
            Path(staged_root).resolve(),
            (Path(state_root).resolve() / EUDRS_U_EVIDENCE_DIR_REL).resolve(),
            Path(state_root).resolve(),
        ]

    def load_artifact_ref_bytes(self, artifact_ref: dict[str, Any], *, expected_relpath_prefix: str | None = None) -> bytes:
        ref = require_artifact_ref_v1(artifact_ref, reason=REASON_VISION4_SCHEMA_INVALID)
        p = verify_artifact_ref_v1(artifact_ref=ref, base_dir=self.state_root, expected_relpath_prefix=expected_relpath_prefix)
        return p.read_bytes()

    def load_artifact_bytes(self, *, artifact_id: str, artifact_type: str, ext: str) -> bytes:
        aid = str(artifact_id).strip()
        at = str(artifact_type).strip()
        ex = str(ext).strip()
        if not aid.startswith("sha256:") or len(aid) != len("sha256:") + 64:
            raise DMPLError(reason_code=REASON_VISION4_SCHEMA_INVALID, details={"artifact_id": aid})
        if ex not in {"json", "bin"} or not at:
            raise DMPLError(reason_code=REASON_VISION4_SCHEMA_INVALID, details={"artifact_type": at, "ext": ex})

        hex64 = aid.split(":", 1)[1]
        filename = f"sha256_{hex64}.{at}.{ex}"
        matches: list[Path] = []
        for root in self.roots:
            if root.exists() and root.is_dir():
                matches.extend([p for p in root.rglob(filename) if p.is_file()])
        matches = sorted(set(matches), key=lambda p: p.as_posix())
        if not matches:
            raise DMPLError(reason_code=REASON_VISION4_SCHEMA_INVALID, details={"missing": filename})

        raw0 = matches[0].read_bytes()
        if sha256_prefixed(raw0) != aid:
            raise DMPLError(reason_code=REASON_VISION4_SCHEMA_INVALID, details={"hash_mismatch": filename})
        for p in matches[1:]:
            raw = p.read_bytes()
            if sha256_prefixed(raw) != aid or raw != raw0:
                raise DMPLError(reason_code=REASON_VISION4_SCHEMA_INVALID, details={"duplicate_mismatch": filename})
        return raw0


@dataclass(frozen=True, slots=True)
class _Stage1TransitionV1:
    episode_id: str
    t_u32: int
    start_state_id: str
    state_t_bytes: bytes
    state_tp1_bytes: bytes


def _load_json_obj(path: Path, *, schema_id: str, reason: str) -> dict[str, Any]:
    raw = path.read_bytes()
    obj = gcj1_loads_and_verify_canonical(raw)
    if not isinstance(obj, dict):
        fail(reason)
    require_no_absolute_paths(obj)
    if str(obj.get("schema_id", "")).strip() != schema_id:
        fail(reason)
    try:
        validate_schema(obj, schema_id)
    except Exception:  # noqa: BLE001
        fail(reason)
    return dict(obj)


def _load_canon_json_obj(path: Path, *, reason: str) -> dict[str, Any]:
    raw = path.read_bytes()
    obj = gcj1_loads_and_verify_canonical(raw)
    if not isinstance(obj, dict):
        fail(reason)
    require_no_absolute_paths(obj)
    return dict(obj)


def _q32(value: Any, *, reason: str) -> int:
    if not isinstance(value, dict) or set(value.keys()) != {"q"}:
        fail(reason)
    q = value.get("q")
    if not isinstance(q, int):
        fail(reason)
    return int(q)


def _resolve_state_roots(state_dir: Path) -> tuple[Path, Path]:
    state_root = Path(state_dir).resolve()
    if not state_root.exists() or not state_root.is_dir():
        fail("MISSING_STATE_INPUT")
    staged = state_root / "eudrs_u" / "staged_registry_tree"
    if staged.exists() and staged.is_dir():
        return state_root, staged.resolve()
    return state_root, state_root


def _resolve_relpath_in_state(*, state_root: Path, staged_root: Path, relpath: str) -> Path:
    s = require_safe_relpath_v1(str(relpath), reason=REASON_VISION4_SCHEMA_INVALID)
    p = (staged_root / s).resolve()
    if not p.exists() or not p.is_file():
        p = (state_root / s).resolve()
    try:
        _ = p.relative_to(state_root)
    except Exception:
        fail(REASON_VISION4_SCHEMA_INVALID)
    if not p.exists() or not p.is_file():
        fail("MISSING_STATE_INPUT")
    return p


def _rel_ref_under_state(state_root: Path, path: Path) -> dict[str, str]:
    p = Path(path).resolve()
    try:
        rel = p.relative_to(state_root.resolve()).as_posix()
    except Exception:
        fail(REASON_VISION4_SCHEMA_INVALID)
    raw = p.read_bytes()
    return {"artifact_id": sha256_prefixed(raw), "artifact_relpath": rel}


def _find_single_json_by_schema_id(*, directory: Path, schema_id: str) -> tuple[Path, dict[str, Any]] | None:
    matches: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(Path(directory).glob("*.json"), key=lambda p: p.as_posix()):
        try:
            obj = gcj1_loads_and_verify_canonical(path.read_bytes())
        except Exception:  # noqa: BLE001
            continue
        if isinstance(obj, dict) and str(obj.get("schema_id", "")).strip() == str(schema_id):
            matches.append((path.resolve(), dict(obj)))
    if not matches:
        return None
    if len(matches) != 1:
        fail(REASON_VISION4_BINDING_MISMATCH)
    return matches[0]


def _verify_system_manifest_bindings_from_summary(
    *,
    state_root: Path,
    staged_root: Path,
    qxrl_model_ref_cli: dict[str, str],
    wroot_ref_cli: dict[str, str],
    world_model_ref_cli: dict[str, str],
    eval_manifest_ref_cli: dict[str, str],
) -> None:
    evidence_dir = Path(state_root).resolve() / EUDRS_U_EVIDENCE_DIR_REL
    summary_match = _find_single_json_by_schema_id(directory=evidence_dir, schema_id="eudrs_u_promotion_summary_v1")
    if summary_match is None:
        fail(REASON_VISION4_BINDING_MISMATCH)
    _summary_path, summary_obj = summary_match
    proposed_ref = require_artifact_ref_v1(summary_obj.get("proposed_root_tuple_ref"), reason=REASON_VISION4_BINDING_MISMATCH)
    root_path = verify_artifact_ref_v1(
        artifact_ref=proposed_ref,
        base_dir=state_root,
        expected_relpath_prefix="eudrs_u/staged_registry_tree/polymath/registry/eudrs_u/roots/",
    )
    root_obj = gcj1_loads_and_verify_canonical(root_path.read_bytes())
    if not isinstance(root_obj, dict):
        fail(REASON_VISION4_BINDING_MISMATCH)
    require_no_absolute_paths(root_obj)

    wroot_ref = require_artifact_ref_v1(root_obj.get("wroot"), reason=REASON_VISION4_BINDING_MISMATCH)
    if str(wroot_ref.get("artifact_id", "")).strip() != str(wroot_ref_cli.get("artifact_id", "")).strip():
        fail(REASON_VISION4_BINDING_MISMATCH)

    sroot_ref = require_artifact_ref_v1(root_obj.get("sroot"), reason=REASON_VISION4_BINDING_MISMATCH)
    sroot_path = verify_artifact_ref_v1(
        artifact_ref=sroot_ref,
        base_dir=staged_root,
        expected_relpath_prefix="polymath/registry/eudrs_u/",
    )
    system_obj = gcj1_loads_and_verify_canonical(sroot_path.read_bytes())
    if not isinstance(system_obj, dict):
        fail(REASON_VISION4_BINDING_MISMATCH)
    require_no_absolute_paths(system_obj)

    qxrl_bind = system_obj.get("qxrl")
    qxwmr_bind = system_obj.get("qxwmr")
    if not isinstance(qxrl_bind, dict) or not isinstance(qxwmr_bind, dict):
        fail(REASON_VISION4_BINDING_MISMATCH)

    model_ref = require_artifact_ref_v1(qxrl_bind.get("model_manifest_ref"), reason=REASON_VISION4_BINDING_MISMATCH)
    if str(model_ref.get("artifact_id", "")).strip() != str(qxrl_model_ref_cli.get("artifact_id", "")).strip():
        fail(REASON_VISION4_BINDING_MISMATCH)

    wm_ref = require_artifact_ref_v1(qxwmr_bind.get("world_model_manifest_ref"), reason=REASON_VISION4_BINDING_MISMATCH)
    ev_ref = require_artifact_ref_v1(qxwmr_bind.get("eval_manifest_ref"), reason=REASON_VISION4_BINDING_MISMATCH)
    if str(wm_ref.get("artifact_id", "")).strip() != str(world_model_ref_cli.get("artifact_id", "")).strip():
        fail(REASON_VISION4_BINDING_MISMATCH)
    if str(ev_ref.get("artifact_id", "")).strip() != str(eval_manifest_ref_cli.get("artifact_id", "")).strip():
        fail(REASON_VISION4_BINDING_MISMATCH)


def _verify_world_model_manifest_bindings(
    *,
    staged_root: Path,
    world_model_obj: dict[str, Any],
    qxrl_model_ref_cli: dict[str, str],
    wroot_ref_cli: dict[str, str],
    suite_ref: dict[str, str],
    eval_manifest_obj: dict[str, Any],
) -> tuple[dict[str, str], dict[str, str], dict[str, str], dict[str, Any]]:
    rep = world_model_obj.get("rep_qxrl")
    dyn = world_model_obj.get("dynamics_dmpl")
    caps = world_model_obj.get("caps")
    if not isinstance(rep, dict) or not isinstance(dyn, dict) or not isinstance(caps, dict):
        fail(REASON_VISION4_BINDING_MISMATCH)

    rep_model_ref = require_artifact_ref_v1(rep.get("model_manifest_ref"), reason=REASON_VISION4_BINDING_MISMATCH)
    rep_wroot_ref = require_artifact_ref_v1(rep.get("wroot_ref"), reason=REASON_VISION4_BINDING_MISMATCH)
    token_adapter_id = str(rep.get("token_adapter_id", "")).strip()
    if not token_adapter_id:
        fail(REASON_VISION4_BINDING_MISMATCH)

    if str(rep_model_ref.get("artifact_id", "")).strip() != str(qxrl_model_ref_cli.get("artifact_id", "")).strip():
        fail(REASON_VISION4_BINDING_MISMATCH)
    if str(rep_wroot_ref.get("artifact_id", "")).strip() != str(wroot_ref_cli.get("artifact_id", "")).strip():
        fail(REASON_VISION4_BINDING_MISMATCH)

    droot_ref = require_artifact_ref_v1(dyn.get("dmpl_droot_ref"), reason=REASON_VISION4_BINDING_MISMATCH)
    cfg_ref = require_artifact_ref_v1(dyn.get("dmpl_config_ref"), reason=REASON_VISION4_BINDING_MISMATCH)
    modelpack_ref = require_artifact_ref_v1(dyn.get("dmpl_modelpack_ref"), reason=REASON_VISION4_BINDING_MISMATCH)

    droot_path = verify_artifact_ref_v1(artifact_ref=droot_ref, base_dir=staged_root, expected_relpath_prefix="polymath/registry/eudrs_u/")
    cfg_path = verify_artifact_ref_v1(artifact_ref=cfg_ref, base_dir=staged_root, expected_relpath_prefix="polymath/registry/eudrs_u/")
    modelpack_path = verify_artifact_ref_v1(artifact_ref=modelpack_ref, base_dir=staged_root, expected_relpath_prefix="polymath/registry/eudrs_u/")

    droot_obj = _load_json_obj(droot_path, schema_id="dmpl_droot_v1", reason=REASON_VISION4_BINDING_MISMATCH)
    cfg_obj = _load_json_obj(cfg_path, schema_id="dmpl_config_v1", reason=REASON_VISION4_BINDING_MISMATCH)
    modelpack_obj = _load_json_obj(modelpack_path, schema_id="dmpl_modelpack_v1", reason=REASON_VISION4_BINDING_MISMATCH)

    if str(droot_obj.get("dmpl_config_id", "")).strip() != str(cfg_ref.get("artifact_id", "")).strip():
        fail(REASON_VISION4_BINDING_MISMATCH)
    if str(cfg_obj.get("active_modelpack_id", "")).strip() != str(modelpack_ref.get("artifact_id", "")).strip():
        fail(REASON_VISION4_BINDING_MISMATCH)

    dims = modelpack_obj.get("dims")
    if not isinstance(dims, dict):
        fail(REASON_VISION4_BINDING_MISMATCH)
    d_u32 = dims.get("d_u32")
    if not isinstance(d_u32, int) or int(d_u32) < 1:
        fail(REASON_VISION4_BINDING_MISMATCH)

    H = caps.get("rollout_H_u32")
    Nmax = caps.get("rollout_Nmax_u32")
    max_abs_z = caps.get("max_abs_z_q32")
    if not isinstance(H, int) or not isinstance(Nmax, int) or H < 0 or Nmax < 0:
        fail(REASON_VISION4_BINDING_MISMATCH)
    max_abs_z_q32 = _q32(max_abs_z, reason=REASON_VISION4_BINDING_MISMATCH)

    cfg_caps = cfg_obj.get("caps")
    if not isinstance(cfg_caps, dict):
        fail(REASON_VISION4_BINDING_MISMATCH)
    if int(H) > int(cfg_caps.get("H_u32", -1)) or int(Nmax) > int(cfg_caps.get("Nmax_u32", -1)):
        fail(REASON_VISION4_BINDING_MISMATCH)

    eval_suite_ref = require_artifact_ref_v1(eval_manifest_obj.get("eval_suite_ref"), reason=REASON_VISION4_BINDING_MISMATCH)
    if str(eval_suite_ref.get("artifact_id", "")).strip() != str(suite_ref.get("artifact_id", "")).strip():
        fail(REASON_VISION4_BINDING_MISMATCH)

    thresholds = eval_manifest_obj.get("thresholds")
    if not isinstance(thresholds, dict):
        fail(REASON_VISION4_BINDING_MISMATCH)
    _ = _q32(thresholds.get("mean_l1_max_q32"), reason=REASON_VISION4_BINDING_MISMATCH)
    _ = _q32(thresholds.get("rollout_drift_max_q32"), reason=REASON_VISION4_BINDING_MISMATCH)
    _ = _q32(thresholds.get("saturation_rate_max_q32"), reason=REASON_VISION4_BINDING_MISMATCH)

    return droot_ref, cfg_ref, modelpack_ref, {
        "token_adapter_id": str(token_adapter_id),
        "max_abs_z_q32": int(max_abs_z_q32),
        "d_u32": int(d_u32),
    }


def _parse_stage1_relpaths_arg(stage1_run_manifest_relpaths: str) -> list[str]:
    raw = str(stage1_run_manifest_relpaths).strip()
    if not raw:
        return []
    parts = [p.strip() for p in raw.replace("\n", ",").split(",")]
    return [p for p in parts if p]


def _load_stage1_run_manifest_paths(
    *,
    state_root: Path,
    staged_root: Path,
    stage1_run_manifest_paths: list[Path] | None,
    vision_transition_listing_path: Path | None,
) -> list[Path]:
    out: list[Path] = []
    for p in list(stage1_run_manifest_paths or []):
        out.append(Path(p).resolve())

    if vision_transition_listing_path is not None:
        listing_obj = gcj1_loads_and_verify_canonical(Path(vision_transition_listing_path).resolve().read_bytes())
        if not isinstance(listing_obj, dict):
            fail(REASON_VISION4_SCHEMA_INVALID)
        require_no_absolute_paths(listing_obj)

        for key in ("run_manifest_relpaths", "stage1_run_manifest_relpaths"):
            rows = listing_obj.get(key)
            if isinstance(rows, list):
                for row in rows:
                    if not isinstance(row, str):
                        fail(REASON_VISION4_SCHEMA_INVALID)
                    out.append(_resolve_relpath_in_state(state_root=state_root, staged_root=staged_root, relpath=str(row)))

        run_manifest_refs = listing_obj.get("run_manifest_refs")
        if isinstance(run_manifest_refs, list):
            for row in run_manifest_refs:
                ref = require_artifact_ref_v1(row, reason=REASON_VISION4_SCHEMA_INVALID)
                out.append(
                    verify_artifact_ref_v1(
                        artifact_ref=ref,
                        base_dir=staged_root,
                        expected_relpath_prefix="polymath/registry/eudrs_u/vision/perception/runs/",
                    )
                )

        runs = listing_obj.get("runs")
        if isinstance(runs, list):
            for row in runs:
                if not isinstance(row, dict):
                    fail(REASON_VISION4_SCHEMA_INVALID)
                rel = row.get("run_manifest_relpath")
                if isinstance(rel, str):
                    out.append(_resolve_relpath_in_state(state_root=state_root, staged_root=staged_root, relpath=str(rel)))
                ref_obj = row.get("run_manifest_ref")
                if isinstance(ref_obj, dict):
                    ref = require_artifact_ref_v1(ref_obj, reason=REASON_VISION4_SCHEMA_INVALID)
                    out.append(
                        verify_artifact_ref_v1(
                            artifact_ref=ref,
                            base_dir=staged_root,
                            expected_relpath_prefix="polymath/registry/eudrs_u/vision/perception/runs/",
                        )
                    )

    uniq = sorted({p.resolve() for p in out}, key=lambda p: p.as_posix())
    for p in uniq:
        _ = _load_json_obj(p, schema_id="vision_perception_run_manifest_v1", reason=REASON_VISION4_SCHEMA_INVALID)
    return uniq


def _collect_stage1_transitions(
    *,
    run_manifest_paths: list[Path],
    staged_root: Path,
    sample_stride_u32: int,
    max_transitions_u64: int,
) -> list[_Stage1TransitionV1]:
    stride = int(sample_stride_u32)
    max_transitions = int(max_transitions_u64)
    if stride < 1 or max_transitions < 1:
        fail(REASON_VISION4_SCHEMA_INVALID)

    transitions: list[_Stage1TransitionV1] = []
    for run_path in sorted(list(run_manifest_paths), key=lambda p: p.as_posix()):
        run_raw = run_path.read_bytes()
        run_id = sha256_prefixed(run_raw)
        run_obj = _load_json_obj(run_path, schema_id="vision_perception_run_manifest_v1", reason=REASON_VISION4_SCHEMA_INVALID)
        states_raw = run_obj.get("qxwmr_states")
        if not isinstance(states_raw, list):
            fail(REASON_VISION4_SCHEMA_INVALID)

        states_rows: list[tuple[int, dict[str, Any], bytes]] = []
        prev_idx: int | None = None
        for row in sorted(list(states_raw), key=lambda r: int(r.get("frame_index_u32", -1)) if isinstance(r, dict) else -1):
            if not isinstance(row, dict):
                fail(REASON_VISION4_SCHEMA_INVALID)
            frame_idx = row.get("frame_index_u32")
            if not isinstance(frame_idx, int) or frame_idx < 0 or frame_idx > 0xFFFFFFFF:
                fail(REASON_VISION4_SCHEMA_INVALID)
            if prev_idx is not None and int(frame_idx) <= int(prev_idx):
                fail(REASON_VISION4_SCHEMA_INVALID)
            prev_idx = int(frame_idx)
            state_ref = require_artifact_ref_v1(row.get("state_ref"), reason=REASON_VISION4_SCHEMA_INVALID)
            state_path = verify_artifact_ref_v1(
                artifact_ref=state_ref,
                base_dir=staged_root,
                expected_relpath_prefix="polymath/registry/eudrs_u/vision/perception/qxwmr_states/",
            )
            states_rows.append((int(frame_idx), dict(state_ref), state_path.read_bytes()))

        for i in range(0, max(0, len(states_rows) - 1), stride):
            frame_idx, state_ref, s_t = states_rows[i]
            _next_idx, _next_ref, s_tp1 = states_rows[i + 1]
            transitions.append(
                _Stage1TransitionV1(
                    episode_id=str(run_id),
                    t_u32=int(frame_idx),
                    start_state_id=str(state_ref.get("artifact_id", "")),
                    state_t_bytes=bytes(s_t),
                    state_tp1_bytes=bytes(s_tp1),
                )
            )

    transitions.sort(key=lambda r: (str(r.episode_id), int(r.t_u32)))
    return transitions[:max_transitions]


def _load_dataset_samples_from_pack(*, dataset_pack_obj: dict[str, Any], resolver: _Stage4Resolver) -> list[dict[str, Any]]:
    sample_count = dataset_pack_obj.get("sample_count_u64")
    chunks = dataset_pack_obj.get("chunks")
    if not isinstance(sample_count, int) or sample_count < 0 or not isinstance(chunks, list):
        fail(REASON_VISION4_DMPL_REPLAY_FAIL)

    rows = sorted(list(chunks), key=lambda r: int(r.get("chunk_index_u32", -1)) if isinstance(r, dict) else -1)
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            fail(REASON_VISION4_DMPL_REPLAY_FAIL)
        idx = row.get("chunk_index_u32")
        if not isinstance(idx, int) or int(idx) != int(i):
            fail(REASON_VISION4_DMPL_REPLAY_FAIL)

    stream = bytearray()
    for row in rows:
        cid = str(row.get("chunk_bin_id", "")).strip()
        cbytes = row.get("chunk_bytes_u32")
        if not isinstance(cbytes, int) or cbytes < 0:
            fail(REASON_VISION4_DMPL_REPLAY_FAIL)
        try:
            chunk = resolver.load_artifact_bytes(artifact_id=str(cid), artifact_type="dmpl_dataset_chunk_v1", ext="bin")
        except DMPLError:
            fail(REASON_VISION4_DMPL_REPLAY_FAIL)
        if int(len(chunk)) != int(cbytes):
            fail(REASON_VISION4_DMPL_REPLAY_FAIL)
        stream += bytes(chunk)

    try:
        objs, _raws = parse_lenpref_canonjson_stream_v1(stream_bytes=bytes(stream), record_count_u64=int(sample_count))
    except DMPLError:
        fail(REASON_VISION4_DMPL_REPLAY_FAIL)
    return [dict(o) for o in objs]


def _verify_dataset_rebuild_from_stage1(
    *,
    transitions: list[_Stage1TransitionV1],
    sample_objs: list[dict[str, Any]],
    qxrl_model_obj: dict[str, Any],
    wroot_obj: dict[str, Any],
    registry_loader,
    d_u32: int,
    max_abs_z_q32: int,
    token_adapter_id: str,
    resolver: _Stage4Resolver,
) -> int:
    if not transitions:
        fail(REASON_VISION4_DMPL_REPLAY_FAIL)
    if len(sample_objs) != len(transitions):
        fail(REASON_VISION4_DMPL_REPLAY_FAIL)

    for tr, sample in zip(transitions, sample_objs, strict=True):
        if not isinstance(sample, dict) or str(sample.get("record_kind", "")).strip() != "SAMPLE":
            fail(REASON_VISION4_DMPL_REPLAY_FAIL)
        if str(sample.get("episode_id", "")).strip() != str(tr.episode_id):
            fail(REASON_VISION4_DMPL_REPLAY_FAIL)
        t_u32 = sample.get("t_u32")
        if not isinstance(t_u32, int) or int(t_u32) != int(tr.t_u32):
            fail(REASON_VISION4_DMPL_REPLAY_FAIL)

        start_state_id = sample.get("start_state_id")
        if isinstance(start_state_id, str) and start_state_id and str(start_state_id).strip() != str(tr.start_state_id):
            fail(REASON_VISION4_DMPL_REPLAY_FAIL)

        expected_z_t = vision_state_to_dmpl_tensor_bytes_v1(
            qxwmr_state_bytes=bytes(tr.state_t_bytes),
            qxrl_model_manifest_obj=dict(qxrl_model_obj),
            weights_manifest_obj=dict(wroot_obj),
            registry_loader=registry_loader,
            d_u32=int(d_u32),
            max_abs_z_q32=int(max_abs_z_q32),
            token_adapter_id=str(token_adapter_id),
        )
        expected_z_tp1 = vision_state_to_dmpl_tensor_bytes_v1(
            qxwmr_state_bytes=bytes(tr.state_tp1_bytes),
            qxrl_model_manifest_obj=dict(qxrl_model_obj),
            weights_manifest_obj=dict(wroot_obj),
            registry_loader=registry_loader,
            d_u32=int(d_u32),
            max_abs_z_q32=int(max_abs_z_q32),
            token_adapter_id=str(token_adapter_id),
        )

        z_t_id = str(sample.get("z_t_bin_id", "")).strip()
        z_tp1_id = str(sample.get("z_tp1_true_bin_id", "")).strip()
        if not z_t_id or not z_tp1_id:
            fail(REASON_VISION4_DMPL_REPLAY_FAIL)
        try:
            got_z_t = resolver.load_artifact_bytes(artifact_id=str(z_t_id), artifact_type="dmpl_tensor_q32_v1", ext="bin")
            got_z_tp1 = resolver.load_artifact_bytes(artifact_id=str(z_tp1_id), artifact_type="dmpl_tensor_q32_v1", ext="bin")
        except DMPLError:
            fail(REASON_VISION4_DMPL_REPLAY_FAIL)

        if bytes(got_z_t) != bytes(expected_z_t) or bytes(got_z_tp1) != bytes(expected_z_tp1):
            fail(REASON_VISION4_DMPL_REPLAY_FAIL)
    return int(len(transitions))


def verify(
    state_dir: Path,
    *,
    qxrl_model_manifest_path: Path,
    wroot_path: Path,
    dmpl_dataset_pack_path: Path,
    dmpl_train_run_path: Path,
    dmpl_train_trace_path: Path,
    dmpl_train_receipt_path: Path,
    qxwmr_world_model_manifest_path: Path,
    qxwmr_eval_manifest_path: Path,
    vision_wm_eval_suite_path: Path,
    stage1_run_manifest_paths: list[Path] | None = None,
    vision_transition_listing_path: Path | None = None,
) -> dict[str, Any]:
    state_root, staged_root = _resolve_state_roots(state_dir)

    qxrl_model_ref = _rel_ref_under_state(state_root, qxrl_model_manifest_path)
    wroot_ref = _rel_ref_under_state(state_root, wroot_path)
    world_model_ref = _rel_ref_under_state(state_root, qxwmr_world_model_manifest_path)
    eval_manifest_ref = _rel_ref_under_state(state_root, qxwmr_eval_manifest_path)
    dataset_pack_ref = _rel_ref_under_state(state_root, dmpl_dataset_pack_path)
    train_run_ref = _rel_ref_under_state(state_root, dmpl_train_run_path)
    train_trace_ref = _rel_ref_under_state(state_root, dmpl_train_trace_path)
    train_receipt_ref = _rel_ref_under_state(state_root, dmpl_train_receipt_path)
    suite_ref = _rel_ref_under_state(state_root, vision_wm_eval_suite_path)

    world_model_obj = _load_json_obj(qxwmr_world_model_manifest_path.resolve(), schema_id="qxwmr_world_model_manifest_v1", reason=REASON_VISION4_SCHEMA_INVALID)
    eval_manifest_obj = _load_json_obj(qxwmr_eval_manifest_path.resolve(), schema_id="qxwmr_eval_manifest_v1", reason=REASON_VISION4_SCHEMA_INVALID)
    suite_obj = _load_json_obj(vision_wm_eval_suite_path.resolve(), schema_id="vision_world_model_eval_suite_v1", reason=REASON_VISION4_SCHEMA_INVALID)
    qxrl_model_obj = _load_canon_json_obj(qxrl_model_manifest_path.resolve(), reason=REASON_VISION4_SCHEMA_INVALID)
    wroot_obj = _load_canon_json_obj(wroot_path.resolve(), reason=REASON_VISION4_SCHEMA_INVALID)

    _verify_system_manifest_bindings_from_summary(
        state_root=state_root,
        staged_root=staged_root,
        qxrl_model_ref_cli=dict(qxrl_model_ref),
        wroot_ref_cli=dict(wroot_ref),
        world_model_ref_cli=dict(world_model_ref),
        eval_manifest_ref_cli=dict(eval_manifest_ref),
    )

    droot_ref, _cfg_ref, _modelpack_ref, wm_bindings = _verify_world_model_manifest_bindings(
        staged_root=staged_root,
        world_model_obj=dict(world_model_obj),
        qxrl_model_ref_cli=dict(qxrl_model_ref),
        wroot_ref_cli=dict(wroot_ref),
        suite_ref=dict(suite_ref),
        eval_manifest_obj=dict(eval_manifest_obj),
    )

    resolver = _Stage4Resolver(state_root=state_root, staged_root=staged_root)

    try:
        verify_dmpl_train_replay_v1(
            root_tuple_obj={"droot": dict(droot_ref)},
            train_run_ref=dict(train_run_ref),
            train_trace_ref=dict(train_trace_ref),
            train_receipt_ref=dict(train_receipt_ref),
            resolver=resolver,
        )
    except DMPLError as exc:
        fail(str(exc.reason_code))

    train_run_obj = _load_json_obj(dmpl_train_run_path.resolve(), schema_id="dmpl_train_run_v1", reason=REASON_VISION4_DMPL_REPLAY_FAIL)
    train_receipt_obj = _load_json_obj(dmpl_train_receipt_path.resolve(), schema_id="dmpl_train_receipt_v1", reason=REASON_VISION4_DMPL_REPLAY_FAIL)
    dataset_pack_obj = _load_json_obj(dmpl_dataset_pack_path.resolve(), schema_id="dmpl_dataset_pack_v1", reason=REASON_VISION4_DMPL_REPLAY_FAIL)

    dataset_pack_id = str(train_run_obj.get("dataset_pack_id", "")).strip()
    if dataset_pack_id != str(dataset_pack_ref.get("artifact_id", "")).strip():
        fail(REASON_VISION4_BINDING_MISMATCH)

    droot_path = verify_artifact_ref_v1(artifact_ref=droot_ref, base_dir=staged_root, expected_relpath_prefix="polymath/registry/eudrs_u/")
    droot_obj = _load_json_obj(droot_path, schema_id="dmpl_droot_v1", reason=REASON_VISION4_DMPL_REPLAY_FAIL)
    cfg_id = str(droot_obj.get("dmpl_config_id", "")).strip()
    cfg_path = None
    for p in (staged_root / "polymath/registry/eudrs_u/dmpl/config").glob("*.dmpl_config_v1.json"):
        if sha256_prefixed(p.read_bytes()) == cfg_id:
            cfg_path = p
            break
    if cfg_path is None:
        fail(REASON_VISION4_DMPL_REPLAY_FAIL)
    cfg_obj = _load_json_obj(cfg_path, schema_id="dmpl_config_v1", reason=REASON_VISION4_DMPL_REPLAY_FAIL)

    checked_transitions_u64 = 0
    run_paths = _load_stage1_run_manifest_paths(
        state_root=state_root,
        staged_root=staged_root,
        stage1_run_manifest_paths=stage1_run_manifest_paths,
        vision_transition_listing_path=vision_transition_listing_path,
    )
    if run_paths:
        dataset_policy = suite_obj.get("dataset_policy")
        if not isinstance(dataset_policy, dict):
            fail(REASON_VISION4_SCHEMA_INVALID)
        sample_stride_u32 = dataset_policy.get("sample_stride_u32")
        max_transitions_u64 = dataset_policy.get("max_transitions_u64")
        if (
            not isinstance(sample_stride_u32, int)
            or sample_stride_u32 < 1
            or not isinstance(max_transitions_u64, int)
            or max_transitions_u64 < 1
        ):
            fail(REASON_VISION4_SCHEMA_INVALID)

        transitions = _collect_stage1_transitions(
            run_manifest_paths=run_paths,
            staged_root=staged_root,
            sample_stride_u32=int(sample_stride_u32),
            max_transitions_u64=int(max_transitions_u64),
        )
        samples = _load_dataset_samples_from_pack(dataset_pack_obj=dict(dataset_pack_obj), resolver=resolver)

        def _registry_loader(ref: dict[str, Any]) -> bytes:
            aref = require_artifact_ref_v1(ref, reason=REASON_VISION4_SCHEMA_INVALID)
            p = verify_artifact_ref_v1(
                artifact_ref=aref,
                base_dir=staged_root,
                expected_relpath_prefix="polymath/registry/eudrs_u/",
            )
            return p.read_bytes()

        checked_transitions_u64 = _verify_dataset_rebuild_from_stage1(
            transitions=transitions,
            sample_objs=samples,
            qxrl_model_obj=dict(qxrl_model_obj),
            wroot_obj=dict(wroot_obj),
            registry_loader=_registry_loader,
            d_u32=int(wm_bindings["d_u32"]),
            max_abs_z_q32=int(wm_bindings["max_abs_z_q32"]),
            token_adapter_id=str(wm_bindings["token_adapter_id"]),
            resolver=resolver,
        )

    candidate_droot_id = str(train_receipt_obj.get("candidate_droot_id", "")).strip()
    mean_l1_q32 = int(
        _compute_holdout_mean_L1_pred_q32(
            candidate_droot_id=candidate_droot_id,
            dataset_pack_obj=dict(dataset_pack_obj),
            config_obj=dict(cfg_obj),
            resolver=resolver,
        )
    )

    # v1 deterministic derived metrics.
    rollout_drift_q32 = int(mean_l1_q32)
    saturation_rate_q32 = 0

    suite_thresholds = suite_obj.get("thresholds")
    eval_thresholds = eval_manifest_obj.get("thresholds")
    if not isinstance(suite_thresholds, dict) or not isinstance(eval_thresholds, dict):
        fail(REASON_VISION4_SCHEMA_INVALID)

    mean_max = min(
        _q32(suite_thresholds.get("mean_l1_max_q32"), reason=REASON_VISION4_SCHEMA_INVALID),
        _q32(eval_thresholds.get("mean_l1_max_q32"), reason=REASON_VISION4_SCHEMA_INVALID),
    )
    drift_max = min(
        _q32(suite_thresholds.get("rollout_drift_max_q32"), reason=REASON_VISION4_SCHEMA_INVALID),
        _q32(eval_thresholds.get("rollout_drift_max_q32"), reason=REASON_VISION4_SCHEMA_INVALID),
    )
    sat_max = min(
        _q32(suite_thresholds.get("saturation_rate_max_q32"), reason=REASON_VISION4_SCHEMA_INVALID),
        _q32(eval_thresholds.get("saturation_rate_max_q32"), reason=REASON_VISION4_SCHEMA_INVALID),
    )

    if int(mean_l1_q32) > int(mean_max) or int(rollout_drift_q32) > int(drift_max) or int(saturation_rate_q32) > int(sat_max):
        fail(REASON_VISION4_THRESHOLD_FAIL)

    report_obj = {
        "schema_id": "vision_world_model_eval_report_v1",
        "suite_id": str(suite_obj.get("suite_id", "")),
        "droot_id": str(candidate_droot_id),
        "metrics": {
            "mean_l1_q32": {"q": int(mean_l1_q32)},
            "rollout_drift_q32": {"q": int(rollout_drift_q32)},
            "saturation_rate_q32": {"q": int(saturation_rate_q32)},
        },
        "thresholds": {
            "mean_l1_max_q32": {"q": int(mean_max)},
            "rollout_drift_max_q32": {"q": int(drift_max)},
            "saturation_rate_max_q32": {"q": int(sat_max)},
        },
        "status": "PASS",
    }
    try:
        validate_schema(report_obj, "vision_world_model_eval_report_v1")
    except Exception:  # noqa: BLE001
        fail(REASON_VISION4_SCHEMA_INVALID)

    report_id = sha256_prefixed(gcj1_canon_bytes(report_obj))

    return {
        "schema_id": "vision_stage4_verify_receipt_v1",
        "verdict": "VALID",
        "computed": {
            "candidate_droot_id": str(candidate_droot_id),
            "mean_l1_q32": {"q": int(mean_l1_q32)},
            "rollout_drift_q32": {"q": int(rollout_drift_q32)},
            "saturation_rate_q32": {"q": int(saturation_rate_q32)},
            "eval_report_id": str(report_id),
            "checked_stage1_transitions_u64": int(checked_transitions_u64),
        },
    }


def _write_receipt(*, state_dir: Path, receipt_obj: dict[str, Any]) -> None:
    evidence_dir = Path(state_dir).resolve() / EUDRS_U_EVIDENCE_DIR_REL
    evidence_dir.mkdir(parents=True, exist_ok=True)
    (evidence_dir / "vision_stage4_verify_receipt_v1.json").write_bytes(gcj1_canon_bytes(receipt_obj))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="verify_vision_stage4_v1")
    parser.add_argument("--state_dir", required=True)
    parser.add_argument("--stage1_run_manifest_relpaths", required=False)
    parser.add_argument("--vision_transition_listing_relpath", required=False)
    parser.add_argument("--qxrl_model_manifest_relpath", required=True)
    parser.add_argument("--wroot_relpath", required=True)
    parser.add_argument("--dmpl_dataset_pack_relpath", required=True)
    parser.add_argument("--dmpl_train_run_relpath", required=True)
    parser.add_argument("--dmpl_train_trace_relpath", required=True)
    parser.add_argument("--dmpl_train_receipt_relpath", required=True)
    parser.add_argument("--qxwmr_world_model_manifest_relpath", required=True)
    parser.add_argument("--qxwmr_eval_manifest_relpath", required=True)
    parser.add_argument("--vision_wm_eval_suite_relpath", required=True)
    args = parser.parse_args(argv)

    state_dir = Path(args.state_dir).resolve()
    state_root, staged_root = _resolve_state_roots(state_dir)

    def _resolve(rel: str) -> Path:
        return _resolve_relpath_in_state(state_root=state_root, staged_root=staged_root, relpath=str(rel))

    stage1_paths: list[Path] = []
    if args.stage1_run_manifest_relpaths:
        raw = str(args.stage1_run_manifest_relpaths).strip()
        if raw:
            # Allow passing a text file (one relpath per line) or inline CSV relpaths.
            if "," not in raw and "\n" not in raw:
                p0 = _resolve(raw)
                if p0.suffix in {".txt", ".list"}:
                    lines = [ln.strip() for ln in p0.read_text(encoding="utf-8").splitlines() if ln.strip()]
                    stage1_paths = [_resolve(ln) for ln in lines]
                else:
                    stage1_paths = [p0]
            else:
                stage1_paths = [_resolve(tok) for tok in _parse_stage1_relpaths_arg(raw)]

    transition_listing_path = _resolve(str(args.vision_transition_listing_relpath)) if args.vision_transition_listing_relpath else None

    try:
        receipt = verify(
            state_dir=state_dir,
            qxrl_model_manifest_path=_resolve(str(args.qxrl_model_manifest_relpath)),
            wroot_path=_resolve(str(args.wroot_relpath)),
            dmpl_dataset_pack_path=_resolve(str(args.dmpl_dataset_pack_relpath)),
            dmpl_train_run_path=_resolve(str(args.dmpl_train_run_relpath)),
            dmpl_train_trace_path=_resolve(str(args.dmpl_train_trace_relpath)),
            dmpl_train_receipt_path=_resolve(str(args.dmpl_train_receipt_relpath)),
            qxwmr_world_model_manifest_path=_resolve(str(args.qxwmr_world_model_manifest_relpath)),
            qxwmr_eval_manifest_path=_resolve(str(args.qxwmr_eval_manifest_relpath)),
            vision_wm_eval_suite_path=_resolve(str(args.vision_wm_eval_suite_relpath)),
            stage1_run_manifest_paths=stage1_paths,
            vision_transition_listing_path=transition_listing_path,
        )
        _write_receipt(state_dir=state_dir, receipt_obj=receipt)
        print("VALID")
    except OmegaV18Error as exc:
        reason = str(exc)
        if reason.startswith("INVALID:"):
            reason = reason.split(":", 1)[1]
        receipt = {"schema_id": "vision_stage4_verify_receipt_v1", "verdict": "INVALID", "reason_code": str(reason)}
        try:
            _write_receipt(state_dir=state_dir, receipt_obj=receipt)
        except Exception:  # noqa: BLE001
            pass
        print("INVALID:" + str(reason))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
