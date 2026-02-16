from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from cdel.v18_0.eudrs_u.qxrl_common_v1 import compute_eval_id_config_hash, compute_self_hash_id
from cdel.v18_0.eudrs_u.qxrl_dataset_v1 import QXRLDatasetExampleV1
from cdel.v18_0.eudrs_u.qxrl_eval_v1 import compute_qxrl_eval_scorecard_v1
from cdel.v18_0.eudrs_u.qxrl_forward_qre_v1 import parse_qxrl_model_manifest_v1
from cdel.v18_0.eudrs_u.qxrl_train_replay_v1 import (
    WeightsBlockDescV1,
    WeightsTensorDescV1,
    load_and_verify_weights_manifest_v1,
    replay_qxrl_training_v1,
)


def _find_superproject_root() -> Path | None:
    here = Path(__file__).resolve()
    for anc in [here, *here.parents]:
        if (anc / "polymath/registry/eudrs_u/manifests").is_dir():
            return anc
    return None


def _fixture_opset_id() -> str:
    return "opset:eudrs_u_v1:sha256:" + ("0" * 64)


def _tensor_specs_qre(*, vocab: int, seq: int, dm: int, dh: int, de: int) -> list[dict]:
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
    specs: list[dict] = []
    for name, shape in sorted(req.items()):
        specs.append({"name": str(name), "shape_u32": list(shape), "dtype": "Q32_S64_V1", "trainable": True})
        mom = "qxrl/opt/mom/" + str(name)[len("qxrl/") :]
        specs.append({"name": str(mom), "shape_u32": list(shape), "dtype": "Q32_S64_V1", "trainable": False})
    specs.sort(key=lambda row: str(row.get("name", "")))
    return specs


def _tensor_specs_tsae(*, vocab: int, seq: int, dm: int, de: int, n_layers: int, d_ff: int) -> list[dict]:
    req: dict[str, list[int]] = {
        "qxrl/tok_emb": [int(vocab), int(dm)],
        "qxrl/pos_emb": [int(seq), int(dm)],
    }
    for l in range(int(n_layers)):
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

    specs: list[dict] = []
    for name, shape in sorted(req.items()):
        specs.append({"name": str(name), "shape_u32": list(shape), "dtype": "Q32_S64_V1", "trainable": True})
        mom = "qxrl/opt/mom/" + str(name)[len("qxrl/") :]
        specs.append({"name": str(mom), "shape_u32": list(shape), "dtype": "Q32_S64_V1", "trainable": False})
    specs.sort(key=lambda row: str(row.get("name", "")))
    return specs


def _fixture_model() -> object:
    opset_id = _fixture_opset_id()
    vocab = 257
    seq = 8
    dm = 2
    dh = 2
    de = 2
    lut_manifest_ref = {
        "artifact_id": "sha256:" + ("0" * 64),
        "artifact_relpath": "polymath/registry/eudrs_u/manifests/sha256_" + ("0" * 64) + ".qxrl_invsqrt_lut_manifest_v1.json",
    }
    model_obj = {
        "schema_id": "qxrl_model_manifest_v1",
        "model_id": "sha256:" + ("0" * 64),
        "opset_id": opset_id,
        "dc1_id": "dc1:q32_v1",
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
    return parse_qxrl_model_manifest_v1(model_obj)


def _fixture_model_tsae() -> object:
    opset_id = _fixture_opset_id()
    vocab = 257
    seq = 4
    dm = 2
    de = 2
    n_layers = 1
    n_heads = 1
    d_head = 2
    d_ff = 2
    topk = 2

    lut_manifest_ref = {
        "artifact_id": "sha256:3158e21d9ae5dee2321a12a149688a60c17fd2be66e967c37932cfff282c7bef",
        "artifact_relpath": "polymath/registry/eudrs_u/manifests/sha256_3158e21d9ae5dee2321a12a149688a60c17fd2be66e967c37932cfff282c7bef.qxrl_invsqrt_lut_manifest_v1.json",
    }

    model_obj = {
        "schema_id": "qxrl_model_manifest_v1",
        "model_id": "sha256:" + ("0" * 64),
        "opset_id": opset_id,
        "dc1_id": "dc1:q32_v1",
        "tokenizer_kind": "BYTE_TOK_257_V1",
        "vocab_size_u32": vocab,
        "seq_len_u32": seq,
        "encoder_kind": "TSAE_V1",
        "d_model_u32": dm,
        "d_embed_u32": de,
        "math": {
            "dot_kind": "DOT_Q32_SHIFT_END_V1",
            "div_kind": "DIV_Q32_POS_RNE_V1",
            "invsqrt_kind": "INVSQRT_Q32_NR_LUT_V1",
            "invsqrt_lut_manifest_ref": lut_manifest_ref,
        },
        "tsae": {
            "n_layers_u32": n_layers,
            "n_heads_u32": n_heads,
            "d_head_u32": d_head,
            "d_ff_u32": d_ff,
            "topk_u32": topk,
            "rms_epsilon_q32": {"q": 1},
            "inv_seq_len_q32": {"q": (1 << 32) // seq},
        },
        "tensor_specs": _tensor_specs_tsae(vocab=vocab, seq=seq, dm=dm, de=de, n_layers=n_layers, d_ff=d_ff),
    }
    model_obj["model_id"] = compute_self_hash_id(model_obj, id_field="model_id")
    return parse_qxrl_model_manifest_v1(model_obj)


def _fixture_dataset() -> tuple[list[QXRLDatasetExampleV1], bytes]:
    examples = [
        QXRLDatasetExampleV1(example_id_u64=i, anchor_tokens_u32=[i + 1] * 8, positive_tokens_u32=[i + 2] * 8)
        for i in range(4)
    ]
    seg_digest32 = hashlib.sha256(b"QXRL_SEGMENT_DUMMY_V1").digest()
    dataset_root_hash32 = hashlib.sha256(b"QXRL_DATASET_ROOT_V1" + seg_digest32).digest()
    return examples, dataset_root_hash32


def _fixture_dataset_seq4() -> tuple[list[QXRLDatasetExampleV1], bytes]:
    seq = 4
    examples = [
        QXRLDatasetExampleV1(example_id_u64=i, anchor_tokens_u32=[i + 1] * seq, positive_tokens_u32=[i + 2] * seq)
        for i in range(4)
    ]
    seg_digest32 = hashlib.sha256(b"QXRL_SEGMENT_DUMMY_V1").digest()
    dataset_root_hash32 = hashlib.sha256(b"QXRL_DATASET_ROOT_V1" + seg_digest32).digest()
    return examples, dataset_root_hash32


def _one_block(total: int) -> list[WeightsBlockDescV1]:
    return [
        WeightsBlockDescV1(
            elem_offset_u64=0,
            elem_count_u32=int(total),
            # Placeholder ref; encoding derives real refs deterministically from bytes.
            block_ref={"artifact_id": "sha256:" + ("0" * 64), "artifact_relpath": "x"},
        )
    ]


def _fixture_initial_weights(opset_id: str) -> tuple[str, object]:
    Q32_ONE = 1 << 32
    vocab = 257
    seq = 8
    dm = 2
    dh = 2
    de = 2

    # tok_emb[v,0]=v<<16; tok_emb[v,1]=(v^0x55)<<16
    tok_emb = []
    for v in range(vocab):
        tok_emb.append(v << 16)
        tok_emb.append((v ^ 0x55) << 16)

    # pos_emb[p,0]=p<<16; pos_emb[p,1]=(p*3)<<16
    pos_emb = []
    for p in range(seq):
        pos_emb.append(p << 16)
        pos_emb.append((p * 3) << 16)

    enc_w1 = [Q32_ONE, 0, 0, Q32_ONE]  # 2x2 identity
    enc_b1 = [0, 0]
    enc_w2 = [Q32_ONE, 0, 0, Q32_ONE]  # 2x2 identity
    enc_b2 = [0, 0]

    tok_proj_w = [Q32_ONE, 0, 0, Q32_ONE]  # 2x2 identity
    tok_proj_b = [0, 0]

    # out_emb[v,0]=v<<16; out_emb[v,1]=(v*7)<<16
    out_emb = []
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

    manifest_obj, _manifest_bytes, manifest_id, blocks_out = tr._build_weights_manifest_bytes_from_descs(
        dc1_id="dc1:q32_v1",
        opset_id=str(opset_id),
        merkle_fanout_u32=2,
        tensor_descs=sorted(tensor_descs, key=lambda t: t.name),
    )

    block_bytes_by_id = {ref["artifact_id"]: b for ref, b in blocks_out}

    def _mem_loader(ref: dict[str, str]) -> bytes:
        return block_bytes_by_id[ref["artifact_id"]]

    weights = load_and_verify_weights_manifest_v1(weights_manifest_obj=manifest_obj, registry_loader=_mem_loader)
    return str(manifest_id), weights


def _fixture_initial_weights_tsae(opset_id: str) -> tuple[str, object]:
    Q32_ONE = 1 << 32
    vocab = 257
    seq = 4
    dm = 2
    de = 2
    n_layers = 1
    d_ff = 2

    # tok_emb[v,0]=v<<16; tok_emb[v,1]=(v^0x55)<<16
    tok_emb = []
    for v in range(vocab):
        tok_emb.append(v << 16)
        tok_emb.append((v ^ 0x55) << 16)

    # pos_emb[p,0]=p<<16; pos_emb[p,1]=(p*3)<<16
    pos_emb = []
    for p in range(seq):
        pos_emb.append(p << 16)
        pos_emb.append((p * 3) << 16)

    ident2 = [Q32_ONE, 0, 0, Q32_ONE]  # 2x2 identity

    def _tdesc(name: str, shape: list[int], data: list[int]) -> WeightsTensorDescV1:
        total = 1
        for d in shape:
            total *= int(d)
        assert len(data) == total
        return WeightsTensorDescV1(
            name=name, dtype="Q32_S64_V1", shape_u32=shape, blocks=_one_block(total), data_q32_s64=data
        )

    tensor_descs: list[WeightsTensorDescV1] = []
    tensor_descs.append(_tdesc("qxrl/tok_emb", [vocab, dm], tok_emb))
    tensor_descs.append(_tdesc("qxrl/pos_emb", [seq, dm], pos_emb))

    for l in range(n_layers):
        for name in ("wq", "wk", "wv", "wo"):
            tensor_descs.append(_tdesc(f"qxrl/tsae/l{l}/{name}", [dm, dm], list(ident2)))
        tensor_descs.append(_tdesc(f"qxrl/tsae/l{l}/rms1_gamma", [dm], [Q32_ONE] * dm))
        tensor_descs.append(_tdesc(f"qxrl/tsae/l{l}/rms2_gamma", [dm], [Q32_ONE] * dm))
        tensor_descs.append(_tdesc(f"qxrl/tsae/l{l}/ff_w1", [d_ff, dm], list(ident2)))
        tensor_descs.append(_tdesc(f"qxrl/tsae/l{l}/ff_b1", [d_ff], [0] * d_ff))
        tensor_descs.append(_tdesc(f"qxrl/tsae/l{l}/ff_w2", [dm, d_ff], list(ident2)))
        tensor_descs.append(_tdesc(f"qxrl/tsae/l{l}/ff_b2", [dm], [0] * dm))

    tensor_descs.append(_tdesc("qxrl/tsae/proj_w", [de, dm], list(ident2)))
    tensor_descs.append(_tdesc("qxrl/tsae/proj_b", [de], [0] * de))
    tensor_descs.append(_tdesc("qxrl/tok_proj_w", [de, dm], list(ident2)))
    tensor_descs.append(_tdesc("qxrl/tok_proj_b", [de], [0] * de))

    # out_emb[v,0]=v<<16; out_emb[v,1]=(v*7)<<16
    out_emb = []
    for v in range(vocab):
        out_emb.append(v << 16)
        out_emb.append((v * 7) << 16)
    tensor_descs.append(_tdesc("qxrl/out_emb", [vocab, de], out_emb))
    tensor_descs.append(_tdesc("qxrl/out_b", [vocab], [0] * vocab))

    tensor_descs2: list[WeightsTensorDescV1] = []
    for t in sorted(tensor_descs, key=lambda t: t.name):
        tensor_descs2.append(t)
        mom = "qxrl/opt/mom/" + t.name[len("qxrl/") :]
        tensor_descs2.append(_tdesc(mom, list(t.shape_u32), [0] * len(t.data_q32_s64)))

    from cdel.v18_0.eudrs_u import qxrl_train_replay_v1 as tr

    manifest_obj, _manifest_bytes, manifest_id, blocks_out = tr._build_weights_manifest_bytes_from_descs(
        dc1_id="dc1:q32_v1",
        opset_id=str(opset_id),
        merkle_fanout_u32=2,
        tensor_descs=sorted(tensor_descs2, key=lambda t: t.name),
    )

    block_bytes_by_id = {ref["artifact_id"]: b for ref, b in blocks_out}

    def _mem_loader(ref: dict[str, str]) -> bytes:
        return block_bytes_by_id[ref["artifact_id"]]

    weights = load_and_verify_weights_manifest_v1(weights_manifest_obj=manifest_obj, registry_loader=_mem_loader)
    return str(manifest_id), weights


def _fixture_training_manifest(opset_id: str) -> dict:
    tm = {
        "schema_id": "qxrl_training_manifest_v1",
        "training_id": "sha256:" + ("0" * 64),
        "opset_id": str(opset_id),
        "dc1_id": "dc1:q32_v1",
        "model_manifest_ref": {
            "artifact_id": "sha256:" + ("1" * 64),
            "artifact_relpath": "polymath/registry/eudrs_u/manifests/sha256_" + ("1" * 64) + ".qxrl_model_manifest_v1.json",
        },
        "dataset_manifest_ref": {
            "artifact_id": "sha256:" + ("2" * 64),
            "artifact_relpath": "polymath/registry/eudrs_u/datasets/sha256_" + ("2" * 64) + ".qxrl_dataset_manifest_v1.json",
        },
        "dot_kind": "DOT_Q32_SHIFT_END_V1",
        "optimizer_kind": "SGD_MOMENTUM_Q32_V1",
        "init_scale_q32": {"q": 1},
        "train_steps_u64": 1,
        "batch_size_u32": 2,
        "checkpoint_every_steps_u32": 1,
        "mask_prob_q32": {"q": 1 << 32},  # always mask; cap selects lowest positions
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
    return tm


def test_qxrl_one_update_replay_pinned() -> None:
    opset_id = _fixture_opset_id()
    model = _fixture_model()
    examples, dataset_root_hash32 = _fixture_dataset()
    init_wroot_id, init_weights = _fixture_initial_weights(opset_id)
    init_wroot_id2, init_weights2 = _fixture_initial_weights(opset_id)
    assert init_wroot_id2 == init_wroot_id
    tm = _fixture_training_manifest(opset_id)

    expected_final_wroot_id = "sha256:ac4d76128da3428db97c402a5386d641628c7766105b05ab5373f77cce061f8e"
    expected_h_train_tail_hex = "76983082a41142e75b071cd52e0a8f74ade113b881fbc4387f4ec2bf9c2246f7"

    out1 = replay_qxrl_training_v1(
        training_manifest_obj=tm,
        model=model,
        dataset_root_hash32=dataset_root_hash32,
        examples=examples,
        initial_weights_manifest_id=init_wroot_id,
        initial_weights_manifest=init_weights,
        registry_loader=lambda _ref: b"",
        return_debug=False,
    )
    out2 = replay_qxrl_training_v1(
        training_manifest_obj=tm,
        model=model,
        dataset_root_hash32=dataset_root_hash32,
        examples=examples,
        initial_weights_manifest_id=init_wroot_id,
        initial_weights_manifest=init_weights2,
        registry_loader=lambda _ref: b"",
        return_debug=False,
    )

    _final_bytes1, final_id1, _final_obj1, _final_blocks1, h_train_tail32_1, _dbg1 = out1
    _final_bytes2, final_id2, _final_obj2, _final_blocks2, h_train_tail32_2, _dbg2 = out2
    assert final_id1 == final_id2
    assert h_train_tail32_1 == h_train_tail32_2
    assert final_id1 == expected_final_wroot_id
    assert h_train_tail32_1.hex() == expected_h_train_tail_hex


def test_qxrl_mask_and_negs_pinned() -> None:
    opset_id = _fixture_opset_id()
    model = _fixture_model()
    examples, dataset_root_hash32 = _fixture_dataset()
    init_wroot_id, init_weights = _fixture_initial_weights(opset_id)
    tm = _fixture_training_manifest(opset_id)

    _final_bytes, _final_id, _final_obj, _final_blocks, _h_train_tail32, dbg = replay_qxrl_training_v1(
        training_manifest_obj=tm,
        model=model,
        dataset_root_hash32=dataset_root_hash32,
        examples=examples,
        initial_weights_manifest_id=init_wroot_id,
        initial_weights_manifest=init_weights,
        registry_loader=lambda _ref: b"",
        return_debug=True,
    )
    assert dbg is not None and len(dbg) == 1
    step = dbg[0]
    assert step.prng_draws_masks_u64 == 16  # batch_size * seq_len
    assert step.prng_draws_negs_u64 == 8
    assert step.prng_counter_u64 == 24

    sel0 = step.selections[0]
    assert sel0.mask_bitmap_bytes.hex() == "03"
    assert sel0.masked_positions_u32 == [0, 1]
    assert sel0.true_token_ids_u32 == [1, 1]
    assert sel0.neg_token_ids_by_mask_pos == [[115, 182], [92, 62]]


def test_qxrl_eval_replay_pinned() -> None:
    opset_id = _fixture_opset_id()
    model = _fixture_model()
    examples, dataset_root_hash32 = _fixture_dataset()
    init_wroot_id, init_weights = _fixture_initial_weights(opset_id)
    tm = _fixture_training_manifest(opset_id)

    final_bytes, final_id, final_obj, final_blocks, _h_train_tail32, _dbg = replay_qxrl_training_v1(
        training_manifest_obj=tm,
        model=model,
        dataset_root_hash32=dataset_root_hash32,
        examples=examples,
        initial_weights_manifest_id=init_wroot_id,
        initial_weights_manifest=init_weights,
        registry_loader=lambda _ref: b"",
        return_debug=False,
    )

    # Parse final weights into a WeightsManifestV1 for evaluation.
    blocks_by_id = {ref["artifact_id"]: b for ref, b in final_blocks}

    def _mem_loader(ref: dict[str, str]) -> bytes:
        return blocks_by_id[ref["artifact_id"]]

    final_weights = load_and_verify_weights_manifest_v1(weights_manifest_obj=final_obj, registry_loader=_mem_loader)

    # Minimal dataset manifest (internal IDs only; used for scorecard fields).
    seg_digest32 = hashlib.sha256(b"QXRL_SEGMENT_DUMMY_V1").digest()
    dataset_manifest = {
        "schema_id": "qxrl_dataset_manifest_v1",
        "dataset_id": "sha256:" + ("0" * 64),
        "opset_id": opset_id,
        "dc1_id": "dc1:q32_v1",
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
                "segment_ref": {
                    "artifact_id": "sha256:" + seg_digest32.hex(),
                    "artifact_relpath": "polymath/registry/eudrs_u/datasets/segments/sha256_" + seg_digest32.hex() + ".qxrl_dataset_segment_v1.bin",
                },
            }
        ],
        "dataset_root_hash32_hex": hashlib.sha256(b"QXRL_DATASET_ROOT_V1" + seg_digest32).hexdigest(),
    }
    dataset_manifest["dataset_id"] = compute_self_hash_id(dataset_manifest, id_field="dataset_id")

    # Eval manifest (scorecard_ref is required by schema but not used by eval_id config hash).
    scorecard_ref = {
        "artifact_id": "sha256:" + ("0" * 64),
        "artifact_relpath": "polymath/registry/eudrs_u/eval/sha256_" + ("0" * 64) + ".qxrl_eval_scorecard_v1.json",
    }
    eval_manifest = {
        "schema_id": "qxrl_eval_manifest_v1",
        "eval_id": "sha256:" + ("0" * 64),
        "opset_id": opset_id,
        "dc1_id": "dc1:q32_v1",
        "model_manifest_ref": {"artifact_id": "sha256:" + ("1" * 64), "artifact_relpath": "x"},
        "dataset_manifest_ref": {"artifact_id": "sha256:" + ("2" * 64), "artifact_relpath": "x"},
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
        "scorecard_ref": scorecard_ref,
    }
    eval_manifest["eval_id"] = compute_eval_id_config_hash(eval_manifest)

    expected_scorecard_artifact_id = "sha256:291fa287ddbc3931daaa8cab6ce0ab1da4a8679db2325211dda725ce4f26b750"
    expected_h_eval_tail_hex = "548a4781fb033c6d309ee72221d54878cec1a048b956a39f32d6ff57d0979136"

    sc_obj1, sc_bytes1, sc_art_id1, h_eval_tail32_1 = compute_qxrl_eval_scorecard_v1(
        eval_manifest_obj=eval_manifest,
        model=model,
        model_manifest_id="sha256:" + ("1" * 64),
        dataset_manifest_obj=dataset_manifest,
        dataset_root_hash32=dataset_root_hash32,
        examples=examples,
        weights_manifest_id=final_id,
        weights_manifest=final_weights,
        enforce_floors=True,
    )
    sc_obj2, sc_bytes2, sc_art_id2, h_eval_tail32_2 = compute_qxrl_eval_scorecard_v1(
        eval_manifest_obj=eval_manifest,
        model=model,
        model_manifest_id="sha256:" + ("1" * 64),
        dataset_manifest_obj=dataset_manifest,
        dataset_root_hash32=dataset_root_hash32,
        examples=examples,
        weights_manifest_id=final_id,
        weights_manifest=final_weights,
        enforce_floors=True,
    )

    assert sc_bytes1 == sc_bytes2
    assert sc_art_id1 == sc_art_id2
    assert h_eval_tail32_1 == h_eval_tail32_2

    assert sc_art_id1 == expected_scorecard_artifact_id
    assert h_eval_tail32_1.hex() == expected_h_eval_tail_hex
    assert sc_obj1["tails"]["h_eval_tail32_hex"] == expected_h_eval_tail_hex


def test_qxrl_tsae_one_update_and_eval_replay_pinned() -> None:
    opset_id = _fixture_opset_id()
    model = _fixture_model_tsae()
    examples, dataset_root_hash32 = _fixture_dataset_seq4()
    init_wroot_id, init_weights = _fixture_initial_weights_tsae(opset_id)
    init_wroot_id2, init_weights2 = _fixture_initial_weights_tsae(opset_id)
    assert init_wroot_id2 == init_wroot_id
    tm = _fixture_training_manifest(opset_id)

    repo_root = _find_superproject_root()
    if repo_root is None:
        pytest.skip("requires polymath registry fixtures (run via AGI-Stack)")
    lut_manifest_artifact_id = "sha256:3158e21d9ae5dee2321a12a149688a60c17fd2be66e967c37932cfff282c7bef"
    lut_manifest_bytes = (
        repo_root
        / "polymath/registry/eudrs_u/manifests/sha256_3158e21d9ae5dee2321a12a149688a60c17fd2be66e967c37932cfff282c7bef.qxrl_invsqrt_lut_manifest_v1.json"
    ).read_bytes()
    lut_bin_artifact_id = "sha256:f6b7eac00dae22340aefefc36692994958acb88933698f97968ae9cb37e97864"
    lut_bin_bytes = (
        repo_root
        / "polymath/registry/eudrs_u/manifests/sha256_f6b7eac00dae22340aefefc36692994958acb88933698f97968ae9cb37e97864.qxrl_invsqrt_lut_v1.bin"
    ).read_bytes()

    def _lut_loader(ref: dict[str, str]) -> bytes:
        aid = str(ref.get("artifact_id", ""))
        if aid == lut_manifest_artifact_id:
            return lut_manifest_bytes
        if aid == lut_bin_artifact_id:
            return lut_bin_bytes
        raise KeyError(aid)

    expected_final_wroot_id = "sha256:c107a4b1ace6a5dcba94ed64d02f3dc20057a78b20279a85c7fb523baf2b8255"
    expected_h_train_tail_hex = "209661d6b96305cb8e84535617f0a995d461ea113628957a37661534abbc9167"
    expected_scorecard_artifact_id = "sha256:7b8012461c465a1bf8e33678f2e21a004a89dbec2dc38537a9dfbb0f061555d3"
    expected_h_eval_tail_hex = "8d7621a7f1ec89ae57f85ccd61bc87d4522c00baffff57bb74f63abf2126b223"

    out1 = replay_qxrl_training_v1(
        training_manifest_obj=tm,
        model=model,
        dataset_root_hash32=dataset_root_hash32,
        examples=examples,
        initial_weights_manifest_id=init_wroot_id,
        initial_weights_manifest=init_weights,
        registry_loader=_lut_loader,
        return_debug=False,
    )
    out2 = replay_qxrl_training_v1(
        training_manifest_obj=tm,
        model=model,
        dataset_root_hash32=dataset_root_hash32,
        examples=examples,
        initial_weights_manifest_id=init_wroot_id,
        initial_weights_manifest=init_weights2,
        registry_loader=_lut_loader,
        return_debug=False,
    )

    _final_bytes1, final_id1, final_obj1, final_blocks1, h_train_tail32_1, _dbg1 = out1
    _final_bytes2, final_id2, _final_obj2, _final_blocks2, h_train_tail32_2, _dbg2 = out2
    assert final_id1 == final_id2
    assert h_train_tail32_1 == h_train_tail32_2
    assert final_id1 == expected_final_wroot_id
    assert h_train_tail32_1.hex() == expected_h_train_tail_hex

    # Parse final weights into a WeightsManifestV1 for evaluation.
    blocks_by_id = {ref["artifact_id"]: b for ref, b in final_blocks1}

    def _weights_loader(ref: dict[str, str]) -> bytes:
        return blocks_by_id[ref["artifact_id"]]

    final_weights = load_and_verify_weights_manifest_v1(weights_manifest_obj=final_obj1, registry_loader=_weights_loader)

    # Minimal dataset manifest (internal IDs only; used for scorecard fields).
    seg_digest32 = hashlib.sha256(b"QXRL_SEGMENT_DUMMY_V1").digest()
    dataset_manifest = {
        "schema_id": "qxrl_dataset_manifest_v1",
        "dataset_id": "sha256:" + ("0" * 64),
        "opset_id": opset_id,
        "dc1_id": "dc1:q32_v1",
        "tokenizer_kind": "BYTE_TOK_257_V1",
        "dataset_kind": "PAIR_V1",
        "vocab_size_u32": 257,
        "seq_len_u32": 4,
        "segments": [
            {
                "segment_index_u32": 0,
                "record_count_u32": 4,
                "first_example_id_u64": 0,
                "last_example_id_u64": 3,
                "segment_ref": {
                    "artifact_id": "sha256:" + seg_digest32.hex(),
                    "artifact_relpath": "polymath/registry/eudrs_u/datasets/segments/sha256_" + seg_digest32.hex() + ".qxrl_dataset_segment_v1.bin",
                },
            }
        ],
        "dataset_root_hash32_hex": hashlib.sha256(b"QXRL_DATASET_ROOT_V1" + seg_digest32).hexdigest(),
    }
    dataset_manifest["dataset_id"] = compute_self_hash_id(dataset_manifest, id_field="dataset_id")

    # Eval manifest (scorecard_ref is required by schema but not used by eval_id config hash).
    scorecard_ref = {"artifact_id": "sha256:" + ("0" * 64), "artifact_relpath": "x"}
    eval_manifest = {
        "schema_id": "qxrl_eval_manifest_v1",
        "eval_id": "sha256:" + ("0" * 64),
        "opset_id": opset_id,
        "dc1_id": "dc1:q32_v1",
        "model_manifest_ref": {"artifact_id": "sha256:" + ("1" * 64), "artifact_relpath": "x"},
        "dataset_manifest_ref": {"artifact_id": "sha256:" + ("2" * 64), "artifact_relpath": "x"},
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
        "scorecard_ref": scorecard_ref,
    }
    eval_manifest["eval_id"] = compute_eval_id_config_hash(eval_manifest)

    sc_obj1, sc_bytes1, sc_art_id1, h_eval_tail32_1 = compute_qxrl_eval_scorecard_v1(
        eval_manifest_obj=eval_manifest,
        model=model,
        model_manifest_id="sha256:" + ("1" * 64),
        dataset_manifest_obj=dataset_manifest,
        dataset_root_hash32=dataset_root_hash32,
        examples=examples,
        weights_manifest_id=final_id1,
        weights_manifest=final_weights,
        enforce_floors=True,
        registry_loader=_lut_loader,
    )
    sc_obj2, sc_bytes2, sc_art_id2, h_eval_tail32_2 = compute_qxrl_eval_scorecard_v1(
        eval_manifest_obj=eval_manifest,
        model=model,
        model_manifest_id="sha256:" + ("1" * 64),
        dataset_manifest_obj=dataset_manifest,
        dataset_root_hash32=dataset_root_hash32,
        examples=examples,
        weights_manifest_id=final_id1,
        weights_manifest=final_weights,
        enforce_floors=True,
        registry_loader=_lut_loader,
    )

    assert sc_bytes1 == sc_bytes2
    assert sc_art_id1 == sc_art_id2
    assert h_eval_tail32_1 == h_eval_tail32_2

    assert sc_art_id1 == expected_scorecard_artifact_id
    assert h_eval_tail32_1.hex() == expected_h_eval_tail_hex
    assert sc_obj1["tails"]["h_eval_tail32_hex"] == expected_h_eval_tail_hex
