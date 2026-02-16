from __future__ import annotations

import hashlib
import math
import struct
from pathlib import Path
from typing import Any

import pytest

from cdel.v18_0.eudrs_u.eudrs_u_hash_v1 import gcj1_canon_bytes, sha256_prefixed
from cdel.v18_0.eudrs_u.qxrl_common_v1 import (
    compute_eval_id_config_hash,
    compute_self_hash_id,
    REASON_QXRL_OPSET_LUT_MISMATCH,
    REASON_QXRL_OPTIMIZER_KIND_FORBIDDEN,
)
from cdel.v18_0.eudrs_u.qxrl_dataset_v1 import QXRLDatasetExampleV1
from cdel.v18_0.eudrs_u.qxrl_eval_v1 import compute_qxrl_eval_scorecard_v1
from cdel.v18_0.eudrs_u.qxrl_forward_qre_v1 import parse_qxrl_model_manifest_v1
from cdel.v18_0.eudrs_u.qxrl_forward_tsae_v1 import QXRLTSAELayerWeightsV1, QXRLWeightsViewTSAEV1, forward_encoder_tsae_v1
from cdel.v18_0.eudrs_u.qxrl_opset_math_v1 import div_q32_pos_rne_v1, invsqrt_q32_nr_lut_v1, parse_invsqrt_lut_bin_v1
from cdel.v18_0.eudrs_u.qxrl_ops_v1 import QXRLStepCountersV1, argmax_det, topk_det
from cdel.v18_0.eudrs_u.qxrl_train_replay_v1 import (
    WeightsBlockDescV1,
    WeightsTensorDescV1,
    load_and_verify_weights_manifest_v1,
    replay_qxrl_training_v1,
)
from cdel.v18_0.eudrs_u.verify_eudrs_u_run_v1 import verify as verify_eudrs_u_run
from cdel.v18_0.eudrs_u.verify_qxrl_v1 import verify_qxrl_v1
from cdel.v18_0.omega_common_v1 import OmegaV18Error


def _find_superproject_root() -> Path | None:
    here = Path(__file__).resolve()
    for anc in [here, *here.parents]:
        if (anc / "Genesis/schema/v18_0").is_dir():
            return anc
    return None


_SUPERPROJECT_ROOT = _find_superproject_root()
if _SUPERPROJECT_ROOT is None:
    pytest.skip("requires Genesis schemas (run via AGI-Stack)", allow_module_level=True)


def _copy_schema_file(*, real_repo_root: Path, out_schema_dir: Path, name: str) -> None:
    assert _SUPERPROJECT_ROOT is not None
    src = _SUPERPROJECT_ROOT / "Genesis" / "schema" / "v18_0" / f"{name}.jsonschema"
    dst = out_schema_dir / f"{name}.jsonschema"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(src.read_bytes())


def _write_hashed_bytes(*, out_dir: Path, suffix: str, raw: bytes) -> tuple[Path, str]:
    digest = sha256_prefixed(raw)
    hex64 = digest.split(":", 1)[1]
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"sha256_{hex64}.{suffix}"
    path.write_bytes(raw)
    return path, digest


def _encode_qxds_segment(*, examples: list[QXRLDatasetExampleV1], vocab_size_u32: int, seq_len_u32: int) -> bytes:
    # See qxrl_dataset_segment_v1.bin spec.
    header = struct.pack(
        "<4sIIIIII",
        b"QXDS",
        1,  # version_u32
        1,  # tokenizer_kind_u32: BYTE_TOK_257_V1
        1,  # dataset_kind_u32: PAIR_V1
        int(vocab_size_u32),
        int(seq_len_u32),
        int(len(examples)),
    )
    out = bytearray(header)
    for ex in examples:
        out += struct.pack("<Q", int(ex.example_id_u64) & 0xFFFFFFFFFFFFFFFF)
        for tok in ex.anchor_tokens_u32:
            out += struct.pack("<I", int(tok) & 0xFFFFFFFF)
        for tok in ex.positive_tokens_u32:
            out += struct.pack("<I", int(tok) & 0xFFFFFFFF)
    return bytes(out)


def _one_block(total: int) -> list[WeightsBlockDescV1]:
    return [
        WeightsBlockDescV1(
            elem_offset_u64=0,
            elem_count_u32=int(total),
            # Placeholder; encoding derives deterministic content-addressed refs.
            block_ref={"artifact_id": "sha256:" + ("0" * 64), "artifact_relpath": "x"},
        )
    ]


def _fixture_initial_weights(*, opset_id: str) -> tuple[dict[str, Any], bytes, str, dict[str, bytes]]:
    # Matches the small deterministic fixture used in test_qxrl_v1_fast.py.
    Q32_ONE = 1 << 32
    vocab = 257
    seq = 8
    dm = 2
    dh = 2
    de = 2

    tok_emb: list[int] = []
    for v in range(vocab):
        tok_emb.append(v << 16)
        tok_emb.append((v ^ 0x55) << 16)

    pos_emb: list[int] = []
    for p in range(seq):
        pos_emb.append(p << 16)
        pos_emb.append((p * 3) << 16)

    enc_w1 = [Q32_ONE, 0, 0, Q32_ONE]
    enc_b1 = [0, 0]
    enc_w2 = [Q32_ONE, 0, 0, Q32_ONE]
    enc_b2 = [0, 0]
    tok_proj_w = [Q32_ONE, 0, 0, Q32_ONE]
    tok_proj_b = [0, 0]

    out_emb: list[int] = []
    for v in range(vocab):
        out_emb.append(v << 16)
        out_emb.append((v * 7) << 16)
    out_b = [0] * vocab

    def _tdesc(name: str, shape: list[int], data: list[int]) -> WeightsTensorDescV1:
        total = 1
        for d in shape:
            total *= int(d)
        assert len(data) == total
        return WeightsTensorDescV1(name=name, dtype="Q32_S64_V1", shape_u32=shape, blocks=_one_block(total), data_q32_s64=data)

    names_shapes_data = {
        "qxrl/tok_emb": ([vocab, dm], tok_emb),
        "qxrl/pos_emb": ([seq, dm], pos_emb),
        "qxrl/enc_w1": ([dh, dm], enc_w1),
        "qxrl/enc_b1": ([dh], enc_b1),
        "qxrl/enc_w2": ([de, dh], enc_w2),
        "qxrl/enc_b2": ([de], enc_b2),
        "qxrl/tok_proj_w": ([de, dm], tok_proj_w),
        "qxrl/tok_proj_b": ([de], tok_proj_b),
        "qxrl/out_emb": ([vocab, de], out_emb),
        "qxrl/out_b": ([vocab], out_b),
    }

    tensor_descs: list[WeightsTensorDescV1] = []
    for name, (shape, data) in sorted(names_shapes_data.items()):
        tensor_descs.append(_tdesc(name, list(shape), list(data)))
        mom = "qxrl/opt/mom/" + name[len("qxrl/") :]
        tensor_descs.append(_tdesc(mom, list(shape), [0] * len(data)))

    from cdel.v18_0.eudrs_u import qxrl_train_replay_v1 as tr

    manifest_obj, manifest_bytes, manifest_id, blocks_out = tr._build_weights_manifest_bytes_from_descs(
        dc1_id="dc1:q32_v1",
        opset_id=str(opset_id),
        merkle_fanout_u32=2,
        tensor_descs=sorted(tensor_descs, key=lambda t: t.name),
    )

    block_bytes_by_id = {ref["artifact_id"]: b for ref, b in blocks_out}
    return manifest_obj, manifest_bytes, str(manifest_id), block_bytes_by_id


def _tensor_specs_qre(*, vocab: int, seq: int, dm: int, dh: int, de: int) -> list[dict[str, Any]]:
    req = {
        "qxrl/tok_emb": [int(vocab), int(dm)],
        "qxrl/pos_emb": [int(seq), int(dm)],
        "qxrl/enc_w1": [int(dh), int(dm)],
        "qxrl/enc_b1": [int(dh)],
        "qxrl/enc_w2": [int(de), int(dh)],
        "qxrl/enc_b2": [int(de)],
        "qxrl/tok_proj_w": [int(de), int(dm)],
        "qxrl/tok_proj_b": [int(de)],
        "qxrl/out_emb": [int(vocab), int(de)],
        "qxrl/out_b": [int(vocab)],
    }

    specs: list[dict[str, Any]] = []
    for name, shape in sorted(req.items()):
        specs.append({"name": str(name), "shape_u32": list(shape), "dtype": "Q32_S64_V1", "trainable": True})
        mom = "qxrl/opt/mom/" + str(name)[len("qxrl/") :]
        specs.append({"name": str(mom), "shape_u32": list(shape), "dtype": "Q32_S64_V1", "trainable": False})
    specs.sort(key=lambda row: str(row.get("name", "")))
    return specs


def _gen_invsqrt_lut_bytes_phase5() -> bytes:
    # Spec: ISQ1 v1, lut_bits=10, entry_count=1024, s64_le table entries.
    lut_bits_u32 = 10
    entry_count_u32 = 1 << lut_bits_u32
    header = struct.pack("<4sIII", b"ISQ1", 1, lut_bits_u32, entry_count_u32)
    out = bytearray(header)

    num = 1 << 48  # 2^48
    shift = 31 - lut_bits_u32
    for idx in range(entry_count_u32):
        m_sample_q32 = (1 << 32) + ((2 * idx + 1) << shift)
        sqrt_m = math.isqrt(int(m_sample_q32))
        q0, r = divmod(int(num), int(sqrt_m))
        twice_r = int(r) * 2
        if twice_r > int(sqrt_m):
            y0 = int(q0) + 1
        elif twice_r < int(sqrt_m):
            y0 = int(q0)
        else:
            y0 = int(q0) + (1 if (int(q0) & 1) == 1 else 0)
        # Clamp to s64 range if needed (should not trigger in Phase 5).
        if y0 > (1 << 63) - 1:
            y0 = (1 << 63) - 1
        out += struct.pack("<q", int(y0))

    return bytes(out)


def _setup_repo_root_with_prev_active_wroot(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    init_wroot_id: str,
    init_manifest_bytes: bytes,
    init_blocks_by_id: dict[str, bytes],
) -> tuple[Path, str, str]:
    """Create a temp repo_root with:
    - Genesis schemas needed by validate_schema
    - polymath/registry/eudrs_u/active/active_root_tuple_ref_v1.json
    - a previous active root tuple that references init_wroot
    - init weights manifest + blocks on disk (content-addressed filenames)
    """

    repo_root = tmp_path / "repo_verify_qxrl"
    schema_dir = repo_root / "Genesis" / "schema" / "v18_0"

    import cdel.v18_0.omega_common_v1 as omega_common

    real_repo_root = Path(omega_common.__file__).resolve().parents[3]

    for name in [
        "eudrs_u_artifact_ref_v1",
        "qxrl_model_manifest_v1",
        "qxrl_dataset_manifest_v1",
        "qxrl_invsqrt_lut_manifest_v1",
        "qxrl_training_manifest_v1",
        "qxrl_eval_manifest_v1",
        "qxrl_eval_scorecard_v1",
        "determinism_cert_v1",
    ]:
        _copy_schema_file(real_repo_root=real_repo_root, out_schema_dir=schema_dir, name=name)

    monkeypatch.setenv("OMEGA_DEV_BENCHMARK_MODE", "1")
    monkeypatch.setenv("OMEGA_REPO_ROOT", str(repo_root))

    dc1_id = "dc1:q32_v1"
    opset_id = "opset:eudrs_u_v1:sha256:" + ("0" * 64)

    # Write init weights manifest + blocks under repo_root (must match ArtifactRefV1 relpaths).
    init_wroot_hex = str(init_wroot_id).split(":", 1)[1]
    init_wroot_rel = f"polymath/registry/eudrs_u/weights/sha256_{init_wroot_hex}.weights_manifest_v1.json"
    (repo_root / Path(init_wroot_rel).parent).mkdir(parents=True, exist_ok=True)
    (repo_root / init_wroot_rel).write_bytes(bytes(init_manifest_bytes))

    for block_id, block_bytes in init_blocks_by_id.items():
        hex64 = str(block_id).split(":", 1)[1]
        rel = f"polymath/registry/eudrs_u/weights/blocks/sha256_{hex64}.q32_tensor_block_v1.bin"
        (repo_root / Path(rel).parent).mkdir(parents=True, exist_ok=True)
        (repo_root / rel).write_bytes(bytes(block_bytes))

    # Previous root tuple (minimal; verify_qxrl_v1 only needs wroot).
    prev_root_tuple_obj: dict[str, Any] = {
        "schema_id": "eudrs_u_root_tuple_v1",
        "wroot": {"artifact_id": str(init_wroot_id), "artifact_relpath": init_wroot_rel},
    }
    prev_rt_bytes = gcj1_canon_bytes(prev_root_tuple_obj)
    prev_rt_id = sha256_prefixed(prev_rt_bytes)
    prev_rt_hex = prev_rt_id.split(":", 1)[1]
    prev_rt_rel = f"polymath/registry/eudrs_u/roots/sha256_{prev_rt_hex}.eudrs_u_root_tuple_v1.json"
    (repo_root / Path(prev_rt_rel).parent).mkdir(parents=True, exist_ok=True)
    (repo_root / prev_rt_rel).write_bytes(prev_rt_bytes)

    active_ptr_path = repo_root / "polymath/registry/eudrs_u/active/active_root_tuple_ref_v1.json"
    active_ptr_path.parent.mkdir(parents=True, exist_ok=True)
    active_ptr_path.write_bytes(
        gcj1_canon_bytes(
            {
                "schema_id": "active_root_tuple_ref_v1",
                "active_root_tuple": {"artifact_id": prev_rt_id, "artifact_relpath": prev_rt_rel},
            }
        )
    )

    return repo_root, dc1_id, opset_id


def _build_verify_qxrl_ctx_inmem(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    optimizer_kind: str,
    lut_ref_artifact_id_override: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, bytes], dict[str, str]]:
    """Build a minimal in-memory registry + objects for verify_qxrl_v1.

    Returns: (root_tuple_obj, system_manifest_obj, determinism_cert_obj, bytes_by_artifact_id, wroot_ref)
    """

    opset_id = "opset:eudrs_u_v1:sha256:" + ("0" * 64)
    dc1_id = "dc1:q32_v1"

    # Use the canonical small initial weights fixture as both prev-active and proposed WRoot.
    init_manifest_obj, init_manifest_bytes, init_wroot_id, init_blocks_by_id = _fixture_initial_weights(opset_id=opset_id)

    _setup_repo_root_with_prev_active_wroot(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        init_wroot_id=init_wroot_id,
        init_manifest_bytes=init_manifest_bytes,
        init_blocks_by_id=init_blocks_by_id,
    )

    # Phase 5 pinned LUT bytes (or override just the claimed artifact_id in the LUT manifest).
    lut_bytes = _gen_invsqrt_lut_bytes_phase5()
    lut_art_id = sha256_prefixed(lut_bytes)
    lut_hex = lut_art_id.split(":", 1)[1]
    lut_rel = f"polymath/registry/eudrs_u/manifests/sha256_{lut_hex}.qxrl_invsqrt_lut_v1.bin"

    lut_ref_artifact_id = str(lut_art_id) if lut_ref_artifact_id_override is None else str(lut_ref_artifact_id_override)
    lut_ref_hex = lut_ref_artifact_id.split(":", 1)[1]
    lut_ref_rel = f"polymath/registry/eudrs_u/manifests/sha256_{lut_ref_hex}.qxrl_invsqrt_lut_v1.bin"
    lut_ref = {"artifact_id": lut_ref_artifact_id, "artifact_relpath": lut_ref_rel}

    lut_manifest_obj: dict[str, Any] = {
        "schema_id": "qxrl_invsqrt_lut_manifest_v1",
        "lut_manifest_id": "sha256:" + ("0" * 64),
        "dc1_id": dc1_id,
        "opset_id": opset_id,
        "lut_kind": "INVSQRT_Q32_NR_LUT_V1",
        "lut_bits_u32": 10,
        "invsqrt_iters_u32": 2,
        "lut_ref": lut_ref,
    }
    lut_manifest_obj["lut_manifest_id"] = compute_self_hash_id(lut_manifest_obj, id_field="lut_manifest_id")
    lut_manifest_bytes = gcj1_canon_bytes(lut_manifest_obj)
    lut_manifest_art_id = sha256_prefixed(lut_manifest_bytes)
    lut_manifest_hex = lut_manifest_art_id.split(":", 1)[1]
    lut_manifest_rel = f"polymath/registry/eudrs_u/manifests/sha256_{lut_manifest_hex}.qxrl_invsqrt_lut_manifest_v1.json"
    lut_manifest_ref = {"artifact_id": lut_manifest_art_id, "artifact_relpath": lut_manifest_rel}

    # QRE model manifest (Phase 5 fields required).
    vocab = 257
    seq = 8
    dm = 2
    dh = 2
    de = 2
    model_obj: dict[str, Any] = {
        "schema_id": "qxrl_model_manifest_v1",
        "model_id": "sha256:" + ("0" * 64),
        "opset_id": opset_id,
        "dc1_id": dc1_id,
        "tokenizer_kind": "BYTE_TOK_257_V1",
        "vocab_size_u32": vocab,
        "seq_len_u32": seq,
        "encoder_kind": "QRE_V1",
        "d_model_u32": dm,
        "d_embed_u32": de,
        "math": {
            "dot_kind": "DOT_Q32_SHIFT_END_V1",
            "div_kind": "DIV_Q32_POS_RNE_V1",
            "invsqrt_kind": "INVSQRT_Q32_NR_LUT_V1",
            "invsqrt_lut_manifest_ref": lut_manifest_ref,
        },
        "qre": {"d_hidden_u32": dh, "inv_seq_len_q32": {"q": (1 << 32) // seq}},
        "tensor_specs": _tensor_specs_qre(vocab=vocab, seq=seq, dm=dm, dh=dh, de=de),
    }
    model_obj["model_id"] = compute_self_hash_id(model_obj, id_field="model_id")
    model_bytes = gcj1_canon_bytes(model_obj)
    model_art_id = sha256_prefixed(model_bytes)
    model_hex = model_art_id.split(":", 1)[1]
    model_rel = f"polymath/registry/eudrs_u/manifests/sha256_{model_hex}.qxrl_model_manifest_v1.json"
    model_ref = {"artifact_id": model_art_id, "artifact_relpath": model_rel}
    model = parse_qxrl_model_manifest_v1(dict(model_obj))

    # Dataset segment + manifest (self-hash enforced by loader).
    examples = [
        QXRLDatasetExampleV1(example_id_u64=i, anchor_tokens_u32=[i + 1] * 8, positive_tokens_u32=[i + 2] * 8)
        for i in range(4)
    ]
    seg_bytes = _encode_qxds_segment(examples=examples, vocab_size_u32=vocab, seq_len_u32=seq)
    seg_art_id = sha256_prefixed(seg_bytes)
    seg_hex = seg_art_id.split(":", 1)[1]
    seg_rel = f"polymath/registry/eudrs_u/datasets/segments/sha256_{seg_hex}.qxrl_dataset_segment_v1.bin"
    seg_digest32 = bytes.fromhex(seg_hex)
    dataset_root_hash32 = hashlib.sha256(b"QXRL_DATASET_ROOT_V1" + seg_digest32).digest()

    dataset_obj: dict[str, Any] = {
        "schema_id": "qxrl_dataset_manifest_v1",
        "dataset_id": "sha256:" + ("0" * 64),
        "opset_id": opset_id,
        "dc1_id": dc1_id,
        "tokenizer_kind": "BYTE_TOK_257_V1",
        "dataset_kind": "PAIR_V1",
        "vocab_size_u32": vocab,
        "seq_len_u32": seq,
        "segments": [
            {
                "segment_index_u32": 0,
                "record_count_u32": 4,
                "first_example_id_u64": 0,
                "last_example_id_u64": 3,
                "segment_ref": {"artifact_id": seg_art_id, "artifact_relpath": seg_rel},
            }
        ],
        "dataset_root_hash32_hex": dataset_root_hash32.hex(),
    }
    dataset_obj["dataset_id"] = compute_self_hash_id(dataset_obj, id_field="dataset_id")
    dataset_bytes = gcj1_canon_bytes(dataset_obj)
    dataset_art_id = sha256_prefixed(dataset_bytes)
    dataset_hex = dataset_art_id.split(":", 1)[1]
    dataset_rel = f"polymath/registry/eudrs_u/datasets/sha256_{dataset_hex}.qxrl_dataset_manifest_v1.json"
    dataset_ref = {"artifact_id": dataset_art_id, "artifact_relpath": dataset_rel}

    # Eval manifest (schema-valid; verifier rejects before scorecard is needed).
    eval_obj: dict[str, Any] = {
        "schema_id": "qxrl_eval_manifest_v1",
        "eval_id": "sha256:" + ("0" * 64),
        "opset_id": opset_id,
        "dc1_id": dc1_id,
        "model_manifest_ref": model_ref,
        "dataset_manifest_ref": dataset_ref,
        "dot_kind": "DOT_Q32_SHIFT_END_V1",
        "eval_example_count_u32": 4,
        "eval_start_index_u64": 0,
        "mask_prob_q32": {"q": 1 << 32},
        "max_masks_per_seq_u32": 2,
        "mlm_neg_k_u32": 2,
        "NEG_RESAMPLE_CAP_u32": 100,
        "recall_k_u32": 2,
        "floors": {"masked_acc_at_1_min_q32": {"q": 0}, "recall_at_k_min_q32": {"q": 0}},
        "checks": {"collapse_check_enabled": False, "drift_check_enabled": False},
        "scorecard_ref": {
            "artifact_id": "sha256:" + ("0" * 64),
            "artifact_relpath": "polymath/registry/eudrs_u/eval/sha256_" + ("0" * 64) + ".qxrl_eval_scorecard_v1.json",
        },
    }
    eval_obj["eval_id"] = compute_eval_id_config_hash(eval_obj)
    eval_bytes = gcj1_canon_bytes(eval_obj)
    eval_art_id = sha256_prefixed(eval_bytes)
    eval_hex = eval_art_id.split(":", 1)[1]
    eval_rel = f"polymath/registry/eudrs_u/manifests/sha256_{eval_hex}.qxrl_eval_manifest_v1.json"
    eval_ref = {"artifact_id": eval_art_id, "artifact_relpath": eval_rel}

    # Training manifest (self-hash enforced).
    tm: dict[str, Any] = {
        "schema_id": "qxrl_training_manifest_v1",
        "training_id": "sha256:" + ("0" * 64),
        "opset_id": opset_id,
        "dc1_id": dc1_id,
        "model_manifest_ref": model_ref,
        "dataset_manifest_ref": dataset_ref,
        "dot_kind": "DOT_Q32_SHIFT_END_V1",
        "optimizer_kind": str(optimizer_kind),
        "init_scale_q32": {"q": 1},
        "train_steps_u64": 1,
        "batch_size_u32": 2,
        "checkpoint_every_steps_u32": 1,
        "mask_prob_q32": {"q": 1 << 32},
        "max_masks_per_seq_u32": 2,
        "mlm_neg_k_u32": 2,
        "NEG_RESAMPLE_CAP_u32": 100,
        "mlm_margin_q32": {"q": 1 << 32},
        "ctr_margin_q32": {"q": 1 << 32},
        "mlm_loss_weight_q32": {"q": 1 << 32},
        "ctr_loss_weight_q32": {"q": 1 << 32},
        "lr_q32": {"q": 1 << 30},
        "momentum_q32": {"q": 0},
    }
    tm["training_id"] = compute_self_hash_id(tm, id_field="training_id")
    tm_bytes = gcj1_canon_bytes(tm)
    tm_art_id = sha256_prefixed(tm_bytes)
    tm_hex = tm_art_id.split(":", 1)[1]
    tm_rel = f"polymath/registry/eudrs_u/manifests/sha256_{tm_hex}.qxrl_training_manifest_v1.json"
    tm_ref = {"artifact_id": tm_art_id, "artifact_relpath": tm_rel}

    # Determinism cert (Phase 5 math fields required; tails may be arbitrary for forbidden tests).
    det_obj: dict[str, Any] = {
        "schema_id": "determinism_cert_v1",
        "epoch_u64": 1,
        "dc1_id": dc1_id,
        "opset_id": opset_id,
        "qxrl": {
            "training_manifest_ref": tm_ref,
            "h_train_tail32_hex": "0" * 64,
            "h_eval_tail32_hex": "0" * 64,
            "math": {
                "dot_kind": str(model.dot_kind),
                "div_kind": str(model.div_kind),
                "invsqrt_kind": str(model.invsqrt_kind),
                "invsqrt_lut_manifest_ref": lut_manifest_ref,
                "invsqrt_iters_u32": 2,
            },
        },
    }

    system_manifest_obj: dict[str, Any] = {
        "schema_id": "eudrs_u_system_manifest_v1",
        "epoch_u64": 1,
        "dc1_id": dc1_id,
        "opset_id": opset_id,
        "qxrl": {"model_manifest_ref": model_ref, "eval_manifest_ref": eval_ref, "dataset_manifest_ref": dataset_ref},
    }

    wroot_ref = {"artifact_id": init_wroot_id, "artifact_relpath": "polymath/registry/eudrs_u/weights/sha256_" + init_wroot_id.split(':', 1)[1] + ".weights_manifest_v1.json"}
    root_tuple_obj: dict[str, Any] = {"schema_id": "eudrs_u_root_tuple_v1", "epoch_u64": 1, "dc1_id": dc1_id, "opset_id": opset_id, "wroot": wroot_ref}

    bytes_by_id: dict[str, bytes] = {}
    bytes_by_id[str(lut_manifest_art_id)] = bytes(lut_manifest_bytes)
    if lut_ref_artifact_id_override is None:
        bytes_by_id[str(lut_art_id)] = bytes(lut_bytes)
    bytes_by_id[str(model_art_id)] = bytes(model_bytes)
    bytes_by_id[str(dataset_art_id)] = bytes(dataset_bytes)
    bytes_by_id[str(seg_art_id)] = bytes(seg_bytes)
    bytes_by_id[str(eval_art_id)] = bytes(eval_bytes)
    bytes_by_id[str(tm_art_id)] = bytes(tm_bytes)

    # Proposed WRoot weights + blocks.
    bytes_by_id[str(init_wroot_id)] = bytes(init_manifest_bytes)
    for bid, b in init_blocks_by_id.items():
        bytes_by_id[str(bid)] = bytes(b)

    return root_tuple_obj, system_manifest_obj, det_obj, bytes_by_id, wroot_ref


def test_qxrl_argmax_topk_tie_fixtures() -> None:
    assert argmax_det([7, 7, 7]) == 0

    ctr = QXRLStepCountersV1()
    pairs = [(10, 2), (10, 1), (9, 0)]
    assert topk_det(pairs, 2, ctr) == [(10, 1), (10, 2)]
    assert ctr.topk_ops_u64 == 1


def test_qxrl_div_q32_pos_rne_phase5_vectors() -> None:
    Q32_ONE = 1 << 32

    assert div_q32_pos_rne_v1(numer_q32_s64=Q32_ONE, denom_q32_pos_s64=3 * Q32_ONE, ctr=None) == 1431655765

    # Tie case: q even (no increment).
    assert div_q32_pos_rne_v1(numer_q32_s64=Q32_ONE + 1, denom_q32_pos_s64=1 << 33, ctr=None) == 2147483648

    # Tie case: q odd (increment to even).
    assert div_q32_pos_rne_v1(numer_q32_s64=Q32_ONE + 3, denom_q32_pos_s64=1 << 33, ctr=None) == 2147483650


def test_qxrl_invsqrt_q32_nr_lut_phase5_vectors() -> None:
    lut_bytes = _gen_invsqrt_lut_bytes_phase5()
    assert sha256_prefixed(lut_bytes) == "sha256:f6b7eac00dae22340aefefc36692994958acb88933698f97968ae9cb37e97864"
    lut_table = parse_invsqrt_lut_bin_v1(lut_bytes=lut_bytes)

    Q32_ONE = 1 << 32
    assert invsqrt_q32_nr_lut_v1(x_q32_pos_s64=1 * Q32_ONE, lut_table_q32_s64=lut_table, ctr=None) == 4294967295
    assert invsqrt_q32_nr_lut_v1(x_q32_pos_s64=2 * Q32_ONE, lut_table_q32_s64=lut_table, ctr=None) == 3037000499
    assert invsqrt_q32_nr_lut_v1(x_q32_pos_s64=4 * Q32_ONE, lut_table_q32_s64=lut_table, ctr=None) == 2147483647
    assert invsqrt_q32_nr_lut_v1(x_q32_pos_s64=9 * Q32_ONE, lut_table_q32_s64=lut_table, ctr=None) == 1431655764


def _tensor_specs_tsae(*, vocab: int, seq: int, dm: int, de: int, layers: int, d_ff: int) -> list[dict[str, Any]]:
    req: dict[str, list[int]] = {
        "qxrl/tok_emb": [int(vocab), int(dm)],
        "qxrl/pos_emb": [int(seq), int(dm)],
    }
    for l in range(int(layers)):
        req[f"qxrl/tsae/l{l}/wq"] = [int(dm), int(dm)]
        req[f"qxrl/tsae/l{l}/wk"] = [int(dm), int(dm)]
        req[f"qxrl/tsae/l{l}/wv"] = [int(dm), int(dm)]
        req[f"qxrl/tsae/l{l}/wo"] = [int(dm), int(dm)]
        req[f"qxrl/tsae/l{l}/rms1_gamma"] = [int(dm)]
        req[f"qxrl/tsae/l{l}/rms2_gamma"] = [int(dm)]
        req[f"qxrl/tsae/l{l}/ff_w1"] = [int(d_ff), int(dm)]
        req[f"qxrl/tsae/l{l}/ff_b1"] = [int(d_ff)]
        req[f"qxrl/tsae/l{l}/ff_w2"] = [int(dm), int(d_ff)]
        req[f"qxrl/tsae/l{l}/ff_b2"] = [int(dm)]

    req["qxrl/tsae/proj_w"] = [int(de), int(dm)]
    req["qxrl/tsae/proj_b"] = [int(de)]

    req["qxrl/tok_proj_w"] = [int(de), int(dm)]
    req["qxrl/tok_proj_b"] = [int(de)]
    req["qxrl/out_emb"] = [int(vocab), int(de)]
    req["qxrl/out_b"] = [int(vocab)]

    specs: list[dict[str, Any]] = []
    for name, shape in sorted(req.items()):
        specs.append({"name": str(name), "shape_u32": list(shape), "dtype": "Q32_S64_V1", "trainable": True})
        mom = "qxrl/opt/mom/" + str(name)[len("qxrl/") :]
        specs.append({"name": str(mom), "shape_u32": list(shape), "dtype": "Q32_S64_V1", "trainable": False})
    specs.sort(key=lambda row: str(row.get("name", "")))
    return specs


def test_qxrl_tsae_topk_tie_determinism_phase5() -> None:
    opset_id = "opset:eudrs_u_v1:sha256:" + ("0" * 64)
    dc1_id = "dc1:q32_v1"

    vocab = 257
    seq = 4
    dm = 2
    de = 2

    n_layers = 1
    n_heads = 1
    d_head = 2
    d_ff = 2
    topk = 2

    model_obj: dict[str, Any] = {
        "schema_id": "qxrl_model_manifest_v1",
        "model_id": "sha256:" + ("0" * 64),
        "opset_id": opset_id,
        "dc1_id": dc1_id,
        "tokenizer_kind": "BYTE_TOK_257_V1",
        "vocab_size_u32": int(vocab),
        "seq_len_u32": int(seq),
        "encoder_kind": "TSAE_V1",
        "d_model_u32": int(dm),
        "d_embed_u32": int(de),
        "math": {
            "dot_kind": "DOT_Q32_SHIFT_END_V1",
            "div_kind": "DIV_Q32_POS_RNE_V1",
            "invsqrt_kind": "INVSQRT_Q32_NR_LUT_V1",
            "invsqrt_lut_manifest_ref": {
                "artifact_id": "sha256:" + ("0" * 64),
                "artifact_relpath": "polymath/registry/eudrs_u/manifests/sha256_" + ("0" * 64) + ".qxrl_invsqrt_lut_manifest_v1.json",
            },
        },
        "tsae": {
            "n_layers_u32": int(n_layers),
            "n_heads_u32": int(n_heads),
            "d_head_u32": int(d_head),
            "d_ff_u32": int(d_ff),
            "topk_u32": int(topk),
            "rms_epsilon_q32": {"q": 1},
            "inv_seq_len_q32": {"q": (1 << 32) // int(seq)},
        },
        "tensor_specs": _tensor_specs_tsae(vocab=vocab, seq=seq, dm=dm, de=de, layers=n_layers, d_ff=d_ff),
    }
    model_obj["model_id"] = compute_self_hash_id(model_obj, id_field="model_id")
    model = parse_qxrl_model_manifest_v1(model_obj)

    # All-zero weights make all attention scores tie; TopKDet must pick lowest indices.
    tok_emb = [0] * (vocab * dm)
    pos_emb = [0] * (seq * dm)
    out_emb = [0] * (vocab * de)
    out_b = [0] * vocab

    layer = QXRLTSAELayerWeightsV1(
        wq=[0] * (dm * dm),
        wk=[0] * (dm * dm),
        wv=[0] * (dm * dm),
        wo=[0] * (dm * dm),
        rms1_gamma=[0] * dm,
        rms2_gamma=[0] * dm,
        ff_w1=[0] * (d_ff * dm),
        ff_b1=[0] * d_ff,
        ff_w2=[0] * (dm * d_ff),
        ff_b2=[0] * dm,
    )
    weights = QXRLWeightsViewTSAEV1(
        tok_emb=tok_emb,
        pos_emb=pos_emb,
        layers=[layer],
        proj_w=[0] * (de * dm),
        proj_b=[0] * de,
        tok_proj_w=[0] * (de * dm),
        tok_proj_b=[0] * de,
        out_emb=out_emb,
        out_b=out_b,
    )

    lut_bytes = _gen_invsqrt_lut_bytes_phase5()
    lut_table = parse_invsqrt_lut_bin_v1(lut_bytes=lut_bytes)

    tokens = [1, 2, 3, 4]
    ctr1 = QXRLStepCountersV1()
    ctr2 = QXRLStepCountersV1()
    c1 = forward_encoder_tsae_v1(tokens_u32=tokens, model=model, weights=weights, lut_table_q32_s64=lut_table, ctr=ctr1, count_tokens=False)
    c2 = forward_encoder_tsae_v1(tokens_u32=tokens, model=model, weights=weights, lut_table_q32_s64=lut_table, ctr=ctr2, count_tokens=False)

    assert c1.layers[0].topk_idx_u32 == c2.layers[0].topk_idx_u32
    assert c1.xL_flat_q32_s64 == c2.xL_flat_q32_s64

    # Query i=2, head=0, K=2 -> base=4.
    assert c1.layers[0].topk_idx_u32[4:6] == [0, 1]


def test_verify_qxrl_v1_rejects_adamw_phase5(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root_tuple_obj, system_manifest_obj, determinism_cert_obj, bytes_by_id, _wroot_ref = _build_verify_qxrl_ctx_inmem(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        optimizer_kind="ADAMW_Q32_V1",
        lut_ref_artifact_id_override=None,
    )

    def _loader(ref: dict[str, str]) -> bytes:
        return bytes_by_id[ref["artifact_id"]]

    ok, reason = verify_qxrl_v1(
        root_tuple_obj=dict(root_tuple_obj),
        system_manifest_obj=dict(system_manifest_obj),
        determinism_cert_obj=dict(determinism_cert_obj),
        registry_loader=_loader,
    )
    assert ok is False
    assert reason == REASON_QXRL_OPTIMIZER_KIND_FORBIDDEN


def test_verify_qxrl_v1_rejects_lut_hash_mismatch_phase5(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    good = _gen_invsqrt_lut_bytes_phase5()
    bad = bytearray(good)
    bad[-1] ^= 1  # flip one byte inside the last entry (header remains correct)
    bad_art_id = sha256_prefixed(bytes(bad))
    assert bad_art_id != "sha256:f6b7eac00dae22340aefefc36692994958acb88933698f97968ae9cb37e97864"

    root_tuple_obj, system_manifest_obj, determinism_cert_obj, bytes_by_id, _wroot_ref = _build_verify_qxrl_ctx_inmem(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        optimizer_kind="SGD_MOMENTUM_Q32_V1",
        lut_ref_artifact_id_override=bad_art_id,
    )

    def _loader(ref: dict[str, str]) -> bytes:
        return bytes_by_id[ref["artifact_id"]]

    ok, reason = verify_qxrl_v1(
        root_tuple_obj=dict(root_tuple_obj),
        system_manifest_obj=dict(system_manifest_obj),
        determinism_cert_obj=dict(determinism_cert_obj),
        registry_loader=_loader,
    )
    assert ok is False
    assert reason == REASON_QXRL_OPSET_LUT_MISMATCH


def test_verify_eudrs_u_run_v1_accepts_qxrl_phase4_promotion(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Use a temp repo root override so verify_qxrl_v1 can load "currently-active" weights deterministically.
    repo_root = tmp_path / "repo"
    schema_dir = repo_root / "Genesis" / "schema" / "v18_0"

    import cdel.v18_0.omega_common_v1 as omega_common

    real_repo_root = Path(omega_common.__file__).resolve().parents[3]

    for name in [
        "eudrs_u_artifact_ref_v1",
        "eudrs_u_root_tuple_v1",
        "eudrs_u_system_manifest_v1",
        "eudrs_u_promotion_summary_v1",
        "dmpl_droot_v1",
        "dmpl_config_v1",
        "dmpl_modelpack_v1",
        "dmpl_params_bundle_v1",
        "qxrl_model_manifest_v1",
        "qxrl_dataset_manifest_v1",
        "qxrl_invsqrt_lut_manifest_v1",
        "qxrl_training_manifest_v1",
        "qxrl_eval_manifest_v1",
        "qxrl_eval_scorecard_v1",
        "determinism_cert_v1",
    ]:
        _copy_schema_file(real_repo_root=real_repo_root, out_schema_dir=schema_dir, name=name)

    monkeypatch.setenv("OMEGA_DEV_BENCHMARK_MODE", "1")
    monkeypatch.setenv("OMEGA_REPO_ROOT", str(repo_root))

    dc1_id = "dc1:q32_v1"
    opset_id = "opset:eudrs_u_v1:sha256:" + ("0" * 64)

    # Stable iroot manifest (to avoid triggering ML-index verification).
    iroot_obj = {"schema_id": "ml_index_root_ptr_v1", "dc1_id": dc1_id, "opset_id": opset_id}
    iroot_bytes = gcj1_canon_bytes(iroot_obj)
    iroot_art_id = sha256_prefixed(iroot_bytes)
    iroot_hex = iroot_art_id.split(":", 1)[1]
    iroot_rel = f"polymath/registry/eudrs_u/manifests/sha256_{iroot_hex}.ml_index_root_ptr_v1.json"
    iroot_ref = {"artifact_id": iroot_art_id, "artifact_relpath": iroot_rel}

    # Install a previous active root tuple (epoch 0) + initial weights under repo_root.
    init_manifest_obj, init_manifest_bytes, init_wroot_id, init_blocks = _fixture_initial_weights(opset_id=opset_id)
    init_wroot_hex = init_wroot_id.split(":", 1)[1]
    init_wroot_rel = f"polymath/registry/eudrs_u/weights/sha256_{init_wroot_hex}.weights_manifest_v1.json"
    (repo_root / Path(init_wroot_rel).parent).mkdir(parents=True, exist_ok=True)
    (repo_root / init_wroot_rel).write_bytes(init_manifest_bytes)
    for block_id, block_bytes in init_blocks.items():
        hex64 = block_id.split(":", 1)[1]
        rel = f"polymath/registry/eudrs_u/weights/blocks/sha256_{hex64}.q32_tensor_block_v1.bin"
        (repo_root / Path(rel).parent).mkdir(parents=True, exist_ok=True)
        (repo_root / rel).write_bytes(block_bytes)

    # Previous root tuple artifact (schema-valid, only wroot must exist).
    prev_epoch = 0
    zero_ref = {
        "artifact_id": "sha256:" + ("0" * 64),
        "artifact_relpath": "polymath/registry/eudrs_u/manifests/sha256_" + ("0" * 64) + ".placeholder.json",
    }
    prev_root_tuple_obj: dict[str, Any] = {
        "schema_id": "eudrs_u_root_tuple_v1",
        "epoch_u64": int(prev_epoch),
        "dc1_id": dc1_id,
        "opset_id": opset_id,
        "sroot": zero_ref,
        "oroot": zero_ref,
        "kroot": zero_ref,
        "croot": zero_ref,
        "droot": zero_ref,
        "mroot": zero_ref,
        "iroot": iroot_ref,
        "wroot": {"artifact_id": init_wroot_id, "artifact_relpath": init_wroot_rel},
        "stability_gate_bundle": zero_ref,
        "determinism_cert": zero_ref,
        "universality_cert": zero_ref,
    }
    prev_rt_bytes = gcj1_canon_bytes(prev_root_tuple_obj)
    prev_rt_id = sha256_prefixed(prev_rt_bytes)
    prev_rt_hex = prev_rt_id.split(":", 1)[1]
    prev_rt_rel = f"polymath/registry/eudrs_u/roots/sha256_{prev_rt_hex}.eudrs_u_root_tuple_v1.json"
    (repo_root / Path(prev_rt_rel).parent).mkdir(parents=True, exist_ok=True)
    (repo_root / prev_rt_rel).write_bytes(prev_rt_bytes)

    # Active root tuple pointer (repo root).
    active_ptr_path = repo_root / "polymath/registry/eudrs_u/active/active_root_tuple_ref_v1.json"
    active_ptr_path.parent.mkdir(parents=True, exist_ok=True)
    active_ptr_path.write_bytes(
        gcj1_canon_bytes(
            {
                "schema_id": "active_root_tuple_ref_v1",
                "active_root_tuple": {"artifact_id": prev_rt_id, "artifact_relpath": prev_rt_rel},
            }
        )
    )

    # Build staged state_dir with a content-addressed staged registry tree.
    state_dir = tmp_path / "state"
    evidence_dir = state_dir / "eudrs_u" / "evidence"
    staged_root = state_dir / "eudrs_u" / "staged_registry_tree"
    reg = staged_root / "polymath" / "registry" / "eudrs_u"
    reg.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)

    # Phase 5 pinned invsqrt LUT binary + manifest.
    lut_bytes = _gen_invsqrt_lut_bytes_phase5()
    lut_art_id = sha256_prefixed(lut_bytes)
    assert lut_art_id == "sha256:f6b7eac00dae22340aefefc36692994958acb88933698f97968ae9cb37e97864"
    lut_hex = lut_art_id.split(":", 1)[1]
    lut_rel = f"polymath/registry/eudrs_u/manifests/sha256_{lut_hex}.qxrl_invsqrt_lut_v1.bin"
    (staged_root / Path(lut_rel).parent).mkdir(parents=True, exist_ok=True)
    (staged_root / lut_rel).write_bytes(lut_bytes)
    lut_ref = {"artifact_id": lut_art_id, "artifact_relpath": lut_rel}

    lut_manifest_obj = {
        "schema_id": "qxrl_invsqrt_lut_manifest_v1",
        "lut_manifest_id": "sha256:" + ("0" * 64),
        "dc1_id": dc1_id,
        "opset_id": opset_id,
        "lut_kind": "INVSQRT_Q32_NR_LUT_V1",
        "lut_bits_u32": 10,
        "invsqrt_iters_u32": 2,
        "lut_ref": lut_ref,
    }
    lut_manifest_obj["lut_manifest_id"] = compute_self_hash_id(lut_manifest_obj, id_field="lut_manifest_id")
    lut_manifest_bytes = gcj1_canon_bytes(lut_manifest_obj)
    lut_manifest_art_id = sha256_prefixed(lut_manifest_bytes)
    lut_manifest_hex = lut_manifest_art_id.split(":", 1)[1]
    lut_manifest_rel = f"polymath/registry/eudrs_u/manifests/sha256_{lut_manifest_hex}.qxrl_invsqrt_lut_manifest_v1.json"
    (staged_root / Path(lut_manifest_rel).parent).mkdir(parents=True, exist_ok=True)
    (staged_root / lut_manifest_rel).write_bytes(lut_manifest_bytes)
    lut_manifest_ref = {"artifact_id": lut_manifest_art_id, "artifact_relpath": lut_manifest_rel}

    # QXRL model manifest.
    vocab = 257
    seq = 8
    dm = 2
    dh = 2
    de = 2
    model_obj = {
        "schema_id": "qxrl_model_manifest_v1",
        "model_id": "sha256:" + ("0" * 64),
        "opset_id": opset_id,
        "dc1_id": dc1_id,
        "tokenizer_kind": "BYTE_TOK_257_V1",
        "vocab_size_u32": vocab,
        "seq_len_u32": seq,
        "encoder_kind": "QRE_V1",
        "d_model_u32": dm,
        "d_embed_u32": de,
        "math": {
            "dot_kind": "DOT_Q32_SHIFT_END_V1",
            "div_kind": "DIV_Q32_POS_RNE_V1",
            "invsqrt_kind": "INVSQRT_Q32_NR_LUT_V1",
            "invsqrt_lut_manifest_ref": lut_manifest_ref,
        },
        "qre": {"d_hidden_u32": dh, "inv_seq_len_q32": {"q": (1 << 32) // seq}},
        "tensor_specs": _tensor_specs_qre(vocab=vocab, seq=seq, dm=dm, dh=dh, de=de),
    }
    model_obj["model_id"] = compute_self_hash_id(model_obj, id_field="model_id")
    model_bytes = gcj1_canon_bytes(model_obj)
    model_art_id = sha256_prefixed(model_bytes)
    model_hex = model_art_id.split(":", 1)[1]
    model_rel = f"polymath/registry/eudrs_u/manifests/sha256_{model_hex}.qxrl_model_manifest_v1.json"
    (staged_root / Path(model_rel).parent).mkdir(parents=True, exist_ok=True)
    (staged_root / model_rel).write_bytes(model_bytes)
    model_ref = {"artifact_id": model_art_id, "artifact_relpath": model_rel}
    model = parse_qxrl_model_manifest_v1(dict(model_obj))

    # Dataset segment + manifest.
    examples = [
        QXRLDatasetExampleV1(example_id_u64=i, anchor_tokens_u32=[i + 1] * 8, positive_tokens_u32=[i + 2] * 8)
        for i in range(4)
    ]
    seg_bytes = _encode_qxds_segment(examples=examples, vocab_size_u32=257, seq_len_u32=8)
    seg_path, seg_art_id = _write_hashed_bytes(
        out_dir=staged_root / "polymath/registry/eudrs_u/datasets/segments",
        suffix="qxrl_dataset_segment_v1.bin",
        raw=seg_bytes,
    )
    seg_rel = seg_path.relative_to(staged_root).as_posix()
    seg_digest32 = bytes.fromhex(seg_art_id.split(":", 1)[1])
    dataset_root_hash32 = hashlib.sha256(b"QXRL_DATASET_ROOT_V1" + seg_digest32).digest()

    dataset_obj: dict[str, Any] = {
        "schema_id": "qxrl_dataset_manifest_v1",
        "dataset_id": "sha256:" + ("0" * 64),
        "opset_id": opset_id,
        "dc1_id": dc1_id,
        "tokenizer_kind": "BYTE_TOK_257_V1",
        "dataset_kind": "PAIR_V1",
        "vocab_size_u32": 257,
        "seq_len_u32": 8,
        "segments": [
            {
                "segment_index_u32": 0,
                "record_count_u32": 4,
                "first_example_id_u64": 0,
                "last_example_id_u64": 3,
                "segment_ref": {"artifact_id": seg_art_id, "artifact_relpath": seg_rel},
            }
        ],
        "dataset_root_hash32_hex": dataset_root_hash32.hex(),
    }
    dataset_obj["dataset_id"] = compute_self_hash_id(dataset_obj, id_field="dataset_id")
    dataset_bytes = gcj1_canon_bytes(dataset_obj)
    dataset_art_id = sha256_prefixed(dataset_bytes)
    dataset_hex = dataset_art_id.split(":", 1)[1]
    dataset_rel = f"polymath/registry/eudrs_u/datasets/sha256_{dataset_hex}.qxrl_dataset_manifest_v1.json"
    (staged_root / Path(dataset_rel).parent).mkdir(parents=True, exist_ok=True)
    (staged_root / dataset_rel).write_bytes(dataset_bytes)
    dataset_ref = {"artifact_id": dataset_art_id, "artifact_relpath": dataset_rel}

    # Training manifest.
    tm: dict[str, Any] = {
        "schema_id": "qxrl_training_manifest_v1",
        "training_id": "sha256:" + ("0" * 64),
        "opset_id": opset_id,
        "dc1_id": dc1_id,
        "model_manifest_ref": model_ref,
        "dataset_manifest_ref": dataset_ref,
        "dot_kind": "DOT_Q32_SHIFT_END_V1",
        "optimizer_kind": "SGD_MOMENTUM_Q32_V1",
        "init_scale_q32": {"q": 1},
        "train_steps_u64": 1,
        "batch_size_u32": 2,
        "checkpoint_every_steps_u32": 1,
        "mask_prob_q32": {"q": 1 << 32},
        "max_masks_per_seq_u32": 2,
        "mlm_neg_k_u32": 2,
        "NEG_RESAMPLE_CAP_u32": 100,
        "mlm_margin_q32": {"q": 1 << 32},
        "ctr_margin_q32": {"q": 1 << 32},
        "mlm_loss_weight_q32": {"q": 1 << 32},
        "ctr_loss_weight_q32": {"q": 1 << 32},
        "lr_q32": {"q": 1 << 30},
        "momentum_q32": {"q": 0},
    }
    tm["training_id"] = compute_self_hash_id(tm, id_field="training_id")
    tm_bytes = gcj1_canon_bytes(tm)
    tm_art_id = sha256_prefixed(tm_bytes)
    tm_hex = tm_art_id.split(":", 1)[1]
    tm_rel = f"polymath/registry/eudrs_u/manifests/sha256_{tm_hex}.qxrl_training_manifest_v1.json"
    (staged_root / Path(tm_rel).parent).mkdir(parents=True, exist_ok=True)
    (staged_root / tm_rel).write_bytes(tm_bytes)
    tm_ref = {"artifact_id": tm_art_id, "artifact_relpath": tm_rel}

    # Replay training to compute final WRoot and H_train tail.
    init_weights = load_and_verify_weights_manifest_v1(
        weights_manifest_obj=dict(init_manifest_obj),
        registry_loader=lambda ref: init_blocks[ref["artifact_id"]],
    )
    final_bytes, final_wroot_id, final_obj, final_blocks_out, h_train_tail32, _dbg = replay_qxrl_training_v1(
        training_manifest_obj=tm,
        model=model,
        dataset_root_hash32=dataset_root_hash32,
        examples=examples,
        initial_weights_manifest_id=init_wroot_id,
        initial_weights_manifest=init_weights,
        registry_loader=lambda _ref: b"",
        return_debug=False,
    )
    assert final_blocks_out is not None

    final_wroot_hex = final_wroot_id.split(":", 1)[1]
    final_wroot_rel = f"polymath/registry/eudrs_u/weights/sha256_{final_wroot_hex}.weights_manifest_v1.json"
    (staged_root / Path(final_wroot_rel).parent).mkdir(parents=True, exist_ok=True)
    (staged_root / final_wroot_rel).write_bytes(final_bytes)
    for block_ref, block_bytes in final_blocks_out:
        rel = block_ref["artifact_relpath"]
        (staged_root / Path(rel).parent).mkdir(parents=True, exist_ok=True)
        (staged_root / rel).write_bytes(block_bytes)

    # Build eval manifest (scorecard_ref filled after scorecard computation).
    eval_obj: dict[str, Any] = {
        "schema_id": "qxrl_eval_manifest_v1",
        "eval_id": "sha256:" + ("0" * 64),
        "opset_id": opset_id,
        "dc1_id": dc1_id,
        "model_manifest_ref": model_ref,
        "dataset_manifest_ref": dataset_ref,
        "dot_kind": "DOT_Q32_SHIFT_END_V1",
        "eval_example_count_u32": 4,
        "eval_start_index_u64": 0,
        "mask_prob_q32": {"q": 1 << 32},
        "max_masks_per_seq_u32": 2,
        "mlm_neg_k_u32": 2,
        "NEG_RESAMPLE_CAP_u32": 100,
        "recall_k_u32": 2,
        "floors": {
            "masked_acc_at_1_min_q32": {"q": 0},
            "recall_at_k_min_q32": {"q": 0},
        },
        "checks": {"collapse_check_enabled": False, "drift_check_enabled": False},
        "scorecard_ref": {"artifact_id": "sha256:" + ("0" * 64), "artifact_relpath": "polymath/registry/eudrs_u/eval/sha256_" + ("0" * 64) + ".qxrl_eval_scorecard_v1.json"},
    }
    eval_obj["eval_id"] = compute_eval_id_config_hash(eval_obj)

    final_weights = load_and_verify_weights_manifest_v1(
        weights_manifest_obj=dict(final_obj),
        registry_loader=lambda ref: {r["artifact_id"]: b for r, b in final_blocks_out}[ref["artifact_id"]],
    )

    scorecard_obj, scorecard_bytes, scorecard_art_id, h_eval_tail32 = compute_qxrl_eval_scorecard_v1(
        eval_manifest_obj=eval_obj,
        model=model,
        model_manifest_id=model_art_id,
        dataset_manifest_obj=dataset_obj,
        dataset_root_hash32=dataset_root_hash32,
        examples=examples,
        weights_manifest_id=final_wroot_id,
        weights_manifest=final_weights,
        enforce_floors=True,
    )
    scorecard_hex = scorecard_art_id.split(":", 1)[1]
    scorecard_rel = f"polymath/registry/eudrs_u/eval/sha256_{scorecard_hex}.qxrl_eval_scorecard_v1.json"
    (staged_root / Path(scorecard_rel).parent).mkdir(parents=True, exist_ok=True)
    (staged_root / scorecard_rel).write_bytes(scorecard_bytes)

    # Finalize eval manifest now that scorecard is known.
    eval_obj["scorecard_ref"] = {"artifact_id": scorecard_art_id, "artifact_relpath": scorecard_rel}
    eval_obj["eval_id"] = compute_eval_id_config_hash(eval_obj)
    eval_bytes = gcj1_canon_bytes(eval_obj)
    eval_art_id = sha256_prefixed(eval_bytes)
    eval_hex = eval_art_id.split(":", 1)[1]
    eval_rel = f"polymath/registry/eudrs_u/manifests/sha256_{eval_hex}.qxrl_eval_manifest_v1.json"
    (staged_root / Path(eval_rel).parent).mkdir(parents=True, exist_ok=True)
    (staged_root / eval_rel).write_bytes(eval_bytes)
    eval_ref = {"artifact_id": eval_art_id, "artifact_relpath": eval_rel}

    # Determinism cert (Phase 4 required fields).
    det_obj = {
        "schema_id": "determinism_cert_v1",
        "epoch_u64": 1,
        "dc1_id": dc1_id,
        "opset_id": opset_id,
        "qxrl": {
            "training_manifest_ref": tm_ref,
            "h_train_tail32_hex": h_train_tail32.hex(),
            "h_eval_tail32_hex": h_eval_tail32.hex(),
            "math": {
                "dot_kind": str(model.dot_kind),
                "div_kind": str(model.div_kind),
                "invsqrt_kind": str(model.invsqrt_kind),
                "invsqrt_lut_manifest_ref": lut_manifest_ref,
                "invsqrt_iters_u32": 2,
            },
        },
    }
    det_bytes = gcj1_canon_bytes(det_obj)
    det_art_id = sha256_prefixed(det_bytes)
    det_hex = det_art_id.split(":", 1)[1]
    det_rel = f"polymath/registry/eudrs_u/certs/sha256_{det_hex}.determinism_cert_v1.json"
    (staged_root / Path(det_rel).parent).mkdir(parents=True, exist_ok=True)
    (staged_root / det_rel).write_bytes(det_bytes)
    det_ref = {"artifact_id": det_art_id, "artifact_relpath": det_rel}

    uni_obj = {"schema_id": "universality_cert_v1", "epoch_u64": 1, "dc1_id": dc1_id, "opset_id": opset_id}
    uni_bytes = gcj1_canon_bytes(uni_obj)
    uni_art_id = sha256_prefixed(uni_bytes)
    uni_hex = uni_art_id.split(":", 1)[1]
    uni_rel = f"polymath/registry/eudrs_u/certs/sha256_{uni_hex}.universality_cert_v1.json"
    (staged_root / Path(uni_rel).parent).mkdir(parents=True, exist_ok=True)
    (staged_root / uni_rel).write_bytes(uni_bytes)
    uni_ref = {"artifact_id": uni_art_id, "artifact_relpath": uni_rel}

    # Write staged iroot.
    (staged_root / Path(iroot_rel).parent).mkdir(parents=True, exist_ok=True)
    (staged_root / iroot_rel).write_bytes(iroot_bytes)

    # System manifest binds QXRL refs for verify_qxrl_v1.
    system_manifest_obj = {
        "schema_id": "eudrs_u_system_manifest_v1",
        "epoch_u64": 1,
        "dc1_id": dc1_id,
        "opset_id": opset_id,
        "qxwmr": {"world_model_manifest_ref": zero_ref, "eval_manifest_ref": zero_ref},
        "qxrl": {"model_manifest_ref": model_ref, "eval_manifest_ref": eval_ref, "dataset_manifest_ref": dataset_ref},
        "ml_index": {"index_manifest_ref": zero_ref, "bucket_listing_manifest_ref": zero_ref},
    }
    sm_bytes = gcj1_canon_bytes(system_manifest_obj)
    sm_art_id = sha256_prefixed(sm_bytes)
    sm_hex = sm_art_id.split(":", 1)[1]
    sm_rel = f"polymath/registry/eudrs_u/manifests/sha256_{sm_hex}.eudrs_u_system_manifest_v1.json"
    (staged_root / Path(sm_rel).parent).mkdir(parents=True, exist_ok=True)
    (staged_root / sm_rel).write_bytes(sm_bytes)
    sroot_ref = {"artifact_id": sm_art_id, "artifact_relpath": sm_rel}

    def _mk_ptr(name: str) -> dict[str, str]:
        obj = {"schema_id": name, "dc1_id": dc1_id, "opset_id": opset_id}
        raw = gcj1_canon_bytes(obj)
        art_id = sha256_prefixed(raw)
        hex64 = art_id.split(":", 1)[1]
        rel = f"polymath/registry/eudrs_u/manifests/sha256_{hex64}.{name}.json"
        (staged_root / Path(rel).parent).mkdir(parents=True, exist_ok=True)
        (staged_root / rel).write_bytes(raw)
        return {"artifact_id": art_id, "artifact_relpath": rel}

    # DMPL (Phase 1): minimal disabled config + droot binding.
    dmpl_leaf = b"DMPL/MERKLE/LEAF/v1\x00"
    dmpl_node = b"DMPL/MERKLE/NODE/v1\x00"
    tensor_bytes = b"DMPLTQ32" + struct.pack("<II", 1, 1) + struct.pack("<I", 1) + struct.pack("<q", 0)
    tensor_path, tensor_id = _write_hashed_bytes(
        out_dir=staged_root / "polymath/registry/eudrs_u/dmpl/tensors",
        suffix="dmpl_tensor_q32_v1.bin",
        raw=tensor_bytes,
    )
    del tensor_path
    tensors = [{"name": "t0", "shape_u32": [1], "tensor_bin_id": tensor_id}]

    def _bundle_root(tensors: list[dict[str, Any]]) -> str:
        leaf_hashes: list[bytes] = []
        for row in tensors:
            name = str(row["name"])
            digest32 = bytes.fromhex(str(row["tensor_bin_id"]).split(":", 1)[1])
            leaf_hashes.append(hashlib.sha256(dmpl_leaf + name.encode("utf-8") + b"\x00" + digest32).digest())
        level = list(leaf_hashes)
        while len(level) > 1:
            if len(level) % 2 == 1:
                level = level + [level[-1]]
            nxt: list[bytes] = []
            for i in range(0, len(level), 2):
                nxt.append(hashlib.sha256(dmpl_node + level[i] + level[i + 1]).digest())
            level = nxt
        return f"sha256:{level[0].hex()}"

    f_merkle = _bundle_root(tensors)
    v_merkle = _bundle_root(tensors)

    modelpack_obj = {
        "schema_id": "dmpl_modelpack_v1",
        "dc1_id": dc1_id,
        "opset_id": opset_id,
        "dims": {"d_u32": 1, "p_u32": 1, "embed_dim_u32": 1},
        "forward_arch_id": "dmpl_linear_pwl_v1",
        "value_arch_id": "dmpl_linear_v1",
        "activation_id": "hard_tanh_q32_v1",
        "gating_arch_id": "linear_gate_v1",
        "inverse_head_supported_b": False,
        "tensor_specs": [{"name": "t0", "shape_u32": [1], "role": "forward"}],
        "patch_policy": {"allowed_patch_types": ["matrix_patch", "lowrank_patch"], "vm_patch_allowed_b": False},
    }
    modelpack_bytes = gcj1_canon_bytes(modelpack_obj)
    modelpack_path, modelpack_id = _write_hashed_bytes(
        out_dir=staged_root / "polymath/registry/eudrs_u/dmpl/modelpacks",
        suffix="dmpl_modelpack_v1.json",
        raw=modelpack_bytes,
    )
    del modelpack_path

    fparams_obj = {
        "schema_id": "dmpl_params_bundle_v1",
        "dc1_id": dc1_id,
        "opset_id": opset_id,
        "bundle_kind": "F",
        "modelpack_id": modelpack_id,
        "tensors": tensors,
        "merkle_root": f_merkle,
    }
    fparams_bytes = gcj1_canon_bytes(fparams_obj)
    fparams_path, fparams_id = _write_hashed_bytes(
        out_dir=staged_root / "polymath/registry/eudrs_u/dmpl/params",
        suffix="dmpl_params_bundle_v1.json",
        raw=fparams_bytes,
    )
    del fparams_path

    vparams_obj = {
        "schema_id": "dmpl_params_bundle_v1",
        "dc1_id": dc1_id,
        "opset_id": opset_id,
        "bundle_kind": "V",
        "modelpack_id": modelpack_id,
        "tensors": tensors,
        "merkle_root": v_merkle,
    }
    vparams_bytes = gcj1_canon_bytes(vparams_obj)
    vparams_path, vparams_id = _write_hashed_bytes(
        out_dir=staged_root / "polymath/registry/eudrs_u/dmpl/params",
        suffix="dmpl_params_bundle_v1.json",
        raw=vparams_bytes,
    )
    del vparams_path

    caps_obj = {
        "K_ctx_u32": 0,
        "K_g_u32": 0,
        "max_concept_bytes_per_step_u32": 0,
        "max_retrieval_bytes_u32": 0,
        "max_retrieval_ops_u64": 0,
        "max_patch_rank_u32": 0,
        "max_patch_bytes_u32": 0,
        "max_patch_vm_steps_u32": 0,
        "H_u32": 0,
        "Nmax_u32": 0,
        "Ka_u32": 0,
        "beam_width_u32": 0,
        "max_trace_bytes_u32": 0,
        "max_node_opcount_u64": 0,
        "max_total_opcount_u64": 0,
        "train_steps_u32": 0,
        "batch_size_u32": 0,
        "max_grad_norm_q32": {"q": 0},
        "lr_q32": {"q": 0},
        "dataset_max_bytes_u64": 0,
        "max_stack_depth_u32": 0,
        "max_recursion_depth_u32": 0,
    }
    caps_digest = sha256_prefixed(gcj1_canon_bytes(caps_obj))

    config_obj = {
        "schema_id": "dmpl_config_v1",
        "dc1_id": dc1_id,
        "opset_id": opset_id,
        "enabled_b": False,
        "active_modelpack_id": modelpack_id,
        "fparams_bundle_id": fparams_id,
        "vparams_bundle_id": vparams_id,
        "caps": caps_obj,
        "retrieval_spec": {
            "ml_index_manifest_id": "sha256:" + ("0" * 64),
            "key_fn_id": "dmpl_key_v1",
            "score_fn_id": "ml_index_v1_default",
            "tie_rule_id": "score_desc_id_asc",
            "scan_cap_per_bucket_u32": 1,
            "K_ctx_u32": 0,
        },
        "gating_spec": {
            "normalize_weights_b": False,
            "epsilon_q32": {"q": 0},
            "pwl_pos_id": "pwl_pos_v1",
            "inv_q32_id": "",
            "inverse_head_enabled_b": False,
            "rev_err_threshold_q32": {"q": 0},
            "theta_cac_lb_q32": {"q": 0},
            "stab_thresholds": {"G0": {"q": 0}, "G1": {"q": 0}, "G2": {"q": 0}, "G3": {"q": 0}, "G4": {"q": 0}, "G5": {"q": 0}},
        },
        "planner_spec": {
            "algorithm_id": "dcbts_l_v1",
            "ladder_policy": {"ell_hi_u32": 0, "ell_lo_u32": 0, "refine_enabled_b": False, "refine_budget_u32": 0, "refine_per_step_budget_u32": 0},
            "action_source_id": "dmpl_action_enum_v1",
            "ordering_policy": {"primary_key_id": "upper_bound_primary_score_desc", "secondary_key_id": "depth_asc", "tertiary_key_id": "node_id_asc"},
            "aux_tie_break_policy": {"dl_proxy_enabled_b": False, "dl_proxy_id": "", "aux_allowed_only_on_exact_score_ties_b": True},
        },
        "hash_layout_ids": {
            "step_digest_layout_id": "dmpl_step_digest_v1",
            "trace_chain_layout_id": "dmpl_trace_chain_v1",
            "record_encoding_id": "lenpref_canonjson_v1",
            "chunking_rule_id": "fixed_1MiB_v1",
        },
        "objective_spec": {"gamma_q32": {"q": 0}, "reward_proxy_id": "ufc_proxy_v1", "ufc_objective_id": "ufc_v1_primary"},
    }
    config_bytes = gcj1_canon_bytes(config_obj)
    config_path, config_id = _write_hashed_bytes(
        out_dir=staged_root / "polymath/registry/eudrs_u/dmpl/configs",
        suffix="dmpl_config_v1.json",
        raw=config_bytes,
    )
    del config_path

    droot_obj = {
        "schema_id": "dmpl_droot_v1",
        "dc1_id": dc1_id,
        "opset_id": opset_id,
        "dmpl_config_id": config_id,
        "froot": f_merkle,
        "vroot": v_merkle,
        "caps_digest": caps_digest,
        "opset_semantics_id": opset_id,
    }
    droot_bytes = gcj1_canon_bytes(droot_obj)
    droot_path, droot_id = _write_hashed_bytes(
        out_dir=staged_root / "polymath/registry/eudrs_u/dmpl/roots",
        suffix="dmpl_droot_v1.json",
        raw=droot_bytes,
    )
    droot_ref = {"artifact_id": droot_id, "artifact_relpath": droot_path.relative_to(staged_root).as_posix()}

    # Root tuple (epoch 1) references staged content-addressed artifacts.
    root_tuple_obj = {
        "schema_id": "eudrs_u_root_tuple_v1",
        "epoch_u64": 1,
        "dc1_id": dc1_id,
        "opset_id": opset_id,
        "sroot": sroot_ref,
        "oroot": _mk_ptr("oroot_ptr_v1"),
        "kroot": _mk_ptr("kroot_ptr_v1"),
        "croot": _mk_ptr("croot_ptr_v1"),
        "droot": droot_ref,
        "mroot": _mk_ptr("mroot_ptr_v1"),
        "iroot": iroot_ref,
        "wroot": {"artifact_id": final_wroot_id, "artifact_relpath": final_wroot_rel},
        "stability_gate_bundle": _mk_ptr("stability_gate_bundle_v1"),
        "determinism_cert": det_ref,
        "universality_cert": uni_ref,
    }
    rt_bytes = gcj1_canon_bytes(root_tuple_obj)
    rt_art_id = sha256_prefixed(rt_bytes)
    rt_hex = rt_art_id.split(":", 1)[1]
    rt_rel = f"polymath/registry/eudrs_u/roots/sha256_{rt_hex}.eudrs_u_root_tuple_v1.json"
    (staged_root / Path(rt_rel).parent).mkdir(parents=True, exist_ok=True)
    (staged_root / rt_rel).write_bytes(rt_bytes)

    # Staged activation pointer must reference the target path without the staging prefix.
    staged_ptr = staged_root / "polymath/registry/eudrs_u/active/active_root_tuple_ref_v1.json"
    staged_ptr.parent.mkdir(parents=True, exist_ok=True)
    staged_ptr.write_bytes(
        gcj1_canon_bytes(
            {
                "schema_id": "active_root_tuple_ref_v1",
                "active_root_tuple": {"artifact_id": rt_art_id, "artifact_relpath": rt_rel},
            }
        )
    )

    # Evidence artifacts (required by promotion verifier).
    def _ev_json(schema_id: str, suffix: str, payload: dict[str, Any] | None = None) -> dict[str, str]:
        obj = {"schema_id": schema_id} if payload is None else dict(payload)
        path, aid = _write_hashed_bytes(out_dir=evidence_dir, suffix=suffix, raw=gcj1_canon_bytes(obj))
        return {"artifact_id": aid, "artifact_relpath": path.relative_to(state_dir).as_posix()}

    ev_weights = _write_hashed_bytes(out_dir=evidence_dir, suffix="weights_manifest_v1.json", raw=final_bytes)
    ev_det = _write_hashed_bytes(out_dir=evidence_dir, suffix="determinism_cert_v1.json", raw=det_bytes)
    ev_uni = _write_hashed_bytes(out_dir=evidence_dir, suffix="universality_cert_v1.json", raw=uni_bytes)

    evidence = {
        "weights_manifest_ref": {"artifact_id": ev_weights[1], "artifact_relpath": ev_weights[0].relative_to(state_dir).as_posix()},
        "ml_index_manifest_ref": _ev_json("ml_index_manifest_v1", "ml_index_manifest_v1.json"),
        "cac_ref": _ev_json("cac_v1", "cac_v1.json"),
        "ufc_ref": _ev_json("ufc_v1", "ufc_v1.json"),
        "cooldown_ledger_ref": _ev_json("cooldown_ledger_v1", "cooldown_ledger_v1.json"),
        "stability_metrics_ref": _ev_json("stability_metrics_v1", "stability_metrics_v1.json"),
        "determinism_cert_ref": {"artifact_id": ev_det[1], "artifact_relpath": ev_det[0].relative_to(state_dir).as_posix()},
        "universality_cert_ref": {"artifact_id": ev_uni[1], "artifact_relpath": ev_uni[0].relative_to(state_dir).as_posix()},
    }

    proposed_root_tuple_ref = {
        "artifact_id": rt_art_id,
        "artifact_relpath": f"eudrs_u/staged_registry_tree/{rt_rel}",
    }
    summary_obj = {
        "schema_id": "eudrs_u_promotion_summary_v1",
        "proposed_root_tuple_ref": proposed_root_tuple_ref,
        "staged_registry_tree_relpath": "eudrs_u/staged_registry_tree",
        "evidence": evidence,
    }
    _write_hashed_bytes(out_dir=evidence_dir, suffix="eudrs_u_promotion_summary_v1.json", raw=gcj1_canon_bytes(summary_obj))

    assert verify_eudrs_u_run(state_dir, mode="full") == "VALID"

    # Re-run to ensure no hidden mutable state affects determinism.
    assert verify_eudrs_u_run(state_dir, mode="full") == "VALID"


def test_verify_eudrs_u_run_v1_rejects_missing_state(tmp_path: Path) -> None:
    # Smoke negative: missing required state inputs must fail-closed.
    with pytest.raises(OmegaV18Error):
        # Minimal call; state_dir missing evidence should fail.
        verify_eudrs_u_run(tmp_path / "missing", mode="full")
