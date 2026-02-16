# CCAP and Genesis Engine SH-1: Technical Deep Dive

**Report Date**: 2026-02-11  
**Version**: v18.0 + SH-1  
**Analysis Scope**: CCAP Protocol, Genesis Engine SH-0/SH-1, Integration Architecture, Continual Learning Mechanisms

---

## Executive Summary

This report provides a comprehensive technical analysis of the **CCAP (Certified Capsule Proposal) protocol** and the **Genesis Engine SH-1 (Symbiotic Harmony v1)** self-improvement system. These components represent a major architectural evolution in the AGI Stack, introducing:

1. **Universal Verification**: CCAP enables a single verifier for arbitrary code patches
2. **Receipt-Driven Meta-Learning**: SH-1 learns from historical outcomes to improve proposal quality
3. **Deterministic Proposal Generation**: Reproducible, verifiable self-improvement
4. **Hard-Avoid Projection**: Prevents novelty laundering and repeated failures

**Key Finding**: This system implements a **limited form of continual learning** focused on meta-optimization (learning *how to propose* better changes) rather than domain knowledge acquisition (learning *what* to change).

---

## Table of Contents

1. [CCAP Protocol Architecture](#1-ccap-protocol-architecture)
2. [Genesis Engine SH-1 Architecture](#2-genesis-engine-sh-1-architecture)
3. [SH-0 vs SH-1: Evolution](#3-sh-0-vs-sh-1-evolution)
4. [Integration Architecture](#4-integration-architecture)
5. [Continual Learning Analysis](#5-continual-learning-analysis)
6. [Function-Level Analysis](#6-function-level-analysis)
7. [Data Flow and State Management](#7-data-flow-and-state-management)
8. [Limitations and Future Directions](#8-limitations-and-future-directions)

---

## 1. CCAP Protocol Architecture

### 1.1 Overview

**CCAP (Certified Capsule Proposal)** is a universal verification protocol for arbitrary code patches. It replaces campaign-specific verifiers with a single, reusable verifier that enforces patch allowlists and runs evaluation kernels.

**Location**: `CDEL-v2/cdel/v18_0/verify_ccap_v1.py` (758 lines)

**Key Innovation**: Separates **what can be changed** (allowlists) from **how changes are verified** (evaluation kernels), enabling flexible self-improvement without modifying verifiers.

### 1.2 Three-Stage Verification Pipeline

CCAP verification proceeds through three deterministic stages:

```
REALIZE → SCORE → FINAL_AUDIT
```

#### Stage 1: REALIZE
**Purpose**: Apply patch and validate schema  
**Timeout**: 30 seconds  
**Gates**: None (always runs)

**Process**:
1. Load CCAP bundle (`ccap_bundle_v1.json`)
2. Validate patch against allowlists
3. Apply patch to base tree
4. Compute `applied_tree_id`
5. Generate `realized_out_id`

**Key Functions**:
```python
def _verify_once(...):
    # Load CCAP bundle
    ccap_bundle = load_canon_dict(ccap_path)
    
    # Validate patch allowlists
    touched_paths = _parse_patch_touched_paths(patch_bytes)
    for path in touched_paths:
        if _path_forbidden_by_allowlists(path, allowlists):
            _write_refutation_cert(..., code="FORBIDDEN_PATH", ...)
            return
    
    # Apply patch (via EK runner)
    run_ek(stage="REALIZE", ...)
```

#### Stage 2: SCORE
**Purpose**: Run evaluation kernel benchmarks  
**Timeout**: 3600 seconds (1 hour)  
**Gates**: `REALIZE` must pass

**Process**:
1. Load evaluation kernel (EK) from authority pins
2. Run benchmark suite on applied tree
3. Compute metrics (e.g., `accuracy_q32`, `pass_count`)
4. Generate scorecard

**Key Functions**:
```python
def run_ek(stage="SCORE", ...):
    # Load EK from authority pins
    ek = _load_pinned_ek(repo_root, pins, ek_id)
    
    # Run benchmark suite
    scoring_impl = ek["scoring_impl"]
    if scoring_impl["kind"] == "OMEGA_BENCHMARK_SUITE":
        # Run omega_benchmark_suite_v1.py
        result = subprocess.run([
            sys.executable,
            str(scoring_impl["code_ref"]["path"]),
            ...
        ])
```

#### Stage 3: FINAL_AUDIT
**Purpose**: Verify promotion criteria  
**Timeout**: 30 seconds  
**Gates**: `SCORE` must pass

**Process**:
1. Check determinism (replay hash match)
2. Validate cost budgets
3. Apply promotion gates (e.g., `min_accuracy_q32`)
4. Generate final decision (PROMOTE/REJECT)

**Key Functions**:
```python
def _verify_once(...):
    # Check determinism
    if determinism_check != "PASS":
        decision = "REJECT"
    
    # Apply promotion gates
    for gate in ek["stages"][2]["gates"]:
        if not _gate_passes(scorecard, gate):
            decision = "REJECT"
    
    # Write receipt
    _write_ccap_receipt(receipt_out_dir, receipt_payload)
```

### 1.3 Patch Allowlist Enforcement

**Location**: `authority/ccap_patch_allowlists_v1.json`

**Mechanism**: Allowlists define **prefix-based rules** for which files can be modified.

**Example Allowlist**:
```json
{
  "schema_version": "ccap_patch_allowlists_v1",
  "allowlists": {
    "OMEGA_CORE": {
      "allowed_prefixes": [
        "orchestrator/",
        "tools/",
        "campaigns/"
      ],
      "forbidden_prefixes": [
        "authority/",
        "meta-core/",
        "CDEL-v2/",
        "Genesis/"
      ]
    }
  }
}
```

**Enforcement Logic**:
```python
def _path_forbidden_by_allowlists(path_rel: str, allowlists: dict) -> bool:
    # Check if path matches any allowed prefix
    allowed = False
    for prefix in allowlists.get("allowed_prefixes", []):
        if _prefix_match(path_rel, prefix):
            allowed = True
            break
    
    # Check if path matches any forbidden prefix (overrides allowed)
    for prefix in allowlists.get("forbidden_prefixes", []):
        if _prefix_match(path_rel, prefix):
            return True  # Forbidden
    
    return not allowed
```

### 1.4 Authority Pins System

**Location**: `authority/authority_pins_v1.json`

**Purpose**: Cryptographic root of trust for evaluation kernels, operator pools, and patch allowlists.

**Structure**:
```json
{
  "schema_version": "authority_pins_v1",
  "pins": {
    "evaluation_kernels": {
      "ek_omega_v18_0_v1": {
        "path": "authority/evaluation_kernels/ek_omega_v18_0_v1.json",
        "hash": "sha256:abc123..."
      }
    },
    "operator_pools": {
      "operator_pool_core_v1": {
        "path": "authority/operator_pools/operator_pool_core_v1.json",
        "hash": "sha256:def456..."
      }
    },
    "patch_allowlists": {
      "ccap_patch_allowlists_v1": {
        "path": "authority/ccap_patch_allowlists_v1.json",
        "hash": "sha256:ghi789..."
      }
    }
  }
}
```

**Verification**:
```python
def _load_pinned_patch_allowlists(repo_root: Path, pins: dict) -> dict:
    # Load pinned allowlists
    pin = pins["pins"]["patch_allowlists"]["ccap_patch_allowlists_v1"]
    path = repo_root / pin["path"]
    expected_hash = pin["hash"]
    
    # Verify hash
    actual_hash = sha256_prefixed(canon_bytes(load_canon_dict(path)))
    if actual_hash != expected_hash:
        fail("AUTH_HASH_MISMATCH")
    
    return load_canon_dict(path)
```

### 1.5 CCAP Bundle Schema

**Schema**: `ccap_bundle_v1`

**Structure**:
```json
{
  "schema_version": "ccap_bundle_v1",
  "ccap_id": "sha256:...",
  "kind": "PATCH",
  "base_tree_id": "sha256:...",
  "ek_id": "ek_omega_v18_0_v1",
  "op_pool_id": "operator_pool_core_v1",
  "build_recipe_id": "omega_v18_0_default",
  "patch_blob_id": "sha256:...",
  "pd_id": "sha256:...",  // Proposal Descriptor ID
  "beh_id": "sha256:..."  // Behavior Signature ID
}
```

**Key Fields**:
- `ccap_id`: Content hash of the bundle
- `base_tree_id`: Git tree hash of the base code
- `ek_id`: Evaluation kernel to use for scoring
- `op_pool_id`: Operator pool for sandbox configuration
- `patch_blob_id`: Hash of the patch file
- `pd_id`: Proposal Descriptor (from SH-1)
- `beh_id`: Behavior Signature (from SH-1)

---

## 2. Genesis Engine SH-1 Architecture

### 2.1 Overview

**Genesis Engine SH-1 (Symbiotic Harmony v1)** is a receipt-driven self-improvement system that learns from historical promotion/rejection patterns to generate better code proposals.

**Location**: `tools/genesis_engine/ge_symbiotic_optimizer_v0_3.py` (847 lines)

**Key Innovation**: **Receipt-Driven Meta-Learning** - the system analyzes past CCAP receipts to learn which types of changes are likely to be accepted.

### 2.2 Core Metrics

#### PD (Promotion Density)
**Purpose**: Measures success rate per file  
**Location**: `tools/genesis_engine/sh1_pd_v1.py` (160 lines)

**Formula**:
```
PD = promotions / (promotions + rejections)
```

**Implementation**:
```python
def build_pd_from_patch_bytes(
    *,
    patch_bytes: bytes,
    base_tree_id: str,
    ek_id: str,
    op_pool_id: str,
    size_buckets_bytes_u64: list[int],
) -> tuple[dict, dict]:
    # Extract patch features
    features = extract_patch_features(
        patch_bytes=patch_bytes,
        size_buckets_bytes_u64=size_buckets_bytes_u64,
    )
    
    # Build PD (Proposal Descriptor)
    pd_no_id = pd_without_id(
        base_tree_id=base_tree_id,
        ek_id=ek_id,
        op_pool_id=op_pool_id,
        touched_paths_hash=features["touched_paths_hash"],
        size_bucket_u8=features["size_bucket_u8"],
    )
    
    # Compute PD ID
    pd_id = pd_id_from_pd_no_id(pd_no_id)
    
    return pd_payload, features
```

**PD Schema**:
```json
{
  "schema_version": "ge_pd_v1",
  "pd_id": "sha256:...",
  "kind": "PATCH",
  "base_tree_id": "sha256:...",
  "ek_id": "ek_omega_v18_0_v1",
  "op_pool_id": "operator_pool_core_v1",
  "touched_paths_hash": "sha256:...",  // Hash of modified files
  "size_bucket_u8": 2  // Patch size category (0-5)
}
```

#### XS (eXploration Score)
**Purpose**: Balances exploitation vs exploration  
**Location**: `tools/genesis_engine/sh1_xs_v1.py` (413 lines)

**Formula**:
```
XS = novelty_bits / 256
```

**Implementation**:
```python
def build_xs_snapshot(
    *,
    recent_runs_root: Path | None,
    ge_config: dict,
    authority_pins_hash: str,
) -> dict:
    # Collect CCAP receipts from recent runs
    receipt_paths = _collect_matching_paths(
        recent_runs_root=recent_runs_root,
        globs=ge_config["receipt_ingest"]["receipt_globs"],
    )
    
    # Build event stream
    events = []
    for receipt_path in receipt_paths:
        receipt = load_canon_dict(receipt_path)
        
        # Extract behavior signature
        beh_sig = build_behavior_signature(
            ge_config=ge_config,
            receipt_payload=receipt,
            refutation_code=refutation_code,
        )
        
        events.append({
            "pd_id": receipt["pd_id"],
            "beh_id": beh_sig["beh_id"],
            "decision": receipt["decision"],
            ...
        })
    
    # Compute novelty series
    beh_ids = [e["beh_id"] for e in events]
    novelty_series = novelty_series(
        beh_ids=beh_ids,
        reservoir_size_u64=ge_config["novelty"]["reservoir_size_u64"],
    )
    
    return xs_snapshot
```

**XS Snapshot Schema**:
```json
{
  "schema_version": "ge_xs_snapshot_v1",
  "xs_id": "sha256:...",
  "authority_pins_hash": "sha256:...",
  "event_stream_hash": "sha256:...",
  "events": [
    {
      "pd_id": "sha256:...",
      "beh_id": "sha256:...",
      "decision": "PROMOTE",
      "novelty_bits_u64": 128
    }
  ]
}
```

#### Behavior Signature
**Purpose**: Fingerprints patch effects for novelty detection  
**Location**: `tools/genesis_engine/sh1_behavior_sig_v1.py` (207 lines)

**Phi Vector**: 8-dimensional feature vector
```python
def phi_vector(
    *,
    ge_config: dict,
    receipt_payload: dict,
    refutation_code: str,
) -> list[int]:
    return [
        _decision_phi(receipt_payload),        # 0: PROMOTE=1, REJECT=0
        _eval_status_phi(receipt_payload),     # 1: PASS=1, FAIL=0, REFUTED=-1
        _determinism_phi(receipt_payload),     # 2: PASS=1, DIVERGED=-1, REFUTED=-2
        sentinel_class_value(...),             # 3: OK=0, BUSY=1, LOGIC=2, SAFETY=3
        _bucket_u8(cpu_ms, thresholds),        # 4: CPU time bucket (0-5)
        _bucket_u8(wall_ms, thresholds),       # 5: Wall time bucket (0-5)
        refutation_code_hash16(refutation_code), # 6: Refutation code hash (0-65535)
        0,                                     # 7: Reserved
    ]
```

**Novelty Computation**:
```python
def novelty_bits(*, beh_id: str, reservoir_beh_ids: Sequence[str]) -> int:
    # Compute Hamming distance to all prior behaviors
    if not reservoir_beh_ids:
        return 256  # Maximum novelty
    
    # Find minimum Hamming distance
    return min(
        hamming_distance_bits(beh_id, prior)
        for prior in reservoir_beh_ids
    )
```

### 2.3 Bucket Planning Algorithm

**Purpose**: Allocates proposal budget across three strategies

**Buckets**:
1. **HOTFIX** (opt): High PD files (exploit known-good targets)
2. **INCREMENTAL** (nov): Medium PD files (balanced exploration)
3. **EXPLORATORY** (grow): Low PD files (explore untested targets)

**Configuration** (`ge_config_v1.json`):
```json
{
  "bucket_fracs_q32": {
    "opt_q32": 2576980378,   // 60% (0.6 in Q32)
    "nov_q32": 858993459,    // 20% (0.2 in Q32)
    "grow_q32": 858993459    // 20% (0.2 in Q32)
  },
  "bucket_min_counts": {
    "opt_u64": 1,
    "nov_u64": 1,
    "grow_u64": 1
  }
}
```

**Implementation**:
```python
def _bucket_plan(*, ge_config: dict, max_ccaps: int) -> dict:
    fracs = ge_config["bucket_fracs_q32"]
    mins = ge_config["bucket_min_counts"]
    
    # Compute counts per bucket
    opt_count = max(mins["opt_u64"], (max_ccaps * fracs["opt_q32"]) >> 32)
    nov_count = max(mins["nov_u64"], (max_ccaps * fracs["nov_q32"]) >> 32)
    grow_count = max(mins["grow_u64"], (max_ccaps * fracs["grow_q32"]) >> 32)
    
    return {
        "opt": opt_count,
        "nov": nov_count,
        "grow": grow_count,
    }
```

### 2.4 Template-Based Patch Generation

**Templates**: Predefined patch patterns for deterministic code modification

**Supported Templates**:
1. **COMMENT_APPEND**: Add explanatory comments
2. **JSON_TWEAK_COOLDOWN**: Adjust cooldown parameters
3. **JSON_TWEAK_BUDGET_HINT**: Adjust budget hints

**Configuration**:
```json
{
  "proposal_space_patch": {
    "templates": [
      {"bucket": "opt", "template_id": "JSON_TWEAK_BUDGET_HINT"},
      {"bucket": "nov", "template_id": "JSON_TWEAK_COOLDOWN"},
      {"bucket": "grow", "template_id": "COMMENT_APPEND"}
    ]
  }
}
```

**Implementation**:
```python
def _build_json_tweak_patch(
    *,
    target_relpath: str,
    marker: str,
    template_id: str,
    repo_root: Path,
) -> str:
    # Load original JSON
    target_path = repo_root / target_relpath
    original_content = target_path.read_text(encoding="utf-8")
    original_obj = json.loads(original_content)
    
    # Find tweak paths
    if template_id == "JSON_TWEAK_COOLDOWN":
        paths = []
        _json_walk_cooldown_paths(original_obj, (), paths)
    elif template_id == "JSON_TWEAK_BUDGET_HINT":
        paths = []
        _json_walk_budget_hint_paths(original_obj, (), paths)
    
    # Select path deterministically
    path = paths[hash(marker) % len(paths)]
    
    # Compute delta
    delta = _deterministic_delta(
        marker=marker,
        template_id=template_id,
        target_relpath=target_relpath,
    )
    
    # Apply delta
    modified_obj = copy.deepcopy(original_obj)
    old_value = _json_get(modified_obj, path)
    new_value = old_value + delta
    _json_set(modified_obj, path, new_value)
    
    # Generate unified diff
    return _build_unified_patch(
        target_relpath=target_relpath,
        before=original_content,
        after=json.dumps(modified_obj, indent=2),
    )
```

**Deterministic Delta**:
```python
def _deterministic_delta(
    *,
    marker: str,
    template_id: str,
    target_relpath: str,
) -> int:
    # Compute deterministic hash
    seed = hashlib.sha256(
        f"{marker}:{template_id}:{target_relpath}".encode("utf-8")
    ).digest()
    
    # Map to delta range
    if template_id == "JSON_TWEAK_COOLDOWN":
        # Reduce cooldown by 1-5 ticks
        return -(1 + (int.from_bytes(seed[:4], "big") % 5))
    elif template_id == "JSON_TWEAK_BUDGET_HINT":
        # Adjust budget by ±0.25 in Q32
        step = _BUDGET_HINT_STEP_Q32  # 1 << 30 (0.25 in Q32)
        return step if (seed[0] & 1) else -step
```

### 2.5 Hard-Avoid Projection

**Purpose**: Prevents "novelty laundering" - disguising repeated failures as new proposals

**Mechanism**: Tracks behavior signatures of rejected proposals and blocks similar future proposals

**Configuration**:
```json
{
  "hard_avoid": {
    "enabled_b": true,
    "pd_projection": {
      "touched_paths_prefix_hex_u8": 8  // Use first 8 hex chars of touched_paths_hash
    },
    "refutation_codes": [
      "NONDETERMINISM_DETECTED",
      "CANONICALIZATION_MISMATCH"
    ]
  }
}
```

**Implementation**:
```python
def _hard_avoid_prefixes(snapshot: dict) -> set[str]:
    # Extract hard-avoid events
    hard_avoid_codes = ge_config["hard_avoid"]["refutation_codes"]
    prefix_len = ge_config["hard_avoid"]["pd_projection"]["touched_paths_prefix_hex_u8"]
    
    prefixes = set()
    for event in snapshot["events"]:
        if event["refutation_code"] in hard_avoid_codes:
            # Extract touched_paths_hash prefix
            pd = event["pd"]
            prefix = touched_paths_hash_prefix_hex(
                touched_paths_hash=pd["touched_paths_hash"],
                prefix_hex_u8=prefix_len,
            )
            prefixes.add(prefix)
    
    return prefixes

def _eligible_target(
    *,
    target_relpath: str,
    repo_root: Path,
    ge_config: dict,
    hard_avoid_prefixes: set[str],
) -> bool:
    # Check if target matches hard-avoid prefix
    touched_paths_hash = touched_paths_hash_for_paths([target_relpath])
    prefix = touched_paths_hash_prefix_hex(
        touched_paths_hash=touched_paths_hash,
        prefix_hex_u8=8,
    )
    
    if prefix in hard_avoid_prefixes:
        return False  # Avoid this target
    
    return True
```

---

## 3. SH-0 vs SH-1: Evolution

### 3.1 SH-0 (Baseline)

**Status**: Not found in codebase  
**Hypothesis**: SH-0 likely refers to a pre-receipt-driven baseline (e.g., random or heuristic-based proposal generation)

**Evidence**:
- No `sh0_*.py` files found
- `ge_symbiotic_optimizer_v0_2.py` exists (likely SH-0 or pre-SH-1)
- `ge_symbiotic_optimizer_v0_3.py` is labeled "SH-1 v0.3"

**Inferred SH-0 Characteristics**:
- No receipt analysis
- No PD/XS metrics
- No behavior signatures
- No hard-avoid projection
- Likely random or heuristic target selection

### 3.2 SH-1 (Symbiotic Harmony v1)

**Status**: Active (v0.3)  
**Key Innovations**:
1. **Receipt-Driven Learning**: Analyzes historical outcomes
2. **PD/XS Metrics**: Quantifies success rate and novelty
3. **Bucket Planning**: Strategic allocation across exploit/explore
4. **Behavior Signatures**: Fingerprints patch effects
5. **Hard-Avoid Projection**: Prevents repeated failures

**Evolution Summary**:
```
SH-0 (Baseline)          SH-1 (Symbiotic Harmony v1)
├─ Random selection  →   ├─ Receipt-driven selection
├─ No learning       →   ├─ PD/XS meta-learning
├─ No novelty        →   ├─ Behavior signatures
└─ No avoidance      →   └─ Hard-avoid projection
```

---

## 4. Integration Architecture

### 4.1 End-to-End Workflow

```
┌─────────────────────────────────────────────────────────────────┐
│                   SH-1 + CCAP Integration                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. RECEIPT ANALYSIS (SH-1)                                     │
│     ├─ sh1_xs_v1.py: Collect receipts from recent runs         │
│     ├─ sh1_pd_v1.py: Extract PD features                       │
│     ├─ sh1_behavior_sig_v1.py: Compute behavior signatures     │
│     └─ Output: XS Snapshot (event stream + novelty series)     │
│                                                                  │
│  2. BUCKET PLANNING (SH-1)                                      │
│     ├─ _bucket_plan(): Allocate budget (60% opt, 20% nov, 20% grow) │
│     ├─ _ranked_targets_for_bucket(): Rank files by PD/XS      │
│     └─ Output: Target list per bucket                          │
│                                                                  │
│  3. PATCH GENERATION (SH-1)                                     │
│     ├─ _template_for_bucket(): Select template                │
│     ├─ _build_json_tweak_patch(): Generate patch              │
│     ├─ _emit_ccap(): Create CCAP bundle                       │
│     └─ Output: CCAP bundles (ccap_bundle_v1.json + patch)     │
│                                                                  │
│  4. CCAP VERIFICATION (CDEL-v2)                                 │
│     ├─ verify_ccap_v1.py: Universal verifier                  │
│     ├─ Stage 1 (REALIZE): Apply patch, validate allowlists    │
│     ├─ Stage 2 (SCORE): Run evaluation kernel                 │
│     ├─ Stage 3 (FINAL_AUDIT): Check promotion gates           │
│     └─ Output: CCAP receipt (ccap_receipt_v1.json)            │
│                                                                  │
│  5. PROMOTION (Omega Daemon)                                    │
│     ├─ omega_promoter_v1.py: Process CCAP receipt             │
│     ├─ meta-core: Constitutional verification                 │
│     └─ Output: Activated code change                          │
│                                                                  │
│  6. FEEDBACK LOOP (SH-1)                                        │
│     └─ Next iteration uses new receipts for learning          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 Campaign Integration

**Campaign**: `rsi_ge_symbiotic_optimizer_sh1_v0_1`  
**Location**: `CDEL-v2/cdel/v18_0/campaign_ge_symbiotic_optimizer_sh1_v0_1.py`

**Workflow**:
```python
def run(*, campaign_pack: Path, out_dir: Path) -> None:
    # 1. Load campaign pack
    pack = _load_pack(campaign_pack)
    
    # 2. Discover runs root (for receipt analysis)
    recent_runs_root = _discover_runs_root(out_dir)
    
    # 3. Invoke SH-1 optimizer
    cmd = [
        sys.executable,
        "tools/genesis_engine/ge_symbiotic_optimizer_v0_3.py",
        "--subrun_out_dir", str(out_dir),
        "--ge_config_path", "tools/genesis_engine/config/ge_config_v1.json",
        "--authority_pins_path", "authority/authority_pins_v1.json",
        "--recent_runs_root", str(recent_runs_root),
        "--max_ccaps", "1",
    ]
    subprocess.run(cmd, check=True)
    
    # 4. Load optimizer summary
    summary = load_canon_dict(out_dir / "ge_symbiotic_optimizer_summary_v0_3.json")
    
    # 5. Emit CCAP promotion bundles
    for ccap in summary["ccaps"]:
        bundle = {
            "schema_version": "omega_promotion_bundle_ccap_v1",
            "ccap_id": ccap["ccap_id"],
            "ccap_relpath": ccap["ccap_relpath"],
            "patch_relpath": ccap["patch_relpath"],
            ...
        }
        write_canon_json(promotion_dir / f"sha256_{bundle_hash}.json", bundle)
```

### 4.3 State Management

**SH-1 State** (Optional):
- **Location**: `OMEGA_GE_STATE_ROOT` environment variable
- **Purpose**: Persistent storage for XS snapshots across runs
- **Schema**: `ge_xs_snapshot_v1`

**CCAP State**:
- **Location**: `runs/{campaign}/tick_{N}/promotion/`
- **Purpose**: CCAP bundles awaiting verification
- **Schema**: `ccap_bundle_v1`

**Receipt State**:
- **Location**: `runs/{campaign}/tick_{N}/ccap_receipt_v1.json`
- **Purpose**: Verification outcomes for feedback loop
- **Schema**: `ccap_receipt_v1`

---

## 5. Continual Learning Analysis

### 5.1 Is This Continual Learning?

**Answer**: **Yes, but limited to meta-optimization.**

**What SH-1 Learns**:
1. **Which files are "hot"** (high PD → likely to accept changes)
2. **Which files are "cold"** (low PD → unexplored potential)
3. **Which patch patterns fail** (hard-avoid projection)
4. **Which behaviors are novel** (behavior signatures)

**What SH-1 Does NOT Learn**:
1. **Domain knowledge** (e.g., "chemistry requires SMILES validation")
2. **Causal models** (e.g., "reducing cooldown improves throughput")
3. **Transfer learning** (e.g., "lessons from campaign A apply to campaign B")
4. **Multimodal representations** (e.g., "images + text → understanding")

### 5.2 Continual Learning Mechanisms

#### Mechanism 1: Receipt Ingestion
**Type**: Experience Replay  
**Implementation**: `sh1_xs_v1.py::build_xs_snapshot()`

**Process**:
1. Scan `recent_runs_root` for CCAP receipts
2. Extract PD, behavior signature, decision
3. Build event stream (chronological)
4. Compute novelty series (Hamming distance)

**Continual Learning Property**: Accumulates experience over time

#### Mechanism 2: PD Tracking
**Type**: Success Rate Estimation  
**Implementation**: `sh1_pd_v1.py::build_pd_from_patch_bytes()`

**Process**:
1. Compute `touched_paths_hash` for each patch
2. Track promotions/rejections per hash
3. Estimate PD = promotions / (promotions + rejections)

**Continual Learning Property**: Updates success estimates as more data arrives

#### Mechanism 3: Behavior Reservoir
**Type**: Novelty Detection  
**Implementation**: `sh1_behavior_sig_v1.py::novelty_series()`

**Process**:
1. Maintain reservoir of recent behavior signatures (size 512)
2. Compute Hamming distance to reservoir for each new proposal
3. Prefer high-novelty proposals (exploration)

**Continual Learning Property**: Adapts to changing behavior distribution

#### Mechanism 4: Hard-Avoid Projection
**Type**: Negative Transfer Prevention  
**Implementation**: `ge_symbiotic_optimizer_v0_3.py::_hard_avoid_prefixes()`

**Process**:
1. Track `touched_paths_hash` prefixes of rejected proposals
2. Block future proposals matching those prefixes
3. Prevents repeated failures

**Continual Learning Property**: Learns what NOT to do

### 5.3 Limitations as Continual Learning

**Limitation 1: No Knowledge Transfer**
- Each campaign learns independently
- No shared representation across domains
- No transfer from chemistry to biology

**Limitation 2: No Causal Reasoning**
- Learns correlations (high PD → accept), not causation
- Cannot explain *why* a change was accepted
- No counterfactual reasoning

**Limitation 3: No Representation Learning**
- Fixed feature space (phi vector)
- No learned embeddings or abstractions
- No deep learning

**Limitation 4: No Lifelong Learning**
- XS snapshots are ephemeral (unless `OMEGA_GE_STATE_ROOT` is set)
- No long-term memory consolidation
- No catastrophic forgetting prevention

### 5.4 Comparison to True Continual Learning

| Property | SH-1 | True Continual Learning |
|----------|------|-------------------------|
| **Experience Accumulation** | ✓ (receipts) | ✓ (datasets) |
| **Online Updates** | ✓ (per tick) | ✓ (per batch) |
| **Catastrophic Forgetting Prevention** | ✗ | ✓ (EWC, replay buffers) |
| **Transfer Learning** | ✗ | ✓ (pre-training, fine-tuning) |
| **Representation Learning** | ✗ | ✓ (embeddings, features) |
| **Causal Reasoning** | ✗ | ✗ (mostly) |
| **Multimodal Learning** | ✗ | ✓ (vision + language) |

**Verdict**: SH-1 is **meta-learning** (learning to propose) rather than **domain learning** (learning to solve).

---

## 6. Function-Level Analysis

### 6.1 CCAP Verifier Functions

**File**: `CDEL-v2/cdel/v18_0/verify_ccap_v1.py` (758 lines)

| Function | Purpose | LOC | Complexity |
|----------|---------|-----|------------|
| `_normalize_patch_relpath()` | Normalize file paths | 7 | Low |
| `_prefix_match()` | Check prefix match | 6 | Low |
| `_parse_patch_touched_paths()` | Extract modified files from patch | 22 | Medium |
| `_load_pinned_patch_allowlists()` | Load and verify allowlists | 29 | Medium |
| `_path_forbidden_by_allowlists()` | Check if path is forbidden | 12 | Medium |
| `_resolve_repo_root()` | Find repository root | 5 | Low |
| `_resolve_subrun_root()` | Find subrun directory | 13 | Low |
| `_resolve_ccap_path()` | Find CCAP bundle path | 8 | Low |
| `_write_refutation_cert()` | Write rejection certificate | 20 | Low |
| `_write_realized_receipt()` | Write REALIZE stage receipt | 38 | Medium |
| `_receipt_payload()` | Build receipt payload | 39 | Medium |
| `_write_ccap_receipt()` | Write final CCAP receipt | 4 | Low |
| **`_verify_once()`** | **Main verification logic** | **423** | **High** |
| `verify()` | Public API wrapper | 13 | Low |
| `main()` | CLI entry point | 45 | Medium |

**Key Function: `_verify_once()`**

**Signature**:
```python
def _verify_once(
    *,
    subrun_root: Path,
    repo_root: Path,
    ccap_relpath: str,
    receipt_out_dir: Path,
) -> None:
```

**Process** (simplified):
```python
def _verify_once(...):
    # 1. Load CCAP bundle
    ccap_bundle = load_canon_dict(ccap_path)
    validate_schema(ccap_bundle, "ccap_bundle_v1")
    
    # 2. Load authority pins
    pins = load_canon_dict(repo_root / "authority/authority_pins_v1.json")
    auth_hash = canon_hash_obj(pins)
    
    # 3. Load patch allowlists
    allowlists = _load_pinned_patch_allowlists(repo_root, pins)
    
    # 4. Validate patch against allowlists
    touched_paths = _parse_patch_touched_paths(patch_bytes)
    for path in touched_paths:
        if _path_forbidden_by_allowlists(path, allowlists):
            _write_refutation_cert(..., code="FORBIDDEN_PATH", ...)
            return
    
    # 5. Run REALIZE stage
    realize_result = run_ek(
        stage="REALIZE",
        ek=active_ek,
        op_pool=op_pool,
        base_tree_id=ccap_bundle["base_tree_id"],
        patch_bytes=patch_bytes,
        ...
    )
    
    # 6. Run SCORE stage (if REALIZE passed)
    if realize_result["eval_status"] == "PASS":
        score_result = run_ek(
            stage="SCORE",
            ek=active_ek,
            ...
        )
    
    # 7. Run FINAL_AUDIT stage (if SCORE passed)
    if score_result["eval_status"] == "PASS":
        audit_result = run_ek(
            stage="FINAL_AUDIT",
            ...
        )
    
    # 8. Determine decision
    decision = "PROMOTE" if all_gates_pass else "REJECT"
    
    # 9. Write CCAP receipt
    receipt_payload = _receipt_payload(
        ccap_id=ccap_bundle["ccap_id"],
        decision=decision,
        ...
    )
    _write_ccap_receipt(receipt_out_dir, receipt_payload)
```

### 6.2 SH-1 Optimizer Functions

**File**: `tools/genesis_engine/ge_symbiotic_optimizer_v0_3.py` (847 lines)

| Function | Purpose | LOC | Complexity |
|----------|---------|-----|------------|
| `_load_active_ek()` | Load evaluation kernel | 9 | Low |
| `_load_build_recipes()` | Load build recipes | 13 | Low |
| `_build_eval_stage_list()` | Extract EK stages | 16 | Low |
| `_base_tree_id_best_effort()` | Get current git tree hash | 27 | Medium |
| `_build_unified_patch()` | Generate unified diff | 14 | Low |
| `_build_comment_patch()` | Generate comment patch | 10 | Low |
| `_json_walk_cooldown_paths()` | Find cooldown fields | 10 | Medium |
| `_json_walk_budget_hint_paths()` | Find budget hint fields | 14 | Medium |
| `_deterministic_delta()` | Compute deterministic change | 2 | Low |
| `_build_json_tweak_patch()` | Generate JSON tweak patch | 50 | High |
| `_collect_prompt_trace()` | Build prompt trace | 17 | Low |
| **`_bucket_plan()`** | **Allocate budget across buckets** | **50** | **Medium** |
| `_empty_target_stats()` | Initialize target stats | 8 | Low |
| `_target_stats_from_events()` | Compute PD from events | 38 | Medium |
| **`_ranked_targets_for_bucket()`** | **Rank files by PD/XS** | **35** | **High** |
| `_template_for_bucket()` | Select template for bucket | 15 | Low |
| `_template_supports_target()` | Check template compatibility | 3 | Low |
| `_hard_avoid_prefixes()` | Extract hard-avoid prefixes | 10 | Medium |
| `_eligible_target()` | Check target eligibility | 27 | Medium |
| **`_emit_ccap()`** | **Generate CCAP bundle** | **111** | **High** |
| `main()` | Main entry point | 177 | Very High |

**Key Function: `_bucket_plan()`**

**Signature**:
```python
def _bucket_plan(*, ge_config: dict, max_ccaps: int) -> dict:
```

**Process**:
```python
def _bucket_plan(*, ge_config: dict, max_ccaps: int) -> dict:
    # 1. Load bucket fractions from config
    fracs = ge_config["bucket_fracs_q32"]
    opt_frac = fracs["opt_q32"]  # 60% (2576980378 in Q32)
    nov_frac = fracs["nov_q32"]  # 20% (858993459 in Q32)
    grow_frac = fracs["grow_q32"]  # 20% (858993459 in Q32)
    
    # 2. Compute counts (Q32 multiplication)
    opt_count = (max_ccaps * opt_frac) >> 32
    nov_count = (max_ccaps * nov_frac) >> 32
    grow_count = (max_ccaps * grow_frac) >> 32
    
    # 3. Enforce minimums
    mins = ge_config["bucket_min_counts"]
    opt_count = max(mins["opt_u64"], opt_count)
    nov_count = max(mins["nov_u64"], nov_count)
    grow_count = max(mins["grow_u64"], grow_count)
    
    # 4. Return plan
    return {
        "opt": int(opt_count),
        "nov": int(nov_count),
        "grow": int(grow_count),
    }
```

**Key Function: `_ranked_targets_for_bucket()`**

**Signature**:
```python
def _ranked_targets_for_bucket(
    *,
    bucket: str,
    allowed_targets: list[str],
    target_stats: dict[str, dict[str, int]],
) -> list[str]:
```

**Process**:
```python
def _ranked_targets_for_bucket(...):
    def _stats(target: str):
        return target_stats.get(target, _empty_target_stats())
    
    # 1. Compute PD for each target
    def _pd(target: str):
        stats = _stats(target)
        promotions = stats["promotions"]
        rejections = stats["rejections"]
        total = promotions + rejections
        if total == 0:
            return 0.0  # Unknown
        return promotions / total
    
    # 2. Rank by bucket strategy
    if bucket == "opt":
        # HOTFIX: Prefer high PD (exploit)
        return sorted(allowed_targets, key=_pd, reverse=True)
    elif bucket == "nov":
        # INCREMENTAL: Prefer medium PD (balanced)
        return sorted(allowed_targets, key=lambda t: abs(_pd(t) - 0.5))
    elif bucket == "grow":
        # EXPLORATORY: Prefer low PD (explore)
        return sorted(allowed_targets, key=_pd)
```

### 6.3 SH-1 PD Functions

**File**: `tools/genesis_engine/sh1_pd_v1.py` (160 lines)

| Function | Purpose | LOC | Complexity |
|----------|---------|-----|------------|
| `touched_paths_from_patch_bytes()` | Parse patch for modified files | 14 | Medium |
| `touched_paths_hash_for_paths()` | Hash file list | 3 | Low |
| `size_bucket_u8_for_bytes()` | Categorize patch size | 12 | Low |
| `extract_patch_features()` | Extract PD features | 8 | Low |
| `touched_paths_hash_prefix_hex()` | Extract hash prefix | 8 | Low |
| `pd_without_id()` | Build PD without ID | 16 | Low |
| `pd_id_from_pd_no_id()` | Compute PD ID | 1 | Low |
| **`build_pd_from_patch_bytes()`** | **Main PD builder** | **29** | **Medium** |

### 6.4 SH-1 XS Functions

**File**: `tools/genesis_engine/sh1_xs_v1.py` (413 lines)

| Function | Purpose | LOC | Complexity |
|----------|---------|-----|------------|
| `load_ge_config()` | Load and validate GE config | 27 | Medium |
| `_collect_matching_paths()` | Find receipt files | 10 | Low |
| `_refutation_match_rank()` | Rank refutation matches | 5 | Low |
| `_match_refutation_for_receipt()` | Find refutation for receipt | 10 | Low |
| `_path_distance()` | Compute path distance | 8 | Low |
| `_find_ccap_bundle_path()` | Find CCAP bundle | 16 | Medium |
| `_find_patch_path_for_ccap()` | Find patch file | 26 | Medium |
| `_event_stream_hash()` | Hash event stream | 9 | Low |
| **`build_xs_snapshot()`** | **Main XS builder** | **228** | **Very High** |

**Key Function: `build_xs_snapshot()`**

**Signature**:
```python
def build_xs_snapshot(
    *,
    recent_runs_root: Path | None,
    ge_config: dict,
    authority_pins_hash: str,
) -> dict:
```

**Process** (simplified):
```python
def build_xs_snapshot(...):
    # 1. Collect CCAP receipts
    receipt_paths = _collect_matching_paths(
        recent_runs_root=recent_runs_root,
        globs=ge_config["receipt_ingest"]["receipt_globs"],
    )
    
    # 2. Build event stream
    events = []
    for receipt_path in receipt_paths[:max_receipts]:
        receipt = load_canon_dict(receipt_path)
        
        # Find refutation (if rejected)
        refutation = _match_refutation_for_receipt(...)
        refutation_code = refutation.get("code", "") if refutation else ""
        
        # Build behavior signature
        beh_sig = build_behavior_signature(
            ge_config=ge_config,
            receipt_payload=receipt,
            refutation_code=refutation_code,
        )
        
        # Find CCAP bundle and patch
        ccap_path = _find_ccap_bundle_path(...)
        patch_path = _find_patch_path_for_ccap(...)
        
        # Build PD
        pd, features = build_pd_from_patch_bytes(
            patch_bytes=patch_path.read_bytes(),
            ...
        )
        
        events.append({
            "pd_id": pd["pd_id"],
            "pd": pd,
            "beh_id": beh_sig["beh_id"],
            "beh": beh_sig,
            "decision": receipt["decision"],
            "refutation_code": refutation_code,
            ...
        })
    
    # 3. Compute novelty series
    beh_ids = [e["beh_id"] for e in events]
    novelty_series = novelty_series(
        beh_ids=beh_ids,
        reservoir_size_u64=ge_config["novelty"]["reservoir_size_u64"],
    )
    
    # 4. Attach novelty to events
    for event, novelty_bits in zip(events, novelty_series):
        event["novelty_bits_u64"] = novelty_bits
    
    # 5. Build XS snapshot
    xs_snapshot = {
        "schema_version": "ge_xs_snapshot_v1",
        "xs_id": _hash_obj({"events": events, ...}),
        "authority_pins_hash": authority_pins_hash,
        "event_stream_hash": _event_stream_hash(events),
        "events": events,
    }
    
    return xs_snapshot
```

### 6.5 SH-1 Behavior Signature Functions

**File**: `tools/genesis_engine/sh1_behavior_sig_v1.py` (207 lines)

| Function | Purpose | LOC | Complexity |
|----------|---------|-----|------------|
| `_thresholds_from_config()` | Extract size thresholds | 13 | Low |
| `_bucket_u8()` | Categorize value | 5 | Low |
| `refutation_code_hash16()` | Hash refutation code | 5 | Low |
| `_decision_phi()` | Extract decision feature | 1 | Low |
| `_eval_status_phi()` | Extract eval status feature | 8 | Low |
| `_determinism_phi()` | Extract determinism feature | 8 | Low |
| `sentinel_class_value()` | Classify refutation | 28 | Medium |
| **`phi_vector()`** | **Build feature vector** | **25** | **Medium** |
| `build_behavior_signature()` | Build behavior signature | 18 | Low |
| `hamming_distance_bits()` | Compute Hamming distance | 3 | Low |
| `novelty_bits()` | Compute novelty | 3 | Low |
| `novelty_series()` | Compute novelty series | 12 | Low |

---

## 7. Data Flow and State Management

### 7.1 Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                      SH-1 + CCAP Data Flow                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  [Recent Runs]                                                  │
│      │                                                           │
│      ├─ runs/tick_001/ccap_receipt_v1.json                     │
│      ├─ runs/tick_002/ccap_receipt_v1.json                     │
│      └─ runs/tick_003/ccap_refutation_cert_v1.json             │
│      │                                                           │
│      ↓                                                           │
│  [Receipt Ingestion] (sh1_xs_v1.py)                            │
│      │                                                           │
│      ├─ Load receipts matching globs                           │
│      ├─ Extract PD (touched_paths_hash, size_bucket)           │
│      ├─ Extract behavior signature (phi vector)                │
│      └─ Compute novelty (Hamming distance)                     │
│      │                                                           │
│      ↓                                                           │
│  [XS Snapshot] (ge_xs_snapshot_v1.json)                        │
│      │                                                           │
│      ├─ events: [{pd_id, beh_id, decision, novelty_bits}]      │
│      └─ event_stream_hash: sha256:...                          │
│      │                                                           │
│      ↓                                                           │
│  [Target Statistics] (_target_stats_from_events)               │
│      │                                                           │
│      ├─ Per-file PD: promotions / (promotions + rejections)    │
│      └─ Per-file XS: avg(novelty_bits)                         │
│      │                                                           │
│      ↓                                                           │
│  [Bucket Planning] (_bucket_plan)                              │
│      │                                                           │
│      ├─ opt (60%): High PD files                               │
│      ├─ nov (20%): Medium PD files                             │
│      └─ grow (20%): Low PD files                               │
│      │                                                           │
│      ↓                                                           │
│  [Target Ranking] (_ranked_targets_for_bucket)                 │
│      │                                                           │
│      ├─ opt: Sort by PD (descending)                           │
│      ├─ nov: Sort by |PD - 0.5| (ascending)                    │
│      └─ grow: Sort by PD (ascending)                           │
│      │                                                           │
│      ↓                                                           │
│  [Patch Generation] (_build_json_tweak_patch)                  │
│      │                                                           │
│      ├─ Load target file                                       │
│      ├─ Find tweak paths (cooldown, budget_hint)               │
│      ├─ Compute deterministic delta                            │
│      └─ Generate unified diff                                  │
│      │                                                           │
│      ↓                                                           │
│  [CCAP Emission] (_emit_ccap)                                  │
│      │                                                           │
│      ├─ Build PD (pd_id, touched_paths_hash)                   │
│      ├─ Build behavior signature (beh_id, phi)                 │
│      ├─ Create CCAP bundle (ccap_bundle_v1.json)               │
│      └─ Write patch file                                       │
│      │                                                           │
│      ↓                                                           │
│  [CCAP Verification] (verify_ccap_v1.py)                       │
│      │                                                           │
│      ├─ REALIZE: Apply patch, validate allowlists              │
│      ├─ SCORE: Run evaluation kernel                           │
│      └─ FINAL_AUDIT: Check promotion gates                     │
│      │                                                           │
│      ↓                                                           │
│  [CCAP Receipt] (ccap_receipt_v1.json)                         │
│      │                                                           │
│      ├─ decision: PROMOTE | REJECT                             │
│      ├─ eval_status: PASS | FAIL | REFUTED                     │
│      ├─ determinism_check: PASS | DIVERGED | REFUTED           │
│      └─ cost_vector: {cpu_ms, wall_ms, ...}                    │
│      │                                                           │
│      └─ [Feedback Loop] → Next iteration                       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 7.2 State Persistence

**Ephemeral State** (per tick):
- CCAP bundles: `runs/tick_{N}/promotion/ccap_bundle_v1.json`
- CCAP receipts: `runs/tick_{N}/ccap_receipt_v1.json`
- Refutation certs: `runs/tick_{N}/ccap_refutation_cert_v1.json`

**Persistent State** (optional):
- XS snapshots: `$OMEGA_GE_STATE_ROOT/xs_snapshot_{hash}.json`
- Behavior reservoir: Embedded in XS snapshot

**Authority State** (immutable):
- Authority pins: `authority/authority_pins_v1.json`
- Evaluation kernels: `authority/evaluation_kernels/ek_omega_v18_0_v1.json`
- Patch allowlists: `authority/ccap_patch_allowlists_v1.json`

---

## 8. Limitations and Future Directions

### 8.1 Current Limitations

**Limitation 1: Template-Only Patches**
- Only supports 3 templates (COMMENT_APPEND, JSON_TWEAK_COOLDOWN, JSON_TWEAK_BUDGET_HINT)
- Cannot generate arbitrary code changes
- Limited to JSON tweaks and comments

**Limitation 2: No Causal Reasoning**
- Learns correlations (high PD → accept), not causation
- Cannot explain *why* a change improves metrics
- No counterfactual simulation

**Limitation 3: No Transfer Learning**
- Each campaign learns independently
- No shared representation across domains
- Cannot apply lessons from one domain to another

**Limitation 4: Limited Novelty Detection**
- Hamming distance on behavior signatures
- No semantic similarity (e.g., "similar code patterns")
- No clustering or dimensionality reduction

**Limitation 5: No Long-Term Memory**
- XS snapshots are ephemeral (unless `OMEGA_GE_STATE_ROOT` is set)
- No memory consolidation or replay buffers
- No catastrophic forgetting prevention

### 8.2 Future Directions

**Direction 1: Richer Patch Templates**
- Function-level refactoring
- Variable renaming
- Control flow optimization
- Data structure changes

**Direction 2: Causal Inference**
- Structural causal models
- Counterfactual reasoning
- Intervention analysis
- Mediation analysis

**Direction 3: Transfer Learning**
- Shared embeddings across campaigns
- Meta-learning across domains
- Few-shot adaptation
- Zero-shot generalization

**Direction 4: Deep Learning Integration**
- Neural patch generators (e.g., transformers)
- Learned embeddings for code
- Reinforcement learning for proposal selection
- Gradient-based optimization

**Direction 5: Lifelong Learning**
- Memory consolidation
- Replay buffers
- Elastic weight consolidation (EWC)
- Progressive neural networks

---

## Conclusion

The **CCAP protocol** and **Genesis Engine SH-1** represent a significant architectural evolution in the AGI Stack, introducing:

1. **Universal Verification**: A single verifier for arbitrary code patches
2. **Receipt-Driven Meta-Learning**: Learning from historical outcomes to improve proposals
3. **Deterministic Proposal Generation**: Reproducible, verifiable self-improvement
4. **Hard-Avoid Projection**: Preventing repeated failures

**Is This Continual Learning?**  
**Yes, but limited.** SH-1 implements a form of continual learning focused on **meta-optimization** (learning *how to propose* better changes) rather than **domain learning** (learning *what* to change). It accumulates experience over time, updates success estimates, and adapts to changing behavior distributions, but lacks transfer learning, causal reasoning, and representation learning.

**Key Insight**: SH-1 is a **meta-learner** that learns to navigate the proposal space more effectively, but it does not acquire domain knowledge or develop new problem-solving capabilities. It is a stepping stone toward continual learning, not a complete implementation.

---

**Report End**

**Generated**: 2026-02-11  
**Total Lines**: ~1,200  
**Total Functions Analyzed**: 60+  
**Code Files Examined**: 10+
