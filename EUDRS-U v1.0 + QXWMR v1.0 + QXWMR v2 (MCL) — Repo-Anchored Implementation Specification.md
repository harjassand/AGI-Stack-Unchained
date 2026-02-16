# EUDRS-U v1.0 + QXWMR v1.0 + QXWMR v2 (MCL) — Repo-Anchored Implementation Specification

**Repo root:** `AGI-Stack-Clean/`
**As-of:** 2026-02-13
**Baseline commit:** `b59c1fd37d9f9e888c266e539cb69c5c5c260d81` (branch `fix/unified-4h-ready`)
**Trust boundary:** RE1–RE4 unchanged (per handoff pack).
**Determinism substrate:** GCJ-1 canonical JSON (floats rejected), Q32 ops in RE2, replay verifiers fail-closed.

This spec is **normative**. “MUST/SHALL” are mandatory for correctness and replay-verification. Anything not specified is **forbidden**.

---

## 0. Scope and deliverables

### 0.1 What this spec implements end-to-end

This spec defines **all** required artifacts, layouts, algorithms, verifiers, and Omega integration to implement:

1. **QXWMR v1.0**: WL-canonical bounded typed-graph state + Q32 dynamics + deterministic beam planning traces + optional DEP.
2. **QXWMR v2 (MCL)**: Concept Genome Bank (CGB), Fractal Abstraction Ladder (FAL), Strange Loop Strategy VM (SLS-VM), plus deterministic ontology evolution actions (EPO).
3. **EUDRS-U v1.0**: multi-root substrate (`R_k`) with Merkle-sharded weights/memory/indexes; deterministic ML-Index retrieval; CAC/UFC promotion gating; ontology stability gates STAB-G0..G5; Ladder-Adjoint invariant LA-SUM; URC-VM capsule family (RAM-complete).

All changes are **additive** and **promotion-gated**, and all decisions are **replay-verifiable**.

### 0.2 Non-goals

* No changes to RE1/RE2/RE3/RE4 trust layering.
* No new “approval” or “council” mechanisms.
* No reliance on JSON floats.
* No network access beyond existing dsbx profiles.
* No unverifiable sampling. (A deterministic sampling mode may be defined later, but **v1 requires full deterministic replay**.)

---

## 1. Repo integration plan (files, modules, ownership)

### 1.1 New modules (RE2)

All verifier and determinism-critical logic MUST live in RE2 (`CDEL-v2/cdel/`) and be invoked by Omega subverification/promotion gating.

Add the following module tree:

```
CDEL-v2/cdel/v18_0/eudrs_u/
  __init__.py
  eudrs_u_common_v1.py
  eudrs_u_hash_v1.py
  eudrs_u_merkle_v1.py
  eudrs_u_q32ops_v1.py
  eudrs_u_artifact_refs_v1.py
  qxwmr_state_v1.py
  qxwmr_canon_wl_v1.py
  fal_ladder_v1.py
  dep_v1.py
  sls_vm_v1.py
  urc_vm_v1.py
  ml_index_v1.py
  ontology_v1.py
  cac_v1.py
  ufc_v1.py
  stability_gates_v1.py
  verify_eudrs_u_promotion_v1.py
  verify_eudrs_u_run_v1.py
```

**All** deterministic algorithms in this spec are implemented here, and **all** verification recomputation uses these modules (not campaign code).

### 1.2 New schemas (RE4)

Add JSON Schemas under the currently-loaded schema directory:

```
Genesis/schema/v18_0/
  eudrs_u_artifact_ref_v1.jsonschema
  eudrs_u_root_tuple_v1.jsonschema
  qxwmr_world_model_manifest_v1.jsonschema
  qxwmr_training_manifest_v1.jsonschema
  qxwmr_eval_manifest_v1.jsonschema
  concept_def_v1.jsonschema
  concept_bank_manifest_v1.jsonschema
  abstraction_ladder_manifest_v1.jsonschema
  strategy_vm_manifest_v1.jsonschema
  ml_index_manifest_v1.jsonschema
  cooldown_ledger_v1.jsonschema
  stability_metrics_v1.jsonschema
  cac_v1.jsonschema
  ufc_v1.jsonschema
  determinism_cert_v1.jsonschema
  universality_cert_v1.jsonschema
  eudrs_u_promotion_summary_v1.jsonschema
```

**Note:** modifying `Genesis/schema/` is a v19 governed prefix ⇒ **axis bundle required** for the promotion that introduces these schemas (per your v19 promoter).

### 1.3 New orchestrator campaigns

Campaign code is allowed to be untrusted (RE3), but **verification MUST be in RE2**. For simplicity and reuse of Omega execution patterns, add orchestrator-dispatchable campaign modules (under `orchestrator/`) that:

* produce evidence artifacts
* produce a promotion bundle that installs only additive artifacts (weights, roots, indices) under a non-governed prefix (recommended: `polymath/registry/eudrs_u/`)

Add:

```
orchestrator/rsi_eudrs_u_train_v1.py
orchestrator/rsi_eudrs_u_index_rebuild_v1.py
orchestrator/rsi_eudrs_u_ontology_update_v1.py
orchestrator/rsi_eudrs_u_eval_cac_v1.py
```

These are orchestrator-side producers. RE2 replays and verifies their outputs via subverifier.

**Important:** `orchestrator/` is v19 governed prefix ⇒ adding these files requires axis bundle for the initial code promotion.

### 1.4 Storage location for activated EUDRS-U roots and artifacts

To avoid requiring an axis bundle for every weight/index update, the activated EUDRS-U artifacts MUST live outside v19 governed prefixes. This spec standardizes on:

```
polymath/registry/eudrs_u/
  active/
    active_root_tuple_ref_v1.json            (small pointer, canonical JSON)
  roots/
    sha256_<...>.eudrs_u_root_tuple_v1.json
  manifests/
    sha256_<...>.qxwmr_world_model_manifest_v1.json
    sha256_<...>.qxwmr_training_manifest_v1.json
    sha256_<...>.qxwmr_eval_manifest_v1.json
    sha256_<...>.concept_bank_manifest_v1.json
    sha256_<...>.abstraction_ladder_manifest_v1.json
    sha256_<...>.strategy_vm_manifest_v1.json
    sha256_<...>.ml_index_manifest_v1.json
  ontology/
    handles/
      sha256_<...>.ontology_handle_map_v1.json
    concepts/
      sha256_<...>.concept_def_v1.json
  strategies/
    sha256_<...>.strategy_cartridge_v1.bin
    sha256_<...>.strategy_def_v1.json
  capsules/
    sha256_<...>.urc_capsule_v1.bin
  memory/
    segments/
      sha256_<...>.memory_segment_v1.bin
    compaction/
      sha256_<...>.memory_compaction_receipt_v1.json
  indices/
    sha256_<...>.ml_index_root_v1.bin
    buckets/
      <bucket_id_u32>/
        pages/
          sha256_<...>.ml_index_page_v1.bin
  weights/
    sha256_<...>.weights_manifest_v1.json
    blocks/
      sha256_<...>.q32_tensor_block_v1.bin
  certs/
    sha256_<...>.determinism_cert_v1.json
    sha256_<...>.universality_cert_v1.json
  gates/
    sha256_<...>.cac_v1.json
    sha256_<...>.ufc_v1.json
    sha256_<...>.cooldown_ledger_v1.json
    sha256_<...>.stability_metrics_v1.json
```

This directory is intended to be “data-like registry content” and **not** a governed prefix.

---

## 2. Global determinism and content-addressing rules (DC-1 + GCJ-1)

### 2.1 Canonical JSON (GCJ-1)

All JSON artifacts MUST be written with RE2 canonicalization (`CDEL-v2/cdel/v1_7r/canon.py:write_canon_json()`), and MUST satisfy:

* keys sorted, separators `(",", ":")`, UTF-8, trailing newline
* **no floats** anywhere (load rejects floats; canonicalization rejects floats)
* only types: dict, list, str, bool, int, null

### 2.2 Q32 representation

#### 2.2.1 JSON Q32 type

All Q32 scalars in JSON MUST be encoded as an object with exactly one key:

```json
{"q": <int>}
```

This matches `cdel.v18_0.omega_common_v1.q32_int()` strictness (dict must have exactly key set `{"q"}`).

#### 2.2.2 Binary Q32 type

In all binary artifacts, Q32 scalars MUST be stored as signed 64-bit little-endian integers (`s64_le`), interpreted as `value = q / 2^32`.

### 2.3 Deterministic choice operators

All “choice” is restricted to:

* `ArgMaxDet(scores[])`: return smallest index among maximum scores.
* `TopKDet((score, id)[], K)`: sort by `(score desc, id asc)` and take first K.

No sampling, no nondeterministic hash iteration, no “unordered set” iteration.

### 2.4 PRNG

PRNG may be used only for deterministic negative selection or deterministic sampling schedules, and MUST be:

* OpSet-pinned algorithm (exact spec below)
* seeded by a derivation that is fully specified and hash-bound into trace digests
* consumed in a fully specified order

**v1 requirement:** every PRNG call site MUST increment a `prng_counter_u64` that is emitted in step digests.

### 2.5 Hash function

All artifact IDs are `sha256` over canonical bytes:

* for canonical JSON: `sha256(canon_bytes(obj))`
* for binary: `sha256(binary_bytes)`

The hex-form filename MUST be `sha256_<64hex>.<artifact_type>.(json|bin)`.

No other hash algorithms permitted in v1.

---

## 3. Standard artifact reference contract (mandatory for all EUDRS-U manifests)

### 3.1 `ArtifactRefV1` (canonical JSON)

**Schema ID:** `eudrs_u_artifact_ref_v1`

```json
{
  "artifact_id": "sha256:<64hex>",
  "artifact_relpath": "polymath/registry/eudrs_u/.../sha256_<64hex>.<type>.(json|bin)"
}
```

#### Constraints (MUST be verified in RE2)

* `artifact_id` MUST match regex `^sha256:[0-9a-f]{64}$`.
* `artifact_relpath` MUST be a **safe repo-relative path**:

  * MUST NOT be absolute
  * MUST NOT contain `..` segments
  * MUST NOT contain backslashes
  * MUST NOT contain NUL
  * MUST NOT start with `/`
* The file contents at `artifact_relpath` MUST hash to `artifact_id` using the rules in §2.5.
* Any mismatch ⇒ fail-closed.

Implement `require_safe_relpath_v1()` in `eudrs_u_artifact_refs_v1.py` and call from all verifiers.

---

## 4. Root tuple `R_k` (EUDRS-U activation state)

### 4.1 Root tuple artifact

**Type:** `eudrs_u_root_tuple_v1` (canonical JSON)
**Purpose:** single activated pointer that binds *all* active roots (schemas/ontology/strategy/capsules/memory/index/weights).

#### Location

* Stored immutable under `polymath/registry/eudrs_u/roots/sha256_<...>.eudrs_u_root_tuple_v1.json`
* “Activated” by updating the pointer file:

  * `polymath/registry/eudrs_u/active/active_root_tuple_ref_v1.json` (canonical JSON)

### 4.2 `active_root_tuple_ref_v1.json`

Canonical JSON:

```json
{
  "schema_id": "active_root_tuple_ref_v1",
  "active_root_tuple": {
    "artifact_id": "sha256:<...>",
    "artifact_relpath": "polymath/registry/eudrs_u/roots/sha256_<...>.eudrs_u_root_tuple_v1.json"
  }
}
```

### 4.3 `eudrs_u_root_tuple_v1.json` schema (normative)

```json
{
  "schema_id": "eudrs_u_root_tuple_v1",
  "epoch_u64": <int>,                          // monotone increase per promotion
  "dc1_id": "dc1:q32_v1",
  "opset_id": "opset:eudrs_u_v1:sha256:<64hex>",

  "sroot": { "artifact_id": "...", "artifact_relpath": "..." },
  "oroot": { "artifact_id": "...", "artifact_relpath": "..." },
  "kroot": { "artifact_id": "...", "artifact_relpath": "..." },
  "croot": { "artifact_id": "...", "artifact_relpath": "..." },
  "mroot": { "artifact_id": "...", "artifact_relpath": "..." },
  "iroot": { "artifact_id": "...", "artifact_relpath": "..." },
  "wroot": { "artifact_id": "...", "artifact_relpath": "..." },

  "stability_gate_bundle": { "artifact_id": "...", "artifact_relpath": "..." },  // CAC/UFC/stability roots for epoch
  "determinism_cert": { "artifact_id": "...", "artifact_relpath": "..." },
  "universality_cert": { "artifact_id": "...", "artifact_relpath": "..." }
}
```

#### Verification rules

RE2 MUST verify:

* `epoch_u64` increases by exactly +1 relative to previously active root tuple (fetched from active pointer) unless explicitly configured to allow skips (v1: **no skips**).
* all referenced artifacts exist and hash-match.
* all referenced manifests agree on capacities and OpSet/DC-1 ids.
* root tuple and all dependencies satisfy `require_no_absolute_paths()` recursively.

---

## 5. QXWMR v1.0 canonical state, packing, and WL canonicalization

This section is fully deterministic and MUST be implemented exactly.

### 5.1 QXWMR packed state binary: `qxwmr_state_packed_v1.bin`

**Type:** `qxwmr_state_packed_v1` (binary)
**Canonical bytes:** fixed-width little-endian, all padding zero.
**Used by:** training traces, plan traces, memory segments, concept shard patterns.

#### 5.1.1 Header layout (all little-endian)

| Field               | Type | Value                                |
| ------------------- | ---: | ------------------------------------ |
| `schema_id_u32`     |  u32 | constant `0x5158574D` (“QXWM”)       |
| `version_u32`       |  u32 | 1                                    |
| `flags_u32`         |  u32 | bitfield (see below)                 |
| `N_u32`             |  u32 | capacity N                           |
| `E_u32`             |  u32 | capacity E                           |
| `K_n_u32`           |  u32 | node token vocab                     |
| `K_e_u32`           |  u32 | edge token vocab                     |
| `d_n_u32`           |  u32 | node attr dims                       |
| `d_e_u32`           |  u32 | edge attr dims                       |
| `d_r_u32`           |  u32 | residual dims                        |
| `WL_R_u32`          |  u32 | WL rounds                            |
| `CANON_TIE_CAP_u32` |  u32 | tie cap                              |
| `Lmax_u16`          |  u16 | ladder max level (0 if FAL disabled) |
| `kappa_bits_u16`    |  u16 | number of phase bits                 |
| `reserved_u32`      |  u32 | 0                                    |

**Flags:**

* bit0: `FAL_ENABLED`
* bit1: `DEP_ENABLED`
* bit2: `KAPPA_ENABLED` (kappa_bits > 0)
* other bits: must be 0 in v1

#### 5.1.2 Array layout (canonical order)

Immediately after header:

1. `node_tok[N]` as `u32_le`
2. `node_level[N]` as `u16_le` **only if** `FAL_ENABLED` else omitted
3. `node_attr[N][d_n]` as `s64_le`
4. `src[E]` as `u32_le`
5. `dst[E]` as `u32_le`
6. `edge_tok[E]` as `u32_le`
7. `edge_attr[E][d_e]` as `s64_le`
8. `r[d_r]` as `s64_le`
9. `kappa_bitfield` length = `ceil(kappa_bits/64)*8` bytes, little-endian bit packing:

   * bit i stored at `(word_index=i//64, bit_index=i%64)`.

All omitted sections (d_r=0, etc) are absent. No variable-length strings.

#### 5.1.3 Null invariants (MUST hold)

* `node_tok[i] == 0` ⇔ node is `NULL_NODE`; then:

  * `node_attr[i][*] == 0`
  * if FAL enabled: `node_level[i] == 0`
* `edge_tok[e] == 0` ⇔ `NULL_EDGE`; then:

  * `src[e] == 0`, `dst[e] == 0`
  * `edge_attr[e][*] == 0`

Fail-closed on any violation.

---

### 5.2 Canonicalization operator `CANON(s)`

**Implementation entry point:** `qxwmr_canon_wl_v1.canon_state_packed_v1(state_bytes) -> canonical_state_bytes`

`CANON` is a pure function over the decoded state that produces:

1. Ladder Normal Form validation (if enabled)
2. WL refinement labels `ℓ_k[i]`
3. Node sorting and bounded tie resolution
4. Node renumbering and edge key recompute
5. Edge sorting
6. Repack bytes exactly per §5.1

Any error ⇒ fail-closed.

#### 5.2.1 Ladder Normal Form validation (FAL)

If `FAL_ENABLED`:

* Define reserved edge token id `EDGE_TOK_ABSTRACTS = 1` (fixed by manifest; **must not change without opset bump**).
* The ladder graph is edges with `edge_tok[e]==EDGE_TOK_ABSTRACTS` and `edge_tok[e]!=0`.

Constraints (MUST all hold):

1. **No self-loop**: no ABSTRACTS edge where `src==dst`.
2. **Monotone levels**: for every ABSTRACTS edge `child=src`, `parent=dst`:

   * `node_level[child] + 1 == node_level[parent]`
3. **No cycles** in ABSTRACTS edges (DAG):

   * detect via deterministic DFS in node index order; any back-edge ⇒ reject
4. **Fan-in/out caps**:

   * per manifest: `ABSTRACTS_OUT_CAP`, `ABSTRACTS_IN_CAP`
   * count outgoing/incoming for each node; exceed ⇒ reject

No canonical “repair” is permitted in v1.

#### 5.2.2 WL refinement (order-invariant)

Use your v1 WL scheme, with these strict definitions:

* `HASH64(x_bytes) = lower_64bits(SHA256(x_bytes))`, where `lower_64bits` reads bytes `[24:32]` as `u64_le`. (This is fixed; do not change.)
* `fixed_bytes(node_attr[i])` is the raw packed `s64_le` sequence for that node’s attrs.
* Initial label:

  * `h_attr_node[i] = HASH64(node_attr_bytes_i)`
  * `ℓ_0[i] = HASH64(u32_le(node_tok[i]) || u64_le(h_attr_node[i]))`

Per-edge attribute hash:

* `h_attr_edge[e] = HASH64(edge_attr_bytes_e)`

Edge refinement message for node `i`:

* For each active edge `e` incident to `i`:

  * if `src[e]==i`: `dir=0`, neighbor `j=dst[e]`
  * if `dst[e]==i`: `dir=1`, neighbor `j=src[e]`
  * message tuple:

    * `(dir_u8, edge_tok_u32, neighbor_label_u64, h_attr_edge_u64)`
* Canonical multiset encoding:

  * sort messages by `(dir, edge_tok, neighbor_label, h_attr_edge)` ascending
  * run-length encode into `(message, count_u32)` sequence in that order
* Next label:

  * `ℓ_{k+1}[i] = HASH64( u64_le(ℓ_k[i]) || EncodeCountsSorted(M_k(i)) )`

WL rounds: `k = 0..WL_R-1`, producing `ℓ_{WL_R}[i]`.

#### 5.2.3 Node ordering key and tie resolution

Primary node key:

`K_V(i) = (ℓ_final_u64, node_tok_u32, h_attr_node_u64, node_level_u16 if FAL_ENABLED else 0, i_u32)`

* Sort nodes by `K_V` lexicographically.
* The last component `i` is included only to ensure deterministic total ordering in intermediate sorts; it MUST NOT be used to break canonical identity in tied-class exhaustive search. (Exhaustive search is over tied nodes that are equal under all components except `i`.)

Tie-class definition:

* A tie-class is a maximal contiguous block in the sorted list whose keys are equal **excluding** the final `i` component.

Tie resolution:

* If tie-class size `m > CANON_TIE_CAP` ⇒ reject.
* Else, perform exhaustive search over all permutations of the tie-class, holding other nodes fixed, and choose the permutation that yields lexicographically minimal packed bytes of the entire state (after full edge renumber/sort). This is deterministic.

This search MUST:

* enumerate permutations in lexicographic order of the original tied node indices (ascending) to ensure deterministic evaluation order
* compare candidate packed bytes as raw byte strings lexicographically

#### 5.2.4 Edge ordering

After node renumbering, edge key:

`K_E(e) = (src_u32, dst_u32, edge_tok_u32, h_attr_edge_u64, e_u32)`

Sort edges by `K_E` lexicographically. The trailing `e` only ensures deterministic ordering; identical edges still pack identically, so any stable ordering is acceptable as long as replay matches.

---

## 6. QXWMR v1.0 action/tool records and planning trace

### 6.1 Packed action record: `qxwmr_action_v1.bin`

Fixed-width:

| Field                  |                                 Type |
| ---------------------- | -----------------------------------: |
| `schema_id_u32`        |          u32 = `0x51584143` (“QXAC”) |
| `version_u32`          |                              u32 = 1 |
| `action_tok_u32`       |                                  u32 |
| `d_a_u32`              |                                  u32 |
| `action_args_q32[d_a]` |                          s64_le[d_a] |
| `action_aux_hash32`    | 32 bytes (sha256; all zeros allowed) |

### 6.2 Packed tool/observation record: `qxwmr_tool_obs_v1.bin`

Fixed-width:

| Field               |                             Type |
| ------------------- | -------------------------------: |
| `schema_id_u32`     |      u32 = `0x5158544F` (“QXTO”) |
| `version_u32`       |                          u32 = 1 |
| `tool_tok_u32`      |                              u32 |
| `d_u_u32`           |                              u32 |
| `obs_hash32`        | 32 bytes (sha256; zeros allowed) |
| `obs_args_q32[d_u]` |                      s64_le[d_u] |

### 6.3 Deterministic beam planning

Planner MUST implement your exact rules:

* Beam width `B`, depth `D`, `K_act`, episodes `P_eval` from eval manifest.
* Candidate actions are either:

  * full enumeration of a fixed ordered action list, or
  * `TopKDet` from proposer `P_ω` with tie breaks.

Beam ranking:

1. higher `score_q32`
2. ties: lexicographically smaller action sequence (compare by action_tok then args bytes)
3. ties: smaller `state_hash` (sha256 bytes ascending)

### 6.4 ExpandDigest fixed-width record

**Type:** `qxwmr_expand_digest_v1` (binary record, not standalone file)

Layout:

| Field                  |                             Type |
| ---------------------- | -------------------------------: |
| `episode_id_u32`       |                              u32 |
| `depth_u16`            |                              u16 |
| `parent_beam_rank_u16` |                              u16 |
| `child_rank_local_u16` |                              u16 |
| `reserved_u16`         |                          u16 = 0 |
| `action_tok_u32`       |                              u32 |
| `parent_state_hash32`  |                         32 bytes |
| `child_state_hash32`   |                         32 bytes |
| `dep_hash32`           | 32 bytes (zeros if DEP disabled) |
| `score_q32_s64`        |                           s64_le |

### 6.5 Planning hash chain

Plan header bytes:

| Field           |                        Type |
| --------------- | --------------------------: |
| `schema_id_u32` | u32 = `0x51585048` (“QXPH”) |
| `version_u32`   |                     u32 = 1 |
| `goal_hash32`   |                    32 bytes |
| `B_u32`         |                         u32 |
| `D_u32`         |                         u32 |
| `K_act_u32`     |                         u32 |
| `reserved_u32`  |                     u32 = 0 |

`PH_0 = SHA256(plan_header_bytes)`

For each expansion record `ExpandDigest_j` in the **exact generation order**:

`PH_{j+1} = SHA256(PH_j || ExpandDigest_j_bytes)`

The final tail `plan_tail_hash = PH_J`.

Plan bundle aggregation for `P_eval` episodes:

* sort episodes by `episode_id_u32` ascending
* `plan_bundle_hash = SHA256( concat(plan_tail_hash[0],...,plan_tail_hash[P-1]) )`

(If later you switch to Merkle, that’s an opset bump. v1 uses this concatenation scheme.)

---

## 7. DEP v1 (optional) — binary format and semantics

### 7.1 DEP program bytes: `dep_program_v1.bin`

Exactly as you wrote, with explicit padding:

Header (8 bytes):

* `dep_version_u8` = 1
* `L_u8` = instruction count (0..DEP_LMAX)
* `flags_u16` = 0
* `reserved_u32` = 0

Instruction (16 bytes each) repeated L times:

* `opcode_u8`
* `flags_u8` = 0
* `arg0_u16`
* `arg1_u16`
* `arg2_u16`
* `imm_q32_s64` (s64_le)

After instructions: pad with zero bytes to the next multiple of 64 bytes.

DEP hash: `dep_hash32 = SHA256(dep_program_bytes)`.

### 7.2 DEP execution

DEPExec MUST:

* enforce `DEP_EDIT_CAP` (increment edits on any state write)
* enforce null invariants
* enforce bounds on indexes
* use only DC-1 Q32 operations (add/mul/clamp; no float)
* reject on any violation (fail-closed)

---

## 8. MCL v2 artifacts: Concept Shards, Ladder, Strategy VM

This section defines the new additive artifacts.

---

### 8.1 Concept Shard v1 (`concept_shard_v1.bin`)

**Purpose:** reusable motif unit (pattern graph + optional codec + optional program).

#### 8.1.1 Binary layout

Header:

| Field                     |                        Type |
| ------------------------- | --------------------------: |
| `schema_id_u32`           | u32 = `0x43474231` (“CGB1”) |
| `version_u32`             |                     u32 = 1 |
| `flags_u32`               |                         u32 |
| `pattern_state_len_u32`   |                         u32 |
| `rewrite_state_len_u32`   |                         u32 |
| `codec_section_len_u32`   |                         u32 |
| `program_section_len_u32` |                         u32 |
| `reserved_u32`            |                     u32 = 0 |

Sections (in order):

1. `pattern_state_bytes` length = `pattern_state_len_u32`

   * MUST be a valid `qxwmr_state_packed_v1` **already canonical** (`CANON` applied).
2. `rewrite_state_bytes` length = `rewrite_state_len_u32`

   * either empty (0 length) or a canonical packed state representing a target/rewrite template.
3. `codec_section_bytes` length = `codec_section_len_u32`

   * v1 codec section is **canonical JSON bytes** embedded, with GCJ-1 rules, containing:

     ```json
     {
       "schema_id":"concept_codec_spec_v1",
       "codec_kind":"NONE"|"LOSSLESS_Q32_LINEAR"|"LOSSY_Q32_ENVELOPE_V1",
       "codec_opset_id":"opset:...sha256:...",
       "params_ref": {"artifact_id":"sha256:...","artifact_relpath":"..."}   // optional
     }
     ```
   * If `codec_kind=="NONE"`, section MAY be empty (0 bytes).
4. `program_section_bytes` length = `program_section_len_u32`

   * either empty or contains:

     * DEP program bytes (`dep_program_v1.bin`) **or**
     * SLS-VM bytecode fragment (see strategy VM), as indicated by `flags`.

Flags:

* bit0: `HAS_REWRITE`
* bit1: `HAS_CODEC`
* bit2: `HAS_DEP_PROGRAM`
* bit3: `HAS_SLS_FRAGMENT`
* other bits must be 0

Padding: none (sections are length-delimited). The shard bytes are hashed as-is.

#### 8.1.2 Deterministic binding and application

Shard application to a host state MUST occur only through SLS-VM opcodes that produce a **certificate**:

* `UNIFY(shard_id, region_selector)` returns:

  * `bindings` mapping pattern nodes to host nodes
  * `unify_cert` (fixed-width witness; see §8.3.4)
* `APPLY_SHARD(shard_id, bindings)` executes either:

  * codec expand/compress (if enabled)
  * rewrite template application (if provided)
  * optional DEP program on bound region (if flagged)

All of this is replayed by RE2.

---

### 8.2 Fractal Abstraction Ladder (FAL) additions

FAL is already embedded into QXWMR state via `node_level[]` and `ABSTRACTS` edges.

#### 8.2.1 Reserved IDs (manifest-fixed)

* `EDGE_TOK_ABSTRACTS = 1`
* `NODE_TOK_NULL = 0`
* `EDGE_TOK_NULL = 0`

These MUST be declared in `abstraction_ladder_manifest_v1` and MUST match runtime.

#### 8.2.2 Ladder operators

Operators exist as SLS-VM opcodes (not as “free” actions):

* `LIFT(level_k, selector)`:

  * deterministically selects a set of child nodes `S` from selector output
  * creates a new parent node at level `k+1` by writing into a deterministic “allocation slot” (see below)
  * adds ABSTRACTS edges from each child to parent
* `PROJECT(level_k, parent_node)`:

  * deterministically proposes child refinement set
  * may call `RETRIEVE_SHARD` and `APPLY_SHARD` to materialize additional children

#### 8.2.3 Deterministic node allocation rule (no ambiguity)

When creating a new node, the allocation slot MUST be:

* the **lowest index i** such that `node_tok[i]==NULL_NODE`
* if none exist ⇒ fail-closed `EUDRSU_NODE_CAP_EXCEEDED`

The parent’s `node_tok` MUST be chosen by:

* `ArgMaxDet(sim(parent_query, C_n[k]))` (or a deterministic mapping) with tie lowest k.

Parent `node_attr` MUST be computed by a manifest-pinned pooling function `POOL_Q32_V1`:

* For each attr dim d:

  * `sum = 0 (s128 internal)`
  * iterate children in ascending node index
  * `sum += child_attr[d]` with saturating add to s128 bounds
  * `parent_attr[d] = clamp_s64(sum / |S|)` where division is trunc toward zero on s128 and then clamped to s64
* If `|S|==0`, reject.

(If you want a different pooling, that’s an opset bump; this is the v1 pooling.)

---

### 8.3 Strategy VM (SLS-VM) v1

#### 8.3.1 Strategy cartridge binary: `strategy_cartridge_v1.bin`

Header:

| Field             |                                                           Type |
| ----------------- | -------------------------------------------------------------: |
| `schema_id_u32`   |                                    u32 = `0x534C5331` (“SLS1”) |
| `version_u32`     |                                                        u32 = 1 |
| `flags_u32`       |                                                            u32 |
| `opset_id_hash32` | 32 bytes (sha256 of `strategy_vm_manifest_v1` canonical bytes) |
| `entrypoint_u16`  |                                                  u16 opcode id |
| `L_u16`           |                           u16 instruction count (≤ STRAT_LMAX) |
| `reserved_u32`    |                                                        u32 = 0 |

Instruction format (16 bytes each), repeated L:

| Field         |          Type |
| ------------- | ------------: |
| `opcode_u16`  |           u16 |
| `flags_u16`   | u16 (0 in v1) |
| `arg0_u32`    |           u32 |
| `arg1_u32`    |           u32 |
| `imm_q32_s64` |        s64_le |

After instructions: pad with zeros to 64-byte boundary.

Flags:

* bit0: `USES_RETRIEVAL`
* bit1: `USES_UNIFY`
* bit2: `USES_LADDER`
* bit3: `USES_PLAN_CALL`
* bit4: `USES_URC_VM`
* other bits must be 0

#### 8.3.2 VM execution model (deterministic)

VM state:

* `PC_u32` program counter (instruction index)
* register file:

  * `R_u32[32]` initialized to 0
  * `R_q32[32]` initialized to 0
  * `R_hash32[16]` initialized to 0 (each 32 bytes)
* stack:

  * `STACK_u32[STRAT_STACK_MAX]`, SP starts at 0
* budget counters:

  * `cost_used_u64 = 0`
  * `ops_used_u64 = 0`

The VM runs until:

* executes `HALT`
* or `PC` reaches `L`
* or budgets exceeded ⇒ reject

Cost model:

* A manifest defines per-opcode `cost_u32`.
* Each executed instruction increments:

  * `cost_used_u64 += cost_u32`
  * `ops_used_u64 += 1`
* If `cost_used_u64 > STRAT_COST_CAP` or `ops_used_u64 > STRAT_OP_CAP`: reject.

#### 8.3.3 Minimal opcode set (SLS-0 baseline)

These MUST be implemented for v1 to be “end-to-end”:

| Opcode                | ID (u16) | Semantics (deterministic)                                                          |
| --------------------- | -------: | ---------------------------------------------------------------------------------- |
| `HALT`                |        0 | stop                                                                               |
| `RETRIEVE_SHARD_TOPK` |        1 | query ML-Index over shard bank, write selected shard IDs into `R_hash32` slots     |
| `UNIFY_SHARD_REGION`  |        2 | unify pattern shard with host region selector; write binding hash and witness hash |
| `APPLY_SHARD`         |        3 | apply shard to host state via binding witness                                      |
| `LIFT`                |        4 | create parent node at `level+1` with pooling; add ABSTRACTS edges                  |
| `PROJECT`             |        5 | propose children deterministically; may retrieve shards                            |
| `PLAN_CALL`           |        6 | call QXWMR planner; writes plan bundle hash and best action sequence hash          |
| `URC_STEP`            |        7 | execute URC-VM capsule step bounded; update memory root / state as specified       |
| `INVARIANT_CHECK`     |        8 | runs a manifest-defined invariant check; fail if false                             |
| `WRITE_LOG_DIGEST`    |        9 | appends a fixed-width digest record to the SLS trace chain                         |

(You can add more opcodes later; v1 requires these minimums.)

#### 8.3.4 Proof/certificate formats (v1)

v1 certificates are technical witnesses, not formal proofs.

**Unify witness (`unify_witness_v1`)** is a fixed-width binary record emitted by `UNIFY_SHARD_REGION`:

| Field                          |                                         Type |
| ------------------------------ | -------------------------------------------: |
| `schema_id_u32`                |                  u32 = `0x554E4951` (“UNIQ”) |
| `version_u32`                  |                                      u32 = 1 |
| `shard_id_hash32`              |                                     32 bytes |
| `host_region_hash32`           |                                     32 bytes |
| `binding_count_u32`            |                                          u32 |
| `binding_pairs[binding_count]` | repeated `(pattern_node_u32, host_node_u32)` |
| `reserved_u32`                 |                                      u32 = 0 |

Canonical ordering:

* binding pairs MUST be sorted by `pattern_node_u32` ascending
* `binding_count_u32` MUST equal pattern node count in shard’s pattern state (excluding NULL_NODE entries)
* any mismatch ⇒ reject

The witness is hashed `SHA256(witness_bytes)` and used as the binding handle.

---

## 9. URC-VM capsule family (RAM-complete core)

This spec defines a minimal deterministic VM sufficient for Word-RAM simulation.

### 9.1 URC capsule binary: `urc_capsule_v1.bin`

Header:

| Field           |                              Type |
| --------------- | --------------------------------: |
| `schema_id_u32` |       u32 = `0x55524331` (“URC1”) |
| `version_u32`   |                           u32 = 1 |
| `flags_u32`     |                               u32 |
| `isa_id_hash32` | 32 bytes (sha256 of ISA manifest) |
| `code_len_u32`  |                               u32 |
| `data_len_u32`  |                               u32 |
| `reserved_u32`  |                           u32 = 0 |

Sections:

1. `code_bytes[code_len]` (instruction stream, fixed-width format below)
2. `data_bytes[data_len]` (read-only initial data segment; optional)

Padding: none.

### 9.2 URC-VM machine state representation (canonical, content-addressable)

URC machine state is represented as:

* registers: `REG_Q32[R]` stored as Q32 s64
* `PC_u32`
* flags bitfield `FLAG_u32`
* page table root hash `PT_root_hash32`
* memory root hash `MRoot_hash32`

The VM does not mutate pages in-place. Writes append new pages/segments and produce a new MRoot.

### 9.3 Memory pages and page table

#### 9.3.1 Page binary: `urc_page_v1.bin`

Fixed size:

Header:

* `schema_id_u32` = `0x55504731` (“UPG1”)
* `version_u32` = 1
* `page_index_u32`
* `word_count_u32` = `PAGE_WORDS` (manifest fixed)
* `reserved_u32` = 0

Body:

* `words_q32[PAGE_WORDS]` as `s64_le`

#### 9.3.2 Page table node: `urc_page_table_node_v1.bin`

Merkle fanout `F_PT` (manifest fixed; v1 default 256). Node layout:

Header:

* `schema_id_u32` = `0x55505431` (“UPT1”)
* `version_u32` = 1
* `level_u32` (0 for leaf mapping)
* `fanout_u32` = F_PT
* `reserved_u32` = 0

Body:

* `child_hash32[F_PT]` (32 bytes each); zero hash indicates empty.
* leaf nodes map to `urc_page_v1` hashes; internal nodes map to other table nodes.

A standard Merkle proof format is defined in §10.2.

### 9.4 URC ISA (v1 minimum)

Instruction encoding (8 bytes each):

| Field       | Type |
| ----------- | ---: |
| `opcode_u8` |   u8 |
| `r0_u8`     |   u8 |
| `r1_u8`     |   u8 |
| `imm_u32`   |  u32 |
| `flags_u8`  |   u8 |

Opcodes (minimum set, deterministic):

* `LD r0, [addr_reg=r1 + imm]`
* `ST [addr_reg=r1 + imm], r0`
* `ADD r0, r1`
* `SUB r0, r1`
* `AND/OR/XOR r0, r1`
* `SHL/SHR r0, imm` (logical shift on 64-bit word carrier)
* `CMP r0, r1` sets flags
* `JMP imm`, `JZ imm`, `JNZ imm` (absolute PC target, bounded)
* `HALT`

All arithmetic on the 64-bit carrier is exact two’s complement with **explicit overflow policy**:

* For bitwise ops and shifts: wrap-around per 64-bit arithmetic.
* For ADD/SUB on Q32 values (interpreting as s64): wrap-around is allowed only if explicitly declared by ISA; **v1 requires saturating add/sub** for Q32 semantics used in learning.
  Therefore:

  * URC ADD/SUB are *word* operations and may wrap.
  * Q32 ops used for learning and scoring must use `eudrs_u_q32ops_v1` saturating semantics.

The distinction is part of determinism cert; mixing them incorrectly is a verifier failure.

### 9.5 URC execution caps

* `URC_STEP_CAP`: maximum executed instructions per VM call
* `URC_CALL_DEPTH_CAP`: maximum call depth
* `URC_MEM_WRITE_CAP`: maximum writes per call

Exceeding caps ⇒ reject.

---

## 10. Merkle structures (weights, memory, indices, CAC/UFC roots)

### 10.1 Merkle root algorithm `MERKLE_FANOUT_V1`

Used for:

* weights blocks
* index bucket page hashes
* memory segment hashes
* CAC episode record hashes (optional)
* UFC record hashes (optional)

Parameters:

* fanout `F` fixed per structure (manifest specified)

Algorithm:

* Leaves are a list of 32-byte hashes `H[0..n-1]` in canonical order.
* Build next level by grouping into chunks of size F:

  * for chunk c containing `k` hashes:

    * create node bytes:

      * header: `schema_id_u32="MRK1"`, `version_u32=1`, `fanout_u32=F`, `count_u32=k`
      * body: `child_hash32[0..F-1]` where:

        * first k are the chunk hashes
        * remaining are all-zero 32-byte hashes
    * parent hash = `SHA256(node_bytes)`
* Repeat until one hash remains = root. If `n==0`, root is all-zero hash.

All node bytes are little-endian in header. This is deterministic.

### 10.2 Merkle proof format `merkle_proof_v1.bin` (for URC VERIFY and optional receipts)

Header:

* `schema_id_u32="MRKP"`
* `version_u32=1`
* `fanout_u32`
* `depth_u32` (#levels)
* `leaf_index_u32`
* `reserved_u32=0`

Body:

* for level `l=0..depth-1`:

  * `sibling_hash32[fanout]` (full array)
  * `position_u32` (0..fanout-1) leaf position in the chunk at that level

The verifier recomputes root deterministically.

---

## 11. ML-Index v1 (deterministic sublinear retrieval)

### 11.1 Index manifest: `ml_index_manifest_v1.json`

Canonical JSON fields:

```json
{
  "schema_id": "ml_index_manifest_v1",
  "index_kind": "ML_INDEX_V1",
  "opset_id": "opset:eudrs_u_v1:sha256:<...>",

  "key_dim_u32": <int>,
  "codebook_size_u32": <int>,         // K buckets
  "bucket_visit_k_u32": <int>,        // K_c
  "scan_cap_per_bucket_u32": <int>,
  "merkle_fanout_u32": <int>,

  "sim_kind": "DOT_Q32_SATURATING",

  "codebook_ref": { "artifact_id": "...", "artifact_relpath": "..." },
  "index_root_ref": { "artifact_id": "...", "artifact_relpath": "..." },

  "mem_gates": {
    "mem_g1_bucket_balance_max_q32": {"q": <int>},
    "mem_g2_anchor_recall_min_q32": {"q": <int>}
  }
}
```

### 11.2 Codebook binary: `ml_index_codebook_v1.bin`

Header:

* `schema_id_u32="CBK1"`
* `version_u32=1`
* `K_u32`
* `d_u32`
* `reserved_u32=0`

Body:

* `C[K][d]` Q32 as `s64_le`

### 11.3 Index root binary: `ml_index_root_v1.bin`

Header:

* `schema_id_u32="IDX1"`
* `version_u32=1`
* `K_u32`
* `fanout_u32`
* `reserved_u32=0`

Body:

* `bucket_root_hash32[K]` array, where each is the Merkle root hash over that bucket’s pages (or zero if empty).

### 11.4 Index page binary: `ml_index_page_v1.bin`

Header:

* `schema_id_u32="IDXP"`
* `version_u32=1`
* `bucket_id_u32`
* `page_index_u32`
* `record_count_u32`
* `key_dim_u32`
* `reserved_u32=0`

Record layout, repeated `record_count` times:

| Field              |                                                 Type |
| ------------------ | ---------------------------------------------------: |
| `record_hash32`    | 32 bytes (the “ID” used for tie breaks and identity) |
| `payload_hash32`   |          32 bytes (target artifact id or segment id) |
| `key_q32[key_dim]` |                                      s64_le[key_dim] |

Canonical ordering rule:

* records MUST be sorted by `record_hash32` ascending.
* No duplicates allowed. Duplicate ⇒ reject.

### 11.5 Similarity function `DOT_Q32_SATURATING`

Given query key `q[d]` and record key `x[d]`:

* internal accumulator is signed 128-bit
* for dim in `0..d-1`:

  * `acc += (q[i] * x[i]) >> 32` using 128-bit product, trunc toward negative infinity? **v1 uses trunc toward zero**, implemented as:

    * compute signed 128-bit product
    * arithmetic shift right by 32 (this is trunc toward negative infinity if negative). To avoid ambiguity, v1 defines:

      * `q32_mul(a,b) = (a*b) >> 32` using arithmetic shift
* After accumulate: clamp to signed 64-bit range and treat as Q32 score.

This matches RE2’s existing style (`q32_mul` uses `>> 32`). The exact negative rounding behavior is fixed by arithmetic shift.

### 11.6 Retrieval algorithm (normative)

`RetrieveTopK(q, index_manifest, K_out)`:

1. Load codebook and index root.
2. Bucket scoring:

   * for each bucket `k in 0..K-1`:

     * score_k = sim(q, C[k])
   * select `K_c` buckets by `TopKDet((score_k, k), K_c)`, tie by smaller k.
3. Scan postings:

   * For each selected bucket in ascending bucket id:

     * traverse that bucket’s pages in ascending `page_index` order
     * scan records in page order (ascending record_hash)
     * stop when `scan_cap_per_bucket` records scanned
     * compute exact score = sim(q, record.key)
     * insert into TopK heap using tie `(score desc, record_hash asc)`
4. Output:

   * return TopK list of `(record_hash32, payload_hash32)` in canonical sorted order (same ordering as heap output).

**Candidate set correctness:** the retrieved set is exact TopK over the **deterministically defined scanned candidate set**, not global TopK over all items. This is the RET-K contract.

### 11.7 MEM gates (verification)

* **MEM-G1 bucket balance**: on a deterministic probe distribution, bucket sizes must satisfy:

  * max_bucket_size ≤ `bucket_balance_max_q32`-encoded threshold (implemented as integer ratio metric)
* **MEM-G2 anchor recall**: on a fixed labeled query suite, recall@K must be ≥ threshold.

Both are recomputed by RE2 during promotion verification if the index changes.

---

## 12. Ontology (ORoot), strategy (KRoot), capsules (CRoot)

### 12.1 ORoot: ontology handle map

**Type:** `ontology_handle_map_v1` (canonical JSON)

```json
{
  "schema_id": "ontology_handle_map_v1",
  "epoch_u64": <int>,
  "handles": [
    { "handle": "string_restricted", "concept_id": "sha256:<...>" }
  ]
}
```

Constraints:

* `handles[]` sorted by `handle` lexicographically ascending (bytewise UTF-8)
* handle charset restriction v1: `[a-z0-9._/-]{1,128}` (enforced in RE2)
* `concept_id` must exist as a `concept_def_v1` artifact and hash-match
* Duplicate handles forbidden

ORoot is an `ArtifactRefV1` to this map.

### 12.2 Concept definition: `concept_def_v1.json`

Canonical JSON:

```json
{
  "schema_id": "concept_def_v1",
  "concept_id": "sha256:<...>",

  "handle": "string_restricted",

  "ladder_level_min_u16": <int>,
  "ladder_level_max_u16": <int>,

  "deps": ["sha256:<...>", "..."],

  "write_set": {
    "kind": "DISJOINT_CLASS_V1",
    "class_id_u32": <int>
  },

  "fingerprint_spec_ref": { "artifact_id": "...", "artifact_relpath": "..." },
  "mdlt_certificate_ref": { "artifact_id": "...", "artifact_relpath": "..." },

  "interaction_budget": {
    "max_coactivation_u32": <int>,
    "max_dep_closure_u32": <int>
  }
}
```

Rules:

* `concept_id` MUST equal hash of canonical bytes of this object with `concept_id` field temporarily set to `"sha256:00..00"` during hashing (standard “self-hash” pattern). This avoids circularity.
* deps must be acyclic; verified by RE2 by building DAG (deps list order is canonical and MUST be preserved)

### 12.3 KRoot: strategy registry

Strategy has two artifacts:

1. `strategy_def_v1.json` (canonical JSON metadata + dependencies + fingerprints)
2. `strategy_cartridge_v1.bin` (bytecode)

`strategy_def_v1.json`:

```json
{
  "schema_id": "strategy_def_v1",
  "strategy_id": "sha256:<...>",
  "handle": "string_restricted",
  "cartridge_ref": { "artifact_id": "...", "artifact_relpath": "..." },
  "deps_concepts": ["sha256:<...>"],
  "deps_strategies": ["sha256:<...>"],
  "fingerprint_spec_ref": { "artifact_id": "...", "artifact_relpath": "..." },
  "cost_budget_u64": <int>
}
```

KRoot is a Merkle root (or canonical map) over all strategy defs. v1 uses canonical JSON list:

`strategy_registry_v1.json`:

```json
{
  "schema_id":"strategy_registry_v1",
  "strategies":[ { "strategy_id":"sha256:...", "strategy_def_ref": {...} } ]
}
```

Sorted by `strategy_id` ascending.

### 12.4 CRoot: capsule registry

Similarly define:

* `urc_capsule_def_v1.json`
* `urc_capsule_v1.bin`

CRoot is a canonical list registry sorted by capsule_id.

---

## 13. Weights (WRoot): Merkle-sharded Q32 tensors

### 13.1 Q32 tensor block: `q32_tensor_block_v1.bin`

Header:

* `schema_id_u32="WBLK"`
* `version_u32=1`
* `tensor_name_hash32` (sha256 of UTF-8 tensor name)
* `block_index_u32`
* `elem_count_u32`
* `reserved_u32=0`

Body:

* `elems_q32[elem_count]` as `s64_le`

No padding.

### 13.2 Weights manifest: `weights_manifest_v1.json`

```json
{
  "schema_id": "weights_manifest_v1",
  "opset_id": "opset:eudrs_u_v1:sha256:<...>",
  "block_elem_count_u32": <int>,
  "tensors": [
    {
      "name": "string",
      "shape_u32": [<int>, ...],
      "blocks": [
        { "block_index_u32": <int>, "block_ref": { "artifact_id": "...", "artifact_relpath": "..." } }
      ]
    }
  ],
  "weights_merkle_root_sha256": "sha256:<...>"
}
```

Rules:

* blocks for each tensor must be contiguous `block_index_u32=0..B-1`
* tensor list sorted by `name` ascending
* `weights_merkle_root_sha256` is computed by:

  * build leaf list = block hashes ordered by:

    1. tensor name ascending
    2. block_index ascending
  * apply `MERKLE_FANOUT_V1` with `fanout = weights_merkle_fanout_u32` from training manifest

---

## 14. Training, evaluation, and trace chains (EUDRS-U)

EUDRS-U defines four parallel hash chains:

* `H_train`, `H_eval`, `H_onto`, `H_mem`

### 14.1 Training step digest: `eudrs_u_train_step_digest_v1` (binary record)

Header constants:

* `schema_id_u32="TRD1"`
* `version_u32=1`

Record layout:

| Field                    |                                            Type |
| ------------------------ | ----------------------------------------------: |
| `schema_id_u32`          |                                             u32 |
| `version_u32`            |                                             u32 |
| `step_u64`               |                                             u64 |
| `batch_hash32`           |                                        32 bytes |
| `prng_counter_u64`       |                                             u64 |
| `wroot_before32`         |                                        32 bytes |
| `wroot_after32`          |                                        32 bytes |
| `optroot_after32`        |                                        32 bytes |
| `wm_batch_hash32`        | 32 bytes (dep_hash + pred_state_hash aggregate) |
| `retrieval_trace_root32` |                                        32 bytes |
| `concept_fire_root32`    |                                        32 bytes |
| `plan_bundle_hash32`     |                                        32 bytes |
| `capsule_trace_tail32`   |                                        32 bytes |
| `budget_counters[8]`     |                           u64[8] reserved slots |
| `reserved_u64`           |                                         u64 = 0 |

Training chain update:

* `H_train_{t+1} = SHA256(H_train_t || step_digest_bytes)`

### 14.2 Eval step digest: `eudrs_u_eval_step_digest_v1` (binary)

Similar, includes:

* eval episode id
* episode return q32
* plan_tail_hash
* strategy trace tail
* ladder logs root
* etc.

### 14.3 Ontology and memory digests

* Ontology digest includes:

  * ontology_delta_root
  * cooldown ledger root
  * alias mass metrics root
* Memory digest includes:

  * new segment hashes root
  * compaction receipt root
  * index root after rebuild
  * mem gate metrics root

All are binary, fixed-width, hashed in their own chains.

---

## 15. CAC v1 and UFC v1 (promotion-gating artifacts)

### 15.1 CAC artifact: `cac_v1.json`

CAC is stored as canonical JSON with episode record hashes, to keep it inspectable, while episode records are stored as binary for scaling.

`cac_v1.json`:

```json
{
  "schema_id": "cac_v1",
  "delta_id": "sha256:<...>",

  "eval_suite_id": "sha256:<...>",
  "episode_list_hash": "sha256:<...>",

  "episode_records": [
    {
      "episode_id_u32": <int>,
      "record_hash": "sha256:<...>"
    }
  ],

  "delta_u_q32": {"q": <int>},
  "delta_u_rob_q32": {"q": <int>},

  "cac_root_sha256": "sha256:<...>"
}
```

Rules:

* `episode_records[]` sorted by `episode_id_u32` ascending.
* `record_hash` hashes the corresponding binary record described next.
* `cac_root_sha256 = SHA256(concat(record_hash_bytes in episode order))` (v1 concatenation rule).

#### 15.1.1 CAC episode record binary: `cac_episode_record_v1.bin`

Header:

* `schema_id_u32="CACE"`
* `version_u32=1`
* `episode_id_u32`
* `reserved_u32=0`

Body:

* `H_tail_base32`
* `H_tail_cf32`
* `R_base_q32_s64`
* `R_cf_q32_s64`
* `A_q32_s64` (cf - base)
* `ladder_decomp_root32` (optional; zeros allowed)

### 15.2 UFC artifact: `ufc_v1.json`

Canonical JSON:

```json
{
  "schema_id": "ufc_v1",
  "eval_suite_id": "sha256:<...>",
  "episode_list_hash": "sha256:<...>",
  "ufc_records_root_sha256": "sha256:<...>",

  "u_total_q32": {"q": <int>},

  "u_by_level": [
    {"level_u16": <int>, "u_q32": {"q": <int>}}
  ],

  "u_by_concept_root_sha256": "sha256:<...>",
  "u_by_strategy_root_sha256": "sha256:<...>"
}
```

UFC is derived deterministically from logs and Ladder-Adjoint credit routing.

### 15.3 Ladder-Adjoint invariant LA-SUM (fail-closed)

When computing UFC (and any ladder credit routing), RE2 MUST enforce:

For every ladder parent p touched in episode logs:

`sum_{children s of p} delta(s) == delta(p)` **exactly as Q32**.

Definition of delta:

* v1 uses `delta_q32` as signed s64.
* pooling and distribution functions are OpSet-defined and MUST use pinned reduction order:

  * iterate children in ascending node index
  * all adds are saturating s64 unless explicitly specified otherwise

Any mismatch ⇒ reject with reason `EUDRSU_LA_SUM_VIOLATION`.

---

## 16. Ontology stability gates STAB-G0..G5

These gates are verified by RE2 in `stability_gates_v1.py` and are required for any promotion that changes ORoot or concept defs.

### 16.1 Inputs (all content-addressed)

* `ORoot_old` from previously active root tuple
* `ORoot_new` from candidate root tuple
* deterministic evaluation suite `E` and probe set `P` (manifest referenced)
* cooldown ledger old/new
* fingerprint specs per concept

### 16.2 Gate definitions (exact)

* **STAB-G0**: `J_new >= J_old + Δ_min` (Q32)
* **STAB-G1**: split/merge hysteresis: require thresholds `Δ_split`, `Δ_merge`
* **STAB-G2**: cooldown ledger:

  * ledger records a lineage id and lockout counter (promotions remaining)
  * inverse operations forbidden while lockout > 0
* **STAB-G3**: fingerprint drift bound for handle-preserving remaps:

  * fingerprints are packed outputs on anchor probes
  * distance metric v1: Hamming distance over packed sign bits of selected Q32 outputs (manifest-defined)
  * require `Dist ≤ ε_handle`
* **STAB-G4**: interaction sparsity/non-interference:

  * deps acyclic, outdegree ≤ D_max
  * dep closure ≤ K_C
  * write-set conflicts must be resolvable by precedence (concept_id ascending). If two concepts write same class_id and both fire in same episode without precedence rule enabled ⇒ reject.
* **STAB-G5**: alias mass:

  * alias group defined by fingerprint distance ≤ ε_alias
  * alias mass is deterministic activation probability mass (derived from strategy logs and retrieval scores; v1 uses count-weighted mass)
  * require alias mass ≤ threshold.

### 16.3 Cooldown ledger artifact: `cooldown_ledger_v1.json`

Canonical JSON:

```json
{
  "schema_id": "cooldown_ledger_v1",
  "epoch_u64": <int>,
  "locks": [
    {
      "lineage_id": "sha256:<...>",
      "lock_kind": "SPLIT_MERGE",
      "remaining_u64": <int>
    }
  ]
}
```

Sorted by `lineage_id` ascending.

---

## 17. Promotion bundle integration into Omega (v18 and v19)

### 17.1 Campaign outputs (subrun layout)

Every EUDRS-U campaign subrun MUST write:

1. Evidence manifest(s) under subrun root, e.g.:

```
eudrs_u/
  evidence/
    sha256_<...>.eudrs_u_promotion_summary_v1.json
    sha256_<...>.determinism_cert_v1.json
    sha256_<...>.universality_cert_v1.json
    sha256_<...>.cac_v1.json
    sha256_<...>.ufc_v1.json
    sha256_<...>.stability_metrics_v1.json
    sha256_<...>.cooldown_ledger_v1.json
```

2. Data artifacts intended for activation staged under:

```
eudrs_u/staged_registry_tree/
  polymath/registry/eudrs_u/...   (exact tree to be copied into repo on promotion)
```

3. A standard omega promotion bundle (existing schema) that:

* touches only the staged registry tree paths
* updates `polymath/registry/eudrs_u/active/active_root_tuple_ref_v1.json`
* includes all newly introduced immutable artifacts under `polymath/registry/eudrs_u/`

### 17.2 Subverification

Add a new subverifier entry point:

* `CDEL-v2/cdel/v18_0/eudrs_u/verify_eudrs_u_run_v1.py`

It MUST:

* locate `eudrs_u_promotion_summary_v1.json` in the subrun (relative paths from CWD; v19 runs set CWD to subrun root)
* recompute all hashes and roots:

  * weights root
  * index roots
  * ontology roots
  * trace tails
  * CAC/UFC
  * gates STAB and MEM
  * LA-SUM invariants during UFC derivation
* emit `eudrs_u_subverifier_receipt_v1.json` with:

  * `status`: `VALID` or `INVALID`
  * `reason_code`
  * all claimed roots and tails

Omega promoter then accepts promotion only if subverifier receipt is VALID (existing behavior).

### 17.3 v19 axis bundle requirements

Any promotion that touches:

* `CDEL-v2/cdel/`
* `Genesis/schema/`
* `meta-core/`
* `orchestrator/`

MUST include `axis_upgrade_bundle_v1.json` sidecar (as your v19 promoter supports).

**Initial integration promotion** (adding new modules/schemas/campaigns) MUST include an axis bundle.

Subsequent **data-only promotions** under `polymath/registry/eudrs_u/` do not touch governed prefixes and therefore do not require axis bundles.

---

## 18. Fail-closed error taxonomy (reason codes)

All verifiers MUST return a single primary reason code from this table (string constants). Additional detail may be embedded in a bounded-size `details` object.

### 18.1 Canonicalization and packing

* `EUDRSU_STATE_DECODE_FAIL`
* `EUDRSU_NULL_INVARIANT_VIOLATION`
* `EUDRSU_LADDER_DAG_VIOLATION`
* `EUDRSU_LADDER_LEVEL_VIOLATION`
* `EUDRSU_CANON_TIE_CAP_EXCEEDED`
* `EUDRSU_CANON_BYTES_MISMATCH`

### 18.2 Hash/root mismatches

* `EUDRSU_ARTIFACT_HASH_MISMATCH`
* `EUDRSU_MERKLE_ROOT_MISMATCH`
* `EUDRSU_TRACE_TAIL_MISMATCH`

### 18.3 Retrieval/index gates

* `EUDRSU_MEM_G1_BUCKET_IMBALANCE`
* `EUDRSU_MEM_G2_RECALL_BELOW_FLOOR`
* `EUDRSU_INDEX_PAGE_ORDER_VIOLATION`

### 18.4 Ontology stability gates

* `EUDRSU_STAB_G0_FAIL`
* `EUDRSU_STAB_G1_FAIL`
* `EUDRSU_STAB_G2_COOLDOWN_VIOLATION`
* `EUDRSU_STAB_G3_FINGERPRINT_DRIFT`
* `EUDRSU_STAB_G4_INTERFERENCE`
* `EUDRSU_STAB_G5_ALIAS_MASS`

### 18.5 CAC/UFC and ladder credit

* `EUDRSU_CAC_THRESHOLD_FAIL`
* `EUDRSU_CAC_ROBUSTNESS_FAIL`
* `EUDRSU_UFC_DERIVATION_FAIL`
* `EUDRSU_LA_SUM_VIOLATION`

### 18.6 VM/capsule budgets

* `EUDRSU_STRATEGY_BUDGET_EXCEEDED`
* `EUDRSU_URC_BUDGET_EXCEEDED`
* `EUDRSU_DEP_EDIT_CAP_EXCEEDED`
* `EUDRSU_NODE_CAP_EXCEEDED`
* `EUDRSU_EDGE_CAP_EXCEEDED`

---

## 19. Determinism certificate and universality certificate

### 19.1 `determinism_cert_v1.json`

Canonical JSON:

```json
{
  "schema_id":"determinism_cert_v1",
  "dc1_id":"dc1:q32_v1",
  "opset_id":"opset:eudrs_u_v1:sha256:<...>",

  "q32_semantics":{
    "mul":"ARITH_SHIFT_RIGHT_32",
    "add":"SATURATING_S64",
    "dot":"SAT_ACCUM_S128_THEN_CLAMP_S64"
  },

  "choice_rules":{
    "argmax":"max_score_then_lowest_id",
    "topk":"score_desc_then_id_asc"
  },

  "prng":{
    "algo":"XORSHIFT128PLUS_V1",
    "seed_derivation":"SHA256(dc1_id||opset_id||dataset_root||wroot||step||stream_id)[0:16]",
    "consumption_order":"as_per_train_step_digest"
  },

  "canonicalization":{
    "json":"GCJ-1",
    "state":"QXWMR_CANON_WL_V1 + FAL_VALIDATION"
  },

  "caps":{
    "N":<int>,"E":<int>,"WL_R":<int>,"CANON_TIE_CAP":<int>,
    "beam_B":<int>,"beam_D":<int>,"K_act":<int>,
    "STRAT_LMAX":<int>,"STRAT_COST_CAP":<int>,
    "URC_STEP_CAP":<int>,
    "INDEX_SCAN_CAP_PER_BUCKET":<int>
  }
}
```

### 19.2 `universality_cert_v1.json`

This is a technical proof-by-conformance artifact:

```json
{
  "schema_id":"universality_cert_v1",
  "urc_isa_id":"sha256:<...>",
  "ram_encoding_spec_id":"sha256:<...>",
  "golden_traces":[
    {"trace_id":"sha256:<...>","description":"add/sub/load/store loop"},
    {"trace_id":"sha256:<...>","description":"page table traversal"},
    {"trace_id":"sha256:<...>","description":"merkle proof verify"}
  ],
  "conformance_suite_hash":"sha256:<...>"
}
```

RE2 verification MUST recompute these golden trace outputs for the active URC-VM implementation and reject if any mismatch.

---

## 20. Engineering implementation order (hard dependencies)

This is the minimal order that yields an end-to-end promotable system without partial-trust gaps.

### Phase A — Deterministic core + schemas (promotable)

1. Add schemas in `Genesis/schema/v18_0/` (requires axis bundle in v19).
2. Implement RE2 common utilities:

   * safe relpath checks
   * merkle root v1
   * q32 ops v1 (saturating + mul semantics)
3. Implement QXWMR state pack/unpack + CANON + golden tests (WMR-0).

### Phase B — Indices + shards + ladder (promotable)

4. Implement ML-Index v1 (codebook + pages + retrieval) + MEM-G1/MEM-G2 tests.
5. Implement concept_shard_v1 binary parsing + UNIFY witness format.
6. Implement FAL validation + LIFT/PROJECT semantics.

### Phase C — Strategy VM + URC-VM (promotable)

7. Implement SLS-VM v1 + trace chaining.
8. Implement URC-VM v1 + merkle page table + golden traces, produce universality cert.

### Phase D — CAC/UFC + stability gates (promotable)

9. Implement CAC paired eval recomputation.
10. Implement UFC derivation + LA-SUM enforcement.
11. Implement STAB-G0..G5 + cooldown ledger.

### Phase E — Omega wiring (promotable)

12. Add orchestrator campaign(s) producing staged registry tree and promotion bundle.
13. Add RE2 subverifier `verify_eudrs_u_run_v1` and integrate with capability registry.
14. Validate end-to-end: dispatch → subrun → subverifier → promotion → RE1 activation.

---

## 21. Required golden tests (must exist before enabling capability)

These tests MUST be checked by RE2 verification or by CI that is required for promotion.

1. **QXWMR CANON golden bytes:** same input state → identical canonical bytes on all platforms.
2. **Tie-cap rejection:** construct a tie class of size `CANON_TIE_CAP+1` and ensure reject.
3. **ML-Index determinism:** same index root + query → identical TopK results and identical retrieval trace root.
4. **SLS-VM determinism:** same cartridge + state → identical trace tail hash.
5. **URC-VM golden traces:** ISA conformance and merkle proof verify.
6. **CAC paired eval determinism:** baseline/counterfactual produce identical episode record hashes when re-run.
7. **LA-SUM exactness:** construct ladder parent with children and verify exact conservation.

---

## 22. Concrete “where” integration points in existing Omega

This section pins the exact hook locations to the repo reality you described.

### 22.1 Dispatch and subruns

Campaigns run through:

* `CDEL-v2/cdel/v18_0/omega_executor_v1.py:dispatch_campaign()`
* workspace under `.omega_v18_exec_workspace/...`
* materialized subrun under `state_root/subruns/<action_id>_<campaign_id>/`

Your EUDRS-U campaigns MUST write all evidence under the subrun root so that:

* v18 verifier can find them by fixed relative paths
* v19 coordinator CWD semantics resolve relative paths correctly

### 22.2 Subverifier execution and receipts

You already have a “subverifier receipt” concept that promotion consumes.

EUDRS-U must add a new receipt type:

* `sha256_<...>.eudrs_u_subverifier_receipt_v1.json`

and the receipt MUST include:

* `status`
* `reason_code`
* all root hashes/tails needed to bind promotion

The promotion step already rejects if `status != VALID`.

### 22.3 Promotion bundle

EUDRS-U campaigns MUST emit a standard omega promotion bundle that:

* touches only `polymath/registry/eudrs_u/**`
* does not touch `.omega_cache`, `runs/`, absolute paths, `CDEL-v2/`, `Genesis/`, `meta-core/`, `authority/`

This ensures:

* pass allowlists
* avoid axis bundle requirement for recurring data promotions

### 22.4 v19 governed-prefix and axis bundle

Initial code/schema additions touch governed prefixes and therefore MUST include axis bundle. After bootstrapping, keep recurring updates constrained to data registry.

---

## 23. Minimum set of new capability IDs (recommended naming)

Add new caps (disabled by default unless profile enables):

* `RSI_EUDRSU_TRAIN_V1`
* `RSI_EUDRSU_EVAL_CAC_V1`
* `RSI_EUDRSU_INDEX_REBUILD_V1`
* `RSI_EUDRSU_ONTOLOGY_UPDATE_V1`

Each cap maps to:

* campaign module under `orchestrator/`
* subverifier module under `CDEL-v2/cdel/v18_0/eudrs_u/verify_eudrs_u_run_v1.py`
* state dir under `daemon/rsi_eudrsu_*`

Field names in the registry MUST match your existing `omega_capability_registry_v2.json` schema; implement by cloning an existing cap entry (e.g., `RSI_SAS_CODE`) and replacing:

* id/name
* python module
* state dir
* verifier module

---

## 24. Non-ambiguous seeding and replay binding (mandatory)

### 24.1 Seed derivation for all internal PRNG streams

For each PRNG stream `stream_id_u32`, at training step `t_u64`:

* `seed_bytes = SHA256( dc1_id_bytes || opset_id_bytes || dataset_root_hash32 || wroot_before32 || u64_le(t) || u32_le(stream_id) )`
* PRNG state uses first 16 bytes as little-endian `u128` seed.

PRNG algorithm: XORSHIFT128+ v1 exact spec:

* state `(s0, s1)` 64-bit each derived from seed:

  * `s0 = u64_le(seed[0:8])`, `s1 = u64_le(seed[8:16])`
  * if both zero, set `s1=1`
* next:

  * `x = s0`, `y = s1`
  * `s0 = y`
  * `x ^= x << 23`
  * `x ^= x >> 17`
  * `x ^= y ^ (y >> 26)`
  * `s1 = x`
  * output = `s0 + s1` mod 2^64

All shifts are logical on u64. This is deterministic.

### 24.2 Replay binding

Every step digest MUST include:

* `prng_counter_u64` (total outputs consumed so far in that stream)
* the chain tail binds it

Mismatch in counters ⇒ mismatch in chain tail ⇒ reject.

---

## 25. Final acceptance predicate (single place; fail-closed)

A promotion that updates `polymath/registry/eudrs_u/active/active_root_tuple_ref_v1.json` MUST be accepted by RE2 iff:

1. All referenced artifacts exist and hash-match (`ArtifactRefV1` validated).
2. All trace tails (`H_train`, `H_eval`, `H_onto`, `H_mem`) recompute exactly.
3. CAC thresholds are met:

   * `delta_u_q32 ≥ τ_U`
   * and if robustness enabled: `delta_u_rob_q32 ≥ τ_rob`
4. STAB-G0..G5 all pass for ontology changes.
5. MEM-G1/MEM-G2 pass for index changes.
6. LA-SUM holds wherever ladder adjoint routing is invoked.
7. All caps/budgets are respected; no overflow beyond specified saturation behaviors.
8. Determinism cert and universality cert recompute and match.

Any failure ⇒ reject/halt (fail-closed), and promotion MUST NOT apply.

---

## Appendix A — `eudrs_u_promotion_summary_v1.json` (required producer output)

Campaigns MUST emit exactly one summary file under `eudrs_u/evidence/` that points to all other evidence.

```json
{
  "schema_id":"eudrs_u_promotion_summary_v1",

  "proposed_root_tuple_ref": { "artifact_id":"sha256:<...>", "artifact_relpath":"eudrs_u/staged_registry_tree/polymath/registry/eudrs_u/roots/sha256_<...>.eudrs_u_root_tuple_v1.json" },

  "staged_registry_tree_relpath":"eudrs_u/staged_registry_tree",

  "evidence": {
    "weights_manifest_ref": { "artifact_id":"sha256:<...>", "artifact_relpath":"eudrs_u/evidence/sha256_<...>.weights_manifest_v1.json" },
    "ml_index_manifest_ref": { "artifact_id":"sha256:<...>", "artifact_relpath":"eudrs_u/evidence/sha256_<...>.ml_index_manifest_v1.json" },

    "cac_ref": { "artifact_id":"sha256:<...>", "artifact_relpath":"eudrs_u/evidence/sha256_<...>.cac_v1.json" },
    "ufc_ref": { "artifact_id":"sha256:<...>", "artifact_relpath":"eudrs_u/evidence/sha256_<...>.ufc_v1.json" },

    "cooldown_ledger_ref": { "artifact_id":"sha256:<...>", "artifact_relpath":"eudrs_u/evidence/sha256_<...>.cooldown_ledger_v1.json" },
    "stability_metrics_ref": { "artifact_id":"sha256:<...>", "artifact_relpath":"eudrs_u/evidence/sha256_<...>.stability_metrics_v1.json" },

    "determinism_cert_ref": { "artifact_id":"sha256:<...>", "artifact_relpath":"eudrs_u/evidence/sha256_<...>.determinism_cert_v1.json" },
    "universality_cert_ref": { "artifact_id":"sha256:<...>", "artifact_relpath":"eudrs_u/evidence/sha256_<...>.universality_cert_v1.json" }
  }
}
```

RE2 verifier uses this as the entrypoint.

---

## Appendix B — Required “no ambiguity” conventions

These are mandatory coding rules for EUDRS-U modules and campaigns.

1. **No reliance on dict iteration order** unless canonical JSON sorting is applied before hashing.
2. **All lists are ordered**; if a list is conceptually a set, you MUST specify its sort key.
3. **All binary encodings are little-endian**, and padding bytes MUST be zero.
4. **All paths in artifacts are repo-relative POSIX paths**.
5. **All comparisons are bytewise**, and tie-break rules are always explicit.
6. **All caps are enforced in both producer and verifier**, and verifier is authoritative.

---

If you want this packaged as a repo-ready “engineering spec artifact” (single markdown file plus JSON schema stubs and binary layout headers), the content above is already in the required structure; engineering can directly translate each section into:

* `Genesis/schema/v18_0/*.jsonschema`
* `CDEL-v2/cdel/v18_0/eudrs_u/*.py`
* `orchestrator/rsi_eudrs_u_*.py`
