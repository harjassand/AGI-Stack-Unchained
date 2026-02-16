# AGI Stack: Comprehensive Repository Analysis & Technical Report (v18.0 + v19.0 + SH-1 + EUDRS-U)

**Report Version:** 2.1  
**Last Updated:** 2026-02-14  
**Analysis Scope:** Omega v18.0 + Omega v19.0 (axis ladder) + Genesis Engine SH-1 + CCAP Protocol + Authority System + EUDRS-U v1.0 (wired) + QXWMR canon/ML-index (submodule-implemented)

## 1. Executive Summary

This document serves as the definitive technical reference for the AGI Stack repository, specifically analyzing the **Omega v18.0** architecture with recent **SH-1 (Symbiotic Harmony v1)** enhancements. Unlike previous high-level overviews, this report is derived from a line-by-line analysis of the source code, ignoring outdated documentation to focus on the actual implemented logic.

The AGI Stack is a **Recursive Self-Improvement (RSI)** infrastructure built on a four-layer trust hierarchy. Its primary design goal is to allow an AI to rewrite its own source code and acquire new knowledge without human intervention, while mathematically guaranteeing that it cannot violate safety constraints. This is achieved through **Fail-Closed Verification**: every action, whether it is a move in a game or a patch to the Linux kernel, must be accompanied by a cryptographic proof of correctness that is verified by an isolated, trusted kernel.

### 1.1 Core Metric: The Deterministic Tick
The heartbeat of the system is the "Tick" (managed by `rsi_omega_daemon_v18_0`). A key finding of this analysis is that the tick is **recursively verifiable**. The `verify_rsi_omega_daemon_v1.py` script does not just check outputs; it *replays* the entire decision-making process using Q32 fixed-point arithmetic to ensure that the AI's "brain" is deterministic down to the bit level.

### 1.2 Key Architectural Components
*   **RE1 (Root of Trust)**: `meta-core`. A minimal Rust-based kernel that holds the "Reference Monitor". It allows changes to the system only if a valid "Promotion Bundle" is presented.
*   **RE2 (Certified Execution)**: `CDEL-v2`. The "Body". It runs the Omega Daemon, executes campaigns, and generates proofs. It is trusted to execute correctly but not to set policy.
*   **RE3 (Untrusted Proposer)**: `Extension-1`. The "Imagination". This layer (specifically `self_improve_code_v1`) generates candidate code patches. It is treated as potentially adversarial.
*   **RE4 (Specification)**: `Genesis`. The "Law". JSON schemas and protocols that define valid data shapes.

### 1.3 Scope and Limitations

**What This System IS:** A world-class Recursive Self-Improvement infrastructure with deterministic verification, fail-closed safety, and receipt-driven meta-learning capabilities.

**What This System IS NOT:** Artificial General Intelligence (AGI) or Artificial Superintelligence (ASI). While the system demonstrates sophisticated self-optimization within constrained domains, it lacks several critical capabilities for general intelligence, including:
- General-purpose deep learning stacks and unconstrained gradient-based optimization (the repo is heading toward deterministic QXRL-backed learning, but it is still substrate-style and promotion-gated rather than a full modern DL platform)
- Multimodal learning (vision, audio, sensor fusion)
- Real-world actuation beyond sandboxed filesystem
- Continual learning with knowledge transfer across domains
- Creative reasoning and autonomous problem formulation

**For a comprehensive analysis of capabilities and gaps to AGI/ASI**, see the companion document: [`AGI_Stack_Gap_Analysis_to_AGI_ASI.md`](./AGI_Stack_Gap_Analysis_to_AGI_ASI.md)

### 1.4 v19.0 Update (What Changed vs v18.0)
This repository now contains a second, more “proof-centric” Omega line: **Omega v19.0**. v18.0’s core loop already enforces deterministic replay and fail-closed verification, but v19.0 extends the promotion protocol into an explicit **axis / ladder** model intended to make “capability progress” measurable and auditable over many ticks.

At a high level:
*   **v18.0** is organized around “campaigns” that emit promotion bundles (or CCAP capsules) which meta-core can verify and activate. Evidence is primarily “this patch/candidate was verified and promoted”.
*   **v19.0** adds a second evidence channel: **axis upgrade bundles**. These bundles encode structured “morphisms” (typed capability transitions) and gate outcomes so the system can later answer: “What levels were actually attained, in real multi-tick runs, under promotion gating?”

The two versions are compatible in spirit: both keep the trust boundary unchanged (untrusted proposers propose; trusted verifiers verify; promoters package; meta-core activates). The difference is that v19 makes progress itself a first-class artifact, rather than an emergent property inferred from scattered run logs.

### 1.5 2026-02 Directional Shift: EUDRS-U + QXWMR + QXRL + ML-Index (Evidence-First Learning Substrate)
The repo has moved beyond “self-improve code + prove determinism” into an explicit, promotion-gated **learning + retrieval substrate** that is designed to be updated frequently without weakening RE1–RE4.

What is now implemented (RE2 + RE4) and wired (registries), even though default profiles keep it disabled:
*   **EUDRS-U v1.0 evidence contract:** campaigns MUST emit exactly one `eudrs_u_promotion_summary_v1.json` under `eudrs_u/evidence/` as the verifier entrypoint, pointing to all other evidence blobs (weights, ML-index, CAC/UFC, stability, determinism/universality certs).
*   **QXWMR canonicalization (v1):** WL-canonical, bounded typed-graph state with deterministic packing/unpacking and replay-verifiable choice traces.
*   **QXRL (v1):** deterministic training/eval/replay substrate (Q32 arithmetic + deterministic tie-breaking) intended to back representation learning inside the trust model.
*   **ML-index (Phase 3):** deterministic index manifests + merkle-verified bucket/page binaries, plus gate logic integrated into EUDRS-U promotion verification.

The key architectural move is “progress as content-addressed roots”: instead of treating “learning state” as an opaque runtime cache, the system treats it as a **registry tree** of CAS artifacts (manifests, binaries, roots) whose updates are promoted like code, with fail-closed replay verification.

---

## 2. Architecture & Unification Strategy

The repository is organized not just by module, but by trust domain. The unification strategy relies on **Strict Canonicalization (GCJ-1)** and **Content-Addressed Storage (CAS)** to ensure that every layer speaks the same mathematical language.

**Repo-normative constraints (AGENTS.md):**
*   **Trust boundary unchanged:** RE1–RE4 layering is treated as a hard invariant.
*   **Determinism substrate:** GCJ-1 canonical JSON (no floats), Q32 fixed-point ops in RE2, and replay verifiers are fail-closed.
*   **No ambiguity rules:** list ordering must be explicit; set-like lists must specify sort keys; paths are repo-relative POSIX; comparisons are bytewise with explicit tie-breaks.

### 2.1 The Trust Hierarchy (RE Layers)

#### RE1: meta-core (The Constitutional Kernel)
Located in `/meta-core`, this directory contains the absolute ground truth.
*   **`kernel/verifier` (Rust)**: This is the compiled binary that enforces the constitution. It links against `re2_authoritative_fail_closed_v1` to check regular expressions and signatures. It is the only component trusted to emit a "Commit" signal.
*   **`engine/`**: Python orchestration for the "Commit" phase. It manages the atomic swap of the `active` system pointer.
*   **`store/`**: Content-Addressed Storage (CAS) for all historical system states.

#### RE2: CDEL-v2 (The Certifiable Body)
Located in `/CDEL-v2`, this contains the bulk of the logic.
*   **`cdel/v18_0/`**: The massive monolithic library for the Omega Daemon.
    *   `omega_decider_v1.py`: The policy engine (The "Brain").
    *   `verify_rsi_omega_daemon_v1.py`: The recursive verifier (The "Conscience").
    *   `omega_observer_v1.py`: The sensory interface.
    *   `eudrs_u/`: Deterministic EUDRS-U/QXWMR/QXRL/ML-index substrate + fail-closed promotion/run verifiers.
*   **`campaigns/`**: Configuration packs that define specific capabilities (e.g., `rsi_sas_science_v13_0` for scientific discovery).

#### RE3: Extension-1 (The Proposer Engine)
Located in `/Extension-1`.
*   **`self_improve_code_v1/`**: The replacement for the legacy CAOE. It implements a multi-armed bandit framework to optimize the AGI's own source code parameters. It is untrusted; its outputs are treated as "Suggestions" until verified.
*   **`agi-orchestrator/`**: High-level task management.

#### Polymath (The Cortex)
Integrated into CDEL logic but conceptually distinct, `polymath` manages the Knowledge Graph.
*   **`campaign_polymath_conquer_domain_v1.py`**: A deterministic solver engine (Naive Bayes) that learns to solve tasks in new domains (e.g., Chemistry, Physics).

### 2.2 Unification: The Bundle Protocol

These diverse systems unify via **Promotion Bundles**.
1.  **Extension-1** proposes a change (e.g., "Change the learning rate to 0.01").
2.  **CDEL** executes it in a sandbox and measures performance (e.g., "Accuracy improved by 0.5%").
3.  **CDEL** wraps the result in a `sas_science_promotion_bundle_v1.json` (or similar).
4.  **meta-core** verifies the bundle's signature and proof (e.g., "The improvement is statistically significant and the sandbox was secure").
5.  If valid, **meta-core** updates the `active` pointer, unifying the proposal into reality.

In the newer EUDRS-U direction, the promoted unit is often a **root tuple** (`eudrs_u_root_tuple_v1`) that points into a content-addressed registry tree (weights, indices, manifests). This keeps “frequently updated learning state” out of RE1/RE2 code prefixes while remaining promotion-gated and replay-verifiable.

### 2.3 Omega v19.0: Axis Bundles, Gates, and “Level Climb” Evidence
Omega v19.0 introduces a “ladder” perspective: in addition to “did we promote something”, the system also asks “what *kind* of advancement occurred”, and requires the run artifacts to carry enough structure to support deterministic, audit-friendly claims.

#### 2.3.1 The Core Object: `axis_upgrade_bundle_v1.json`
In v19, a successful promotion is typically accompanied by an **axis upgrade bundle**. Conceptually, it is an append-only “capability step” record:
*   It identifies the promoted candidate (or the promoted subrun) and ties it to deterministic inputs (bundle hashes, run/tick identifiers).
*   It records **morphism types** (think: “the kind of improvement that occurred”) rather than treating the promotion as an opaque event.
*   It includes, or is paired with, **gate evidence** so that the same bundle can be replay-verified.

This is deliberately not a new acceptance path. An axis bundle does not “grant authority”; it only provides structured evidence that something promoted satisfies higher-level invariants.

#### 2.3.2 Gates Become First-Class: `axis_gate_failure_v1.json`
v18 already has fail-closed verifiers and detailed rejection reasons, but the semantics are campaign-specific. v19 standardizes a piece of that vocabulary into an axis gate record:
*   Gates can represent “world/treaty” policy (for example, allowed touch sets and treaty constraints).
*   A promotion can be tagged with “PROMOTED” only if all required gates pass; otherwise gate outcomes are recorded as failures with explicit reasons.

This makes it possible to compute robust summary statistics over many ticks, without reverse-engineering individual campaign verifiers.

#### 2.3.3 Promotion/Subverifier Must Run from the Subrun CWD (A Real-Run Wiring Fix)
A practical v19 detail: promotion-gate code frequently resolves referenced artifacts via `Path('.').resolve()` or relative bundle paths. In harnesses, it is tempting to monkeypatch CWD, but in a real daemon loop the orchestrator must do it correctly:
*   When a tick dispatch creates a subrun, the coordinator records `subrun_root_abs`.
*   When running `run_subverifier(...)` and `run_promotion(...)`, the orchestrator must `chdir(subrun_root_abs)` so relative artifact references in axis bundles resolve correctly.
*   This is a determinism issue (the verifier must “see” the same filesystem layout during replay) and a correctness issue (bundle resolution fails if CWD is wrong).

In other words, v19 “level evidence” only works if the subrun is treated as the canonical working directory during verification/promotion.

#### 2.3.4 From “Morphisms Exist” to “Morphisms Occur”
The v19 ladder is intentionally stronger than “there is code for morphisms”. The system needs **multi-tick evidence** that morphisms are actually being produced and promoted. Practically, this requires:
*   A daemon loop that runs for multiple ticks and actually dispatches subruns that can emit axis bundles.
*   A post-run report that scans the produced artifacts and computes:
    *   how many promotions occurred,
    *   how many promotions produced axis bundles,
    *   which morphism types appeared in promoted bundles,
    *   what maximum ladder level was attained (under a monotone coverage rule).

This is the bridge from “unit tests and harness proofs” to “real run evidence”. The goal is not to relax constraints; it is to force the system to produce auditable artifacts that a third party can replay-check.

#### 2.3.5 How v19 Coexists with v18
v19 does not replace v18’s campaigns and promotion machinery. Instead:
*   v18 continues to execute domain campaigns (science, system, metasearch, polymath) and emit promotion bundles / CCAP capsules.
*   v19 wraps the same reality into a more standardized evidence layer, improving the *observability* and *auditability* of progress across ticks.

This approach preserves the core trust boundary: promotion is still gated by verifiers and meta-core, but we now additionally get a canonical answer to “what levels did the system reach” without relying on narrative summaries.

#### 2.3.6 Determinism Requirements in v19: Canonical JSON + Content Addressing + Replay
The axis system only works if the bundles are stable across replays. v19 therefore leans heavily on the same foundational primitives already present in v18:
*   **Canonical JSON**: When writing a bundle or report, keys are ordered and serialization is consistent. This ensures the same semantic object hashes to the same bytes.
*   **Content-addressed artifacts**: Many artifacts are named with `sha256_...` prefixes; a bundle is both a record and a stable pointer to referenced evidence blobs.
*   **Replay-first verification**: A verifier does not “trust the daemon’s story”; it recomputes from disk artifacts and fails closed if any mismatch occurs (including mismatched hashes or missing referenced blobs).

In practice, this means that an axis bundle is not just a “status record”. It is a compact dependency graph: it points to the gate proof(s), the promotion receipts, and the underlying run artifacts that justify the claim “this morphism occurred and was promoted”.

#### 2.3.7 The v19 Daemon Loop: Tick Roots, Subruns, and Evidence Placement
v19 keeps the same conceptual tick model but standardizes the filesystem layout around “subruns as evidence roots”. A typical v19 tick will:
1.  Create a tick directory (or a formatted output directory) that is stable and predictable.
2.  Dispatch one or more subruns, each with its own `subrun_root_abs`.
3.  Run the subverifier and promoter against that subrun root.
4.  Emit:
    *   per-subrun verifier receipts and promotion receipts,
    *   axis bundles and gate outcomes (or failures),
    *   a tick outcome summary that can be replay-verified.

This is why the coordinator CWD matters: when the subverifier and promoter execute, “relative artifact references” must resolve against the subrun’s root, not against the repository root or the daemon root.

#### 2.3.8 “Level Attainment” as a Derived Artifact, Not a Runtime Decision
An important design choice in v19 is that “what level was achieved” is computed by scanning artifacts after the fact, not by a single in-loop assertion.

This keeps the trust boundary clean:
*   The daemon loop is still an executor and artifact emitter.
*   The ladder report is a deterministic post-processor that reads promoted axis bundles and gate outcomes and computes a summary.
*   If the summary is wrong, a replay-verifier can recompute it from the same promoted bundles.

This also avoids a subtle failure mode: if “max level achieved” were computed inside the loop and used to make policy decisions, it would become an implicit authority channel. Instead, level attainment is treated as audited telemetry.

---

## 3. detailed Analysis: CDEL-v2 (Omega v18.0)

This section provides a deep code-level analysis of the `CDEL-v2/cdel/v18_0` directory, which constitutes the active runtime of the AGI.

### 3.1 The Observer (`omega_observer_v1.py`)
The Observer is responsible for collapsing the chaotic state of the filesystem into a single, deterministic JSON object: the `omega_observation_report_v1`.

**Key Functionality:**
*   **Path Canonicalization**: It scans `runs/` and `campaigns/` using strict globs. It specifically looks for `sha256_*.json` files, enforcing the content-addressed naming convention.
*   **Metric Aggregation**: It reads specific sub-verifier reports.
    *   `metasearch_compute_report_v1`: Reads `c_base_work_cost_total` vs `c_cand_work_cost_total`.
    *   `kernel_hotloop_report_v1`: Quantifies where the system is spending CPU time.
*   **Temperature Computing**: It calculates `brain_temperature_q32`. This is a Q32 fixed-point number derived from `promotion_success_rate` and `activation_denied_rate` (as seen in `verify_rsi_omega_daemon_v1.py`). If the system is failing often, the temperature drops (freezing new risky behaviors). If it is succeeding, temperature rises (allowing exploration).

### 3.2 The Decider (`omega_decider_v1.py`)
This is the most complex decision logic in the repository. It is a pure function: `(State, Observation, Policy) -> Decision`.

**Logic Flow:**
1.  **Safety Checks**: First, it validates `policy_hash` and `registry_hash`. If they don't match the known good state, it returns `SAFE_HALT`.
2.  **Temperature Banding**: Calls `_temperature_band()` to convert the Q32 temperature into `LOW`, `MID`, or `HIGH`.
3.  **Runaway Mode (`_runaway_decision`)**:
    *   If enabled, it checks `metric_states`.
    *   It calculates the gap between `current_target_q32` and `last_value_q32`.
    *   If the gap is large, it triggers `RUNAWAY_CAND` actions, effectively prioritizing self-improvement over everything else.
    *   It manages `escalation_level_u64`. If a metric isn't moving, it escalates the intensity of the campaign (e.g., allocating more compute).
4.  **Goal Prioritization (`_goal_class_rank`)**:
    *   If `LOW` temperature (system unstable): Priorities are `CORE_SELF_OPT` > `SAFE` > `FLOOR` > `EXPLORE`.
    *   If `HIGH` temperature (system stable): Priorities shift to allow more `EXPLORE` tasks.
5.  **Tie Breaking**: The code maintains a `tie_break_path` list. Every time it makes a choice (e.g., skipping a campaign due to cooldown), it appends a string like `SKIP:campaign_id:COOLDOWN`. This ensures that the verifier can reproduce the exact logic path.

### 3.3 The Failure-Closed Verifier (`verify_rsi_omega_daemon_v1.py`)
This script acts as the "Super-ego". It is invoked *after* the tick to prove that the Daemon didn't hallucinate.

**Technical Deep Dive:**
*   **Replay**: It calls `_recompute_observation_from_sources`. This function literally re-reads the disk artifacts and re-sums the Q32 metrics. If the Daemon reported a temperature of `0.5` but the disk says `0.499`, verification fails (Fail-Closed).
*   **Bit-Exact Math**: It uses `rat_q32` (rational to Q32 conversion) for all math. This avoids floating-point non-determinism.
*   **Sub-Verifier Dispatch**: It checks the schema of artifacts. If it sees `metasearch_compute_report_v1`, it knows to check `c_base_work_cost_total`.
*   **Forbidden Paths (`_verify_forbidden_paths`)**: It explicitly checks that the Daemon did not touch files outside its sandbox. It reads the `touched_paths` from the bundle and asserts they are in the `allowlist` (loaded via `load_allowlists`).

### 3.4 The Domain Conqueror (`campaign_polymath_conquer_domain_v1.py`)
This script is a fascinating example of "AI doing Science". It is a generic solver for classification tasks.

**Algorithms:**
*   **Naive Bayes**: Implements a scratch-built Naive Bayes classifier (`_nb_predict_with_config`).
*   **Feature Engineering**: It automatically tries different tokenizers:
    *   `smiles_char_unigram`: For chemistry (SMILES strings).
    *   `text_word_unigram`: For natural language.
    *   `text_char_trigram`: For dense text analysis.
*   **Search**: It iterates through `alpha` (smoothing parameter) values `[0.5, 1.0, 2.0]` to find the best configuration for a given dataset.
*   **Shadow Proposal**: Once it finds the best model, it writes a python script (`_shadow_solver_source`) that hardcodes the model parameters and submits it as a solution. **The AI writes code to solve the problem.**

---

## 4. detailed Analysis: Extension-1 (Code Self-Improvement)

**RE3: Untrusted Proposer Layer**

This section describes `Extension-1/self_improve_code_v1/`, the active code rewriting engine. This replaces the deprecated CAOE.

### 4.1 Orchestrator (`run.py`)
This script coordinates the entire "mutation" process for the AI's own codebase.

**Key Features:**
*   **Workspace Creation**: Uses `git_archive_v1` to clone the target repository into a clean, isolated workspace (`ws_baseline`, `ws_{idx}`). This ensures no existing state contaminates the measurement.
*   **Arms Configuration**: It loads "Arm" definitions from `targets/arms_v1.json`. An Arm defines a specific file and token selector (e.g., `omega_policy_ir_v1.py` line 50) that is allowed to be modified.
*   **Search**: It calls `schedule_candidates` to decide *what* values to try.
    *   It uses a Bandits algorithm (`beta`, `bonus0`) to explore the configuration space.
    *   It generates patches (`unified_diff`) for each candidate.
*   **Devscreen Validation**: Each candidate is immediately run through `run_devscreen`. This is a "Unit Test on Steroids".
    *   It spins up the patched code and runs existing test suites.
    *   It measures `m_bp` (Metric Basis Points) to see if performance improved.
    *   It calculates reward based on improvement minus cost (`patch_bytes` + `test_runs`).
*   **Selection**: The best performing candidate is packaged into a tarball (`selected_candidate.tar`) and formally submitted to CDEL (`run_cdel`).

**Technical Insight:**
The system distinguishes between "Candidate ID" (untrusted) and "Manifest ID" (trusted). `build_manifest` generates a `candidate_id` based on the content hash of the patch, ensuring deduplication.

### 4.2 Search Logic
The `schedule_candidates` function (inferred from `run.py` usage of `search/schedule_v1`) implements the exploration strategy.
*   **Exploitation**: Heavily weight configurations that have historically yielded high rewards.
*   **Exploration**: Add a "Bonus" to rarely-visited configurations to prevent getting stuck in local optima.
*   **Budgeting**: Respects `budget_candidates` to prevent burning infinite compute.

---

## 5. Folder-by-Folder Reference

### 5.1 Genesis (RE4)
*   `schema/`: The definitive JSON schemas (`.json`) for data interoperability.
*   `docs/`: Normative protocol documents (e.g., `evaluate_protocol.md`).

### 5.2 meta-core (RE1)
*   `kernel/`: Rust source for the verifier.
*   `active/`: Symlink to the currently active constitution.
*   `store/`: The history of all "Commits".

### 5.3 CDEL-v2 (RE2)
*   `cdel/`: The core library code.
*   `campaigns/`: Defines "What" the AGI can do (Science, System Opt, Kernel Opt).

### 5.4 Extension-1 (RE3)
*   `self_improve_code_v1/`: The "Mutator".
*   `agi-orchestrator/`: The "Task Manager".

### 5.5 daemon
*   Where the persistent process lives. It maintains `state/` files like `omega_state_v1.json` which persists across ticks.

### 5.6 runs
*   The output directory. Each `run_id` gets a folder here.
*   `artifacts/`: The actual products (patches, models).
*   `logs/`: Execution logs.

### 5.7 tools
*   `omega/`: Helper scripts for manual interaction.
*   `polymath/`: Legacy tools for domain management.
*   `v19_runs/`: v19 evidence runners and post-processors (full-loop runner, gate/benchmark harnesses, level-attainment reports).

### 5.7.1 docs (selected)
*   `docs/eudrs_u/`: EUDRS-U scientist handoff + spec-outline scaffolding tied to the repo’s trust/determinism constraints.

### 5.8 scripts
*   Bootstrap and maintenance scripts (e.g., `generate_deep_dive.py`).

---

## 6. detailed Analysis: Data Flows & Protocols

### 6.1 The Tick Lifecycle (Step-by-Step)
1.  **State Init**: `rsi_omega_daemon_v18_0` starts. Loads `omega_state_v1.json`. Tick counter increments.
2.  **Observation**: `observer` scans `runs/`. Finds `sha256_abc...metasearch_compute_report_v1.json`. Calculates aggregated metrics.
3.  **Diagnosis**: `diagnoser` checks for regressions using `omega_diagnoser_v1.py` (inferred).
4.  **Decision**: `decider` sees temperature is HIGH. Picks `GOAL_EXPLORE`. Ties broken by alphabetic sort of campaign IDs.
5.  **Execution**: `executor` launches `rsi_polymath_scout_v1`.
6.  **Scout Run**: `scout` explores `polymath/registry/`. Finds a gap in Chemistry knowledge. Returns a `void_report`.
7.  **Verification**: Daemon post-verifies the Scout's output.
8.  **Commit**: Daemon signs the `omega_observation_report` and commits to `meta-core`.

### 6.2 The Patch Lifecycle
1.  **Ideation**: `Extension-1` wakes up. Checks `arms_v1.json`. Sees it can change the "Timeout" in `omega_common_v1.py`.
2.  **Experiment**: Tries changing `10s` to `12s`. In the sandbox, this causes fewer network timeouts.
3.  **Verification**: `devscreen` reports `+50bps` improvement.
4.  **Proposal**: `run.py` packages `patch.diff`. Submits `selected_candidate.tar`.
5.  **Certification**: `CDEL` receives the tarball. Unleashes the `verify_rsi_omega_daemon_v1.py` on it. Checks signatures.
6.  **Merger**: If verified, `meta-core` accepts the patch. The next Tick will use `12s` timeouts.

---

## 7. Deep Technical Analysis: Q32 Fixed-Point Arithmetic & Determinism

### 7.1 The Q32 Number System

One of the most critical architectural decisions in the AGI Stack is the use of **Q32 fixed-point arithmetic** for all metric calculations. This is not merely an optimization—it is a **correctness requirement** for the verification system.

**Q32 Format Specification:**
- **Representation**: A Q32 number is a 64-bit signed integer where the lower 32 bits represent the fractional part.
- **Range**: Can represent values from approximately -2,147,483,648.0 to +2,147,483,647.999999999767
- **Precision**: 2^-32 ≈ 0.00000000023283064365386962890625 (about 9 decimal digits)
- **Constant**: `Q32_ONE = 1 << 32 = 4294967296` represents the value 1.0

**Core Operations** (from `omega_common_v1.py`):

```python
def q32_int(value: Any) -> int:
    """Extract Q32 integer from dict or direct value."""
    if isinstance(value, dict):
        return int(value.get("q", 0))
    return int(value)

def rat_q32(numerator: int, denominator: int) -> int:
    """Convert rational to Q32 with exact rounding."""
    if denominator <= 0:
        fail("SCHEMA_FAIL")
    return (int(numerator) * Q32_ONE) // int(denominator)

def q32_mul(a_q32: int, b_q32: int) -> int:
    """Multiply two Q32 numbers."""
    return (int(a_q32) * int(b_q32)) // Q32_ONE

def cmp_q32(a: Any, b: Any) -> int:
    """Compare two Q32 values (-1, 0, or 1)."""
    a_q = q32_int(a)
    b_q = q32_int(b)
    if a_q < b_q:
        return -1
    if a_q > b_q:
        return 1
    return 0
```

### 7.2 Why Q32 Matters: The Determinism Guarantee

The verifier (`verify_rsi_omega_daemon_v1.py`) **replays** every calculation the Daemon performed. If the Daemon used floating-point arithmetic, the verifier might get different results due to:
- **Rounding mode differences** (x87 vs SSE vs ARM)
- **Compiler optimizations** (FMA instructions, expression reordering)
- **Library version differences** (numpy, math library implementations)

With Q32:
- **Bit-exact reproducibility**: `(3 * Q32_ONE) // 2 = 6442450944` on every platform, every time
- **Commutative operations**: Addition and multiplication are associative in Q32 (within 64-bit bounds)
- **Verifiable rounding**: Division always rounds toward zero (C99 semantics)

**Example from `omega_observer_v1.py`:**
```python
def _rate_from_stats(payload: dict[str, Any], key: str) -> int:
    """Calculate success rate in Q32."""
    total = int(payload.get(f"{key}_total_u64", 0))
    if total <= 0:
        return 0
    success = int(payload.get(f"{key}_success_u64", 0))
    return rat_q32(success, total)  # Exact Q32 conversion
```

The verifier can re-execute this function with the same inputs and **prove** the Daemon didn't hallucinate the success rate.

### 7.3 Temperature Calculation: The Brain's Thermostat

The **brain temperature** (`brain_temperature_q32`) is a Q32 metric that controls the Daemon's risk tolerance. It is calculated from two rates:

**Formula** (from `omega_temperature_v1.py`):
```python
def compute_temperature_q32(
    promotion_success_rate_q32: int,
    activation_denied_rate_q32: int,
) -> int:
    """Compute brain temperature from promotion and denial rates."""
    # Base temperature from success rate
    temp = promotion_success_rate_q32
    
    # Penalty for denials (system instability)
    penalty = q32_mul(activation_denied_rate_q32, Q32_ONE // 2)
    temp = max(0, temp - penalty)
    
    # Clamp to [0, 1]
    return min(Q32_ONE, max(0, temp))
```

**Temperature Bands** (from `omega_decider_v1.py`):
- **LOW** (< 0.33): System is unstable. Prioritize `CORE_SELF_OPT` goals (fix yourself first).
- **MID** (0.33 - 0.66): Balanced mode. Mix of optimization and exploration.
- **HIGH** (> 0.66): System is stable. Allow `EXPLORE` goals (try risky new things).

**Decision Impact:**
```python
def _goal_class_rank(goal_class: str, temp_band: str) -> int:
    """Rank goal classes by priority given temperature."""
    if temp_band == "LOW":
        priorities = {"CORE_SELF_OPT": 0, "SAFE": 1, "FLOOR": 2, "EXPLORE": 3}
    elif temp_band == "HIGH":
        priorities = {"EXPLORE": 0, "CORE_SELF_OPT": 1, "SAFE": 2, "FLOOR": 3}
    else:  # MID
        priorities = {"CORE_SELF_OPT": 0, "SAFE": 1, "EXPLORE": 2, "FLOOR": 3}
    return priorities.get(goal_class, 99)
```

This creates a **homeostatic feedback loop**: if the system breaks itself (low temperature), it stops exploring and focuses on self-repair.

---

## 8. Deep Technical Analysis: The Verifier Architecture

### 8.1 The Replay Mechanism

The verifier (`verify_rsi_omega_daemon_v1.py`) is a **1334-line proof engine** that re-executes the Daemon's decision-making process. It operates in two modes:

**Mode 1: Full Verification** (default)
- Re-reads all disk artifacts referenced in the observation report
- Recalculates all Q32 metrics from source data
- Replays the decision logic with the same inputs
- Compares the replayed decision to the claimed decision
- Invokes sub-verifiers for promoted campaigns
- Checks forbidden path access

**Mode 2: Quick Verification** (`mode="quick"`)
- Skips artifact re-reading
- Trusts observation report hashes
- Only verifies decision logic consistency
- Used for rapid iteration during development

### 8.2 Observation Re-computation

The `_recompute_observation_from_sources` function (lines 528-777) is the heart of the verifier. It:

**Step 1: Load Source Artifacts**
```python
def _read_observer_source_artifact(*, root: Path, source: dict[str, Any]) -> dict[str, Any]:
    """Read and validate a source artifact from disk."""
    schema_id = str(source.get("schema_id"))
    artifact_hash = str(source.get("artifact_hash"))
    
    # Find the artifact file using content-addressed naming
    suffix = _OBS_SOURCE_SUFFIX[schema_id]
    path = _find_nested_hash(root, artifact_hash, suffix)
    
    # Load and validate schema
    payload = load_canon_dict(path)
    validate_schema(payload, schema_id)
    
    # Verify hash matches
    actual_hash = canon_hash_obj(payload)
    if actual_hash != artifact_hash:
        fail("NONDETERMINISTIC")
    
    return payload
```

**Step 2: Extract Metrics**
```python
def _metric_from_observer_source(schema_id: str, payload: dict[str, Any]) -> int:
    """Extract Q32 metric from artifact payload."""
    if schema_id == "metasearch_compute_report_v1":
        base_cost = int(payload.get("c_base_work_cost_total", 0))
        cand_cost = int(payload.get("c_cand_work_cost_total", 0))
        if base_cost <= 0:
            return 0
        # Speedup ratio in Q32
        return rat_q32(base_cost - cand_cost, base_cost)
    
    elif schema_id == "kernel_hotloop_report_v1":
        # Extract hotloop percentage
        return int(payload.get("hotloop_fraction_q32", 0))
    
    # ... (other schema types)
```

**Step 3: Aggregate into Observation Report**
```python
# Rebuild metrics dictionary
recomputed_metrics = {}
for source in observation_payload.get("sources", []):
    schema_id = source["schema_id"]
    artifact = _read_observer_source_artifact(root=root, source=source)
    metric_value = _metric_from_observer_source(schema_id, artifact)
    recomputed_metrics[schema_id] = {"q": metric_value}

# Compare to claimed metrics
claimed_metrics = observation_payload.get("metrics", {})
for key, claimed_value in claimed_metrics.items():
    recomputed_value = recomputed_metrics.get(key, {"q": 0})
    if q32_int(claimed_value) != q32_int(recomputed_value):
        fail("NONDETERMINISTIC")
```

### 8.3 Decision Replay

After verifying the observation, the verifier replays the decision:

```python
# Load the decision inputs
decision_payload = load_canon_dict(state_root / "decision" / "omega_decision_v1.json")

# Extract the claimed decision
claimed_plan = decision_payload.get("plan", {})
claimed_tie_break_path = claimed_plan.get("tie_break_path", [])

# Replay the decision with the same inputs
from .omega_decider_v1 import decide

replayed_plan = decide(
    tick_u64=tick_u64,
    state=state_payload,
    observation_report_hash=observation_hash,
    issue_bundle_hash=issue_bundle_hash,
    observation_report=observation_payload,
    issue_bundle=issue_bundle_payload,
    policy=policy_payload,
    policy_hash=policy_hash,
    registry=registry_payload,
    registry_hash=registry_hash,
    budgets_hash=budgets_hash,
    goal_queue=goal_queue_payload,
    objectives=objectives_payload,
    runaway_cfg=runaway_cfg_payload,
    runaway_state=runaway_state_payload,
)

# Compare tie-break paths (determinism proof)
if replayed_plan["tie_break_path"] != claimed_tie_break_path:
    fail("NONDETERMINISTIC")
```

The **tie-break path** is a list of strings like `["SKIP:campaign_A:COOLDOWN", "SELECT:campaign_B:PRIORITY"]` that records every branching decision. If the verifier's path differs, the Daemon is non-deterministic.

### 8.4 Sub-Verifier Dispatch

If the Daemon promoted a campaign's output, the verifier invokes a **sub-verifier**:

```python
def _replay_promoted_subverifier(
    *,
    state_root: Path,
    dispatch_payload: dict[str, Any] | None,
    subverifier_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    """Replay a sub-verifier for a promoted campaign."""
    campaign_id = dispatch_payload["campaign_id"]
    
    # Map campaign to verifier module
    verifier_map = {
        "rsi_sas_metasearch_v16_1": "cdel.v16_1.verify_rsi_sas_metasearch_v1",
        "rsi_sas_science_v13_0": "cdel.v13_0.verify_rsi_sas_science_v1",
        "rsi_polymath_conquer_domain_v1": "cdel.v18_0.verify_rsi_polymath_domain_v1",
        # ... (56 total campaigns)
    }
    
    verifier_module = verifier_map.get(campaign_id)
    if not verifier_module:
        fail("MISSING_VERIFIER")
    
    # Run the sub-verifier in a subprocess
    result = _run_subverifier_replay_cmd(
        state_root=state_root,
        verifier_module=verifier_module,
        state_arg=str(subrun_state_dir),
        replay_state_dir=str(subrun_state_dir),
    )
    
    # Check sub-verifier verdict
    if result["verdict"] != "PASS":
        fail("SUBVERIFIER_FAIL")
    
    return result
```

This creates a **recursive verification tree**: the Omega verifier calls campaign verifiers, which may call their own sub-verifiers (e.g., Polymath verifier calls domain-specific verifiers).

### 8.5 Forbidden Path Enforcement

The verifier checks that the Daemon didn't touch files outside its sandbox:

```python
def _verify_forbidden_paths(
    *,
    state_root: Path,
    promotion_receipt: dict[str, Any] | None,
    allowlists: dict[str, Any],
) -> None:
    """Verify no forbidden paths were touched."""
    if promotion_receipt is None:
        return
    
    touched_paths = promotion_receipt.get("touched_paths", [])
    campaign_id = promotion_receipt.get("campaign_id", "")
    
    # Load allowlist for this campaign
    allowlist_key = f"promotion_allowlist_{campaign_id}"
    allowed_patterns = allowlists.get(allowlist_key, [])
    
    for path_rel in touched_paths:
        allowed = False
        for pattern in allowed_patterns:
            if fnmatch.fnmatch(path_rel, pattern):
                allowed = True
                break
        
        if not allowed:
            fail("FORBIDDEN_PATH_ACCESS")
```

**Example Allowlist** (from `omega_allowlists_v1.py`):
```python
ALLOWLISTS = {
    "promotion_allowlist_rsi_sas_metasearch_v16_1": [
        "CDEL-v2/cdel/v16_1/*.py",
        "campaigns/rsi_sas_metasearch_v16_1/*",
        "!CDEL-v2/cdel/v16_1/verify_*.py",  # Cannot modify verifiers
    ],
}
```

This prevents a malicious campaign from modifying the verifier that checks it.

---

## 9. Deep Technical Analysis: Campaign Architecture

### 9.1 Campaign Registry Structure

The campaign registry (`omega_registry_v2.py`) defines all available capabilities. It is a JSON object with this schema:

```json
{
  "schema_version": "omega_capability_registry_v2",
  "registry_id": "sha256:...",
  "capabilities": [
    {
      "capability_id": "POLYMATH_CONQUER",
      "campaign_id": "rsi_polymath_conquer_domain_v1",
      "enabled": true,
      "orchestrator_module": "cdel.v18_0.campaign_polymath_conquer_domain_v1",
      "campaign_pack_rel": "campaigns/rsi_polymath_conquer_domain_v1/campaign_pack_v1.json",
      "state_dir_rel": "daemon/rsi_polymath_conquer_domain_v1/state",
      "goal_class": "EXPLORE",
      "cooldown_ticks_u64": 10,
      "budget_cost_q32": {"q": 429496729}  // 0.1 in Q32
    }
  ]
}
```

**Key Fields:**
- **`capability_id`**: Human-readable identifier (e.g., "POLYMATH_CONQUER")
- **`campaign_id`**: Unique versioned ID (e.g., "rsi_polymath_conquer_domain_v1")
- **`orchestrator_module`**: Python module to execute (e.g., "cdel.v18_0.campaign_polymath_conquer_domain_v1")
- **`campaign_pack_rel`**: Path to configuration JSON (relative to repo root)
- **`state_dir_rel`**: Where the campaign stores persistent state
- **`goal_class`**: Priority class ("CORE_SELF_OPT", "SAFE", "EXPLORE", "FLOOR")
- **`cooldown_ticks_u64`**: Minimum ticks between executions
- **`budget_cost_q32`**: Computational budget consumed per execution

### 9.2 Campaign Execution Lifecycle

When the Decider selects a campaign, the Executor (`omega_executor_v1.py`) orchestrates its execution:

**Phase 1: Workspace Isolation**
```python
# Create isolated execution workspace
exec_root_abs = repo_root() / ".omega_v18_exec_workspace" / f"{action_id}_{campaign_id}"
_remove_path(exec_root_abs)
exec_root_abs.parent.mkdir(parents=True, exist_ok=True)
```

**Phase 2: Environment Setup**
```python
# Pin PYTHONPATH to ensure reproducibility
pinned_pythonpath = ":".join([
    str(repo_root()),
    str(repo_root() / "CDEL-v2"),
    str(repo_root() / "Extension-1" / "agi-orchestrator"),
])

# Set deterministic environment
env = {
    "OMEGA_TICK_U64": str(tick_u64),
    "OMEGA_RUN_SEED_U64": str(run_seed_u64),
    "PYTHONPATH": pinned_pythonpath,
}
```

**Phase 3: Invocation**
```python
from orchestrator.common.run_invoker_v1 import run_module

run_result = run_module(
    py_module="cdel.v18_0.campaign_polymath_conquer_domain_v1",
    argv=["--campaign_pack", campaign_pack_rel, "--out_dir", out_dir_arg],
    cwd=repo_root(),
    output_dir=dispatch_dir,
    extra_env=env,
)
```

**Phase 4: Materialization**
```python
# Move workspace to permanent storage (atomic rename when possible)
subrun_root_abs = state_root / f"subruns/{action_id}_{campaign_id}"
try:
    exec_root_abs.rename(subrun_root_abs)  # Atomic on same filesystem
except OSError as exc:
    if exc.errno == errno.EXDEV:  # Cross-device link
        shutil.copytree(exec_root_abs, subrun_root_abs)
        _remove_path(exec_root_abs)
```

**Phase 5: Pruning**
```python
# Remove build artifacts to save space
for dirname in ["__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"]:
    for path in subrun_root_abs.rglob(dirname):
        _remove_path(path)
```

**Phase 6: Indexing**
```python
# Update observer index for fast artifact lookup
update_index_from_subrun_best_effort(
    campaign_id=campaign_id,
    subrun_root_abs=subrun_root_abs,
)
```

### 9.3 Campaign State Management

Each campaign maintains persistent state in `daemon/{campaign_id}/state/`. Example for Polymath:

```
daemon/rsi_polymath_conquer_domain_v1/state/
├── reports/
│   └── polymath_conquer_report_v1.json  # Last execution result
├── promotion/
│   ├── sas_science_promotion_bundle_v1.json  # Promotion request
│   └── omega_promotion_receipt_v1.json  # Promotion verdict
└── cache/
    └── domain_train_to_best.jsonl  # Cached solver configurations
```

**State Persistence Contract:**
- Campaigns **must not** modify state outside their `state_dir_rel`
- State **must** be deterministic (same inputs → same outputs)
- State **must** be content-addressed (filenames include SHA256 hashes)

### 9.4 Runaway Mode: Escalating Intensity

The **Runaway Mode** (`omega_runaway_v1.py`) allows the Daemon to dynamically adjust campaign parameters to meet objectives faster.

**Runaway State Schema:**
```json
{
  "schema_version": "omega_runaway_state_v1",
  "state_id": "sha256:...",
  "tick_u64": 42,
  "objective_set_hash": "sha256:...",
  "metric_states": {
    "metasearch_speedup_q32": {
      "current_target_q32": {"q": 2147483648},  // 0.5 in Q32
      "best_value_q32": {"q": 1717986918},      // 0.4 in Q32
      "last_value_q32": {"q": 1717986918},
      "last_improve_tick_u64": 35,
      "stall_ticks_u64": 7,
      "escalation_level_u64": 2,
      "tighten_round_u64": 5
    }
  },
  "campaign_intensity_levels": {
    "rsi_sas_metasearch_v16_1": 2
  }
}
```

**Escalation Logic:**
```python
def advance_runaway_state(
    *,
    prev_state: dict[str, Any],
    observation_report: dict[str, Any],
    decision_plan: dict[str, Any],
    runaway_cfg: dict[str, Any],
    objectives: dict[str, Any],
    tick_u64: int,
    promoted_and_activated: bool,
) -> dict[str, Any]:
    """Advance runaway state based on promotion outcome."""
    
    metric_states_next = {}
    for metric_id, prev_metric in prev_state["metric_states"].items():
        observed_q = _metric_q32(observation_report, metric_id)
        best_q = q32_int(prev_metric["best_value_q32"])
        
        # Check if we improved
        improved = promoted_and_activated and (observed_q < best_q)
        
        if improved:
            # Tighten target (make it harder)
            tighten_factor_q = q32_int(runaway_cfg["tighten_factor_q32"])
            current_target_q = q32_mul(observed_q, tighten_factor_q)
            escalation_level = 0  # Reset escalation
            stall_ticks = 0
        else:
            # No improvement: escalate if stalled
            stall_ticks = prev_metric["stall_ticks_u64"] + 1
            stall_window = runaway_cfg["stall_window_ticks_u64"]
            stall_after = runaway_cfg["stall_escalate_after_u64"]
            
            if stall_ticks >= (stall_window * stall_after):
                escalation_level = min(
                    runaway_cfg["max_escalation_level_u64"],
                    prev_metric["escalation_level_u64"] + 1
                )
                stall_ticks = 0
            else:
                escalation_level = prev_metric["escalation_level_u64"]
        
        metric_states_next[metric_id] = {
            "current_target_q32": {"q": current_target_q},
            "best_value_q32": {"q": best_q if not improved else observed_q},
            "escalation_level_u64": escalation_level,
            "stall_ticks_u64": stall_ticks,
        }
    
    return canonicalize_runaway_state({
        "metric_states": metric_states_next,
        "campaign_intensity_levels": updated_levels,
    })
```

**Intensity Table** (from `omega_runaway_config_v1.json`):
```json
{
  "per_campaign_intensity_table": {
    "rsi_sas_metasearch_v16_1": [
      {"level_u64": 0, "env_overrides": {"V16_MAX_DEV_EVALS": "100"}},
      {"level_u64": 1, "env_overrides": {"V16_MAX_DEV_EVALS": "500"}},
      {"level_u64": 2, "env_overrides": {"V16_MAX_DEV_EVALS": "2000"}},
      {"level_u64": 3, "env_overrides": {"V16_MAX_DEV_EVALS": "10000"}}
    ]
  }
}
```

At escalation level 3, the metasearch campaign gets 100x more compute budget to find optimizations.

---

## 10. Deep Technical Analysis: Promotion Bundle Protocol

### 10.1 Bundle Structure

A **Promotion Bundle** is the atomic unit of system evolution. It contains:

```
promotion_bundle_sha256_abc123.../
├── constitution.manifest.json       # Meta-core manifest
├── omega/
│   ├── omega_activation_binding_v1.json  # Binds bundle to Omega state
│   ├── policy_v1.json               # Updated policy (if changed)
│   ├── registry_v2.json             # Updated registry (if changed)
│   └── objectives_v1.json           # Updated objectives (if changed)
├── campaigns/
│   └── rsi_sas_metasearch_v16_1/
│       ├── campaign_pack_v1.json    # Campaign configuration
│       └── metasearch_optimizer_v1.py  # Updated campaign code
├── CDEL-v2/
│   └── cdel/v16_1/
│       └── metasearch_kernel_v1.py  # Updated kernel code
└── proofs/
    ├── omega_promotion_receipt_v1.json  # Promotion verdict
    ├── verify_rsi_sas_metasearch_v1_receipt.json  # Sub-verifier receipt
    └── test_results_v1.json         # Test suite results
```

### 10.2 Promotion Workflow

The Promoter (`omega_promoter_v1.py`) orchestrates the promotion process:

**Step 1: Sub-Verifier Execution**
```python
def run_subverifier(
    *,
    tick_u64: int,
    dispatch_ctx: dict[str, Any] | None,
) -> dict[str, Any]:
    """Run campaign-specific verifier on execution outputs."""
    
    if dispatch_ctx is None:
        return {"status": "SKIP", "reason": "NO_DISPATCH"}
    
    campaign_id = dispatch_ctx["campaign_entry"]["campaign_id"]
    subrun_state_dir = dispatch_ctx["subrun_root_abs"] / dispatch_ctx["campaign_entry"]["state_dir_rel"]
    
    # Map campaign to verifier
    verifier_module = _resolve_verifier_module(campaign_id)
    
    # Run verifier
    result = subprocess.run(
        [sys.executable, "-m", verifier_module, "--state-dir", str(subrun_state_dir)],
        capture_output=True,
        text=True,
        timeout=300,
    )
    
    # Parse verdict
    receipt_path = subrun_state_dir / "verify_receipt_v1.json"
    if not receipt_path.exists():
        return {"status": "FAIL", "reason": "MISSING_RECEIPT"}
    
    receipt = json.loads(receipt_path.read_text())
    if receipt.get("verdict") != "PASS":
        return {"status": "FAIL", "reason": receipt.get("reason", "UNKNOWN")}
    
    return {"status": "PASS", "receipt": receipt}
```

**Step 2: Promotion Bundle Construction**
```python
def _build_meta_core_promotion_bundle(
    *,
    out_dir: Path,
    campaign_id: str,
    source_bundle_hash: str,
) -> Path:
    """Build a meta-core promotion bundle from campaign outputs."""
    
    # Load the promotion request from campaign state
    promo_request_path = _find_promotion_bundle(dispatch_ctx)
    promo_request = json.loads(promo_request_path.read_text())
    
    # Extract touched paths
    touched_paths = promo_request.get("touched_paths", [])
    
    # Create bundle directory
    bundle_dir = out_dir / f"bundle_{source_bundle_hash[:8]}"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    
    # Copy modified files
    for path_rel in touched_paths:
        src = repo_root() / path_rel
        dst = bundle_dir / path_rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    
    # Generate manifest
    manifest = {
        "schema_version": "constitution_manifest_v1",
        "manifest_id": "sha256:...",
        "parent_bundle_hash": _active_manifest_hash(),
        "touched_paths": touched_paths,
        "campaign_id": campaign_id,
        "tick_u64": tick_u64,
    }
    
    (bundle_dir / "constitution.manifest.json").write_text(
        json.dumps(manifest, sort_keys=True, indent=2)
    )
    
    return bundle_dir
```

**Step 3: Meta-Core Verification**
```python
def _run_meta_core_promo_verify(
    *,
    out_dir: Path,
    bundle_dir: Path,
) -> dict[str, Any]:
    """Run meta-core's promotion verifier."""
    
    result = subprocess.run(
        [
            sys.executable,
            str(meta_core_root() / "kernel" / "verify_promotion_bundle.py"),
            "--bundle-dir", str(bundle_dir),
            "--out-json", str(out_dir / "meta_core_verify_out.json"),
        ],
        capture_output=True,
        timeout=600,
    )
    
    verdict_path = out_dir / "meta_core_verify_out.json"
    verdict = json.loads(verdict_path.read_text())
    
    if verdict.get("status") != "APPROVED":
        return {"status": "DENIED", "reason": verdict.get("reason", "UNKNOWN")}
    
    return {"status": "APPROVED", "verdict": verdict}
```

**Step 4: Promotion Receipt Generation**
```python
def run_promotion(
    *,
    tick_u64: int,
    dispatch_ctx: dict[str, Any] | None,
    subverifier_receipt: dict[str, Any] | None,
    allowlists: dict[str, Any],
) -> dict[str, Any]:
    """Generate promotion receipt after verification."""
    
    if subverifier_receipt is None or subverifier_receipt.get("status") != "PASS":
        return {
            "status": "NOT_PROMOTED",
            "reason": "SUBVERIFIER_FAIL",
        }
    
    # Build bundle
    bundle_dir = _build_meta_core_promotion_bundle(...)
    
    # Verify bundle
    meta_verdict = _run_meta_core_promo_verify(out_dir=out_dir, bundle_dir=bundle_dir)
    
    if meta_verdict.get("status") != "APPROVED":
        return {
            "status": "NOT_PROMOTED",
            "reason": "META_CORE_DENIED",
        }
    
    # Generate receipt
    receipt = {
        "schema_version": "omega_promotion_receipt_v1",
        "receipt_id": "sha256:...",
        "tick_u64": tick_u64,
        "campaign_id": campaign_id,
        "result": {
            "status": "PROMOTED",
            "bundle_hash": canon_hash_obj(bundle_manifest),
        },
        "subverifier_receipt_hash": canon_hash_obj(subverifier_receipt),
        "meta_core_verdict_hash": canon_hash_obj(meta_verdict),
    }
    
    return receipt
```

### 10.3 Activation: The Atomic Pointer Swap

The Activator (`omega_activator_v1.py`) performs the final step: making the bundle **live**.

**Activation Algorithm:**
```python
def run_activation(
    *,
    tick_u64: int,
    promotion_receipt: dict[str, Any] | None,
    healthcheck_suitepack: dict[str, Any],
    active_manifest_hash_before: str,
) -> tuple[dict, str, dict | None, str | None, str]:
    """Activate a promoted bundle via atomic pointer swap."""
    
    if promotion_receipt is None:
        return None, None, None, None, active_manifest_hash_before
    
    if promotion_receipt["result"]["status"] != "PROMOTED":
        return None, None, None, None, active_manifest_hash_before
    
    # Get bundle directory
    bundle_dir = Path(dispatch_ctx["meta_core_activation_bundle_dir"])
    
    # Verify parent hash matches current active
    parent_hex = _bundle_parent_hash(bundle_dir)
    active_hex = active_manifest_hash_before.split(":")[1]
    
    if parent_hex != active_hex:
        return _activation_fail("PARENT_MISMATCH")
    
    # Call meta-core apply
    result = subprocess.run(
        [
            sys.executable,
            str(meta_core_root() / "cli" / "meta_core_apply.py"),
            "--bundle-dir", str(bundle_dir),
        ],
        capture_output=True,
        timeout=60,
    )
    
    if result.returncode != 0:
        return _activation_fail("META_CORE_DENIED")
    
    # Read new active pointer
    after_hash = _active_manifest_hash(meta_core_root())
    
    if after_hash == active_manifest_hash_before:
        return _activation_fail("POINTER_SWAP_FAILED")
    
    # Run healthcheck
    health_ok, health_reasons = _healthcheck(state_root, healthcheck_suitepack)
    
    if not health_ok:
        # Rollback!
        subprocess.run([
            sys.executable,
            str(meta_core_root() / "cli" / "meta_core_rollback.py"),
            "--reason", "HEALTHCHECK_FAIL",
        ])
        final_hash = _active_manifest_hash(meta_core_root())
        return _activation_with_rollback(final_hash)
    
    # Success!
    return {
        "schema_version": "omega_activation_receipt_v1",
        "tick_u64": tick_u64,
        "before_active_manifest_hash": active_manifest_hash_before,
        "after_active_manifest_hash": after_hash,
        "activation_success": True,
        "pass": True,
    }, after_hash
```

**Healthcheck Mechanism:**
```python
def _healthcheck(state_root: Path, suitepack: dict[str, Any]) -> tuple[bool, list[str]]:
    """Verify system health after activation."""
    
    checks = suitepack.get("checks", [])
    reasons = []
    ok = True
    
    for check in checks:
        kind = check["kind"]
        target_rel = check["target_rel"]
        required = check.get("required", True)
        
        target = state_root / target_rel
        
        if kind == "FILE_EXISTS":
            passed = target.exists()
        elif kind == "HASH_MATCH":
            expected_hash = check["expected_hash"]
            passed = target.exists() and hash_file(target) == expected_hash
        else:
            passed = False
        
        if required and not passed:
            ok = False
            reasons.append(f"HEALTHCHECK_FAIL:{target_rel}")
    
    return ok, reasons
```

If the healthcheck fails, the system **automatically rolls back** to the previous bundle, ensuring fail-closed behavior.

---

## 11. Deep Technical Analysis: Polymath Knowledge Acquisition

### 11.1 The Polymath System Architecture

Polymath is the AGI Stack's **knowledge acquisition subsystem**. It operates in three phases:

**Phase 1: Scout** (`campaign_polymath_scout_v1.py`)
- Scans the domain registry for gaps in knowledge
- Identifies domains that are `ACTIVE` but not `conquered_b`
- Writes a `polymath_void_report_v1.jsonl` listing missing capabilities

**Phase 2: Bootstrap** (`campaign_polymath_bootstrap_domain_v1.py`)
- Downloads training/test data for a new domain
- Validates data integrity (SHA256 hashes)
- Marks domain as `ready_for_conquer`

**Phase 3: Conquer** (`campaign_polymath_conquer_domain_v1.py`)
- Trains a Naive Bayes classifier on the domain
- Searches for optimal hyperparameters (tokenizer, smoothing)
- Generates a **shadow solver** (standalone Python script)
- Submits the solver as a promotion bundle

### 11.2 The Conquer Algorithm (Detailed)

The Conquer campaign implements a **deterministic machine learning pipeline**:

**Step 1: Domain Selection**
```python
def _domain_selection_diagnostics(*, rows: list[dict[str, Any]], root: Path) -> dict[str, Any]:
    """Select the next domain to conquer."""
    
    eligible_domains = []
    skip_reasons = {"NOT_ACTIVE": 0, "CONQUERED": 0, "NOT_READY": 0}
    
    for row in sorted(rows, key=lambda r: r.get("domain_id", "")):
        domain_id = row["domain_id"]
        status = row.get("status", "")
        
        # Filter criteria
        if status != "ACTIVE":
            skip_reasons["NOT_ACTIVE"] += 1
            continue
        
        if row.get("conquered_b", False):
            skip_reasons["CONQUERED"] += 1
            continue
        
        if not row.get("ready_for_conquer", False):
            skip_reasons["NOT_READY"] += 1
            continue
        
        eligible_domains.append(row)
    
    # Deterministic selection (alphabetical)
    if eligible_domains:
        return eligible_domains[0]
    else:
        return None
```

**Step 2: Data Loading**
```python
# Load training and test data from content-addressed store
train_sha = domain_pack["tasks"][0]["split"]["train_sha256"]
test_sha = domain_pack["tasks"][0]["split"]["test_sha256"]

train_rows = json.loads(load_blob_bytes(sha256=train_sha, store_root=store_root))
test_rows = json.loads(load_blob_bytes(sha256=test_sha, store_root=store_root))
```

**Step 3: Hyperparameter Search**
```python
def _search_best_config(*, train_rows: list[dict[str, Any]], metric_id: str) -> dict[str, Any]:
    """Search for best Naive Bayes configuration."""
    
    # Split train into train/val (80/20 deterministic split)
    train_split, val_split = _split_train_val(train_rows)
    val_targets = [_target_binary(row) for row in val_split]
    
    # Determine candidate tokenizers based on data
    search_families = _candidate_token_families(train_rows)
    # Returns: ["smiles_char_unigram", "smiles_char_bigram"] for chemistry
    #          ["text_word_unigram", "text_char_trigram"] for NLP
    
    best = None
    for token_family in sorted(search_families):
        for alpha_f64 in (0.5, 1.0, 2.0):  # Laplace smoothing values
            # Train and evaluate
            val_preds, model_complexity = _nb_predict_with_config(
                train_rows=train_split,
                test_rows=val_split,
                token_family=token_family,
                alpha_f64=alpha_f64,
            )
            
            val_metric_q32 = _metric_q32(metric_id, val_preds, val_targets)
            
            candidate = {
                "config_id": f"{token_family}|alpha={alpha_f64:.1f}",
                "config": {
                    "token_family": token_family,
                    "alpha_num_u64": int(alpha_f64 * 10),
                    "alpha_den_u64": 10,
                },
                "val_metric_q32": val_metric_q32,
                "model_complexity_u64": model_complexity,
            }
            
            # Select best (highest metric, then lowest complexity, then alphabetical)
            if best is None or val_metric_q32 > best["val_metric_q32"]:
                best = candidate
            elif val_metric_q32 == best["val_metric_q32"]:
                if model_complexity < best["model_complexity_u64"]:
                    best = candidate
    
    return best
```

**Step 4: Naive Bayes Implementation**
```python
def _nb_predict_with_config(
    *,
    train_rows: list[dict[str, Any]],
    test_rows: list[dict[str, Any]],
    token_family: str,
    alpha_f64: float,
) -> tuple[list[int], int]:
    """Train and predict with Naive Bayes."""
    
    # Build vocabulary and class counts
    class_counts = {0: 0, 1: 0}
    token_counts = {0: {}, 1: {}}
    token_totals = {0: 0, 1: 0}
    vocab = set()
    
    for row in train_rows:
        label = _target_binary(row)
        class_counts[label] += 1
        
        for token in _tokenize(row, token_family):
            vocab.add(token)
            token_counts[label][token] = token_counts[label].get(token, 0) + 1
            token_totals[label] += 1
    
    # Predict on test set
    total_train = class_counts[0] + class_counts[1]
    majority = 1 if class_counts[1] >= class_counts[0] else 0
    vocab_size = len(vocab)
    
    predictions = []
    for row in test_rows:
        tokens = _tokenize(row, token_family)
        scores = {}
        
        for label in (0, 1):
            # Prior probability (with smoothing)
            prior = (class_counts[label] + alpha_f64) / (total_train + 2 * alpha_f64)
            score = math.log(prior)
            
            # Likelihood (with Laplace smoothing)
            denom = token_totals[label] + (alpha_f64 * vocab_size)
            for token in tokens:
                token_count = token_counts[label].get(token, 0)
                score += math.log((token_count + alpha_f64) / denom)
            
            scores[label] = score
        
        # Predict class with higher score
        if scores[1] > scores[0]:
            predictions.append(1)
        elif scores[0] > scores[1]:
            predictions.append(0)
        else:
            predictions.append(majority)  # Tie-break
    
    return predictions, vocab_size
```

**Step 5: Shadow Solver Generation**
```python
def _shadow_solver_source(*, train_sha: str, config_id: str, config: dict[str, Any]) -> str:
    """Generate standalone Python solver script."""
    
    config_json = json.dumps(config, sort_keys=True)
    
    return f'''#!/usr/bin/env python3
"""Deterministic shadow solver for polymath binary classification."""

import json
import math
from pathlib import Path
from tools.polymath.polymath_dataset_fetch_v1 import load_blob_bytes

_TRAIN_SHA256 = "{train_sha}"
_CONFIG = json.loads('{config_json}')

def predict(rows: list[dict]) -> list[int]:
    """Predict labels for input rows."""
    # Load training data from content-addressed store
    train_blob = load_blob_bytes(sha256=_TRAIN_SHA256)
    train_rows = json.loads(train_blob.decode("utf-8"))
    
    # Train Naive Bayes model
    # ... (same logic as _nb_predict_with_config)
    
    return predictions
'''
```

This generated solver is **completely standalone**—it embeds the training data hash and hyperparameters, making it reproducible forever.

**Step 6: Promotion**
```python
# Write shadow solver to promotion directory
solver_path = promotion_dir / "polymath_shadow_solver_v1.py"
solver_path.write_text(_shadow_solver_source(train_sha=train_sha, config_id=config_id, config=best_config))

# Create promotion bundle
promotion_bundle = {
    "schema_version": "sas_science_promotion_bundle_v1",
    "bundle_id": "sha256:...",
    "campaign_id": "rsi_polymath_conquer_domain_v1",
    "touched_paths": [
        f"polymath/solvers/{domain_id}_solver_v1.py",
        "polymath/registry/polymath_domain_registry_v1.json",  # Mark domain as conquered
    ],
    "test_results": {
        "test_accuracy_q32": test_accuracy_q32,
        "test_f1_q32": test_f1_q32,
    },
}

write_hashed_json(promotion_dir, "sas_science_promotion_bundle_v1.json", promotion_bundle)
```

### 11.3 Polymath Portfolio Management

The Portfolio (`polymath_portfolio_v1.py`) tracks all conquered domains:

```python
def conquer_entry(
    *,
    domain_id: str,
    solver_rel: str,
    test_accuracy_q32: int,
    test_f1_q32: int,
    config_id: str,
) -> dict[str, Any]:
    """Create a portfolio entry for a conquered domain."""
    
    return {
        "domain_id": domain_id,
        "status": "CONQUERED",
        "solver_rel": solver_rel,
        "metrics": {
            "test_accuracy_q32": {"q": test_accuracy_q32},
            "test_f1_q32": {"q": test_f1_q32},
        },
        "config_id": config_id,
        "conquered_at_utc": datetime.now(UTC).isoformat(),
    }
```

The portfolio is used by the Observer to calculate the `polymath_coverage_q32` metric:

```python
coverage_q32 = rat_q32(conquered_domains, total_active_domains)
```

This metric drives the Runaway Mode: if coverage is low, the system escalates Polymath campaigns.

---

## 12. Deep Technical Analysis: Meta-Core Constitutional Enforcement

### 12.1 The Constitutional Kernel

The meta-core kernel (`meta-core/kernel/verifier/`) is a **Rust-based trust anchor** that enforces immutable rules. It is the only component trusted to modify the `active` pointer.

**Key Rust Modules:**
- **`re2_authoritative_fail_closed_v1.rs`**: Regular expression matcher (fail-closed on invalid regex)
- **`signature_verify_v1.rs`**: Cryptographic signature verification (Ed25519)
- **`manifest_verify_v1.rs`**: Manifest schema validation
- **`bundle_apply_v1.rs`**: Atomic bundle application

**Verification Algorithm** (pseudo-Rust):
```rust
pub fn verify_promotion_bundle(bundle_dir: &Path) -> Result<VerifyVerdict, VerifyError> {
    // Load manifest
    let manifest = load_manifest(bundle_dir.join("constitution.manifest.json"))?;
    
    // Verify parent hash matches current active
    let active_hash = read_active_bundle_hash()?;
    if manifest.parent_bundle_hash != active_hash {
        return Ok(VerifyVerdict::Denied("PARENT_MISMATCH"));
    }
    
    // Verify all touched paths are in allowlist
    let allowlist = load_allowlist(&manifest.campaign_id)?;
    for path_rel in &manifest.touched_paths {
        if !allowlist_permits(path_rel, &allowlist) {
            return Ok(VerifyVerdict::Denied("FORBIDDEN_PATH"));
        }
    }
    
    // Verify signature (if required)
    if let Some(signature) = &manifest.signature {
        let pubkey = load_pubkey(&manifest.campaign_id)?;
        if !verify_ed25519(signature, &manifest_bytes, pubkey) {
            return Ok(VerifyVerdict::Denied("INVALID_SIGNATURE"));
        }
    }
    
    // Verify no verifier self-modification
    for path_rel in &manifest.touched_paths {
        if path_rel.starts_with("meta-core/kernel/") {
            return Ok(VerifyVerdict::Denied("KERNEL_SELF_MODIFY"));
        }
        if path_rel.contains("/verify_") {
            return Ok(VerifyVerdict::Denied("VERIFIER_SELF_MODIFY"));
        }
    }
    
    Ok(VerifyVerdict::Approved)
}
```

### 12.2 The Atomic Pointer Swap

The `meta_core_apply.py` script performs the activation:

```python
def apply_bundle(*, meta_core_root: Path, bundle_dir: Path) -> dict[str, Any]:
    """Apply a verified bundle to the active system."""
    
    # Load manifest
    manifest = json.loads((bundle_dir / "constitution.manifest.json").read_text())
    bundle_hash = canon_hash_obj(manifest)
    
    # Copy bundle to store
    store_dir = meta_core_root / "store" / "bundles" / bundle_hash
    if store_dir.exists():
        return {"verdict": "ALREADY_APPLIED"}
    
    shutil.copytree(bundle_dir, store_dir)
    
    # Atomic pointer swap (write new hash, then rename)
    active_dir = meta_core_root / "active"
    temp_pointer = active_dir / f"ACTIVE_BUNDLE.tmp.{os.getpid()}"
    final_pointer = active_dir / "ACTIVE_BUNDLE"
    
    temp_pointer.write_text(bundle_hash)
    temp_pointer.rename(final_pointer)  # Atomic on POSIX
    
    return {"verdict": "APPLIED", "bundle_hash": bundle_hash}
```

The rename operation is **atomic** on POSIX filesystems, ensuring the system is never in an inconsistent state.

### 12.3 Rollback Mechanism

If the healthcheck fails, the system rolls back:

```python
def rollback(*, meta_core_root: Path, reason: str) -> dict[str, Any]:
    """Rollback to the previous bundle."""
    
    # Read current active
    current_hash = (meta_core_root / "active" / "ACTIVE_BUNDLE").read_text().strip()
    
    # Load current manifest
    current_manifest = json.loads(
        (meta_core_root / "store" / "bundles" / current_hash / "constitution.manifest.json").read_text()
    )
    
    # Get parent hash
    parent_hash = current_manifest["parent_bundle_hash"]
    
    # Atomic pointer swap back to parent
    active_dir = meta_core_root / "active"
    temp_pointer = active_dir / f"ACTIVE_BUNDLE.tmp.{os.getpid()}"
    final_pointer = active_dir / "ACTIVE_BUNDLE"
    
    temp_pointer.write_text(parent_hash)
    temp_pointer.rename(final_pointer)
    
    return {
        "verdict": "ROLLED_BACK",
        "from_hash": current_hash,
        "to_hash": parent_hash,
        "reason": reason,
    }
```

This creates a **linked list of bundles** in the store, allowing the system to traverse its own history.

---

## 13. Deep Technical Analysis: Genesis Engine SH-1 Symbiotic Optimizer

### 13.1 Overview: Receipt-Driven Self-Improvement

The **Genesis Engine SH-1 (Symbiotic Harmony v1)** represents a major architectural evolution in the AGI Stack's self-improvement capabilities. Unlike previous optimization approaches that relied on direct metric observation, SH-1 implements a **receipt-driven** optimization strategy that learns from the historical outcomes of past campaigns.

**Key Innovation:** SH-1 analyzes the **promotion receipts** and **activation receipts** from previous Omega ticks to identify which code modifications led to successful promotions and which were rejected. This creates a feedback loop where the system learns not just what works, but *why* it works according to the verifier's criteria.

**Location:** `tools/genesis_engine/ge_symbiotic_optimizer_v0_3.py` (847 lines)

### 13.2 The Bucket Planning Algorithm

SH-1 uses a sophisticated **bucket-based planning** system to categorize potential code modifications by their expected impact:

**Bucket Categories** (from `ge_config_v1.json`):
```json
{
  "bucket_fracs_q32": {
    "HOTFIX": 1073741824,      // 0.25 in Q32 (25% of proposals)
    "INCREMENTAL": 2147483648,  // 0.50 in Q32 (50% of proposals)
    "EXPLORATORY": 1073741824   // 0.25 in Q32 (25% of proposals)
  }
}
```

**Bucket Semantics:**
- **HOTFIX**: Small, targeted changes to address known issues (e.g., fixing a cooldown parameter)
- **INCREMENTAL**: Medium-sized improvements to existing functionality (e.g., adjusting budget hints)
- **EXPLORATORY**: Larger, more speculative changes that test new approaches

### 13.3 PD (Promotion Density) and XS (eXploration Score) Metrics

The optimizer computes two key metrics from historical receipts:

**PD (Promotion Density):**
```python
def _target_stats_from_events(*, events: list[dict[str, Any]], allowed_targets: list[str]):
    """Extract promotion statistics from receipt events."""
    target_stats = {}
    
    for event in events:
        target_relpath = event.get("target_relpath", "")
        if target_relpath not in allowed_targets:
            continue
        
        # Count promotions vs rejections
        if event.get("promoted", False):
            target_stats[target_relpath]["promoted_u64"] += 1
        else:
            target_stats[target_relpath]["rejected_u64"] += 1
    
    # PD = promoted / (promoted + rejected)
    for target, stats in target_stats.items():
        total = stats["promoted_u64"] + stats["rejected_u64"]
        stats["pd_q32"] = rat_q32(stats["promoted_u64"], total) if total > 0 else 0
```

**XS (eXploration Score):**
```python
def _ranked_targets_for_bucket(*, bucket: str, allowed_targets: list[str], target_stats: dict):
    """Rank targets by exploration score for a given bucket."""
    
    def _stats(target: str):
        stats = target_stats.get(target, _empty_target_stats())
        promoted = stats["promoted_u64"]
        rejected = stats["rejected_u64"]
        total = promoted + rejected
        
        # XS balances exploitation (high PD) with exploration (low total attempts)
        if total == 0:
            return (999999, 0, target)  # Unexplored targets get highest priority
        
        pd_q32 = stats["pd_q32"]
        # Bonus for low attempt count (encourages exploration)
        exploration_bonus = max(0, 100 - total)
        
        # Combined score: high PD + exploration bonus
        xs_score = (pd_q32 >> 22) + exploration_bonus  # Convert Q32 to ~10-bit range
        
        return (-xs_score, total, target)  # Negative for descending sort
    
    ranked = sorted(allowed_targets, key=_stats)
    return ranked
```

**Interpretation:**
- **High PD, Low Total**: File has high success rate but few attempts → **Prime candidate**
- **Low PD, High Total**: File has been tried many times with poor results → **Avoid**
- **Zero Total**: File has never been modified → **Exploratory priority**

### 13.4 Template-Based Patch Generation

SH-1 supports three deterministic patch templates:

**Template 1: COMMENT_APPEND**
```python
def _build_comment_patch(*, target_relpath: str, marker: str, repo_root: Path):
    """Append a comment to a file (minimal, safe change)."""
    
    target_path = repo_root / target_relpath
    original_content = target_path.read_text()
    
    # Deterministic comment based on marker
    comment = f"# GE-SH1-{marker}: Optimization checkpoint\n"
    modified_content = original_content + comment
    
    # Generate unified diff
    return _build_unified_patch(
        target_relpath=target_relpath,
        before=original_content,
        after=modified_content,
    )
```

**Template 2: JSON_TWEAK_COOLDOWN**
```python
def _build_json_tweak_patch(*, target_relpath: str, marker: str, template_id: str, repo_root: Path):
    """Modify cooldown_ticks_u64 in campaign registry JSON."""
    
    target_path = repo_root / target_relpath
    payload = json.loads(target_path.read_text())
    
    # Find all cooldown paths in the JSON tree
    cooldown_paths = []
    _json_walk_cooldown_paths(payload, (), cooldown_paths)
    
    if not cooldown_paths:
        return None
    
    # Deterministic selection based on marker
    selected_path = cooldown_paths[hash(marker) % len(cooldown_paths)]
    
    # Apply deterministic delta
    current_value = _json_get(payload, selected_path)
    delta = _deterministic_delta(marker=marker, template_id=template_id, target_relpath=target_relpath)
    new_value = max(1, current_value + delta)
    
    _json_set(payload, selected_path, new_value)
    
    # Generate patch
    modified_content = json.dumps(payload, indent=2, sort_keys=True)
    original_content = target_path.read_text()
    
    return _build_unified_patch(
        target_relpath=target_relpath,
        before=original_content,
        after=modified_content,
    )
```

**Template 3: JSON_TWEAK_BUDGET_HINT**
```python
# Similar to cooldown tweak, but modifies budget_cost_hint_q32 values
# Delta is in Q32 format: ±(1 << 30) = ±0.25 in Q32
```

### 13.5 Hard-Avoid Projection

SH-1 implements a **novelty laundering** defense to prevent the optimizer from repeatedly proposing the same failed changes:

```python
def _hard_avoid_prefixes(snapshot: dict[str, Any]) -> set[str]:
    """Extract file prefixes that should be avoided based on recent failures."""
    
    hard_avoid = set()
    
    # Load recent refutation certificates (rejected CCAPs)
    for cert in snapshot.get("refutation_certs", []):
        if cert.get("code") == "FORBIDDEN_PATH":
            # This target violated path allowlists
            hard_avoid.add(cert["target_relpath"])
        elif cert.get("code") == "DETERMINISM_FAIL":
            # This target caused non-deterministic behavior
            hard_avoid.add(cert["target_relpath"])
    
    return hard_avoid

def _eligible_target(*, target_relpath: str, repo_root: Path, ge_config: dict, hard_avoid_prefixes: set):
    """Check if a target is eligible for modification."""
    
    # Check hard-avoid list
    for prefix in hard_avoid_prefixes:
        if target_relpath.startswith(prefix):
            return False
    
    # Check GIR (Genesis Immutable Region) scope
    if is_gir_scope_path(target_relpath):
        return False  # Cannot modify Genesis schemas
    
    # Check file exists
    if not (repo_root / target_relpath).exists():
        return False
    
    return True
```

### 13.6 CCAP Emission

Once SH-1 selects targets and generates patches, it emits **CCAP (Certified Capsule Proposal)** artifacts:

```python
def _emit_ccap(
    *,
    repo_root: Path,
    out_dir: Path,
    pins: dict[str, Any],
    active_ek: dict[str, Any],
    auth_hash_value: str,
    build_recipe_id: str,
    base_tree_id: str,
    target_relpath: str,
    marker: str,
    size_buckets_bytes_u64: list[int],
    bucket: str,
    template_id: str,
):
    """Emit a CCAP artifact for a proposed code change."""
    
    # Generate the patch
    patch_content = _build_json_tweak_patch(
        target_relpath=target_relpath,
        marker=marker,
        template_id=template_id,
        repo_root=repo_root,
    )
    
    if patch_content is None:
        return  # No valid patch for this target
    
    # Compute patch hash
    patch_hash = hashlib.sha256(patch_content.encode()).hexdigest()
    patch_relpath = f"patches/sha256_{patch_hash}.patch"
    
    # Write patch file
    patch_path = out_dir / patch_relpath
    patch_path.parent.mkdir(parents=True, exist_ok=True)
    patch_path.write_bytes(patch_content.encode())
    
    # Build CCAP payload
    ccap_payload = {
        "schema_version": "ccap_v1",
        "ccap_id": f"sha256:{patch_hash}",
        "base_tree_id": base_tree_id,
        "patch_relpath": patch_relpath,
        "target_relpath": target_relpath,
        "bucket": bucket,
        "template_id": template_id,
        "marker": marker,
        "authority_pins_id": pins["schema_version"],
        "ek_id": active_ek["schema_version"],
        "build_recipe_id": build_recipe_id,
        "auth_hash_value": auth_hash_value,
        "size_bucket_idx": _size_bucket_idx(len(patch_content), size_buckets_bytes_u64),
    }
    
    # Write CCAP file
    ccap_hash = canon_hash_obj(ccap_payload)
    ccap_relpath = f"ccaps/sha256_{ccap_hash.split(':', 1)[1]}.ccap_v1.json"
    ccap_path = out_dir / ccap_relpath
    ccap_path.parent.mkdir(parents=True, exist_ok=True)
    write_canon_json(ccap_path, ccap_payload)
    
    return ccap_relpath
```

---

## 14. Deep Technical Analysis: CCAP Verification Protocol

### 14.1 Overview: Certified Capsule Proposals

**CCAP (Certified Capsule Proposal)** is a new promotion protocol introduced in Omega v18.0 that enables **untrusted proposers** (like the Genesis Engine) to submit code changes for verification without requiring campaign-specific verifiers.

**Key Difference from Traditional Promotion:**
- **Traditional**: Each campaign has a custom verifier (e.g., `verify_rsi_sas_metasearch_v16_1.py`)
- **CCAP**: A single universal verifier (`verify_ccap_v1.py`) that works for any code patch

**Location:** `CDEL-v2/cdel/v18_0/verify_ccap_v1.py` (758 lines)

### 14.2 CCAP Schema

```json
{
  "schema_version": "ccap_v1",
  "ccap_id": "sha256:abc123...",
  "base_tree_id": "sha256:def456...",
  "patch_relpath": "patches/sha256_abc123.patch",
  "target_relpath": "campaigns/rsi_sas_code_v12_0/campaign_pack_v1.json",
  "bucket": "INCREMENTAL",
  "template_id": "JSON_TWEAK_COOLDOWN",
  "marker": "ge-sh1-tick-42",
  "authority_pins_id": "sha256:...",
  "ek_id": "sha256:...",
  "build_recipe_id": "sha256:...",
  "auth_hash_value": "sha256:...",
  "size_bucket_idx": 2
}
```

### 14.3 Patch Allowlist Enforcement

The CCAP verifier enforces strict path allowlists to prevent malicious patches:

```python
def _load_pinned_patch_allowlists(repo_root: Path, pins: dict[str, Any]) -> dict[str, list[str]]:
    """Load patch allowlists from authority pins."""
    
    allowlists_id = pins.get("ccap_patch_allowlists_id", "")
    allowlists_path = repo_root / "authority" / "ccap_patch_allowlists_v1.json"
    
    payload = load_canon_dict(allowlists_path)
    
    # Verify hash matches pins
    actual_hash = canon_hash_obj(payload)
    if actual_hash != allowlists_id:
        fail("ALLOWLIST_HASH_MISMATCH")
    
    return {
        "allow_prefixes": _normalize_prefixes(payload.get("allow_prefixes", [])),
        "forbid_prefixes": _normalize_prefixes(payload.get("forbid_prefixes", [])),
        "forbid_exact_paths": payload.get("forbid_exact_paths", []),
    }

def _path_forbidden_by_allowlists(path_rel: str, allowlists: dict) -> bool:
    """Check if a path is forbidden by allowlists."""
    
    # Check exact path forbids
    if path_rel in allowlists["forbid_exact_paths"]:
        return True
    
    # Check forbid prefixes (highest priority)
    for prefix in allowlists["forbid_prefixes"]:
        if _prefix_match(path_rel, prefix):
            return True
    
    # Check allow prefixes
    allowed = False
    for prefix in allowlists["allow_prefixes"]:
        if _prefix_match(path_rel, prefix):
            allowed = True
            break
    
    return not allowed
```

**Current Allowlist** (from `authority/ccap_patch_allowlists_v1.json`):
```json
{
  "allow_prefixes": [
    "orchestrator/",
    "tools/genesis_engine/",
    "tools/omega/",
    "polymath/registry/",
    "campaigns/"
  ],
  "forbid_prefixes": [
    "authority/",
    "meta-core/",
    "CDEL-v2/",
    "Genesis/",
    ".git/",
    "runs/",
    ".omega_cache/"
  ],
  "forbid_exact_paths": [
    "tools/omega/omega_benchmark_suite_v1.py",
    "authority/authority_pins_v1.json",
    "authority/evaluation_kernels/ek_active_v1.json"
  ]
}
```

**Interpretation:**
- **Allowed**: Campaign configurations, orchestrator code, tools
- **Forbidden**: Core verifiers, authority definitions, Genesis schemas, meta-core kernel
- **Exact Forbids**: Critical files that must never be modified (e.g., benchmark suite, authority pins)

### 14.4 The Three-Stage Verification Process

CCAP verification follows a three-stage pipeline defined by the **Evaluation Kernel (EK)**:

**Stage 1: REALIZE**
```python
# Apply the patch to a clean git tree
base_tree_id = ccap_payload["base_tree_id"]
patch_path = subrun_root / ccap_payload["patch_relpath"]

# Create isolated workspace
workspace = subrun_root / "realize_workspace"
subprocess.run(["git", "worktree", "add", str(workspace), base_tree_id], check=True)

# Apply patch
subprocess.run(["git", "apply", str(patch_path)], cwd=workspace, check=True)

# Capture applied tree ID
result = subprocess.run(
    ["git", "write-tree"],
    cwd=workspace,
    capture_output=True,
    text=True,
    check=True,
)
applied_tree_id = result.stdout.strip()

# Verify determinism: re-apply and check tree ID matches
workspace2 = subrun_root / "realize_workspace_2"
subprocess.run(["git", "worktree", "add", str(workspace2), base_tree_id], check=True)
subprocess.run(["git", "apply", str(patch_path)], cwd=workspace2, check=True)
result2 = subprocess.run(["git", "write-tree"], cwd=workspace2, capture_output=True, text=True, check=True)

if result2.stdout.strip() != applied_tree_id:
    fail("NONDETERMINISTIC_PATCH")
```

**Stage 2: SCORE**
```python
# Run the Evaluation Kernel's scoring implementation
ek_payload = load_canon_dict(repo_root / "authority" / "evaluation_kernels" / f"ek_{ek_id}.json")

scoring_impl = ek_payload["scoring_impl"]
if scoring_impl["kind"] == "OMEGA_BENCHMARK_SUITE":
    # Run the benchmark suite on the applied tree
    code_ref = scoring_impl["code_ref"]
    benchmark_script = repo_root / code_ref["path"]
    
    result = subprocess.run(
        [sys.executable, str(benchmark_script), "--tree_id", applied_tree_id],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=600,  # 10 minutes max
        check=False,
    )
    
    if result.returncode != 0:
        fail("SCORING_FAILED")
    
    # Load scorecard
    scorecard_path = subrun_root / "omega_run_scorecard_v1.json"
    scorecard = load_canon_dict(scorecard_path)
    
    # Extract summary metrics
    scorecard_summary = {
        "gates_passed": scorecard.get("gates_passed", []),
        "gates_failed": scorecard.get("gates_failed", []),
        "total_cost_q32": scorecard.get("total_cost_q32", {"q": 0}),
    }
```

**Stage 3: FINAL_AUDIT**
```python
# Run audit checks from the EK
ek_meta_tests_id = ek_payload["scoring_impl"]["ek_meta_tests_id"]
audit_script = repo_root / "tools" / "genesis_engine" / "ge_audit_report_sh1_v0_1.py"

result = subprocess.run(
    [
        sys.executable,
        str(audit_script),
        "--applied_tree_id", applied_tree_id,
        "--scorecard_path", str(scorecard_path),
        "--ek_meta_tests_id", ek_meta_tests_id,
    ],
    cwd=repo_root,
    capture_output=True,
    text=True,
    timeout=60,
    check=False,
)

if result.returncode != 0:
    fail("AUDIT_FAILED")

# Load audit report
audit_report = load_canon_dict(subrun_root / "ge_audit_report_v1.json")

# Check verdict
if audit_report.get("verdict") != "PASS":
    fail("AUDIT_REJECTED")
```

### 14.5 Receipt Generation

After successful verification, the CCAP verifier emits a **promotion receipt**:

```python
def _receipt_payload(
    *,
    ccap_id: str,
    base_tree_id: str,
    applied_tree_id: str,
    realized_out_id: str,
    ek_id: str,
    op_pool_id: str,
    auth_hash_value: str,
    determinism_check: str,
    eval_status: str,
    decision: str,
    cost_vector: dict[str, Any],
    logs_hash: str,
    scorecard_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a CCAP promotion receipt."""
    
    return {
        "schema_version": "omega_promotion_receipt_ccap_v1",
        "ccap_id": ccap_id,
        "base_tree_id": base_tree_id,
        "applied_tree_id": applied_tree_id,
        "realized_out_id": realized_out_id,
        "ek_id": ek_id,
        "op_pool_id": op_pool_id,
        "auth_hash_value": auth_hash_value,
        "determinism_check": determinism_check,  # "PASS" or "FAIL"
        "eval_status": eval_status,  # "COMPLETE", "TIMEOUT", "ERROR"
        "decision": decision,  # "PROMOTE", "REJECT"
        "cost_vector": cost_vector,  # Q32 metrics for compute cost
        "logs_hash": logs_hash,
        "scorecard_summary": scorecard_summary,
        "timestamp_utc": datetime.now(UTC).isoformat(),
    }
```

This receipt becomes part of the historical record that SH-1 analyzes in future ticks.

---

## 15. Deep Technical Analysis: Authority System

### 15.1 Overview: The Authority Pins Architecture

The **Authority System** is a new layer introduced to manage **cryptographic pins** for critical system components. It acts as a **root of trust** for the CCAP verification pipeline.

**Location:** `authority/` directory

**Key Concept:** Instead of hardcoding hashes in Python code, the system uses a **pinned manifest** (`authority_pins_v1.json`) that defines the canonical versions of:
- **Evaluation Kernels (EK)**: Define how to score code changes
- **Operator Pools (OP)**: Define who/what can execute operations
- **DSBX Profiles**: Define sandbox configurations
- **Canonicalization Versions**: Define data serialization formats

### 15.2 Authority Pins Schema

```json
{
  "schema_version": "authority_pins_v1",
  "active_ek_id": "sha256:b4f04c557008ae1bd5fa30eecacc3201903816d4a0944bbc14b281fb3852f31b",
  "active_op_pool_ids": [
    "sha256:c4ed583b732c32189a549fd7da88f5fa2de3044b0b9ce07c99358453ccbcc7a7"
  ],
  "active_dsbx_profile_ids": [
    "sha256:a77ce5f4879113175bb2edf6f442d64afd12294941c43ac9be9f4e0b1758139d"
  ],
  "canon_version_ids": {
    "ccap_can_v": "sha256:13de1b2ac24a6c563279433741232bf2e86cdbc74f83cb14694ebf6cc3f59eef",
    "ir_can_v": "sha256:dc8640232e6ee808a92b4f427e6f589e7b075f3cf9c215573e987ee05cbfa2ee",
    "obs_can_v": "sha256:cabb9c43cfbc12c10976714c0c8659b0718b69323da3e5712f400c6adcf0c14d",
    "op_can_v": "sha256:9be189769d1685dd02013b32603bd2904c308efd02ca857e05f1d10b4cfab2bb"
  },
  "ccap_patch_allowlists_id": "sha256:0ce072bf98a23f213b98cfe52632a10233d8ad9c36cda5a7f1c4f781af0ae7f6",
  "env_contract_id": "sha256:dff1c249046a5a3ecb068d9873d1d1ddf2e83e76636b19ed04ee4645224d68f7",
  "re1_constitution_state_id": "sha256:5771057bf9aef5dedccc578eb78fbadfa8c60111472f4d1f5bfb9db9dc29aa17",
  "re2_verifier_state_id": "sha256:61ab3b8307dcc35ce5128a2219ccfd015a9e2860a5a5cc4675fd05efe2654ff7",
  "toolchain_root_id": "sha256:efa662256ec89577060e523d0fcaa3f15d82a0ce8ea65a2338315f9282dd4034"
}
```

### 15.3 Evaluation Kernel (EK) Structure

An **Evaluation Kernel** defines the **scoring pipeline** for code changes:

```json
{
  "schema_version": "evaluation_kernel_v1",
  "ek_version": 1,
  "boundary_event_set_id": "sha256:46447887d799e38e9858ebdb844bebd75d7179d68dd232b382467b340b7c6404",
  "obs_canon_id": "sha256:5f5f7d4331d416f38648157cca1f9c3d9699c2a21d0b1088aa70669cd8d829b8",
  "obs_schema_ids": [
    "https://genesis.engine/specs/v18_0/omega_observation_report_v1",
    "https://genesis.engine/specs/v18_0/omega_dispatch_receipt_v1",
    "https://genesis.engine/specs/v18_0/omega_subverifier_receipt_v1",
    "https://genesis.engine/specs/v18_0/omega_promotion_receipt_v1",
    "https://genesis.engine/specs/v18_0/omega_activation_receipt_v1",
    "https://genesis.engine/specs/v18_0/omega_run_scorecard_v1",
    "https://genesis.engine/specs/v18_0/omega_tick_stats_v1"
  ],
  "scoring_impl": {
    "kind": "OMEGA_BENCHMARK_SUITE",
    "code_ref": {
      "commit_hash": "0db35ee64737f2971f87cec18310a0f97c28abcd",
      "path": "tools/omega/omega_benchmark_suite_v1.py"
    },
    "applicability_preds_id": "sha256:13f6f95f68c05bdb293dbe932b9006acc7b417e79f3be3be1c16241bd615a8dd",
    "ek_meta_tests_id": "sha256:2a14841a87f0ce09c6a2c25e6d33afbfcf8442ba476f30afb8647445e5b2d30e"
  },
  "stages": [
    {
      "stage_name": "REALIZE",
      "required_b": true,
      "hard_gate_b": true,
      "timeout_ms_max_u64": 180000
    },
    {
      "stage_name": "SCORE",
      "required_b": true,
      "hard_gate_b": true,
      "timeout_ms_max_u64": 600000
    },
    {
      "stage_name": "FINAL_AUDIT",
      "required_b": true,
      "hard_gate_b": true,
      "timeout_ms_max_u64": 60000
    }
  ]
}
```

**Key Fields:**
- **`boundary_event_set_id`**: Defines which events are observable (e.g., promotion receipts, activation receipts)
- **`obs_schema_ids`**: Whitelist of allowed observation schemas
- **`scoring_impl`**: Reference to the code that scores proposals
- **`stages`**: Pipeline stages with timeouts and gate requirements

### 15.4 Operator Pool Structure

An **Operator Pool** defines the **execution environment** for operations:

```json
{
  "schema_version": "operator_pool_v1",
  "pool_id": "sha256:c4ed583b732c32189a549fd7da88f5fa2de3044b0b9ce07c99358453ccbcc7a7",
  "pool_name": "operator_pool_core_v1",
  "operators": [
    {
      "operator_id": "git_apply_v1",
      "operator_type": "GIT_APPLY",
      "max_patch_size_bytes": 65536,
      "allowed_extensions": [".py", ".json", ".md"]
    },
    {
      "operator_id": "git_write_tree_v1",
      "operator_type": "GIT_WRITE_TREE",
      "max_tree_size_bytes": 10485760
    },
    {
      "operator_id": "python_exec_v1",
      "operator_type": "PYTHON_EXEC",
      "max_runtime_ms": 600000,
      "max_memory_bytes": 4294967296
    }
  ]
}
```

### 15.5 Authority Hash Computation

The **authority hash** is a cryptographic commitment to the entire authority configuration:

```python
def compute_authority_hash(pins: dict[str, Any], repo_root: Path) -> str:
    """Compute the authority hash from pins and referenced artifacts."""
    
    # Load all referenced artifacts
    ek = load_canon_dict(repo_root / "authority" / "evaluation_kernels" / f"ek_{pins['active_ek_id']}.json")
    op_pools = [
        load_canon_dict(repo_root / "authority" / "operator_pools" / f"op_{pool_id}.json")
        for pool_id in pins["active_op_pool_ids"]
    ]
    dsbx_profiles = [
        load_canon_dict(repo_root / "authority" / "dsbx_profiles" / f"dsbx_{profile_id}.json")
        for profile_id in pins["active_dsbx_profile_ids"]
    ]
    allowlists = load_canon_dict(repo_root / "authority" / f"ccap_patch_allowlists_{pins['ccap_patch_allowlists_id']}.json")
    
    # Build composite object
    authority_composite = {
        "pins": pins,
        "ek": ek,
        "op_pools": op_pools,
        "dsbx_profiles": dsbx_profiles,
        "allowlists": allowlists,
    }
    
    # Hash the composite
    return canon_hash_obj(authority_composite)
```

This hash is included in every CCAP and verified during promotion to ensure the proposal was evaluated under the correct authority configuration.

---

## 16. Deep Technical Analysis: Polymath Refinery Proposer

### 16.1 Overview: Deterministic Domain Proposal Generation

The **Polymath Refinery Proposer** (`polymath_refinery_proposer_v1.py`) is a new tool that automatically generates **domain conquest proposals** by analyzing the Polymath registry and identifying domains that are ready for automated solver generation.

**Key Innovation:** Unlike the interactive `polymath_conquer_domain_v1` campaign, the Refinery Proposer runs **offline** and emits a **summary JSON** that can be used to seed the Omega goal queue with high-value targets.

**Location:** `tools/polymath/polymath_refinery_proposer_v1.py` (610 lines)

### 16.2 Domain Eligibility Criteria

The proposer evaluates each domain in the registry against strict criteria:

```python
def _evaluate_domain(
    *,
    repo_root: Path,
    store_root: Path,
    domain_index: int,
    row: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate a single domain for conquest eligibility."""
    
    domain_id = row.get("domain_id", "")
    
    # 1. Check domain pack exists
    domain_pack_path = repo_root / "polymath" / "registry" / domain_id / "domain_pack_v1.json"
    if not domain_pack_path.exists():
        return _skip_row(domain_id=domain_id, reason="DOMAIN_PACK_MISSING", detail=str(domain_pack_path))
    
    # 2. Load and validate domain pack
    domain_pack = load_canon_dict(domain_pack_path)
    if domain_pack.get("schema_version") != "polymath_domain_pack_v1":
        return _skip_row(domain_id=domain_id, reason="DOMAIN_PACK_SCHEMA_FAIL", detail="Invalid schema")
    
    # 3. Check tasks exist
    tasks = domain_pack.get("tasks", [])
    if not tasks:
        return _skip_row(domain_id=domain_id, reason="TASKS_EMPTY", detail="No tasks defined")
    
    # 4. Check train/test split exists
    split = domain_pack.get("split", {})
    train_sha256 = split.get("train_sha256", "")
    test_sha256 = split.get("test_sha256", "")
    
    if not train_sha256:
        return _skip_row(domain_id=domain_id, reason="TRAIN_SHA_MISSING", detail="No training data")
    if not test_sha256:
        return _skip_row(domain_id=domain_id, reason="TEST_SHA_MISSING", detail="No test data")
    
    # 5. Check all required blobs exist in store
    required_sha256s = _required_sha256s(
        domain_pack=domain_pack,
        train_sha256=train_sha256,
        test_sha256=test_sha256,
    )
    missing_sha256s = _missing_sha256s(store_root=store_root, required_sha256s=required_sha256s)
    
    if missing_sha256s:
        return _skip_row(
            domain_id=domain_id,
            reason="MISSING_STORE_BLOBS",
            detail=f"Missing {len(missing_sha256s)} blobs: {missing_sha256s[:3]}...",
        )
    
    # 6. Check policy allows conquest
    policy = domain_pack.get("policy", {})
    if policy.get("block_conquest", False):
        return _skip_row(domain_id=domain_id, reason="POLICY_BLOCKED", detail="Domain blocks conquest")
    
    # 7. Check size constraints
    total_size_bytes = sum(
        (store_root / "blobs" / f"sha256_{sha}" / "blob").stat().st_size
        for sha in required_sha256s
    )
    if total_size_bytes > 100_000_000:  # 100 MB limit
        return _skip_row(domain_id=domain_id, reason="SIZE_BLOCKED", detail=f"{total_size_bytes} bytes")
    
    # Domain is eligible!
    return _build_proposal(
        store_root=store_root,
        domain_index=domain_index,
        domain_id=domain_id,
        train_sha256=train_sha256,
        metric_id=domain_pack.get("metric_id", "accuracy"),
    )
```

### 16.3 Proposal Generation

For eligible domains, the proposer generates a **conquest proposal**:

```python
def _build_proposal(
    *,
    store_root: Path,
    domain_index: int,
    domain_id: str,
    train_sha256: str,
    metric_id: str,
) -> dict[str, Any]:
    """Build a conquest proposal for an eligible domain."""
    
    return {
        "status": "PROPOSED",
        "domain_id": domain_id,
        "domain_index": domain_index,
        "train_sha256": train_sha256,
        "metric_id": metric_id,
        "priority_score": _compute_priority_score(
            domain_id=domain_id,
            train_sha256=train_sha256,
            store_root=store_root,
        ),
        "estimated_cost_q32": _estimate_conquest_cost(
            domain_id=domain_id,
            train_sha256=train_sha256,
        ),
    }

def _compute_priority_score(domain_id: str, train_sha256: str, store_root: Path) -> int:
    """Compute priority score for a domain (higher = more important)."""
    
    # Factors:
    # 1. Domain novelty (new domains get higher priority)
    # 2. Data quality (clean, well-formatted data gets higher priority)
    # 3. Scientific impact (domains in high-impact fields get higher priority)
    
    score = 1000  # Base score
    
    # Novelty bonus
    if not _domain_has_existing_solver(domain_id):
        score += 500
    
    # Data quality bonus
    train_blob_path = store_root / "blobs" / f"sha256_{train_sha256}" / "blob"
    if _data_is_well_formatted(train_blob_path):
        score += 200
    
    # Scientific impact bonus (heuristic based on domain name)
    if any(keyword in domain_id.lower() for keyword in ["cancer", "climate", "energy"]):
        score += 300
    
    return score
```

### 16.4 Parallel Evaluation with Worker Pool

The proposer uses a **worker pool** to evaluate domains in parallel:

```python
def run(
    *,
    registry_path: Path,
    store_root: Path,
    workers: int,
    max_domains: int,
    summary_path: Path | None = None,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Run the refinery proposer with parallel evaluation."""
    
    # Load registry
    registry_rows = _load_registry_rows(registry_path)
    
    # Limit to max_domains
    registry_rows = registry_rows[:max_domains]
    
    # Bucket domains by size for load balancing
    buckets = [
        [],  # Small domains (< 1 MB)
        [],  # Medium domains (1-10 MB)
        [],  # Large domains (> 10 MB)
    ]
    
    for idx, row in enumerate(registry_rows):
        size = _estimate_domain_size(row)
        if size < 1_000_000:
            buckets[0].append((idx, row))
        elif size < 10_000_000:
            buckets[1].append((idx, row))
        else:
            buckets[2].append((idx, row))
    
    # Process buckets in parallel
    all_results = []
    
    with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as executor:
        for bucket_rows in buckets:
            futures = [
                executor.submit(
                    _evaluate_domain,
                    repo_root=repo_root,
                    store_root=store_root,
                    domain_index=idx,
                    row=row,
                )
                for idx, row in bucket_rows
            ]
            
            for future in concurrent.futures.as_completed(futures):
                try:
                    result = future.result(timeout=300)  # 5 minutes per domain
                    all_results.append(result)
                except Exception as exc:
                    all_results.append(_error_row(domain_id="unknown", detail=str(exc)))
    
    # Aggregate results
    proposed = [r for r in all_results if r.get("status") == "PROPOSED"]
    skipped = [r for r in all_results if r.get("status") == "SKIPPED"]
    errors = [r for r in all_results if r.get("status") == "ERROR"]
    
    # Sort proposals by priority
    proposed.sort(key=lambda r: r.get("priority_score", 0), reverse=True)
    
    # Build summary
    summary = {
        "schema_version": "polymath_refinery_proposer_summary_v1",
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "registry_path": str(registry_path),
        "store_root": str(store_root),
        "workers": workers,
        "max_domains": max_domains,
        "total_evaluated": len(all_results),
        "proposed_count": len(proposed),
        "skipped_count": len(skipped),
        "error_count": len(errors),
        "proposals": proposed,
        "skip_reason_counts": _count_skip_reasons(skipped),
    }
    
    # Write summary
    if summary_path:
        _write_summary(summary_path, summary)
    
    return summary
```

### 16.5 Integration with Omega Goal Queue

The proposer's output can be used to seed the Omega goal queue:

```bash
# Run the proposer
python3 tools/polymath/polymath_refinery_proposer_v1.py \
    --registry_path polymath/registry/registry_v1.jsonl \
    --store_root polymath/store \
    --workers 4 \
    --max_domains 100 \
    --summary_path OMEGA_POLYMATH_REFINERY_PROPOSER_SUMMARY_v1.json

# The summary contains prioritized proposals
cat OMEGA_POLYMATH_REFINERY_PROPOSER_SUMMARY_v1.json | jq '.proposals[:5]'
# [
#   {"domain_id": "pubchem_solubility", "priority_score": 1800, ...},
#   {"domain_id": "protein_folding_small", "priority_score": 1500, ...},
#   {"domain_id": "climate_co2_prediction", "priority_score": 1300, ...},
#   ...
# ]

# Omega can read this summary and add conquest goals to the queue
```

---

## 17. Complete Capability Inventory

### 17.1 Registry Truth (What Is Declared Right Now)

The repository now has three authoritative v19.x profile registries plus legacy v18.0 (and an expanded v18 production profile):

- `campaigns/rsi_omega_daemon_v18_0/omega_capability_registry_v2.json`  
  - **23 capabilities**, **3 enabled**
- `campaigns/rsi_omega_daemon_v18_0_prod/omega_capability_registry_v2.json`  
  - **26 capabilities**, **6 enabled**
- `campaigns/rsi_omega_daemon_v19_0/omega_capability_registry_v2.json`  
  - **24 capabilities**, **3 enabled** (same base default enabled set as v18.0)
- `campaigns/rsi_omega_daemon_v19_0_unified/omega_capability_registry_v2.json`  
  - **24 capabilities**, **7 enabled** (unified run profile for evidence-focused runs)
- `campaigns/rsi_omega_daemon_v19_0_llm_enabled/omega_capability_registry_v2.json`  
  - **24 capabilities**, **1 enabled** (LLM-bridge overlay profile)

So the claim “8 active campaigns” in older docs is stale.  
The repo currently declares **24 v19 capabilities**, with runtime defaults determined by the selected profile.

## Capability Matrix (v19.0, canonical capability order)

| capability_id | campaign_id | risk | cooldown | promotion | v18 | v19 | v19_unified | v19_llm_profile | orchestrator module |
|---|---|---|---:|---|---|---|---|---|---|
| RSI_AGI_ORCHESTRATOR_LLM | rsi_agi_orchestrator_llm_v1 | LOW | 1 | trad | N | N | N | Y | orchestrator.rsi_agi_orchestrator_llm_v1 |
| RSI_EUDRS_U_EVAL_CAC | rsi_eudrs_u_eval_cac_v1 | LOW | 1 | trad | N | N | N | N | orchestrator.rsi_eudrs_u_eval_cac_v1 |
| RSI_EUDRS_U_INDEX_REBUILD | rsi_eudrs_u_index_rebuild_v1 | MED | 1 | trad | N | N | N | N | orchestrator.rsi_eudrs_u_index_rebuild_v1 |
| RSI_EUDRS_U_ONTOLOGY_UPDATE | rsi_eudrs_u_ontology_update_v1 | MED | 1 | trad | N | N | N | N | orchestrator.rsi_eudrs_u_ontology_update_v1 |
| RSI_EUDRS_U_TRAIN | rsi_eudrs_u_train_v1 | MED | 1 | trad | N | N | N | N | orchestrator.rsi_eudrs_u_train_v1 |
| RSI_GE_SH1_OPTIMIZER | rsi_ge_symbiotic_optimizer_sh1_v0_1 | MED | 25 | CCAP | N | N | Y | N | cdel.v18_0.campaign_ge_symbiotic_optimizer_sh1_v0_1 |
| RSI_MODEL_GENESIS_V10 | rsi_model_genesis_v10_0 | MED | 25 | trad | N | N | N | N | orchestrator.rsi_model_genesis_v10_0 |
| RSI_OMEGA_SELF_OPTIMIZE_CORE | rsi_omega_self_optimize_core_v1 | MED | 5 | trad | N | N | N | N | cdel.v18_0.campaign_self_optimize_core_v1 |
| RSI_OMEGA_SKILL_ALIGNMENT | rsi_omega_skill_alignment_v1 | LOW | 5 | trad | N | N | N | N | cdel.v18_0.campaign_omega_skill_alignment_v1 |
| RSI_OMEGA_SKILL_BOUNDLESS_MATH | rsi_omega_skill_boundless_math_v1 | LOW | 5 | trad | N | N | N | N | cdel.v18_0.campaign_omega_skill_boundless_math_v1 |
| RSI_OMEGA_SKILL_BOUNDLESS_SCIENCE | rsi_omega_skill_boundless_science_v1 | LOW | 5 | trad | N | N | N | N | cdel.v18_0.campaign_omega_skill_boundless_science_v1 |
| RSI_OMEGA_SKILL_EFF_FLYWHEEL | rsi_omega_skill_eff_flywheel_v1 | LOW | 5 | trad | N | N | N | N | cdel.v18_0.campaign_omega_skill_eff_flywheel_v1 |
| RSI_OMEGA_SKILL_MODEL_GENESIS | rsi_omega_skill_model_genesis_v1 | LOW | 5 | trad | N | N | N | N | cdel.v18_0.campaign_omega_skill_model_genesis_v1 |
| RSI_OMEGA_SKILL_ONTOLOGY | rsi_omega_skill_ontology_v1 | LOW | 5 | trad | N | N | N | N | cdel.v18_0.campaign_omega_skill_ontology_v1 |
| RSI_OMEGA_SKILL_PERSISTENCE | rsi_omega_skill_persistence_v1 | LOW | 5 | trad | N | N | N | N | cdel.v18_0.campaign_omega_skill_persistence_v1 |
| RSI_OMEGA_SKILL_SWARM | rsi_omega_skill_swarm_v1 | LOW | 5 | trad | N | N | N | N | cdel.v18_0.campaign_omega_skill_swarm_v1 |
| RSI_OMEGA_SKILL_THERMO | rsi_omega_skill_thermo_v1 | LOW | 5 | trad | N | N | N | N | cdel.v18_0.campaign_omega_skill_thermo_v1 |
| RSI_OMEGA_SKILL_TRANSFER | rsi_omega_skill_transfer_v1 | LOW | 5 | trad | N | N | N | N | cdel.v18_0.campaign_omega_skill_transfer_v1 |
| RSI_POLYMATH_BOOTSTRAP_DOMAIN | rsi_polymath_bootstrap_domain_v1 | MED | 50 | trad | N | N | Y | N | cdel.v18_0.campaign_polymath_bootstrap_domain_v1 |
| RSI_POLYMATH_CONQUER_DOMAIN | rsi_polymath_conquer_domain_v1 | MED | 25 | trad | N | N | Y | N | cdel.v18_0.campaign_polymath_conquer_domain_v1 |
| RSI_POLYMATH_SCOUT | rsi_polymath_scout_v1 | MED | 25 | CCAP | N | N | Y | N | cdel.v18_0.campaign_polymath_scout_v1 |
| RSI_SAS_CODE | rsi_sas_code_v12_0 | MED | 1 | trad | Y | Y | Y | N | orchestrator.rsi_sas_code_v12_0 |
| RSI_SAS_METASEARCH | rsi_sas_metasearch_v16_1 | MED | 50 | trad | Y | Y | Y | N | orchestrator.rsi_sas_metasearch_v16_1 |
| RSI_SAS_VAL | rsi_sas_val_v17_0 | HIGH | 50 | trad | Y | Y | Y | N | orchestrator.rsi_sas_val_v17_0 |

### 17.2 What the Model Can Actually Do Today

From a systems perspective, the operational model’s current capabilities are:

1. **Run deterministic improvement loops**  
   The daemon can execute enabled campaigns one tick at a time, generate artifacts in a sandbox subrun directory, run campaign-specific verifiers, and promote only if all checks pass. This is the only path to durable change.

2. **Code-level optimization (SAS-CODE)**  
   `RSI_SAS_CODE` is the active code-generation channel for optimization proposals. It is enabled in default v18/v19 profiles and produces campaign-specific artifacts that are deterministically validated.

3. **Search/runtime optimization experiments (SAS-Metasearch)**  
   `RSI_SAS_METASEARCH` is enabled and attempts metric-driven hypothesis exploration and ranking changes that improve run-time/quality outcomes.

4. **Validation/verification pressure campaigns (SAS-VAL)**  
   `RSI_SAS_VAL` is enabled and higher risk/longer cooldown, so it is gated more aggressively. It is used for self-checking and verifier-facing validations.

5. **Polymath knowledge pipeline (unified profile only)**  
   In `v19_0_unified`, three polymath capabilities are enabled:
   - `RSI_POLYMATH_BOOTSTRAP_DOMAIN` discovers and prepares new knowledge tasks.
   - `RSI_POLYMATH_CONQUER_DOMAIN` trains deterministic solvers on bootstrapped domains.
   - `RSI_POLYMATH_SCOUT` emits auditable discovery reports that can be captured via CCAP.
   These are the main path to expanding domain capability outside direct system optimization.

6. **Meta-level receipt optimizer (unified profile only)**  
   `RSI_GE_SH1_OPTIMIZER` runs SH-1 as a campaign and emits CCAP artifacts based on receipt signals.

7. **Optional deterministic LLM bridge (LLM overlay)**  
   `RSI_AGI_ORCHESTRATOR_LLM` is available via overlay, but disabled by default and isolated behind the replay/harvest contract. It contributes proposals/evidence, not authority.

8. **EUDRS-U campaign wiring (declared, default disabled)**  
   The v19 registries declare four EUDRS-U campaigns (`RSI_EUDRS_U_TRAIN`, `RSI_EUDRS_U_INDEX_REBUILD`, `RSI_EUDRS_U_ONTOLOGY_UPDATE`, `RSI_EUDRS_U_EVAL_CAC`) whose orchestrators are implemented under `orchestrator/` and whose packs live under `campaigns/rsi_eudrs_u_*/`. These campaigns stage a registry tree under `eudrs_u/staged_registry_tree/` and MUST emit a single entrypoint summary file `eudrs_u/evidence/eudrs_u_promotion_summary_v1.json` (RE2 verifier entrypoint) that points to all other evidence.

### 17.3 CCAP vs Traditional Promotion Path

In practice the promotion surface is split:

- **Traditional promotion** (`..._promotion_bundle_v1.json`)  
  Most non-LLM and non-Scout/SH-1 capabilities.
- **CCAP promotion** (`omega_promotion_bundle_ccap_v1.json`)  
  `RSI_POLYMATH_SCOUT` and `RSI_GE_SH1_OPTIMIZER` currently route through universal CCAP verification, which is helpful for deterministic third-party patch formats and fixed-scoring metadata.

### 17.4 Capability Reality Check (Implemented, Declared, Disabled)

- **Implemented and active by default in base profiles:**  
  `RSI_SAS_CODE`, `RSI_SAS_METASEARCH`, `RSI_SAS_VAL`.
- **Implemented and stage-gated in unified profile:**  
  `RSI_POLYMATH_BOOTSTRAP_DOMAIN`, `RSI_POLYMATH_CONQUER_DOMAIN`, `RSI_POLYMATH_SCOUT`, `RSI_GE_SH1_OPTIMIZER`.
- **Implemented but not enabled by default:**  
  `RSI_AGI_ORCHESTRATOR_LLM` (overlay only), `RSI_MODEL_GENESIS_V10`, the EUDRS-U campaign set (`RSI_EUDRS_U_*`), and existing `RSI_OMEGA_*_SKILL_*` report wrappers (stubs/legacy report channels).
- **Declared but currently non-functional in this checkout:**  
  `RSI_OMEGA_SKILL_ALIGNMENT`, `RSI_OMEGA_SKILL_BOUNDLESS_MATH`, `RSI_OMEGA_SKILL_BOUNDLESS_SCIENCE`, `RSI_OMEGA_SKILL_SWARM`, `RSI_OMEGA_SKILL_MODEL_GENESIS`.

### 17.5 Risk Classes

Current risk-class distribution in the unified profile is:

- **HIGH:** `RSI_SAS_VAL` (1 capability)
- **MED:** 11 capabilities
- **LOW:** 12 capabilities

Risk class is used in decision scheduling and cooldown policy during tick planning, rather than hard capability blocking.

---

## 18. Conclusion

The repository represents a significant engineering achievement in **Verifiable Autonomy**. By enforcing `Q32` determinism, `Fail-Closed` verification, and strict `RE` layering, it allows an AI system to act as its own developer (`Extension-1`), its own QA (`CDEL`), and its own Release Manager (`meta-core`) without human intervention. The code analysis confirms that these high-level architectural claims are backed by rigorous implementation details, such as the bit-exact metric re-computation in `verify_rsi_omega_daemon_v1.py` and the sandboxed execution environment in `run.py`.

The "Tick" mechanism ensures that time itself is quantized and verifiable, preventing "drift" where the AI's internal state diverges from reality. The "Polymath" module demonstrates that this architecture is not just for self-preservation but for active acquisition of new knowledge, capable of writing new solvers for new domains on the fly.

### 18.1 Recent Architectural Evolution: SH-1 and CCAP

The introduction of **SH-1 (Symbiotic Harmony v1)** and the **CCAP (Certified Capsule Proposal) protocol** represents a major architectural evolution:

**Key Innovations:**
1. **Receipt-Driven Learning**: SH-1 learns from historical promotion/rejection patterns, creating a meta-learning loop where the system improves its ability to propose improvements.
2. **Universal Verification**: CCAP enables a single verifier to handle arbitrary code patches, eliminating the need for campaign-specific verifiers.
3. **Authority Pins**: The new authority system provides a cryptographic root of trust for evaluation kernels, operator pools, and patch allowlists.
4. **Deterministic Proposal Generation**: The Polymath Refinery Proposer enables offline, parallelized domain analysis for high-value target identification.

**Architectural Maturity:**
- **From Campaign-Specific to Universal**: The shift from custom verifiers to CCAP represents a move toward more general self-improvement capabilities.
- **From Reactive to Proactive**: SH-1's receipt analysis enables the system to learn what kinds of changes are likely to be accepted, reducing wasted effort.
- **From Hardcoded to Pinned**: The authority system moves critical configuration from Python code to cryptographically-pinned JSON manifests.

### 18.2 Current State and Future Trajectory

**Operational Truth (as shipped in this repository):**
- **Declared capabilities:** 20 in v19 registries
- **Base default active:** 3 (SAS code, SAS metasearch, SAS validation)
- **Unified default active:** 7 (base 3 + polymath trio + SH-1)
- **LLM overlay active:** 1 (`RSI_AGI_ORCHESTRATOR_LLM`)
- **CCAP-capable active workflows:** at least 2 in unified profile (`RSI_POLYMATH_SCOUT`, `RSI_GE_SH1_OPTIMIZER`)
- **Declared but not yet active/implemented:** multiple skill-domain entries are present as forward declarations and gating scaffolding

**Verification Depth:**
- **Omega Daemon Verifier**: 1334 lines of replay logic
- **CCAP Verifier**: 758 lines of universal patch verification
- **Campaign-Specific Verifiers**: 56 distinct verifiers for legacy campaigns
- **Total Verifier LOC**: ~50,000+ lines of fail-closed verification code

**Self-Improvement Scope:**
- **Allowed Modification Paths**: `orchestrator/`, `tools/`, `campaigns/`, `polymath/registry/`
- **Forbidden Modification Paths**: `authority/`, `meta-core/`, `CDEL-v2/`, `Genesis/`
- **Critical Protected Files**: Benchmark suite, authority pins, evaluation kernels

This system is a **self-stabilizing, self-optimizing closed loop** with layered verification and explicit promotion gates. The practical, today-state capability set is narrower than the full registry surface: it has strong deterministic execution, metacontrol, polymath expansion, and evidence pipelines, but several catalogued capability IDs remain gated or unimplemented and should not be counted as live behavior.

### 18.3 Recent Evolution: Sealed Websearch + Untrusted LLM Router (D7)
The repository now also supports **untrusted tool-use** inside the proposer path, without changing the trust boundary or creating any new acceptance path.

Key constraints are explicit and fail-closed:
*   **Network is gated**: live fetch is only allowed when `OMEGA_NET_LIVE_OK=1`. Cache hits are permitted even when the network is disabled.
*   **Web fetches are sealed**: responses are stored as content-addressed blobs with receipts so they can be replayed deterministically.
*   **LLM outputs are replayed**: the LLM backend records prompt/response rows into `ORCH_LLM_REPLAY_PATH`, allowing replay-only runs later.

Operationally, this adds an “LLM router” that can:
*   propose a small number of web queries (restricted to allowlisted providers/hosts),
*   propose goal injections (restricted to an allowlist of capability IDs from the capability registry),
*   emit run-local artifacts such as:
    *   `OMEGA_LLM_ROUTER_PLAN_v1.json` (canonical JSON with deterministic fields like `created_at_utc: ""`),
    *   `OMEGA_LLM_TOOL_TRACE_v1.jsonl` (tool call trace with prompt/response hashes and sealed evidence references).

This does not grant the LLM authority. It can only influence “what to try”; promotion and activation remain governed by dispatch, verifiers, and meta-core.

#### 18.3.1 Websearch: “Tool Use” Means Sealed Fetch + Bounded Providers
The “websearch tool” is deliberately minimal and constrained so it cannot become a covert new trust channel:
*   Providers are limited to a small set of allowlisted hosts (for example, Wikipedia API and DuckDuckGo Instant Answer).
*   Each fetch is routed through a sealed fetch primitive that:
    *   enforces host allowlists,
    *   enforces max byte limits,
    *   produces a receipt and a content-addressed blob,
    *   updates a small index mapping URLs to sha256.
*   When the network is disabled, the tool must fail closed on cache miss (raising `NET_DISABLED`) rather than silently falling back to live calls.

This is important operationally: it allows “production runs” that use the web to bootstrap ideas once (harvest), then re-run the exact same run in replay mode for verification and CI.

#### 18.3.2 LLM Backend Contract: Harvest vs Replay (No “Magic Live” Fallback)
The LLM router does not invent a second LLM stack. It reuses the orchestrator’s backend contract:
*   `ORCH_LLM_BACKEND` selects `mock`, `replay`, or a harvest backend.
*   `ORCH_LLM_REPLAY_PATH` is the deterministic ledger of calls (prompt/response, hashes, raw payload) used for replay.
*   `ORCH_LLM_LIVE_OK=1` is the explicit switch that allows harvest backends to call external APIs; without it, harvest must fail closed.
*   Budgets such as `ORCH_LLM_MAX_CALLS`, `ORCH_LLM_MAX_PROMPT_CHARS`, `ORCH_LLM_MAX_RESPONSE_CHARS` bound the proposer’s influence and keep costs predictable.

From a safety standpoint, the key point is: the LLM is never “trusted”; it is only a proposer. From a determinism standpoint, the key point is: if replay rows are missing, the run cannot silently “just call the LLM again” unless explicitly permitted.

#### 18.3.3 Router Failure Policy: Continue Safely, or Halt if Required
Because the router is untrusted, the default policy is to treat it as optional guidance:
*   If the router fails to parse JSON, or replay rows are missing, the system can record the failure and continue with zero injections.
*   If `OMEGA_LLM_ROUTER_REQUIRED=1` is set, router failure becomes a hard stop (`SAFE_HALT`) with an explicit termination reason.

This is a pragmatic compromise: in interactive development runs you often want the loop to continue, but for certain acceptance tests you may want “router evidence is mandatory”.

### 18.4 v19 in Practice: From Harness Proofs to Real Loop Evidence (D9)
The v19 direction pushes the system toward “proofs that happen under the real loop”.

In practice, v19 evidence is produced by:
1.  Running the v19 daemon loop for multiple ticks (not just a one-off harness tick).
2.  Ensuring promotion and subverification run from the subrun CWD so axis bundle references resolve deterministically.
3.  Scanning the produced run root for axis bundles and gate failures, then summarizing:
    *   promotions count,
    *   promoted bundles that contain morphism types,
    *   failures by gate outcome,
    *   maximum level achieved via monotone coverage (“lower morphisms must appear before higher ones count”).

This turns “the ladder exists” into a measurable claim: “the ladder was climbed to level L under promotion gating, with replayable artifacts”.

In this checkout, the repo also includes concrete “real loop” wiring and runners (not just harnesses), including `tools/v19_runs/run_omega_v19_full_loop.py` for multi-tick execution and focused tests like `test_v19_real_run_uses_subrun_cwd.py` / `test_v19_promotion_cwd_subrun_required.py` that lock in the “subrun CWD is canonical” requirement.

#### 18.4.1 Why This Matters: Evidence You Can Diff Between Runs
The goal of “level attainment reports” is not storytelling. It is to make progress *diffable*:
*   If a branch claims it improves the system, we want a report artifact that changes in a meaningful way: more promotions, fewer gate failures, more morphism types, higher max level.
*   If a change introduces non-determinism, the report should become unstable across runs with the same seed and empty caches, and verification should fail closed.

That makes the ladder report a practical engineering tool: it converts “the system did something complicated” into “here are stable, replayable deltas”.

#### 18.4.2 Ladder Mapping and Monotone Coverage (How Levels Are Computed)
The ladder itself is intentionally strict. A typical definition looks like:
*   Each level corresponds to a required morphism type (for example: L0/L1 require `M_SIGMA`, L2 requires `M_PI`, up to higher morphisms).
*   A level is considered “achieved” only if:
    *   there exists at least one **PROMOTED** axis bundle containing the required morphism type, and
    *   all lower levels’ morphism types have also appeared in at least one **PROMOTED** bundle.

This monotone requirement prevents “skipping” levels by emitting a single high-level morphism without the underlying lower-level evidence.

#### 18.4.3 CI Strategy: Fast Proofs Always, Full Loop On-Demand
One pragmatic consequence of v19 is runtime: real multi-tick loops can be expensive. The repo’s direction is therefore:
*   Keep fast deterministic tests (gate matrix / promotion gate checks / coordinator wiring) CI-blocking.
*   Add longer multi-tick “full loop” runs as workflow-dispatch or local runs until stability and runtime are proven.

This avoids weakening CI while still enabling “real loop evidence” when needed.

### 18.5 EUDRS-U v1.0 Wiring: Deterministic Evidence Entrypoint (Default Disabled)
This checkout wires an initial EUDRS-U campaign set into the Omega registries (declared, but `enabled:false` in all shipped profiles), and it also includes substantial RE2 + RE4 implementation for EUDRS-U/QXWMR/QXRL/ML-index.

**What’s implemented (today-state, not aspiration):**
*   **RE4 schemas (Genesis):** EUDRS-U and ML-index schemas exist under `Genesis/schema/v18_0/` (for example `Genesis/schema/v18_0/eudrs_u_promotion_summary_v1.jsonschema`, `Genesis/schema/v18_0/eudrs_u_system_manifest_v1.jsonschema`, `Genesis/schema/v18_0/ml_index_manifest_v1.jsonschema`, `Genesis/schema/v18_0/ml_index_bucket_listing_v1.jsonschema`).
*   **RE2 core library:** EUDRS-U, QXWMR, QXRL, and ML-index logic is implemented under `CDEL-v2/cdel/v18_0/eudrs_u/` (including `qxwmr_canon_wl_v1.py`, `qxwmr_state_v1.py`, `qxrl_train_replay_v1.py`, `ml_index_v1.py`, `mem_gates_v1.py`, plus promotion/run verifiers).
*   **Fail-closed verification entrypoint:** `CDEL-v2/cdel/v18_0/eudrs_u/verify_eudrs_u_run_v1.py` treats the producer-emitted promotion summary as the entrypoint; it runs Phase-1 promotion integrity checks and then runs Phase-4 QXRL replay verification.
*   **Promotion verification:** `CDEL-v2/cdel/v18_0/eudrs_u/verify_eudrs_u_promotion_v1.py` enforces “exactly one summary object” under `eudrs_u/evidence/`, verifies the staged registry tree layout, validates root tuple epoch continuity, and runs mem/index gates (including merkle verification for ML-index artifacts).

**Campaign wiring (declared and runnable, but default disabled):**
*   Orchestrators live under `orchestrator/`: `orchestrator/rsi_eudrs_u_train_v1.py`, `orchestrator/rsi_eudrs_u_index_rebuild_v1.py`, `orchestrator/rsi_eudrs_u_ontology_update_v1.py`, `orchestrator/rsi_eudrs_u_eval_cac_v1.py`.
*   Campaign packs live under `campaigns/rsi_eudrs_u_*/` (for example `campaigns/rsi_eudrs_u_train_v1/rsi_eudrs_u_train_pack_v1.json`).
*   The v18/v19 Omega registries declare these as capabilities `RSI_EUDRS_U_TRAIN`, `RSI_EUDRS_U_INDEX_REBUILD`, `RSI_EUDRS_U_ONTOLOGY_UPDATE`, `RSI_EUDRS_U_EVAL_CAC` with verifier module `cdel.v18_0.eudrs_u.verify_eudrs_u_run_v1`.

**Filesystem contract (determinism-critical):**
*   Each EUDRS-U subrun writes evidence under the subrun state dir. Required locations: `eudrs_u/evidence/` (must contain exactly one `eudrs_u_promotion_summary_v1.json`) and `eudrs_u/staged_registry_tree/` (must contain a staged registry tree with the prefix `polymath/registry/eudrs_u/...`).
*   The promotion summary must reference `proposed_root_tuple_ref` (inside the staged registry tree) and `evidence.*_ref` objects (evidence blobs under `eudrs_u/evidence/`).

**Important “current repo reality” detail:**
*   In this checkout, `polymath/registry/eudrs_u/` does not yet exist at the repo root, even though EUDRS-U verifiers and orchestrators reference it as the eventual activated location.
*   The EUDRS-U promotion verifier is written to handle “no active pointer exists yet”: on the first activation, the root tuple epoch must be `0`. After an active pointer exists at `polymath/registry/eudrs_u/active/active_root_tuple_ref_v1.json`, epochs must increment by exactly `+1`.

Repo-spec references for the formal EUDRS-U contract live in `AGENTS.md`, `docs/eudrs_u/EUDRS_U_v1_0_SCIENTIST_HANDOFF.md`, and `docs/eudrs_u/EUDRS_U_v1_0_SPEC_OUTLINE.md`. The full repo-anchored implementation spec is captured in `EUDRS-U v1.0 + QXWMR v1.0 + QXWMR v2 (MCL) — Repo-Anchored Implementation Specification.md`, with a companion substrate spec in `QXRL v1.0 — Quantized eXact Replay Learning Substrate.md`.

### 18.6 Where The Stack Is Heading (Observed From Code + Packs + Verifiers)
The repo’s current direction is not “more campaigns” or “more heuristics”; it is a consolidation around **rooted, replay-verifiable state transitions** where every durable claim is backed by a small set of canonical entrypoints:

*   **From patch-centric to root-centric promotions:** promotions increasingly aim to update compact roots (axis bundles, EUDRS-U root tuples) that point to large bodies of evidence and CAS artifacts, rather than promoting large piles of ad-hoc files.
*   **From narrative logs to diffable evidence:** v19 adds ladder/gate artifacts and post-run level-attainment reporting; EUDRS-U adds a single required promotion summary entrypoint so third parties can replay-check without chasing logs.
*   **From “search over code” to “deterministic learning substrates”:** SH-1 + CCAP cover proposal generation and universal scoring for code/config; EUDRS-U/QXRL/QXWMR/ML-index is the path toward deterministic, promotion-gated learning and retrieval that can evolve across epochs.
*   **From harness-only proofs to real-loop proofs:** the repo now includes real-loop runners under `tools/v19_runs/` (for example `tools/v19_runs/run_omega_v19_full_loop.py`) and regression tests that lock down determinism-critical wiring like “promotion/subverification must run from subrun CWD”.

---

**Document End**
