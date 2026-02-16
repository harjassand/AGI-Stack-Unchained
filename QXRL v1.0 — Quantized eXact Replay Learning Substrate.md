# QXRL v1.0 — Quantized eXact Replay Learning Substrate

## Aligned with the previously specified EUDRS‑U/QXWMR/MCL architecture

This is a **complete, implementable QXRL v1.0 spec** that is **compatible** with the earlier EUDRS‑U/QXWMR/MCL specification (GCJ‑1 canonical JSON, Q32 encoding, deterministic choice rules, XORSHIFT128+ PRNG, Merkle layouts, promotion + RE2 replay verification).

This spec is **normative**. “MUST/SHALL” are mandatory.

---

## 0. Compatibility invariants

QXRL v1.0 MUST satisfy all invariants already required by the EUDRS‑U spec:

1. **Authority unchanged**: RE3 proposes; RE2 replays/verifies deterministically; only RE1 activates via promotion bundle.
2. **Canonical JSON**: GCJ‑1, floats rejected (all non-integer scalars encoded as Q32 `{"q":int}`).
3. **Determinism**: no sampling; only `ArgMaxDet` and `TopKDet` with explicit tie rules.
4. **PRNG**: uses the EUDRS‑U PRNG (XORSHIFT128PLUS_V1) and seed derivation (no ChaCha20 in v1).
5. **Promotion is additive + content-addressed**: all artifacts referenced by `sha256` of canonical bytes; no in-place mutation.
6. **Replay is fail-closed**: any mismatch in hashes, roots, digests, caps, or invariants ⇒ reject.

---

## 1. Terminology and shared primitives (imported from the EUDRS‑U spec)

QXRL v1.0 **reuses** the following definitions from the earlier EUDRS‑U spec (no redefinition allowed):

* **Canonical JSON / hashing**: EUDRS‑U spec §2.1 and §2.5
* **Q32 JSON scalar format**: EUDRS‑U spec §2.2.1 (`{"q":int}`)
* **Deterministic choice**: EUDRS‑U spec §2.3
* **PRNG algorithm + seed derivation**: EUDRS‑U spec §24.1
* **Merkle fanout root**: EUDRS‑U spec §10.1
* **Weights blocks + weights manifest**: EUDRS‑U spec §13
* **Training step digest + chain `H_train`**: EUDRS‑U spec §14.1

QXRL adds only QXRL-specific manifests, dataset formats, forward/backward rules, and evaluation rules.

---

## 2. DC‑1-aligned arithmetic contract for QXRL

QXRL v1.0 uses **the aligned integer semantics** (consistent with the earlier EUDRS‑U spec):

### 2.1 Types

* `S64`: signed 64-bit integer
* `S128`: signed 128-bit integer (intermediate only)
* `Q32`: `S64` interpreted as `real = q / 2^32`

### 2.2 Saturating clamp

`SAT64(x:S128) -> S64` clamps to `[-2^63, 2^63-1]`.

### 2.3 Q32 operations

These are the **only** arithmetic primitives QXRL may assume; everything else is an OpSet function.

* **AddSat**
  `AddSat(a,b) = SAT64(S128(a) + S128(b))`

* **MulWide**
  `MulWide(a,b) = S128(a) * S128(b)`

* **MulQ32 (aligned)**
  `MulQ32(a,b) = SAT64(MulWide(a,b) >> 32)`
  where `>>` is arithmetic shift.

### 2.4 Dot product (aligned reduction order)

QXRL defines a deterministic dot product used in matmul:

**DotQ32S128Acc(x:S64, w:S64) -> S64**

1. `acc = 0 (S128)`
2. for `i=0..n-1` in ascending index:

   * `acc += MulWide(x[i], w[i])`
3. return `SAT64(acc >> 32)`

This matches the “pinned order, S128 accumulate, clamp at end” style already used in the EUDRS‑U spec.

### 2.5 Deterministic comparisons and Top‑K

* `ArgMaxDet`: highest score wins; ties → lowest id.
* `TopKDet`: sort by `(score desc, id asc)`.

All Top‑K/argmax operations MUST emit stable inputs to traces (see §9).

---

## 3. QXRL artifact set and directory layout

All QXRL artifacts MUST live under the previously standardized EUDRS‑U registry tree (so repeated QXRL promotions can be data-only and avoid v19 governed prefixes):

```
polymath/registry/eudrs_u/
  manifests/
    sha256_<...>.qxrl_model_manifest_v1.json
    sha256_<...>.qxrl_training_manifest_v1.json
    sha256_<...>.qxrl_eval_manifest_v1.json
  datasets/
    sha256_<...>.qxrl_dataset_manifest_v1.json
    segments/
      sha256_<...>.qxrl_dataset_segment_v1.bin
  eval/
    sha256_<...>.qxrl_eval_scorecard_v1.json
  weights/
    sha256_<...>.weights_manifest_v1.json
    blocks/
      sha256_<...>.q32_tensor_block_v1.bin
  gates/
    sha256_<...>.cac_v1.json                 (QXRL delta CAC)
    sha256_<...>.stability_metrics_v1.json    (includes QXRL metrics)
```

All references between these artifacts MUST use the shared `ArtifactRefV1` contract (EUDRS‑U spec §3).

---

## 4. Manifests (canonical JSON; no floats)

All manifests MUST be GCJ‑1 canonical JSON and schema-validated in RE2.

### 4.1 `qxrl_model_manifest_v1.json`

**Purpose:** defines the encoder family and all architecture hyperparameters.

Normative structure:

```json
{
  "schema_id": "qxrl_model_manifest_v1",

  "dc1_id": "dc1:q32_v1",
  "opset_id": "opset:eudrs_u_v1:sha256:<64hex>",

  "model_id": "sha256:<64hex>",

  "tokenization": {
    "kind": "PRETOKENIZED_U32_V1 | BYTE_TOK_257_V1",
    "vocab_size_u32": <int>,
    "pad_token_u32": 0,
    "mask_token_u32": 1
  },

  "io": {
    "seq_len_u32": <int>,
    "d_model_u32": <int>,
    "d_embed_u32": <int>
  },

  "family": {
    "kind": "QRE_V1 | TSAE_TOPK_V1",

    "qre": {
      "n_layers_u32": <int>,
      "mlp_hidden_u32": <int>,
      "clip_act_q32": {"q": <int>}
    },

    "tsae": {
      "n_layers_u32": <int>,
      "n_heads_u32": <int>,
      "d_head_u32": <int>,
      "topk_k_u32": <int>,
      "attn_scale_q32": {"q": <int>},

      "norm_kind": "NONE | RMSNORM_V1",
      "rmsnorm_eps_q32": {"q": <int>},

      "mlp_hidden_u32": <int>,
      "clip_act_q32": {"q": <int>}
    }
  },

  "output": {
    "pooling_kind": "CLS_0 | MEAN_TREELESS_V1",
    "normalize_embed_kind": "NONE | L1_NORM_V1 | RMSNORM_V1"
  },

  "caps": {
    "max_params_u64": <int>,
    "max_tokens_u64": <int>,
    "max_steps_u64": <int>
  }
}
```

**Deterministic constraints**

* `model_id` MUST be the self-hash of the canonical bytes of this manifest with `model_id` field zeroed (same pattern as concept_id in the EUDRS‑U spec).
* If `family.kind == TSAE_TOPK_V1`, then `d_model == n_heads * d_head` MUST hold (reject otherwise).
* All `*_q32` values MUST be `{"q":int}`.

### 4.2 `qxrl_training_manifest_v1.json`

**Purpose:** defines dataset, schedule, objectives, optimizer, PRNG usage, trace behavior.

Normative structure:

```json
{
  "schema_id": "qxrl_training_manifest_v1",

  "model_manifest_ref": { "artifact_id": "sha256:<...>", "artifact_relpath": "..." },
  "dataset_manifest_ref": { "artifact_id": "sha256:<...>", "artifact_relpath": "..." },

  "schedule": {
    "epochs_u32": <int>,
    "batch_size_u32": <int>,
    "steps_u64": <int>,
    "shuffle_kind": "NONE | BLOCK_HASH_SORT_V1 | FISHER_YATES_XORSHIFT_V1",
    "shuffle_block_size_u32": <int>
  },

  "objectives": {
    "contrastive_hinge_v1": {
      "enabled": true,
      "alpha_q32": {"q": <int>},
      "margin_q32": {"q": <int>},
      "negatives_per_anchor_u32": <int>,
      "neg_source": "IN_BATCH | DATASET_SAMPLE"
    },
    "masked_hinge_v1": {
      "enabled": true,
      "beta_q32": {"q": <int>},
      "mask_rate_bp_u32": <int>,               // 0..10000
      "masks_per_seq_cap_u32": <int>,
      "negatives_per_mask_u32": <int>,
      "margin_q32": {"q": <int>}
    },
    "reg_v1": {
      "enabled": true,
      "gamma_q32": {"q": <int>},
      "weight_decay_q32": {"q": <int>},
      "embed_variance_floor_q32": {"q": <int>}
    }
  },

  "optimizer": {
    "kind": "SGD_MOMENTUM_Q32_V1 | ADAMW_Q32_V1",
    "lr_q32": {"q": <int>},

    "sgd_momentum": {
      "mu_q32": {"q": <int>},
      "clip_grad_elem_q32": {"q": <int>},
      "clip_param_elem_q32": {"q": <int>}
    },

    "adamw": {
      "beta1_q32": {"q": <int>},
      "beta2_q32": {"q": <int>},
      "eps_q32": {"q": <int>},
      "clip_grad_elem_q32": {"q": <int>},
      "clip_param_elem_q32": {"q": <int>},
      "bias_correction_kind": "LUT_V1",
      "bias_lut_ref": { "artifact_id": "sha256:<...>", "artifact_relpath": "..." }
    }
  },

  "trace": {
    "use_eudrs_u_train_step_digest_v1": true,
    "emit_checkpoints": true,
    "checkpoint_every_steps_u64": <int>
  },

  "caps": {
    "max_prng_draws_u64": <int>,
    "max_topk_ops_u64": <int>,
    "max_dot_ops_u64": <int>
  }
}
```

**Deterministic constraints**

* `mask_rate_bp_u32` is basis points (0..10000). Mask selection is deterministic (see §8.2).
* If `optimizer.kind == ADAMW_Q32_V1`, the manifest MUST include `bias_lut_ref` and RE2 MUST verify that LUT bytes hash-match and LUT length covers all steps.
* All caps must be enforced by producer **and** verifier.

### 4.3 `qxrl_eval_manifest_v1.json`

**Purpose:** defines deterministic evaluation tasks and gates used for QXRL promotions.

Normative structure:

```json
{
  "schema_id": "qxrl_eval_manifest_v1",

  "model_manifest_ref": { "artifact_id": "sha256:<...>", "artifact_relpath": "..." },

  "anchor_set": {
    "dataset_manifest_ref": { "artifact_id": "sha256:<...>", "artifact_relpath": "..." },
    "anchor_count_u32": <int>
  },

  "retrieval_eval": {
    "enabled": true,
    "query_count_u32": <int>,
    "k_u32": <int>,
    "pos_kind": "SAME_EXAMPLE_ALT_MASK | NEIGHBOR_IN_DATASET_V1"
  },

  "masked_eval": {
    "enabled": true,
    "seq_count_u32": <int>,
    "masks_per_seq_u32": <int>,
    "negatives_per_mask_u32": <int>
  },

  "drift_eval": {
    "enabled": true,
    "max_drift_q32": {"q": <int>},
    "reference_model_root_tuple_ref": { "artifact_id": "sha256:<...>", "artifact_relpath": "..." }
  },

  "collapse_eval": {
    "enabled": true,
    "min_variance_q32": {"q": <int>},
    "min_norm_q32": {"q": <int>},
    "max_norm_q32": {"q": <int>}
  },

  "floors": {
    "retrieval_recall_at_k_min_q32": {"q": <int>},
    "masked_acc_at1_min_q32": {"q": <int>}
  }
}
```

### 4.4 `qxrl_eval_scorecard_v1.json`

**Purpose:** deterministic evaluation outputs (hash-bound, replayed).

Normative structure:

```json
{
  "schema_id": "qxrl_eval_scorecard_v1",

  "model_id": "sha256:<...>",
  "wroot_sha256": "sha256:<...>",
  "h_eval_tail_sha256": "sha256:<...>",

  "metrics": {
    "retrieval_recall_at_k_q32": {"q": <int>},
    "masked_acc_at1_q32": {"q": <int>},

    "drift_q32": {"q": <int>},
    "embed_norm_min_q32": {"q": <int>},
    "embed_norm_mean_q32": {"q": <int>},
    "embed_norm_max_q32": {"q": <int>},
    "embed_variance_min_q32": {"q": <int>}
  },

  "caps_used": {
    "tokens_u64": <int>,
    "topk_ops_u64": <int>,
    "dot_ops_u64": <int>,
    "prng_draws_u64": <int>
  }
}
```

---

## 5. Dataset format (content-addressed, deterministic)

### 5.1 `qxrl_dataset_manifest_v1.json`

**Purpose:** ordered dataset definition.

Normative structure:

```json
{
  "schema_id": "qxrl_dataset_manifest_v1",

  "dataset_id": "sha256:<...>",

  "record_kind": "TOKSEQ_U32_FIXED_V1",
  "seq_len_u32": <int>,
  "vocab_size_u32": <int>,

  "segments": [
    { "segment_ref": { "artifact_id": "sha256:<...>", "artifact_relpath": "..." },
      "first_example_id_u32": <int>,
      "example_count_u32": <int>
    }
  ]
}
```

Rules:

* `segments[]` MUST be sorted by `first_example_id_u32` ascending.
* Segments MUST be contiguous with no gaps and no overlaps.
* `dataset_id` is the self-hash of manifest bytes with `dataset_id` zeroed.

### 5.2 `qxrl_dataset_segment_v1.bin`

**Purpose:** fixed-width token sequences, deterministic decode.

Header:

| Field                  |                        Type |
| ---------------------- | --------------------------: |
| `schema_id_u32`        | u32 = `0x51584453` (“QXDS”) |
| `version_u32`          |                     u32 = 1 |
| `first_example_id_u32` |                         u32 |
| `example_count_u32`    |                         u32 |
| `seq_len_u32`          |                         u32 |
| `reserved_u32`         |                     u32 = 0 |

Body:

* `tokens[example_count][seq_len]` as `u32_le` token ids.

Rules:

* token ids MUST be `< vocab_size_u32` (else reject).
* padding uses token 0.
* segment hash is `sha256` of raw bytes.

---

## 6. Weights and parameter naming (reuses EUDRS‑U WRoot)

QXRL parameters are stored using:

* `q32_tensor_block_v1.bin` blocks (EUDRS‑U spec §13.1)
* `weights_manifest_v1.json` (EUDRS‑U spec §13.2)

### 6.1 Canonical tensor naming (mandatory)

QXRL tensors MUST use deterministic names. v1 reserves the namespace:

* `qxrl/emb_tok` — token embedding table `[vocab_size, d_model]`
* `qxrl/emb_pos` — positional embedding `[seq_len, d_model]` (optional; if omitted, treated as zeros)
* For each layer `ℓ`:

**QRE_V1**

* `qxrl/qre/l<ℓ>/W1` `[mlp_hidden, d_model]`
* `qxrl/qre/l<ℓ>/b1` `[mlp_hidden]`
* `qxrl/qre/l<ℓ>/W2` `[d_model, mlp_hidden]`
* `qxrl/qre/l<ℓ>/b2` `[d_model]`

**TSAE_TOPK_V1**

* `qxrl/tsae/l<ℓ>/Wq` `[d_model, d_model]`
* `qxrl/tsae/l<ℓ>/Wk` `[d_model, d_model]`
* `qxrl/tsae/l<ℓ>/Wv` `[d_model, d_model]`
* `qxrl/tsae/l<ℓ>/Wo` `[d_model, d_model]`
* `qxrl/tsae/l<ℓ>/W1` `[mlp_hidden, d_model]`
* `qxrl/tsae/l<ℓ>/b1` `[mlp_hidden]`
* `qxrl/tsae/l<ℓ>/W2` `[d_model, mlp_hidden]`
* `qxrl/tsae/l<ℓ>/b2` `[d_model]`
* If RMSNorm enabled:

  * `qxrl/tsae/l<ℓ>/norm_scale` `[d_model]`

**Output projection for masked logits** (if masked objective enabled):

* `qxrl/out_tok` `[vocab_size, d_model]`
  (tied weights allowed: if `tied=true` in model manifest, `out_tok` is an alias of `emb_tok` and MUST NOT be separately stored.)

Tensor ordering for Merkle leaves is exactly the EUDRS‑U rule: tensor name ascending, then block index ascending.

---

## 7. Forward computation (QRE and TSAE)

All computations are Q32 with the aligned primitives.

### 7.1 Shared components

#### 7.1.1 Token embedding lookup

For token `t`:

* embedding row = `emb_tok[t]` (Q32 vector length `d_model`)

Sequence input `X[L,d_model]`:

* `X[i] = emb_tok[token[i]] + emb_pos[i]` using `AddSat` elementwise.

#### 7.1.2 Clip and ReLU

* `ReLU(x) = max(0, x)` on `S64`
* `ClipElem(x, B) = min(max(x, -B), B)` where B is Q32 `S64`.

At exactly boundary, values are clipped; backward derivative at boundary is defined as 0 (§8.5).

---

### 7.2 QRE_V1 layer

For each position vector `h ∈ S64[d_model]`:

1. `u1[j] = DotQ32S128Acc(h, W1[j,*]) + b1[j]`
2. `a1[j] = ReLU(u1[j])`
3. `u2[k] = DotQ32S128Acc(a1, W2[k,*]) + b2[k]`
4. `h' = ClipElemVec( h + u2, clip_act_q32 )`

Sequence output is `H'[L,d_model]`.

---

### 7.3 TSAE_TOPK_V1 layer (deterministic Top‑K attention + MLP)

Let `H[L,d_model]` be input.

#### 7.3.1 Optional RMSNorm_V1 (OpSet function)

If `norm_kind == RMSNORM_V1`, apply:

For each position i:

1. `ms = mean( MulQ32(H[i,k], H[i,k]) )` computed as:

   * accumulate `S128` over k in ascending order
   * divide by `d_model` using `DivQ32_Pos_RNE_V1` (see §7.3.4)
2. `den = eps + ms` using `AddSat`
3. `inv = InvSqrtQ32_V1(den)` (see §7.3.5)
4. `Hn[i,k] = MulQ32( MulQ32(H[i,k], inv), norm_scale[k] )`

If norm is NONE: `Hn = H`.

#### 7.3.2 Q/K/V projections

For each position i:

* `q_i = matmul(Hn[i], Wq)` producing `d_model`
* `k_i = matmul(Hn[i], Wk)`
* `v_i = matmul(Hn[i], Wv)`

Matmul uses `DotQ32S128Acc` per output coordinate.

Then reshape into heads:

* `q_i[h, d_head]`, `k_i[h,*]`, `v_i[h,*]`

#### 7.3.3 Attention scores and Top‑K

For each position i and head h, for each j in `0..L-1`:

* `s_ij = MulQ32( DotQ32S128Acc(q_i[h], k_j[h]), attn_scale_q32 )`

Select `J_i` = TopKDet over j indices of `s_ij`, size `topk_k_u32`.
Comparator: score desc, j asc.

#### 7.3.4 Nonnegative gating and normalization

For j in `J_i`:

* `a_ij = max(0, s_ij)` (ReLU on score)

Let `A_i = sum_{j∈J_i} a_ij` in ascending j order using `S128` accumulate then `SAT64`.

If `A_i == 0`:

* set `w_ij = uniform_q32(topk_k)` deterministically:

  * `base = floor((1<<32)/K)`
  * `rem = (1<<32) - base*K`
  * assign `w` as:

    * for the first `rem` items in ascending j order: `w = base+1`
    * remaining: `w = base`
      Else:
* `w_ij = DivQ32_Pos_RNE_V1(a_ij, A_i)`.

**DivQ32_Pos_RNE_V1(a,b)** (OpSet function, b>0, a>=0):

* compute `num = (S128(a) << 32) + (S128(b) >> 1)`
* compute `q = num / S128(b)` using trunc toward zero (same as floor since positive)
* return `SAT64(q)`

#### 7.3.5 InvSqrtQ32_V1 (OpSet function; required if RMSNorm enabled)

Input: `x_q32` MUST satisfy `x_q32 > 0`. Else reject.

Algorithm:

1. Compute exponent `e = msb(u64(x_q32)) - 32` (signed).
2. Mantissa normalize:

   * if `e>=0`: `m = x_q32 >> e`
   * else: `m = x_q32 << (-e)` (saturating)
   * Now `m ∈ [1<<32, 2<<32)`.
3. LUT index:

   * `idx = (u64(m) >> 24) & 0xFF` (top 8 frac bits)
4. `y = inv_sqrt_lut[idx]` (Q32), where LUT is a pinned artifact referenced by OpSet manifest.
5. Exponent correction:

   * if `e` is odd: `y = MulQ32(y, INV_SQRT2_Q32)` where `INV_SQRT2_Q32` is a pinned constant in opset.
   * shift by `k = floor(e/2)`:

     * if `k>0`: `y = y >> k`
     * if `k<0`: `y = y << (-k)` saturating
6. Newton refinement with fixed iterations `INV_SQRT_ITERS_U32` (manifest-pinned, v1 default 2):

   * repeat:

     * `y2 = MulQ32(y, y)`
     * `xy2 = MulQ32(x_q32, y2)`
     * `half_xy2 = xy2 >> 1`
     * `three_halves = 0x0000000180000000` (1.5 in Q32)
     * `term = AddSat(three_halves, -half_xy2)`
     * `y = MulQ32(y, term)`
7. return y

Any saturation during steps MUST increment a counter that is reported in the scorecard (see §10).

#### 7.3.6 Attention output

For each i, head h:

* `o_i[h] = sum_{j∈J_i} MulQ32(w_ij, v_j[h])` reduced in ascending j order (S128 accumulate per component, clamp at end)

Concatenate heads and project:

* `o_i_full = matmul(concat(o_i[*]), Wo)`
* residual:

  * `h_attn = ClipElemVec(H[i] + o_i_full, clip_act_q32)`

#### 7.3.7 MLP block

As in QRE, applied to `h_attn`:

* `h_out = ClipElemVec(h_attn + W2(ReLU(W1 h_attn + b1)) + b2, clip_act_q32)`

Output layer yields `H'`.

---

## 8. Training algorithm (deterministic; replay-verifiable)

Training MUST be specified entirely by:

* `qxrl_model_manifest_v1`
* `qxrl_training_manifest_v1`
* `qxrl_dataset_manifest_v1`
* initial weights rule
* PRNG seed derivation and consumption order

### 8.1 Initialization (deterministic)

Initialization scheme v1: `PRNG_UNIFORM_Q32_V1`

For each parameter element:

* draw `u64` from PRNG
* map to signed Q32 in range `[-init_scale, +init_scale]` deterministically:

  * `r = (u64 >> 1)` (63-bit)
  * `sign = u64 & 1`
  * `val = (r % init_scale_q32)` (nonnegative)
  * if sign==1: `val = -val`
* store `val`

`init_scale_q32` is a field in training manifest (Q32).

PRNG stream:

* v1 uses a single stream; consumption order is exactly:

  1. init draws in tensor-name/block-index/element order
  2. per-step draws in the order specified below

### 8.2 Mask selection (deterministic)

Given a sequence length `L`, mask rate in basis points `mask_rate_bp`, masks cap `M_cap`:

For each example in batch, do:

1. compute `target_masks = floor(L * mask_rate_bp / 10000)`
2. `m = min(target_masks, M_cap)`
3. choose mask positions by repeated PRNG draws:

   * maintain a boolean `masked[L]=false`
   * while count < m:

     * draw `u64`
     * `p = u64 % L`
     * if p already masked: continue
     * mark masked[p]=true
4. produce masked input tokens:

   * if masked[p]: token[p] = mask_token_u32 else unchanged

This is replayable and uses a fully specified draw order.

### 8.3 Negatives (deterministic)

#### 8.3.1 Contrastive hinge negatives

Two options (manifest selected):

* `IN_BATCH`:

  * negatives for anchor i are the other batch examples in ascending batch index order, capped to `negatives_per_anchor_u32`
* `DATASET_SAMPLE`:

  * sample `negatives_per_anchor_u32` example ids from the dataset using PRNG draws:

    * each draw gives `idx = u64 % dataset_size`
    * if idx equals anchor example id: resample (deterministic loop; must cap resamples at `NEG_RESAMPLE_CAP`, else reject)

### 8.4 Objectives

Let `fθ(x)` be the embedding output vector `z ∈ S64[d_embed]`.

#### 8.4.1 Embedding normalization

If `normalize_embed_kind` is:

* `NONE`: `z̃=z`
* `L1_NORM_V1`: `z̃ = DivVecQ32(z, sum(|z|) + eps)` (DivQ32_Pos_RNE_V1 per component, eps pinned)
* `RMSNORM_V1`: treat vector as one “position” and apply RMSNorm rules with InvSqrtQ32

#### 8.4.2 Contrastive hinge loss

For each anchor `x` and its positive view `x+` (same example, different mask pattern generated deterministically):

* `s_pos = DotQ32S128Acc(z̃, z̃+)`
* for each negative `x-`:

  * `s_neg = DotQ32S128Acc(z̃, z̃-)`
  * hinge term:

    * `t = margin_q32 - s_pos + s_neg`
    * `loss += max(0, t)`
      At `t==0`, gradient is defined as 0.

#### 8.4.3 Masked hinge loss

For each masked position p in a sequence:

* model produces hidden `h_p ∈ S64[d_model]`
* candidate set includes:

  * true token `y`
  * `R = negatives_per_mask_u32` negative token ids sampled deterministically via PRNG, excluding `y` (cap resamples)
* logits:

  * `g(v) = DotQ32S128Acc(h_p, out_tok[v])`
* hinge loss:

  * for each negative ν:

    * `t = margin_q32 - g(y) + g(ν)`
    * add `max(0,t)`

#### 8.4.4 Regularization

* Weight decay: applied inside optimizer update (see §9)
* Anti-collapse variance floor:

  * evaluate embedding variance on a deterministic anchor minibatch
  * record `embed_variance_min_q32`
  * promotion gate checks it against `embed_variance_floor_q32`

### 8.5 Backpropagation rules (deterministic subgradients)

Backward must use fixed-point arithmetic with these boundary rules:

* ReLU: derivative 1 iff input > 0 else 0 (at 0 → 0)
* Clip: derivative 1 iff |x| < B else 0 (at boundary → 0)
* Hinge max: derivative 1 iff t > 0 else 0 (at 0 → 0)
* Top‑K selection: treat selected indices `J_i` as constants; gradients flow only through selected paths.

---

## 9. Optimizers (deterministic)

### 9.1 SGD_MOMENTUM_Q32_V1 (required)

Let `w`, `v`, `g` be Q32 S64 arrays.

Update per element:

1. clip gradient elementwise:

   * `g = ClipElem(g, clip_grad_elem_q32)`
2. momentum:

   * `v = AddSat( MulQ32(mu, v), g )`
3. weight decay term:

   * `wd_term = MulQ32(weight_decay_q32, w)`
4. update:

   * `w = AddSat( w, -MulQ32(lr_q32, AddSat(v, wd_term)) )`
5. clip parameter:

   * `w = ClipElem(w, clip_param_elem_q32)`

Any saturation MUST increment counters reported in trace/scorecard.

### 9.2 ADAMW_Q32_V1 (optional)

Allowed only if:

* bias LUT exists and hashes match,
* DivQ32_Pos_RNE_V1 and InvSqrtQ32_V1 are present in the OpSet,
* golden tests pass.

Exact AdamW element update is defined in implementation terms using those OpSet operations; if enabled, its full numeric path MUST be locked by the opset manifest and determinism cert.

---

## 10. Trace, replay binding, checkpoints (uses EUDRS‑U digests)

QXRL training MUST use the EUDRS‑U training digest record (`eudrs_u_train_step_digest_v1`, EUDRS‑U spec §14.1).

### 10.1 Populating the step digest fields for QXRL steps

For each global step `t`:

* `batch_hash32` MUST be:

  * SHA256 over packed bytes:

    * epoch index
    * step index
    * ordered example ids in batch
    * mask positions per example (packed bitmap)
    * sampled negatives (example ids or token ids) in deterministic order
* `wm_batch_hash32` MUST be used as the **QXRL batch evidence hash**:

  * SHA256 of per-example:

    * embedding hash `SHA256(z_bytes)`
    * `s_pos_q32`, all `s_neg_q32`
    * masked hinge summary hashes
* `wroot_before32`, `wroot_after32`, `optroot_after32` are as usual.
* `retrieval_trace_root32` is:

  * zero unless the training uses ML-Index for negative selection, in which case it is the retrieval trace Merkle root.
* other roots not used by QXRL are set to zero.

`prng_counter_u64` is total draws consumed so far.

### 10.2 Checkpoints

If checkpoints enabled:

* every `checkpoint_every_steps_u64`, producer writes:

  * a `weights_manifest_v1.json` snapshot ref
  * the `H_train` chain value at that step

Verifier MAY use checkpoints as replay optimization but MUST still require exact final tails and roots.

---

## 11. Evaluation (deterministic; fail-closed gates)

Evaluation MUST compute the scorecard (§4.4) and MUST enforce gates from `qxrl_eval_manifest_v1`:

* retrieval recall@K ≥ floor
* masked acc@1 ≥ floor
* drift ≤ max_drift (if enabled)
* collapse metrics meet bounds

All eval computations must be deterministic and hash-bound into `H_eval` (EUDRS‑U eval digest chain; use the same style as EUDRS‑U §14.2).

---

## 12. Promotion gating for QXRL updates (integrated with EUDRS‑U gates)

A QXRL update is a **WRoot change**. To align with the EUDRS‑U acceptance model (which expects gate artifacts), QXRL promotions MUST include:

1. `qxrl_eval_scorecard_v1.json` (claimed)
2. `stability_metrics_v1.json` that includes QXRL metrics (claimed)
3. A `cac_v1.json` where:

   * `delta_id` represents the proposed WRoot update (e.g., hash of `(wroot_before||wroot_after||model_id)`).
   * each “episode” is a deterministic eval task from `qxrl_eval_manifest_v1`.
   * return `R_e` is a manifest-defined scalar Q32 utility (e.g., weighted sum of recall and masked accuracy).
   * advantage `A_e = R_cf - R_base` where:

     * base uses old root tuple’s QXRL weights
     * cf uses proposed root tuple’s QXRL weights
     * everything else identical and replayed
   * `delta_u_q32` is the clipped weighted sum of `A_e` records.

This makes QXRL promotions compatible with the EUDRS‑U “gate bundle” pattern without changing RE1–RE4.

---

## 13. RE2 verification procedure (fail-closed)

RE2 verification for a candidate QXRL promotion MUST:

1. Load previously active root tuple and the proposed root tuple.
2. Validate all referenced artifacts via `ArtifactRefV1`:

   * safe relpaths
   * sha256 matches
3. Recompute:

   * QXRL training replay (full replay or checkpoint-resume replay) to obtain:

     * `wroot_after_replay`
     * `H_train_tail_replay`
   * QXRL eval to obtain:

     * `qxrl_eval_scorecard_replay`
     * `H_eval_tail_replay`
4. Recompute CAC paired eval records and CAC root.
5. Enforce all QXRL floors and CAC thresholds.
6. Require all claimed roots and tails match replay exactly.
7. Emit `eudrs_u_subverifier_receipt_v1.json` with `VALID` only if all pass.

Any mismatch or cap violation ⇒ fail with a single reason code (use the EUDRS‑U taxonomy; add QXRL-specific codes under the same mechanism if needed).

---

## 14. Integration into EUDRS‑U/QXWMR/MCL (how QXRL is used)

### 14.1 QXRL as the key extractor for ML‑Index

When building ML‑Index pages (EUDRS‑U spec §11), QXRL provides `key_q32[d]`:

* For a record payload (concept shard, strategy cartridge, memory segment):

  1. deterministically tokenize payload bytes:

     * if tokenization kind is `BYTE_TOK_257_V1`:

       * token 0 = PAD
       * token (b+1) encodes byte value b
       * truncate/pad to `seq_len_u32`
  2. compute embedding z via QXRL encoder
  3. map to key vector:

     * if `d_embed == key_dim`: key = z
     * else key = `matmul(z, W_keyproj)` where `W_keyproj` is a QXRL tensor pinned in WRoot
* Store key in index pages as Q32 s64.

### 14.2 QXRL in MCL strategies

SLS‑VM opcodes that retrieve shards/strategies may use ML‑Index keys. Therefore:

* strategy execution remains deterministic
* retrieval is replayable
* QXRL weights are part of WRoot, so retrieval behavior is bound by WRoot hash

---

## 15. Implementation mapping (exact repo locations)

This is where engineering implements QXRL inside the repo structure defined earlier.

### 15.1 RE4 schemas

Add:

* `Genesis/schema/v18_0/qxrl_model_manifest_v1.jsonschema`
* `Genesis/schema/v18_0/qxrl_training_manifest_v1.jsonschema`
* `Genesis/schema/v18_0/qxrl_eval_manifest_v1.jsonschema`
* `Genesis/schema/v18_0/qxrl_eval_scorecard_v1.jsonschema`
* `Genesis/schema/v18_0/qxrl_dataset_manifest_v1.jsonschema`

### 15.2 RE2 modules

Add under:

* `CDEL-v2/cdel/v18_0/eudrs_u/`

Files:

* `qxrl_common_v1.py`
* `qxrl_dataset_v1.py` (segment decode + dataset iteration)
* `qxrl_forward_qre_v1.py`
* `qxrl_forward_tsae_v1.py`
* `qxrl_ops_v1.py` (matmul, relu, clip, topk)
* `qxrl_opset_math_v1.py` (DivQ32_Pos_RNE_V1, InvSqrtQ32_V1 + LUT integration)
* `qxrl_backward_v1.py`
* `qxrl_optimizer_v1.py`
* `qxrl_train_replay_v1.py`
* `qxrl_eval_v1.py`
* `verify_qxrl_v1.py`

And integrate into:

* `CDEL-v2/cdel/v18_0/eudrs_u/verify_eudrs_u_run_v1.py`
  (dispatch to QXRL verification if the promotion summary includes QXRL manifests/scorecard)

### 15.3 Orchestrator campaign

Add (optional but recommended for separation):

* `orchestrator/rsi_qxrl_train_v1.py`

Outputs staged artifacts under:

* `eudrs_u/staged_registry_tree/polymath/registry/eudrs_u/...`

---

## 16. Required golden tests (must exist before enabling capability)

1. DotQ32 and MulQ32 test vectors (including negative values).
2. TopKDet stability (ties, ordering).
3. DivQ32_Pos_RNE_V1 test vectors.
4. InvSqrtQ32_V1 test vectors + LUT hash pin.
5. End-to-end single-step training replay: exact `wroot_after` and `H_train_tail`.
6. End-to-end eval replay: exact scorecard hash.
7. CAC paired eval replay: exact episode record hashes and CAC root.

---

If you want this QXRL spec to be emitted as **repo-ready schema stubs + a single markdown file** (so engineering can drop it into `docs/` and start implementing with exact filenames and constants), say so and I will output:

* concrete default constants (clip bounds, eps, invsqrt iters, LUT requirements),
* the exact `schema_id_u32` constants as hex,
* and a complete list of reason codes to add for QXRL failures.
