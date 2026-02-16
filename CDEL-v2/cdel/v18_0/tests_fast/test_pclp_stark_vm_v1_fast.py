from __future__ import annotations

import hashlib
import math
import struct
from pathlib import Path
from typing import Any

import pytest

from cdel.v18_0.eudrs_u.eudrs_u_hash_v1 import gcj1_canon_bytes, sha256_prefixed
from cdel.v18_0.eudrs_u.pclp_common_v1 import (
    EUDRSU_PCLP_BINDING_MISMATCH,
    EUDRSU_PCLP_CONFIG_MISMATCH,
    EUDRSU_PCLP_PROOF_INVALID,
    EUDRSU_PCLP_PUBLIC_INPUT_MISMATCH,
    EUDRSU_PCLP_SCHEMA_INVALID,
    EUDRSU_PCLP_UNSUPPORTED_MODE,
    compute_public_inputs_base_hash32,
    compute_public_inputs_hash32,
    compute_self_hash_id_omit,
    compute_rollhash32x2_commitments_v1,
    derive_pclp_tails_v1,
)
from cdel.v18_0.eudrs_u.poseidon_gld_v1 import gen_poseidon_params_gld_v1_bin
from cdel.v18_0.eudrs_u.qxrl_common_v1 import (
    compute_eval_id_config_hash,
    compute_self_hash_id,
)
from cdel.v18_0.eudrs_u.qxrl_dataset_v1 import QXRLDatasetExampleV1
from cdel.v18_0.eudrs_u.qxrl_eval_v1 import compute_qxrl_eval_scorecard_v1
from cdel.v18_0.eudrs_u.qxrl_forward_qre_v1 import parse_qxrl_model_manifest_v1
from cdel.v18_0.eudrs_u.qxrl_opset_math_v1 import parse_invsqrt_lut_bin_v1
from cdel.v18_0.eudrs_u.qxrl_train_replay_v1 import (
    WeightsBlockDescV1,
    WeightsTensorDescV1,
    load_and_verify_weights_manifest_v1,
    replay_qxrl_training_v1,
)
from cdel.v18_0.eudrs_u.verify_qxrl_v1 import verify_qxrl_v1
from cdel.v18_0.eudrs_u.vpvm_q32_programs_v1 import build_vpvm_program_qxrl_qre_train_eval_v1
from cdel.v18_0.eudrs_u.vpvm_stark_prover_v1 import (
    build_pclp_bundle_v1,
    build_stark_vm_proof_v1_bin,
    build_vpvm_config_v1,
    build_vpvm_public_inputs_v1,
)


def _find_superproject_root() -> Path | None:
    here = Path(__file__).resolve()
    found: Path | None = None
    for anc in [here, *here.parents]:
        if (anc / "Genesis/schema/v18_0").is_dir():
            # Prefer the outermost superproject root (AGI-Stack) over vendored CDEL-v2/Genesis.
            found = anc
    return found


_SUPERPROJECT_ROOT = _find_superproject_root()
if _SUPERPROJECT_ROOT is None:
    pytest.skip("requires Genesis schemas (run via AGI-Stack)", allow_module_level=True)


def _copy_schema_file(*, real_repo_root: Path, out_schema_dir: Path, name: str) -> None:
    assert _SUPERPROJECT_ROOT is not None
    src = _SUPERPROJECT_ROOT / "Genesis" / "schema" / "v18_0" / f"{name}.jsonschema"
    dst = out_schema_dir / f"{name}.jsonschema"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(src.read_bytes())


def _copy_required_schemas(*, real_repo_root: Path, out_schema_dir: Path) -> None:
    for name in [
        "eudrs_u_artifact_ref_v1",
        "qxrl_model_manifest_v1",
        "qxrl_dataset_manifest_v1",
        "qxrl_invsqrt_lut_manifest_v1",
        "qxrl_training_manifest_v1",
        "qxrl_eval_manifest_v1",
        "qxrl_eval_scorecard_v1",
        "pclp_bundle_v1",
        "vpvm_config_v1",
        "vpvm_public_inputs_v1",
        "stark_vm_proof_v1",
        "determinism_cert_v1",
    ]:
        _copy_schema_file(real_repo_root=real_repo_root, out_schema_dir=out_schema_dir, name=name)


def _encode_qxds_segment(*, examples: list[QXRLDatasetExampleV1], vocab_size_u32: int, seq_len_u32: int) -> bytes:
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
            block_ref={"artifact_id": "sha256:" + ("0" * 64), "artifact_relpath": "x"},
        )
    ]


def _fixture_initial_weights(*, opset_id: str) -> tuple[dict[str, Any], bytes, str, dict[str, bytes]]:
    # Matches the deterministic fixture used in test_qxrl_v1_run_verifier_fast.py.
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
        if y0 > (1 << 63) - 1:
            y0 = (1 << 63) - 1
        out += struct.pack("<q", int(y0))
    return bytes(out)


def _install_active_root_tuple_with_init_weights(
    *,
    repo_root: Path,
    dc1_id: str,
    opset_id: str,
    init_manifest_bytes: bytes,
    init_wroot_id: str,
    init_blocks_by_id: dict[str, bytes],
) -> None:
    init_hex = init_wroot_id.split(":", 1)[1]
    init_rel = f"polymath/registry/eudrs_u/weights/sha256_{init_hex}.weights_manifest_v1.json"
    (repo_root / Path(init_rel).parent).mkdir(parents=True, exist_ok=True)
    (repo_root / init_rel).write_bytes(init_manifest_bytes)
    for block_id, block_bytes in init_blocks_by_id.items():
        block_hex = block_id.split(":", 1)[1]
        block_rel = f"polymath/registry/eudrs_u/weights/blocks/sha256_{block_hex}.q32_tensor_block_v1.bin"
        (repo_root / Path(block_rel).parent).mkdir(parents=True, exist_ok=True)
        (repo_root / block_rel).write_bytes(block_bytes)

    init_wroot_ref = {"artifact_id": init_wroot_id, "artifact_relpath": init_rel}

    prev_root_tuple_obj: dict[str, Any] = {
        "schema_id": "eudrs_u_root_tuple_v1",
        "epoch_u64": 0,
        "dc1_id": str(dc1_id),
        "opset_id": str(opset_id),
        "wroot": init_wroot_ref,
    }
    prev_root_tuple_bytes = gcj1_canon_bytes(prev_root_tuple_obj)
    prev_root_tuple_id = sha256_prefixed(prev_root_tuple_bytes)
    prev_hex = prev_root_tuple_id.split(":", 1)[1]
    prev_rel = f"polymath/registry/eudrs_u/roots/sha256_{prev_hex}.eudrs_u_root_tuple_v1.json"
    (repo_root / Path(prev_rel).parent).mkdir(parents=True, exist_ok=True)
    (repo_root / prev_rel).write_bytes(prev_root_tuple_bytes)

    ptr_obj = {
        "schema_id": "active_root_tuple_ref_v1",
        "active_root_tuple": {"artifact_id": prev_root_tuple_id, "artifact_relpath": prev_rel},
    }
    ptr_rel = "polymath/registry/eudrs_u/active/active_root_tuple_ref_v1.json"
    (repo_root / Path(ptr_rel).parent).mkdir(parents=True, exist_ok=True)
    (repo_root / ptr_rel).write_bytes(gcj1_canon_bytes(ptr_obj))


def _build_valid_qre_pclp_ctx(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    repo_root = tmp_path / "repo"
    schema_dir = repo_root / "Genesis" / "schema" / "v18_0"

    import cdel.v18_0.omega_common_v1 as omega_common

    real_repo_root = Path(omega_common.__file__).resolve().parents[3]
    _copy_required_schemas(real_repo_root=real_repo_root, out_schema_dir=schema_dir)

    monkeypatch.setenv("OMEGA_DEV_BENCHMARK_MODE", "1")
    monkeypatch.setenv("OMEGA_REPO_ROOT", str(repo_root))

    dc1_id = "dc1:q32_v1"
    opset_id = "opset:eudrs_u_v1:sha256:" + ("0" * 64)

    init_manifest_obj, init_manifest_bytes, init_wroot_id, init_blocks_by_id = _fixture_initial_weights(opset_id=opset_id)
    _install_active_root_tuple_with_init_weights(
        repo_root=repo_root,
        dc1_id=dc1_id,
        opset_id=opset_id,
        init_manifest_bytes=init_manifest_bytes,
        init_wroot_id=init_wroot_id,
        init_blocks_by_id=init_blocks_by_id,
    )

    bytes_by_id: dict[str, bytes] = {}

    # Phase 5 pinned LUT bytes + manifest.
    lut_bytes = _gen_invsqrt_lut_bytes_phase5()
    lut_art_id = sha256_prefixed(lut_bytes)
    lut_hex = lut_art_id.split(":", 1)[1]
    lut_rel = f"polymath/registry/eudrs_u/manifests/sha256_{lut_hex}.qxrl_invsqrt_lut_v1.bin"
    lut_ref = {"artifact_id": lut_art_id, "artifact_relpath": lut_rel}

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

    bytes_by_id[str(lut_art_id)] = bytes(lut_bytes)
    bytes_by_id[str(lut_manifest_art_id)] = bytes(lut_manifest_bytes)

    # QRE model manifest.
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
            "dot_kind": "DOT_Q32_SHIFT_EACH_DIM_V1",
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
    bytes_by_id[str(model_art_id)] = bytes(model_bytes)

    # Dataset segment + manifest.
    examples = [QXRLDatasetExampleV1(example_id_u64=i, anchor_tokens_u32=[i + 1] * seq, positive_tokens_u32=[i + 2] * seq) for i in range(4)]
    seg_bytes = _encode_qxds_segment(examples=examples, vocab_size_u32=vocab, seq_len_u32=seq)
    seg_art_id = sha256_prefixed(seg_bytes)
    seg_hex = seg_art_id.split(":", 1)[1]
    seg_rel = f"polymath/registry/eudrs_u/datasets/segments/sha256_{seg_hex}.qxrl_dataset_segment_v1.bin"
    seg_ref = {"artifact_id": seg_art_id, "artifact_relpath": seg_rel}
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
                "segment_ref": seg_ref,
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

    bytes_by_id[str(seg_art_id)] = bytes(seg_bytes)
    bytes_by_id[str(dataset_art_id)] = bytes(dataset_bytes)

    # Training manifest.
    tm: dict[str, Any] = {
        "schema_id": "qxrl_training_manifest_v1",
        "training_id": "sha256:" + ("0" * 64),
        "opset_id": opset_id,
        "dc1_id": dc1_id,
        "model_manifest_ref": model_ref,
        "dataset_manifest_ref": dataset_ref,
        "dot_kind": "DOT_Q32_SHIFT_EACH_DIM_V1",
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
    tm_ref = {"artifact_id": tm_art_id, "artifact_relpath": tm_rel}
    bytes_by_id[str(tm_art_id)] = bytes(tm_bytes)

    # Replay training to obtain final weights + H_train tail.
    # Note: replay_qxrl_training_v1 mutates the weights manifest in-place; load twice so we
    # can keep an immutable snapshot of the initial weights for commitments/proof binding.
    init_weights_replay = load_and_verify_weights_manifest_v1(
        weights_manifest_obj=dict(init_manifest_obj),
        registry_loader=lambda ref: init_blocks_by_id[ref["artifact_id"]],
    )
    init_weights = load_and_verify_weights_manifest_v1(
        weights_manifest_obj=dict(init_manifest_obj),
        registry_loader=lambda ref: init_blocks_by_id[ref["artifact_id"]],
    )
    final_bytes, final_wroot_id, final_obj, final_blocks_out, h_train_tail32, _dbg = replay_qxrl_training_v1(
        training_manifest_obj=tm,
        model=model,
        dataset_root_hash32=dataset_root_hash32,
        examples=examples,
        initial_weights_manifest_id=init_wroot_id,
        initial_weights_manifest=init_weights_replay,
        registry_loader=lambda _ref: b"",
        return_debug=False,
    )
    assert final_blocks_out is not None
    bytes_by_id[str(final_wroot_id)] = bytes(final_bytes)
    final_blocks_by_id = {ref["artifact_id"]: b for ref, b in final_blocks_out}
    for bid, b in final_blocks_by_id.items():
        bytes_by_id[str(bid)] = bytes(b)

    final_wroot_hex = final_wroot_id.split(":", 1)[1]
    final_wroot_rel = f"polymath/registry/eudrs_u/weights/sha256_{final_wroot_hex}.weights_manifest_v1.json"
    final_wroot_ref = {"artifact_id": final_wroot_id, "artifact_relpath": final_wroot_rel}

    # Build eval manifest, compute scorecard, then finalize eval manifest with scorecard_ref.
    eval_obj: dict[str, Any] = {
        "schema_id": "qxrl_eval_manifest_v1",
        "eval_id": "sha256:" + ("0" * 64),
        "opset_id": opset_id,
        "dc1_id": dc1_id,
        "model_manifest_ref": model_ref,
        "dataset_manifest_ref": dataset_ref,
        "dot_kind": "DOT_Q32_SHIFT_EACH_DIM_V1",
        "eval_example_count_u32": 4,
        "eval_start_index_u64": 0,
        "mask_prob_q32": {"q": 1 << 32},
        "max_masks_per_seq_u32": 2,
        "mlm_neg_k_u32": 2,
        "NEG_RESAMPLE_CAP_u32": 100,
        "recall_k_u32": 2,
        "floors": {"masked_acc_at_1_min_q32": {"q": 0}, "recall_at_k_min_q32": {"q": 0}},
        "checks": {"collapse_check_enabled": False, "drift_check_enabled": False},
        "scorecard_ref": {"artifact_id": "sha256:" + ("0" * 64), "artifact_relpath": "polymath/registry/eudrs_u/eval/sha256_" + ("0" * 64) + ".qxrl_eval_scorecard_v1.json"},
    }
    eval_obj["eval_id"] = compute_eval_id_config_hash(eval_obj)

    final_weights = load_and_verify_weights_manifest_v1(weights_manifest_obj=dict(final_obj), registry_loader=lambda ref: final_blocks_by_id[ref["artifact_id"]])
    scorecard_obj, scorecard_bytes, scorecard_art_id, h_eval_tail32 = compute_qxrl_eval_scorecard_v1(
        eval_manifest_obj=eval_obj,
        model=model,
        model_manifest_id=str(model_art_id),
        dataset_manifest_obj=dataset_obj,
        dataset_root_hash32=dataset_root_hash32,
        examples=examples,
        weights_manifest_id=final_wroot_id,
        weights_manifest=final_weights,
        enforce_floors=True,
    )
    scorecard_hex = scorecard_art_id.split(":", 1)[1]
    scorecard_rel = f"polymath/registry/eudrs_u/eval/sha256_{scorecard_hex}.qxrl_eval_scorecard_v1.json"
    scorecard_ref = {"artifact_id": scorecard_art_id, "artifact_relpath": scorecard_rel}
    bytes_by_id[str(scorecard_art_id)] = bytes(scorecard_bytes)

    eval_obj["scorecard_ref"] = scorecard_ref
    eval_obj["eval_id"] = compute_eval_id_config_hash(eval_obj)
    eval_bytes = gcj1_canon_bytes(eval_obj)
    eval_art_id = sha256_prefixed(eval_bytes)
    eval_hex = eval_art_id.split(":", 1)[1]
    eval_rel = f"polymath/registry/eudrs_u/manifests/sha256_{eval_hex}.qxrl_eval_manifest_v1.json"
    eval_ref = {"artifact_id": eval_art_id, "artifact_relpath": eval_rel}
    bytes_by_id[str(eval_art_id)] = bytes(eval_bytes)

    # System manifest binds QXRL refs.
    system_manifest_obj: dict[str, Any] = {
        "schema_id": "eudrs_u_system_manifest_v1",
        "epoch_u64": 1,
        "dc1_id": dc1_id,
        "opset_id": opset_id,
        "qxrl": {"model_manifest_ref": model_ref, "eval_manifest_ref": eval_ref, "dataset_manifest_ref": dataset_ref},
    }

    # Root tuple references the final WRoot.
    root_tuple_obj: dict[str, Any] = {
        "schema_id": "eudrs_u_root_tuple_v1",
        "epoch_u64": 1,
        "dc1_id": dc1_id,
        "opset_id": opset_id,
        "wroot": final_wroot_ref,
    }

    # Determinism cert includes PCLP ref (filled after bundle creation).
    determinism_cert_obj: dict[str, Any] = {
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

    # Poseidon params (real binary artifact; pinned by config schema and artifact refs).
    poseidon_params_bytes = gen_poseidon_params_gld_v1_bin(rf_u32=8, rp_u32=22, seed=b"VPVM_POSEIDON_GLD_V1_SEED")
    poseidon_params_id = sha256_prefixed(poseidon_params_bytes)
    poseidon_params_ref = {"artifact_id": poseidon_params_id, "artifact_relpath": "polymath/registry/eudrs_u/pclp/sha256_" + poseidon_params_id.split(":", 1)[1] + ".poseidon_params_gld_v1.bin"}
    bytes_by_id[str(poseidon_params_id)] = bytes(poseidon_params_bytes)

    # Build VPVM config/program/public inputs/proof + PCLP bundle.
    vpvm_config_obj, vpvm_config_bytes, vpvm_config_ref = build_vpvm_config_v1(
        opset_id=opset_id,
        max_steps_u32=1 << 16,
        poseidon_params_ref=poseidon_params_ref,
    )
    bytes_by_id[str(vpvm_config_ref["artifact_id"])] = bytes(vpvm_config_bytes)

    program_bytes = build_vpvm_program_qxrl_qre_train_eval_v1(
        opset_id=opset_id,
        training_manifest_id=tm_ref["artifact_id"],
        dataset_manifest_id=dataset_ref["artifact_id"],
        eval_manifest_id=eval_ref["artifact_id"],
        lut_manifest_id=lut_manifest_ref["artifact_id"],
        wroot_before_id=init_wroot_id,
        wroot_after_id=final_wroot_id,
    )
    program_id = sha256_prefixed(program_bytes)
    program_ref = {"artifact_id": program_id, "artifact_relpath": "polymath/registry/eudrs_u/pclp/sha256_" + program_id.split(":", 1)[1] + ".vpvm_program_v1.bin"}
    bytes_by_id[str(program_id)] = bytes(program_bytes)

    # Compute proof-mode tails (Option 2): derive from PI base hash + artifact ids + program id.
    _pi_tmp_obj, _pi_tmp_bytes, _pi_tmp_ref, pi_base_hash32, _main_trace_root32 = build_vpvm_public_inputs_v1(
        opset_id=opset_id,
        training_manifest_id=tm_ref["artifact_id"],
        dataset_manifest_id=dataset_ref["artifact_id"],
        eval_manifest_id=eval_ref["artifact_id"],
        lut_manifest_id=lut_manifest_ref["artifact_id"],
        wroot_before_id=init_wroot_id,
        wroot_after_id=final_wroot_id,
        h_train_tail32_hex_expected="0" * 64,
        h_eval_tail32_hex_expected="0" * 64,
        scorecard_artifact_id_expected=scorecard_art_id,
        vpvm_config_obj=vpvm_config_obj,
        poseidon_params_bin=poseidon_params_bytes,
        program_bytes=program_bytes,
        lut_bytes=lut_bytes,
        examples=examples,
        weights_before=init_weights,
        weights_after=final_weights,
    )
    h_train_pclp32, h_eval_pclp32 = derive_pclp_tails_v1(
        poseidon_params_bin=poseidon_params_bytes,
        public_inputs_base_hash32=pi_base_hash32,
        wroot_before_id=init_wroot_id,
        wroot_after_id=final_wroot_id,
        program_id=program_id,
        scorecard_artifact_id=scorecard_art_id,
        eval_manifest_id=eval_art_id,
    )
    h_train_pclp_hex = h_train_pclp32.hex()
    h_eval_pclp_hex = h_eval_pclp32.hex()

    vpvm_public_inputs_obj, vpvm_public_inputs_bytes, vpvm_public_inputs_ref, _pi_base_hash32_2, _main_trace_root32_2 = build_vpvm_public_inputs_v1(
        opset_id=opset_id,
        training_manifest_id=tm_ref["artifact_id"],
        dataset_manifest_id=dataset_ref["artifact_id"],
        eval_manifest_id=eval_ref["artifact_id"],
        lut_manifest_id=lut_manifest_ref["artifact_id"],
        wroot_before_id=init_wroot_id,
        wroot_after_id=final_wroot_id,
        h_train_tail32_hex_expected=h_train_pclp_hex,
        h_eval_tail32_hex_expected=h_eval_pclp_hex,
        scorecard_artifact_id_expected=scorecard_art_id,
        vpvm_config_obj=vpvm_config_obj,
        poseidon_params_bin=poseidon_params_bytes,
        program_bytes=program_bytes,
        lut_bytes=lut_bytes,
        examples=examples,
        weights_before=init_weights,
        weights_after=final_weights,
    )
    assert bytes(_pi_base_hash32_2) == bytes(pi_base_hash32)
    bytes_by_id[str(vpvm_public_inputs_ref["artifact_id"])] = bytes(vpvm_public_inputs_bytes)

    _proof_header_obj, proof_bytes, proof_ref = build_stark_vm_proof_v1_bin(
        vpvm_config_obj=vpvm_config_obj,
        poseidon_params_bin=poseidon_params_bytes,
        vpvm_public_inputs_obj=vpvm_public_inputs_obj,
        program_bytes=program_bytes,
        lut_bytes=lut_bytes,
        examples=examples,
        weights_before=init_weights,
        weights_after=final_weights,
    )
    bytes_by_id[str(proof_ref["artifact_id"])] = bytes(proof_bytes)

    pclp_bundle_obj, pclp_bundle_bytes, pclp_bundle_ref = build_pclp_bundle_v1(
        vpvm_config_ref=vpvm_config_ref,
        public_inputs_ref=vpvm_public_inputs_ref,
        program_bin_ref=program_ref,
        proof_bin_ref=proof_ref,
        opset_id=opset_id,
        training_manifest_ref=tm_ref,
        dataset_manifest_ref=dataset_ref,
        eval_manifest_ref=eval_ref,
        invsqrt_lut_manifest_ref=lut_manifest_ref,
        wroot_after_ref=final_wroot_ref,
        h_train_tail32_hex=h_train_pclp_hex,
        scorecard_ref=scorecard_ref,
        h_eval_tail32_hex=h_eval_pclp_hex,
        reason_code_on_fail=EUDRSU_PCLP_PROOF_INVALID,
    )
    bytes_by_id[str(pclp_bundle_ref["artifact_id"])] = bytes(pclp_bundle_bytes)

    determinism_cert_obj["pclp"] = {
        "pclp_bundle_ref": pclp_bundle_ref,
        "proof_mode": "PCLP_STARK_VM_V1",
        "h_train_pclp_tail32_hex": h_train_pclp_hex,
        "h_eval_pclp_tail32_hex": h_eval_pclp_hex,
    }

    return {
        "repo_root": repo_root,
        "root_tuple_obj": root_tuple_obj,
        "system_manifest_obj": system_manifest_obj,
        "determinism_cert_obj": determinism_cert_obj,
        "bytes_by_id": bytes_by_id,
        "vpvm_config_obj": vpvm_config_obj,
        "vpvm_public_inputs_obj": vpvm_public_inputs_obj,
        "program_bytes": program_bytes,
        "proof_bytes": proof_bytes,
        "poseidon_params_bytes": poseidon_params_bytes,
        "poseidon_params_ref": poseidon_params_ref,
        "lut_bytes": lut_bytes,
        "examples": examples,
        "weights_before": init_weights,
        "weights_after": final_weights,
        "vpvm_config_ref": vpvm_config_ref,
        "vpvm_public_inputs_ref": vpvm_public_inputs_ref,
        "program_ref": program_ref,
        "proof_ref": proof_ref,
        "pclp_bundle_ref": pclp_bundle_ref,
        "pclp_bundle_obj": pclp_bundle_obj,
        "replay": {
            "final_bytes": final_bytes,
            "final_wroot_id": final_wroot_id,
            "final_obj": final_obj,
            "final_blocks_out": final_blocks_out,
            "h_train_tail32": h_train_tail32,
            "scorecard_obj": scorecard_obj,
            "scorecard_bytes": scorecard_bytes,
            "scorecard_art_id": scorecard_art_id,
            "h_eval_tail32": h_eval_tail32,
        },
        "refs": {
            "model_ref": model_ref,
            "dataset_ref": dataset_ref,
            "eval_ref": eval_ref,
            "tm_ref": tm_ref,
            "lut_manifest_ref": lut_manifest_ref,
            "scorecard_ref": scorecard_ref,
        },
    }


def test_pclp_bundle_id_self_hash_v1() -> None:
    obj: dict[str, Any] = {
        "schema_id": "pclp_bundle_v1",
        "pclp_bundle_id": "sha256:" + ("0" * 64),
        "proof_system_id": "stark_vm_v1",
        "vpvm_id": "vpvm_q32_v1",
        "vpvm_config_ref": {"artifact_id": "sha256:" + ("1" * 64), "artifact_relpath": "x"},
        "public_inputs_ref": {"artifact_id": "sha256:" + ("2" * 64), "artifact_relpath": "x"},
        "program_bin_ref": {"artifact_id": "sha256:" + ("3" * 64), "artifact_relpath": "x"},
        "proof_bin_ref": {"artifact_id": "sha256:" + ("4" * 64), "artifact_relpath": "x"},
        "bindings": {
            "opset_id": "opset:eudrs_u_v1:sha256:" + ("0" * 64),
            "dc1_id": "dc1:q32_v1",
            "training_manifest_ref": {"artifact_id": "sha256:" + ("5" * 64), "artifact_relpath": "x"},
            "dataset_manifest_ref": {"artifact_id": "sha256:" + ("6" * 64), "artifact_relpath": "x"},
            "eval_manifest_ref": {"artifact_id": "sha256:" + ("7" * 64), "artifact_relpath": "x"},
            "invsqrt_lut_manifest_ref": {"artifact_id": "sha256:" + ("8" * 64), "artifact_relpath": "x"},
        },
        "expected_outputs": {
            "wroot_after_ref": {"artifact_id": "sha256:" + ("9" * 64), "artifact_relpath": "x"},
            "h_train_tail32_hex": "0" * 64,
            "scorecard_ref": {"artifact_id": "sha256:" + ("a" * 64), "artifact_relpath": "x"},
            "h_eval_tail32_hex": "1" * 64,
            "reason_code_on_fail": EUDRSU_PCLP_PROOF_INVALID,
        },
    }
    h = compute_self_hash_id_omit(obj, id_field="pclp_bundle_id")
    obj["pclp_bundle_id"] = h
    assert compute_self_hash_id_omit(obj, id_field="pclp_bundle_id") == h


def test_vpvm_public_inputs_hash_rule_v1() -> None:
    pi: dict[str, Any] = {
        "opset_id": "opset:eudrs_u_v1:sha256:" + ("0" * 64),
        "dc1_id": "dc1:q32_v1",
        "training_manifest_id": "sha256:" + ("1" * 64),
        "dataset_manifest_id": "sha256:" + ("2" * 64),
        "eval_manifest_id": "sha256:" + ("3" * 64),
        "lut_manifest_id": "sha256:" + ("4" * 64),
        "wroot_before_id": "sha256:" + ("5" * 64),
        "wroot_after_id": "sha256:" + ("6" * 64),
        "h_train_tail32_hex_expected": "0" * 64,
        "h_eval_tail32_hex_expected": "1" * 64,
        "scorecard_artifact_id_expected": "sha256:" + ("7" * 64),
        "caps": {},
        "commitments": {
            "commit_algo_id": "rollhash32_v1",
            "r_bind_u64": 1,
            "weights_before_commit_f": 0,
            "weights_after_commit_f": 0,
            "dataset_commit_f": 0,
            "lut_commit_f": 0,
            "program_commit_f": 0,
        },
    }
    h = compute_public_inputs_hash32(pi)
    assert isinstance(h, (bytes, bytearray)) and len(h) == 32


def test_rollhash_commitments_v1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _build_valid_qre_pclp_ctx(tmp_path=tmp_path, monkeypatch=monkeypatch)
    pi_obj = dict(ctx["vpvm_public_inputs_obj"]["public_inputs"])
    declared = dict(pi_obj["commitments"])
    r_bind_u64_0 = int(declared["r_bind_u64_0"])
    r_bind_u64_1 = int(declared["r_bind_u64_1"])
    commits = compute_rollhash32x2_commitments_v1(
        r_bind_u64_0=r_bind_u64_0,
        r_bind_u64_1=r_bind_u64_1,
        program_bytes=bytes(ctx["program_bytes"]),
        lut_bytes=bytes(ctx["lut_bytes"]),
        examples=list(ctx["examples"]),
        weights_before=ctx["weights_before"],
        weights_after=ctx["weights_after"],
    )
    for k in [
        "program_commit_f0",
        "program_commit_f1",
        "lut_commit_f0",
        "lut_commit_f1",
        "dataset_commit_f0",
        "dataset_commit_f1",
        "weights_before_commit_f0",
        "weights_before_commit_f1",
        "weights_after_commit_f0",
        "weights_after_commit_f1",
    ]:
        assert int(commits[k]) == int(declared[k])


def test_audit_mode_forces_replay_even_with_pclp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _build_valid_qre_pclp_ctx(tmp_path=tmp_path, monkeypatch=monkeypatch)

    import cdel.v18_0.eudrs_u.verify_qxrl_v1 as vmod

    called = {"train": False, "eval": False}

    def _replay_stub(**_kwargs: Any) -> Any:
        called["train"] = True
        r = ctx["replay"]
        return r["final_bytes"], r["final_wroot_id"], r["final_obj"], r["final_blocks_out"], r["h_train_tail32"], None

    def _eval_stub(**_kwargs: Any) -> Any:
        called["eval"] = True
        r = ctx["replay"]
        return r["scorecard_obj"], r["scorecard_bytes"], r["scorecard_art_id"], r["h_eval_tail32"]

    monkeypatch.setattr(vmod, "replay_qxrl_training_v1", _replay_stub)
    monkeypatch.setattr(vmod, "compute_qxrl_eval_scorecard_v1", _eval_stub)

    def _loader(ref: dict[str, str]) -> bytes:
        return ctx["bytes_by_id"][ref["artifact_id"]]

    ok, reason = verify_qxrl_v1(
        root_tuple_obj=dict(ctx["root_tuple_obj"]),
        system_manifest_obj=dict(ctx["system_manifest_obj"]),
        determinism_cert_obj=dict(ctx["determinism_cert_obj"]),
        registry_loader=_loader,
        mode="audit",
    )
    assert ok is True
    assert reason == "EUDRSU_OK"
    assert called["train"] is True
    assert called["eval"] is True


def test_failure_schema_invalid_bundle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _build_valid_qre_pclp_ctx(tmp_path=tmp_path, monkeypatch=monkeypatch)
    bundle_ref = ctx["pclp_bundle_ref"]
    # Non-canonical JSON (no trailing newline) should map to schema invalid.
    ctx["bytes_by_id"][bundle_ref["artifact_id"]] = b"{}"

    def _loader(ref: dict[str, str]) -> bytes:
        return ctx["bytes_by_id"][ref["artifact_id"]]

    ok, reason = verify_qxrl_v1(
        root_tuple_obj=dict(ctx["root_tuple_obj"]),
        system_manifest_obj=dict(ctx["system_manifest_obj"]),
        determinism_cert_obj=dict(ctx["determinism_cert_obj"]),
        registry_loader=_loader,
        mode="full",
    )
    assert ok is False
    assert reason == EUDRSU_PCLP_SCHEMA_INVALID


def test_failure_binding_mismatch_opset_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _build_valid_qre_pclp_ctx(tmp_path=tmp_path, monkeypatch=monkeypatch)
    bundle_ref = ctx["pclp_bundle_ref"]
    bundle_obj = dict(ctx["pclp_bundle_obj"])
    bundle_obj["bindings"] = dict(bundle_obj["bindings"])
    bundle_obj["bindings"]["opset_id"] = "opset:eudrs_u_v1:sha256:" + ("f" * 64)
    bundle_obj["pclp_bundle_id"] = compute_self_hash_id_omit(bundle_obj, id_field="pclp_bundle_id")
    ctx["bytes_by_id"][bundle_ref["artifact_id"]] = gcj1_canon_bytes(bundle_obj)

    def _loader(ref: dict[str, str]) -> bytes:
        return ctx["bytes_by_id"][ref["artifact_id"]]

    ok, reason = verify_qxrl_v1(
        root_tuple_obj=dict(ctx["root_tuple_obj"]),
        system_manifest_obj=dict(ctx["system_manifest_obj"]),
        determinism_cert_obj=dict(ctx["determinism_cert_obj"]),
        registry_loader=_loader,
        mode="full",
    )
    assert ok is False
    assert reason == EUDRSU_PCLP_BINDING_MISMATCH


def test_failure_public_inputs_hash32_bad(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _build_valid_qre_pclp_ctx(tmp_path=tmp_path, monkeypatch=monkeypatch)
    pi_ref = ctx["vpvm_public_inputs_ref"]
    obj = dict(ctx["vpvm_public_inputs_obj"])
    obj["public_inputs_hash32_hex"] = "0" * 64
    ctx["bytes_by_id"][pi_ref["artifact_id"]] = gcj1_canon_bytes(obj)

    def _loader(ref: dict[str, str]) -> bytes:
        return ctx["bytes_by_id"][ref["artifact_id"]]

    ok, reason = verify_qxrl_v1(
        root_tuple_obj=dict(ctx["root_tuple_obj"]),
        system_manifest_obj=dict(ctx["system_manifest_obj"]),
        determinism_cert_obj=dict(ctx["determinism_cert_obj"]),
        registry_loader=_loader,
        mode="full",
    )
    assert ok is False
    assert reason == EUDRSU_PCLP_PUBLIC_INPUT_MISMATCH


def test_failure_config_self_hash_bad(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _build_valid_qre_pclp_ctx(tmp_path=tmp_path, monkeypatch=monkeypatch)
    cfg_ref = ctx["vpvm_config_ref"]
    obj = dict(ctx["vpvm_config_obj"])
    obj["vpvm_config_id"] = "sha256:" + ("0" * 64)
    ctx["bytes_by_id"][cfg_ref["artifact_id"]] = gcj1_canon_bytes(obj)

    def _loader(ref: dict[str, str]) -> bytes:
        return ctx["bytes_by_id"][ref["artifact_id"]]

    ok, reason = verify_qxrl_v1(
        root_tuple_obj=dict(ctx["root_tuple_obj"]),
        system_manifest_obj=dict(ctx["system_manifest_obj"]),
        determinism_cert_obj=dict(ctx["determinism_cert_obj"]),
        registry_loader=_loader,
        mode="full",
    )
    assert ok is False
    assert reason == EUDRSU_PCLP_CONFIG_MISMATCH


def test_failure_proof_corruption(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _build_valid_qre_pclp_ctx(tmp_path=tmp_path, monkeypatch=monkeypatch)
    proof_ref = ctx["proof_ref"]
    raw = bytearray(ctx["bytes_by_id"][proof_ref["artifact_id"]])
    assert raw, "expected non-empty proof bytes"
    raw[-1] ^= 0x01
    ctx["bytes_by_id"][proof_ref["artifact_id"]] = bytes(raw)

    def _loader(ref: dict[str, str]) -> bytes:
        return ctx["bytes_by_id"][ref["artifact_id"]]

    ok, reason = verify_qxrl_v1(
        root_tuple_obj=dict(ctx["root_tuple_obj"]),
        system_manifest_obj=dict(ctx["system_manifest_obj"]),
        determinism_cert_obj=dict(ctx["determinism_cert_obj"]),
        registry_loader=_loader,
        mode="full",
    )
    assert ok is False
    assert reason == EUDRSU_PCLP_PROOF_INVALID


def test_failure_tsae_with_pclp_is_unsupported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _build_valid_qre_pclp_ctx(tmp_path=tmp_path, monkeypatch=monkeypatch)

    # Replace model manifest with a valid TSAE manifest; proof-path must reject as unsupported.
    opset_id = ctx["system_manifest_obj"]["opset_id"]
    dc1_id = ctx["system_manifest_obj"]["dc1_id"]
    lut_manifest_ref = ctx["refs"]["lut_manifest_ref"]

    vocab = 257
    seq = 8
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
            "invsqrt_lut_manifest_ref": lut_manifest_ref,
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
    model_bytes = gcj1_canon_bytes(model_obj)
    model_art_id = sha256_prefixed(model_bytes)
    model_ref = {"artifact_id": model_art_id, "artifact_relpath": "polymath/registry/eudrs_u/manifests/sha256_" + model_art_id.split(":", 1)[1] + ".qxrl_model_manifest_v1.json"}
    ctx["bytes_by_id"][str(model_art_id)] = bytes(model_bytes)

    sysm = dict(ctx["system_manifest_obj"])
    sysm["qxrl"] = dict(sysm["qxrl"])
    sysm["qxrl"]["model_manifest_ref"] = model_ref

    def _loader(ref: dict[str, str]) -> bytes:
        return ctx["bytes_by_id"][ref["artifact_id"]]

    ok, reason = verify_qxrl_v1(
        root_tuple_obj=dict(ctx["root_tuple_obj"]),
        system_manifest_obj=sysm,
        determinism_cert_obj=dict(ctx["determinism_cert_obj"]),
        registry_loader=_loader,
        mode="full",
    )
    assert ok is False
    assert reason == EUDRSU_PCLP_UNSUPPORTED_MODE
