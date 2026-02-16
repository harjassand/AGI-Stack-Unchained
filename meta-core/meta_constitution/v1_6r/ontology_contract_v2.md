# Ontology Contract v2 (Normative)

This contract defines the v2 ontology admission/activation policy for RE2.

## 1. Scope and Trust
- Iron Kernel v1.4 is unchanged.
- Ontology proposals are untrusted; only CDEL evaluation + receipts may activate.
- All ontology artifacts are GCJ-1 canonical JSON and content-addressed.

## 2. Self-hash rule (pinned)
- For any object with a self hash field `F`, the object hash is computed by setting `F = "__SELF__"` and hashing `canon_bytes(obj)`.
- `ontology_id` and `concept_id` MUST follow this rule.
- `ontology_ledger_entry_v2.line_hash` MUST follow this rule.

## 3. Onto-DSL v2 (bounded)
- Input: `z_core` (canonical JSON object).
- Output values are `bool` or signed 32-bit `i32` (wrap two's complement on overflow).
- Allowed ops: `const_i32`, `const_bool`, `get`, `add`, `sub`, `mul`, `eq`, `lt`, `gt`, `and`, `or`, `not`, `select`, `clamp_i32`, `hash_u32`.
- `hash_u32(x)` is defined as SHA-256 of 4-byte little-endian `x` (two's complement), taking the first 4 bytes as unsigned, then wrapping to signed i32.
- Gas and bounds are enforced by constitution constants (see `constants_v1.json`).

## 4. Description Length (DL) Metric
Let `ONTO_CORPUS(t)` be the concatenation of heldout traces from the last `W_onto` epochs.
- Context `ctx = sha256(canon_bytes(z_onto))`, where `z_onto` is ontology output.
- Data bits per context: `n_ctx * 1 + n_nondefault * ALT_BITS`, `ALT_BITS = ceil_log2(|A|-1)`.
- Model bits: `#contexts * ACTION_ID_BITS`, `ACTION_ID_BITS = ceil_log2(|A|)`.
- Rent bits: `8 * len(canon_bytes(ontology_def_v2)) (+ snapshot bits if present)`.
- Total `DL_bits = rent_bits + model_bits + data_bits`.
- Gain: `DL_gain_bits = DL_bits(base) - DL_bits(new)`.

## 5. Promotion Gate
A proposal passes iff:
1. Ontology DSL and bounds pass.
2. `DL_gain_bits ≥ ONTO_DL_GAIN_MIN_BITS`.
3. `support_families_improved ≥ ONTO_SUPPORT_FAMILIES_MIN`.
4. No contract regression on anchor evaluation (fail-closed).

Tie-break among passing proposals:
1. Larger `DL_gain_bits`.
2. Smaller `rent_bits`.
3. Fewer concepts.
4. Lexicographically smallest `ontology_id`.

## 6. Eviction
On each ontology-evaluation epoch:
- Recompute `DL_gain_bits` for the active ontology over the eviction window.
- If `DL_gain_bits < ONTO_EVICT_MIN_GAIN_BITS`, increment `bad_epochs`, else reset.
- If `bad_epochs ≥ ONTO_EVICT_K_DROP`, emit `EVICT` and clear active ontology.

## 7. Artifacts (v2)
- `ontology_def_v2.json`
- `ontology_patch_v2.json`
- `ontology_eval_report_v2.json`
- `ontology_admit_receipt_v2.json`
- `ontology_ledger_entry_v2.jsonl`
- `ontology_active_set_v2.json`
- `ontology_snapshot_v2.json` (optional)
- `rsi_ontology_receipt_v2.json`

All artifacts MUST include x-meta bindings to `META_HASH`, `KERNEL_HASH`, and `constants_hash`.
