# AGI-Stack-Unchained: The Source of Truth

## A Complete Reconstruction Manual for the System's Mental Model

**Version**: v19.0 (Super-Unified) | **Generated**: 2026-02-18 | **Scope**: Full Codebase  
**Word Count Target**: 30,000+ words  
**Purpose**: Enable an external intelligence to reconstruct the project's mental model — its intent, architecture, and hidden mechanics — without access to the raw source files.

---

## Table of Contents

1. [Layer 1: Architectural Philosophy & High-Level Design](#layer-1-architectural-philosophy--high-level-design)
   - 1.1 [The Core Thesis](#11-the-core-thesis)
   - 1.2 [The Ring Architecture (RE1–RE4)](#12-the-ring-architecture-re1re4)
   - 1.3 [Deterministic Substrate & Content Addressing](#13-deterministic-substrate--content-addressing)
   - 1.4 [The Fail-Closed Doctrine](#14-the-fail-closed-doctrine)
   - 1.5 [Repository Topology](#15-repository-topology)
   - 1.6 [Evolution Through Versioning](#16-evolution-through-versioning)
2. [Layer 2: The "Life of the System" (Control Flow)](#layer-2-the-life-of-the-system-control-flow)
   - 2.1 [The Omega Daemon Tick Lifecycle](#21-the-omega-daemon-tick-lifecycle)
   - 2.2 [Observation Phase](#22-observation-phase)
   - 2.3 [Diagnosis Phase](#23-diagnosis-phase)
   - 2.4 [Decision Phase](#24-decision-phase)
   - 2.5 [The Bid Market (Predation Market)](#25-the-bid-market-predation-market)
   - 2.6 [Execution & Dispatch Phase](#26-execution--dispatch-phase)
   - 2.7 [Promotion Phase](#27-promotion-phase)
   - 2.8 [Activation Phase](#28-activation-phase)
   - 2.9 [Verification as Replay](#29-verification-as-replay)
   - 2.10 [The Runaway Escalation Protocol](#210-the-runaway-escalation-protocol)
   - 2.11 [The Ignite Loop](#211-the-ignite-loop)
3. [Layer 3: Data Topography & State Management](#layer-3-data-topography--state-management)
   - 3.1 [The Content-Addressed Universe](#31-the-content-addressed-universe)
   - 3.2 [The State Object](#32-the-state-object)
   - 3.3 [The Campaign Pack System](#33-the-campaign-pack-system)
   - 3.4 [The Authority Pin System](#34-the-authority-pin-system)
   - 3.5 [Schemas & the Genesis Specification Layer](#35-schemas--the-genesis-specification-layer)
   - 3.6 [The Polymath Domain Registry](#36-the-polymath-domain-registry)
   - 3.7 [Q32 Fixed-Point Arithmetic](#37-q32-fixed-point-arithmetic)
   - 3.8 [Artifact Flow Through the System](#38-artifact-flow-through-the-system)
4. [Layer 4: The "Immune System" (Trust & Verification)](#layer-4-the-immune-system-trust--verification)
   - 4.1 [The Trust Hierarchy](#41-the-trust-hierarchy)
   - 4.2 [meta-core: The Constitutional Guardian](#42-meta-core-the-constitutional-guardian)
   - 4.3 [CDEL-v2: The Verification Engine](#43-cdel-v2-the-verification-engine)
   - 4.4 [The CCAP Protocol](#44-the-ccap-protocol)
   - 4.5 [The Allowlist Firewall](#45-the-allowlist-firewall)
   - 4.6 [v19.0 Federation: Treaties, Continuity & Worlds](#46-v190-federation-treaties-continuity--worlds)
   - 4.7 [Objective J: The Dominance Function](#47-objective-j-the-dominance-function)
   - 4.8 [Genesis Engine SH-1: Controlled Self-Modification](#48-genesis-engine-sh-1-controlled-self-modification)
5. [Layer 5: Operational Mechanics & Tooling](#layer-5-operational-mechanics--tooling)
   - 5.1 [The Orchestrator](#51-the-orchestrator)
   - 5.2 [Campaign Configuration](#52-campaign-configuration)
   - 5.3 [Environment Variables & Runtime Configuration](#53-environment-variables--runtime-configuration)
   - 5.4 [The Polymath Lifecycle](#54-the-polymath-lifecycle)
   - 5.5 [Extension-1: The Proposer Layer](#55-extension-1-the-proposer-layer)
   - 5.6 [Operational Playbook](#56-operational-playbook)
   - 5.7 [The Native Module Router](#57-the-native-module-router)
   - 5.8 [The Skill System](#58-the-skill-system)
   - 5.9 [Self-Optimize-Core Campaign](#59-self-optimize-core-campaign)
   - 5.10 [Phase0 CCAP & Survival Drill](#510-phase0-ccap--survival-drill)
6. [Layer 6: The EUDRS-U Stack — Unified Hypothesis for Embodied Intelligence](#layer-6-the-eudrs-u-stack--unified-hypothesis-for-embodied-intelligence)
   - 6.1 [What Is EUDRS-U?](#61-what-is-eudrs-u)
   - 6.2 [The Root Tuple](#62-the-root-tuple-eudrs-us-state-object)
   - 6.3 [The DMPL Runtime](#63-the-dmpl-runtime-deterministic-machine-planning--learning)
   - 6.4 [The QXRL Training System](#64-the-qxrl-training-system-deterministic-neural-training)
   - 6.5 [The Vision Pipeline](#65-the-vision-pipeline-deterministic-perception)
   - 6.6 [The CAC/UFC Certificates](#66-the-cacufc-certificates-verified-advantage--utility)
   - 6.7 [The ML-Index](#67-the-ml-index-deterministic-retrieval-infrastructure)
   - 6.8 [The Ontology](#68-the-ontology-hierarchical-concept-management)
   - 6.9 [The SLS-VM](#69-the-sls-vm-strategy-execution-engine)
   - 6.10 [The URC-VM](#610-the-urc-vm-universal-reasoning-capsule-vm)
   - 6.11 [The VPVM STARK Prover](#611-the-vpvm-stark-prover-proof-carrying-code)
   - 6.12 [EUDRS-U Campaigns & Verification](#612-eudrs-u-campaigns--verification)
   - 6.13 [Why EUDRS-U Matters](#613-why-eudrs-u-matters)

---

# Layer 1: Architectural Philosophy & High-Level Design

## 1.1 The Core Thesis

The AGI-Stack-Unchained repository implements a **self-improving autonomous system** that can modify its own code, evaluate those modifications against formal criteria, and either adopt or reject them — all without human intervention. The central design challenge this system solves is: *How do you let a system rewrite itself without losing control?*

The answer is a layered architecture of decreasing trust, where inner layers verify outer layers, and no layer can modify a layer closer to the core than itself. This is not merely a software architecture pattern — it is a **constitutional system**. The innermost layer (`meta-core`) acts as an unchangeable constitution. The next layer out (`CDEL-v2`) acts as a judiciary, interpreting and enforcing the constitution's rules through deterministic replay. The outermost layers (`Extension-1`, proposers) act as the legislature, proposing changes that must pass judicial review before taking effect.

The reasoning behind this architecture is rooted in a specific threat model: the system must protect against its own creativity. As an autonomous self-improving system, it will inevitably generate modifications that, if applied unchecked, could compromise its verification infrastructure, corrupt its state, or drift from its objectives. Every design decision in the codebase flows from this single concern.

The system's name — "Unchained" — is deliberately ironic. The system achieves freedom through constraint. By binding itself to constitutional rules that cannot be self-modified, the system gains the freedom to safely modify everything else. This is the fundamental paradox the architecture resolves.

## 1.2 The Ring Architecture (RE1–RE4)

The system is organized into four concentric "Runtime Envelope" layers, numbered RE1 (innermost, most trusted) through RE4 (outermost, untrusted). This numbering is not arbitrary — it reflects a strict trust gradient where each layer's output is treated as adversarial input by every layer closer to the core.

### RE1: meta-core — The Trusted Computing Base (TCB)

**Location**: `meta-core/`  
**Language**: Python (engine) + Rust (kernel verifier)  
**Role**: The unchangeable constitutional bedrock.  
**Trust Level**: Absolute. This is the only code the system trusts unconditionally.

meta-core is the smallest, most auditable component. Its responsibilities are deliberately narrow:

1. **Bundle integrity verification**: Every proposed system change is packed into a "bundle" — a directory of content-addressed JSON artifacts. meta-core verifies that every file in the bundle matches its declared SHA-256 hash, that the bundle's Merkle root is correctly computed, and that no undeclared files are present. This is implemented in `meta-core/engine/activation.py` through the `stage_bundle()` function, which ingests a raw bundle directory, computes its canonical hash tree, and stages it for review.

2. **Constitutional constraint enforcement**: meta-core maintains a set of invariants — properties the system must always satisfy. These are checked during the `verify_staged()` phase, where the Rust-based kernel verifier examines the bundle against the constitution. The constitution includes rules about what paths can be modified, what schema versions are acceptable, and what state transitions are legal.

3. **Parent-chain continuity**: Every bundle references its predecessor via a hash pointer. meta-core verifies that this chain is unbroken — that the bundle's declared parent hash matches the hash of the currently active state. This prevents "fork attacks" where a compromised proposer generates bundles from a different timeline. The chain enforcement happens in `commit_staged()`, which atomically writes the new state only if the parent hash still matches.

4. **Atomic activation**: The `commit_staged()` function uses crash-safe atomic filesystem writes (via `atomic_write_text`) to ensure that the system is never in a half-updated state. Either the full bundle is committed, or the previous state is preserved. There is an explicit failpoint (`FAILPOINT_AFTER_PREV_WRITE`) that tests crash recovery between writing the previous-state pointer and writing the new active state.

5. **Rollback**: The `rollback_active()` function can revert to the previous state at any time. Every commit records the previous state hash, making rollback a simple pointer swap. Rollback generates a ledger entry (via `make_rollback_entry`) that is appended crash-safe to the audit log.

The meta-core runtime lifecycle follows a strict seven-phase sequence: **Stage → Verify → Canary → Commit → Apply → Audit → Rollback**. Each phase has a single entry point function in `activation.py`. The canary phase (`canary_staged()`) is particularly sophisticated — it performs a dry-run application of the bundle to detect filesystem conflicts, permission issues, or schema mismatches before committing. This is a defense-in-depth measure: even if the verifier passes a bundle, the canary can catch environmental issues that weren't modeled.

The reasoning behind making meta-core so minimal is the halting problem applied to trust: you cannot verify a verifier with the same verifier, because the verification is circular. By making meta-core small enough to audit by hand (the Rust kernel is designed to be formally verifiable), the system breaks the circular dependency. Everything else in the system — including the 50,000+ lines of CDEL-v2 verification code — is treated as potentially compromised.

### RE2: CDEL-v2 — The Certified Execution Layer

**Location**: `CDEL-v2/`  
**Language**: Python  
**Role**: Deterministic verification of all system operations.  
**Trust Level**: Verified by RE1. Contains ~80,000+ lines of verification code across 60+ distinct verifiers.

CDEL-v2 is the workhorse of the system. Its name — "Certified Definitional Extension Ledger" — reveals its heritage: it began as a formal system for defining and verifying extensions to a base logic, and evolved into a general-purpose verification framework.

The key insight behind CDEL-v2's design is **verification through replay**. Rather than checking properties of a result, CDEL-v2 re-executes the computation that produced the result and verifies that its replay produces identical output. This is why determinism is so critical — if every computation is deterministic, then replaying it with the same inputs must produce the same outputs. Any divergence indicates corruption or tampering.

CDEL-v2 is organized into **43 version directories** (`v1_5r` through `v19_0`), each containing verifiers for the campaigns that were current at that version. This accumulation is deliberate — older verifiers are never deleted, because older state bundles still reference them. The system must be able to verify any historical state, not just the current one.

The current apex versions are:
- **v18.0**: Contains the Omega daemon verifier (`verify_rsi_omega_daemon_v1.py`, 96,356 bytes), the CCAP universal verifier (`verify_ccap_v1.py`, 33,700 bytes), the bid market verifier, native module verifier (`verify_rsi_omega_native_module_v0_1.py`, 11,832 bytes), Polymath verifiers, self-optimize verifier, and the complete EUDRS-U verification surface (88 files, 250KB+ of verification code). The v18.0 directory alone contains 70+ core files and 13 subdirectories.
- **v19.0**: Extends v18.0 with federation capabilities — treaty checking (31,362 bytes), continuity verification (22,937 bytes), objective J dominance gating, and world snapshot integrity through the Sealed Ingestion Protocol (SIP).

### RE3: Extension-1 — The Proposer Layer

**Location**: `Extension-1/`  
**Language**: Python  
**Role**: Generate candidate system modifications.  
**Trust Level**: Untrusted. All outputs are verified by RE2 before acceptance.

Extension-1 contains the "creative" components of the system — the modules that propose changes. It includes:

- **Genesis Engine SH-1** (`tools/genesis_engine/`): The current primary proposer. Uses receipt-driven meta-learning to generate code patches. This is where the system's self-improvement actually originates.
- **CAOE v1.1** (`Extension-1/caoe_v1/`): The legacy proposer. Implements a Wake/Sleep/Dawn cycle for autonomous code evolution.
- **self_improve_code_v1** (`Extension-1/self_improve_code_v1/`): An automated code improvement module.

The critical security property of RE3 is that it **cannot modify anything in RE1, RE2, or RE4**. This is enforced by the CCAP patch allowlist (`authority/ccap_patch_allowlists_v1.json`), which explicitly forbids modifications to `authority/`, `meta-core/`, `CDEL-v2/`, `Genesis/`, `.git/`, and `runs/` directories. RE3 can only propose changes to `orchestrator/`, `tools/genesis_engine/`, `tools/omega/`, `polymath/registry/`, and `campaigns/`. This means the system can improve its operational tooling and campaign configurations, but can never modify its own verification infrastructure.

### RE4: Genesis — The Specification Layer

**Location**: `Genesis/`  
**Language**: JSON schemas, protocol specifications, conformance tests  
**Role**: Define the normative contracts that all components must satisfy.  
**Trust Level**: Specification-only. Cannot contain executable code.

Genesis provides the "type system" for the entire stack. It contains 532+ JSON schema files across versioned directories, 28 protocol specification documents, conformance test harnesses, and test vectors for canonical JSON. Every artifact that flows through the system — observation reports, decision plans, promotion bundles, CCAP receipts — has a schema defined in Genesis.

The reasoning behind separating specifications from implementation is twofold: it makes the specifications independently auditable (you can read the schema without understanding the Python implementation), and it prevents specification drift (changes to a verifier cannot silently change the schema, because the schema is in a different directory with different modification rights).

## 1.3 Deterministic Substrate & Content Addressing

The system's most fundamental technical decision is **total determinism**. Every computation, from metric observation to decision-making to patch generation, must be deterministic — the same inputs must always produce the same outputs, down to the bit level. This is not a performance optimization; it is a security requirement. Determinism enables verification-by-replay, which is the foundation of the entire trust architecture.

### GCJ-1 Canonical JSON

**Implementation**: `CDEL-v2/cdel/v1_7r/canon.py`

All JSON in the system is serialized using GCJ-1 (Guaranteed Canonical JSON, version 1). This means:

1. **UTF-8 encoding** — no BOM, no alternative encodings.
2. **Keys sorted alphabetically** — `{"a":1,"b":2}` is canonical; `{"b":2,"a":1}` is not.
3. **No trailing whitespace** — every line is trimmed.
4. **LF line endings** — no CRLF, no CR.
5. **Minimal 2-space indent formatting** — consistent across all platforms.

The reasoning is that JSON serialization is non-deterministic by default — languages like Python do not guarantee key ordering in dictionaries (prior to 3.7's insertion-order guarantee, and even then, insertion order varies by construction path). By canonicalizing every JSON document before hashing, the system ensures that semantically identical documents always produce the same SHA-256 hash.

The `canon_bytes()` function is the single serialization chokepoint. Every artifact that needs to be hashed goes through `canon_bytes()` first. The hash is then computed as `sha256_prefixed()`, which returns a string of the form `sha256:<hex_digest>`. This prefix-based format is used throughout the system to identify hash algorithms, enabling future migration to stronger hash functions.

### Q32 Fixed-Point Arithmetic

**Implementation**: `CDEL-v2/cdel/v18_0/omega_common_v1.py`

All numerical computations use Q32 fixed-point arithmetic instead of IEEE 754 floating-point. Q32 represents numbers as 32-bit signed integers where the implicit decimal point is at position 32 (i.e., the integer value represents the number multiplied by 2³²).

- **Range**: Approximately ±2.15 billion (as fixed-point: roughly ±0.5 to ±0.5)
- **Precision**: ~2⁻³² ≈ 2.33 × 10⁻¹⁰ (about 9 decimal digits)
- **Operations**: `q32_from_float()`, `q32_to_float()`, `q32_mul()`, `q32_div()`

The reasoning is that floating-point arithmetic is platform-dependent. Different CPUs, compiler settings, and math library versions can produce different rounding results for the same computation. Q32 eliminates this entirely — integer arithmetic is identical on every platform. The cost is reduced precision and range, but the system's computations (scores, ratios, thresholds) don't require the dynamic range of floating-point.

This is a subtle but critical design decision. Without Q32, two verifiers running on different machines could compute different scores for the same observation, leading to non-deterministic verification outcomes. Q32 makes the system's mathematics as portable as its JSON serialization.

### SHA-256 Content Addressing

Every artifact in the system is identified by its SHA-256 hash. This means:
- **Immutability**: An artifact's content is bound to its identifier. Changing the content changes the hash.
- **Deduplication**: Identical artifacts automatically share the same identifier.
- **Integrity**: Corruption is detectable — recomputing the hash reveals any modification.
- **History**: State transitions are recorded as hash chains, where each state references its predecessor.

The system stores artifacts in a content-addressed store (`meta-core/store/`, `polymath/store/blobs/sha256/`) where the filename is the hash. This pattern — borrowed from Git's object store — enables efficient verification: to check an artifact's integrity, you just hash its bytes and compare to its filename.

## 1.4 The Fail-Closed Doctrine

Every component in the system follows a **fail-closed** policy: when encountering any unexpected condition — malformed input, missing files, schema violations, arithmetic overflow, or internal errors — the system rejects the operation rather than attempting to recover. This is implemented through a custom exception class `OmegaV18Error` (defined in `omega_common_v1.py`) that is used for all fail-closed exits.

The reasoning is that fail-open systems are vulnerable to exploitation. If a verifier falls back to "accept" on error, an attacker (or a creative proposer) can craft inputs that trigger errors in the verification path, bypassing checks. Fail-closed makes the system conservative: it may reject valid operations, but it will never accept invalid ones.

This philosophy is so deeply embedded that the CDEL-v2 README explicitly states it as the first principle: "All verifiers default to rejection on any error."

## 1.5 Repository Topology

The repository's directory structure is not arbitrary — it mirrors the RE1-RE4 trust hierarchy:

```
AGI-Stack-Unchained/
├── meta-core/                 # RE1: Trust root (TCB)
│   ├── engine/               # Python activation engine
│   ├── kernel/verifier/      # Rust-based constitutional verifier
│   ├── active/               # Currently active state (single source of truth)
│   ├── stage/                # Staging area for proposed bundles
│   ├── store/                # Content-addressed artifact store
│   ├── cli/                  # Command-line interface
│   └── scripts/              # Maintenance scripts
│
├── CDEL-v2/                   # RE2: Verification layer
│   └── cdel/
│       ├── v1_5r/ ... v18_0/ # 43 version directories, 60+ verifiers
│       ├── v19_0/            # Federation extension
│       │   ├── federation/   # Treaty verification
│       │   ├── continuity/   # Overlap continuity checking
│       │   └── world/        # World snapshot + SIP
│       └── v1_7r/canon.py    # GCJ-1 canonical JSON (shared)
│
├── Extension-1/               # RE3: Proposer layer (untrusted)
│   ├── caoe_v1/              # Legacy: Wake/Sleep/Dawn evolution
│   ├── agi-orchestrator/     # High-level orchestration
│   └── self_improve_code_v1/ # Automated code improvement
│
├── Genesis/                   # RE4: Specification layer
│   ├── schema/               # 532+ JSON schemas
│   ├── docs/                 # 28 protocol specifications
│   ├── conformance/          # Black-box test harness
│   └── test_vectors/         # Canonicalization test vectors
│
├── authority/                 # Trust anchors (pins, kernels, allowlists)
│   ├── authority_pins_v1.json
│   ├── ccap_patch_allowlists_v1.json
│   └── evaluation_kernels/
│
├── orchestrator/              # Campaign coordination
│   ├── omega_v18_0/          # v18 Omega coordinator
│   ├── omega_v19_0/          # v19 Omega coordinator
│   └── common/               # Shared utilities
│
├── tools/                     # Operational tooling
│   ├── genesis_engine/       # SH-1 symbiotic optimizer
│   ├── omega/                # Omega operational tools
│   └── polymath/             # Domain discovery tools
│
├── campaigns/                 # Campaign configuration packs (86+ campaigns)
├── polymath/                  # Domain registry and store
├── domains/                   # Conquered domain data
├── runs/                      # Execution run outputs
├── ignite_runaway.sh          # Top-level runaway loop
└── daemon/                    # Daemon state directories
```

The `authority/` directory deserves special attention. It sits outside the RE1-RE4 hierarchy but serves as the **root of trust for all trust decisions**. It contains the cryptographic pins that bind the system together — the SHA-256 hashes of the active evaluation kernel, operator pool, sandbox profile, constitution state, and verifier state. When a CCAP verifier checks whether a patch is allowed, it retrieves the allowlist hash from `authority_pins_v1.json`, loads the allowlist, and verifies its hash matches the pin. This chain-of-trust mechanism ensures that even if an attacker modifies the allowlist file, the pin mismatch will cause fail-closed rejection.

## 1.6 Evolution Through Versioning

The CDEL-v2 version directory structure (`v1_5r`, `v2_0`, ..., `v18_0`, `v19_0`) reveals the system's evolutionary history. Each version introduced new capabilities:

| Version Range | Era | Key Innovation |
|---|---|---|
| v1.5r–v6.0 | Foundation | Basic definitional extensions, constraint solving |
| v7.0 | Alignment | First alignment verifier |
| v10.0 | Model Genesis | Model-level code generation |
| v11.0–v11.3 | Architecture Synthesis | Automated architecture proposals |
| v12.0 | SAS Code | Self-Amending System code verification |
| v13.0 | SAS Science | Scientific theory discovery validation (1,124 lines) |
| v14.0 | SAS System | System-level self-amendment |
| v15.0 | SAS Kernel | Kernel-level verification |
| v16.0–v16.1 | SAS Metasearch | Search optimization |
| v17.0 | SAS VAL | Native code lift verification |
| v18.0 | **Omega Daemon + CCAP** | Fully autonomous tick-based daemon with universal patch verification |
| v19.0 | **Federation** | Multi-system treaty verification, continuity, world snapshots |

The v18.0 transition is the most significant inflection point. Before v18.0, the system was a collection of independent Self-Amending System (SAS) campaigns, each with its own verifier. v18.0 unified everything under the Omega daemon — a single tick-based controller that orchestrates all campaigns through a unified observation/decision/execution/promotion/activation pipeline. This unification is why v18.0 is by far the largest version, with the Omega daemon verifier alone spanning 1,886 lines.

v19.0 represents the next evolutionary leap: **federation**. The system can now verify not just its own internal consistency, but its relationship with other systems (or other instances of itself). Treaty verification ensures that when two systems interact, their shared artifacts remain compatible. Continuity checking ensures that regime transitions (version upgrades) preserve overlap semantics — that artifacts valid under the old regime remain valid under the new one. World snapshots provide an auditable, tamper-proof view of the system's state at any point in time.

---

# Layer 2: The "Life of the System" (Control Flow)

## 2.1 The Omega Daemon Tick Lifecycle

The Omega daemon is the heartbeat of AGI-Stack. Starting at v18.0, all system activity is organized into discrete **ticks** — atomic units of work where the system observes its world, decides what to do, executes a campaign, verifies the result, and optionally commits the change. Each tick is a complete observe-decide-execute-promote-activate cycle. There are no background processes, no asynchronous callbacks, no event-driven subscriptions. Every tick is a single-threaded, deterministic, replayable unit.

The reasoning for this tick-based architecture is auditability. Each tick produces a complete, self-contained artifact directory that contains every input, intermediate result, and output. A verifier can replay any tick from its artifact directory and confirm that the same outputs would be produced. This makes the system's entire history auditable at any granularity.

A single tick progresses through these phases (each implemented as a separate module in `CDEL-v2/cdel/v18_0/`):

```
OBSERVE -> DIAGNOSE -> DECIDE -> DISPATCH -> EXECUTE -> PROMOTE -> ACTIVATE -> VERIFY
```

State flows forward through this pipeline as immutable data structures. Each phase reads the output of the previous phase and produces its own output. No phase can modify the output of a prior phase.

## 2.2 Observation Phase

**Module**: `omega_observer_v1.py` (48,672 bytes) | **Entry**: `observe()`

The observation phase collects metrics from across the system and assembles them into a canonical observation report. This report is the system's sensory input — everything the daemon knows about the world at the start of a tick.

The observer gathers data from multiple sources: metasearch metrics, hotloop performance indicators, science campaign results, Polymath domain coverage ratios and void scores, and Genesis Engine promotion density (PD) and exploration score (XS). Each metric source is read through deterministic path resolution — the observer reads from specific well-known paths, not directory scans. If a path doesn't exist, the observer records a null observation rather than failing.

The observer also computes the system's **capability frontier** — a rolling window of recent performance tracking whether capabilities are improving, stagnating, or regressing. Window sizes are fixed per campaign to prevent gaming. All arithmetic uses Q32 for bit-exact reproducibility.

A subtle mechanic: the observer reads previous ticks' observation reports to compute delta values, creating temporal awareness. The daemon sees trajectories, not just snapshots. The number of historical ticks consulted is bounded by constants (`WINDOW_SIZE_CAP_FRONTIER`).

## 2.3 Diagnosis Phase

**Module**: `omega_diagnoser_v1.py` (253 lines) | **Entry**: `diagnose()`

The diagnoser analyzes the observation report against current objectives to identify issues: capability regression, stalled campaigns, resource exhaustion, metric anomalies. Each issue is assigned a severity (`CRITICAL`, `WARNING`, `INFO`). The diagnosis is fully deterministic.

The separation from decision-making is intentional: the diagnoser identifies *what* is wrong; the decider determines *what to do about it*. This prevents diagnostic logic from being influenced by action preferences.

## 2.4 Decision Phase

**Module**: `omega_decider_v1.py` (32,879 bytes) | **Entry**: `decide()`

The decision phase is the daemon's brain. Given observation, diagnosis, state, policy, and campaign registry, it selects the next action through a multi-stage pipeline:

1. **Rule Matching**: Observations are compared against policy rules in priority order. The first matching rule determines the action template.
2. **Goal Selection**: A **goal queue** — an ordered list of objectives — is consulted. The highest-priority active goal parameterizes the selected template.
3. **Campaign Routing**: The goal's `campaign_id` maps to a specific campaign from the registry.
4. **Temperature Bands**: A temperature-band system balances exploration vs. exploitation. High temperature (high XS) -> exploratory campaigns; low temperature (high PD) -> exploitation of known-good patterns. Temperature is computed deterministically, never from random generators.
5. **Tie-Breaking**: When campaigns match equally, a deterministic hash-based tie-breaking path is computed and recorded in the `tie_break_path` field.

Under **runaway mode**, the decider's behavior changes significantly: escalation levels override normal goal selection, forcing capability-expansion campaigns at increasing intensity.

## 2.5 The Bid Market (Predation Market)

**Module**: `omega_bid_market_v1.py` (817 lines, 31,696 bytes) | **Entry**: `select_winner()`, `settle_and_advance_market_state()`

The **Bid Market** (internally called the "predation market") is a deterministic resource-allocation mechanism that replaces simple rule-based campaign selection with an economics-inspired competition. When the bid market is enabled, campaigns compete for execution by submitting bids, and the market allocates the tick to the highest-scoring bidder.

### How It Works

1. **Bid Construction** (`build_bid_v1()`): Each eligible campaign submits a bid containing:
   - `roi_q32`: Expected return-on-investment in Q32.
   - `confidence_q32`: Campaign's confidence in its ROI estimate.
   - `horizon_ticks_u64`: How many future ticks the campaign expects to need.
   - `predicted_cost_q32`: Estimated compute cost.
   All values are Q32 fixed-point for deterministic comparison.

2. **Bid Set Assembly** (`build_bid_set_v1()`): All campaign bids are collected into a canonical bid set, hash-bound to the observation report, market state, config, and registry.

3. **Winner Selection** (`select_winner()`, lines 567–700): The market ranks bids using a composite score:
   - `score_q32` = f(ROI, credibility, confidence, campaign_id)
   - Credibility is a per-campaign reputation metric that increases with successful ticks and decreases with failures.
   - Tie-breaking uses `(score desc, roi_q32 desc, credibility_q32 desc, confidence_q32 desc, campaign_id asc)` — fully deterministic.

4. **Settlement** (`settle_and_advance_market_state()`, lines 279–440): After each tick, the market settles:
   - Computes J (objective function) from the observation report.
   - Updates per-campaign bankroll based on actual vs. predicted performance.
   - Applies bankruptcy rules: campaigns that exhaust their bankroll are disabled.
   - Advances credibility scores based on outcome.
   - Emits a settlement receipt binding all inputs and outputs.

### Market State

The market maintains per-campaign state:
- `bankroll_q32`: Available budget (starts at configured initial value).
- `credibility_q32`: Reputation score (clamped to [0, Q32_ONE]).
- `streak_u64`: Consecutive wins/losses.
- `last_selected_tick_u64`: When the campaign was last chosen.

The market state is content-addressed and hash-chained, making it fully auditable and replay-verifiable. The `campaign_bid_market_toy_v1.py` provides a toy implementation for testing, with corresponding good/bad test campaigns in `campaigns/rsi_bid_market_toy_good_v1/` and `campaigns/rsi_bid_market_toy_bad_v1/`.

## 2.6 Execution & Dispatch Phase

**Module**: `omega_executor_v1.py` (12,708 bytes) | **Entry**: `dispatch_campaign()`

The executor dispatches the selected campaign through workspace materialization (isolated directory with only permitted files), pruning (stripping large binaries and historical data), subprocess execution (with controlled `PYTHONPATH` and timeouts), and output collection. The executor is deliberately simple — a launch mechanism, not a control mechanism. Intelligence lives in the decider and promoter.

## 2.7 Promotion Phase

**Module**: `omega_promoter_v1.py` (63,925 bytes — the largest module) | **Entry**: `run_promotion()`

The promotion phase is where verification meets commitment. It orchestrates multi-layer verification:

1. **Subverifier Invocation**: Campaign-type-specific verifiers are invoked via a registry mapping campaign IDs to verifier modules.
2. **CCAP Integration**: Campaigns producing code patches go through the CCAP universal verifier regardless of type.
3. **Axis Bundle Verification**: Verified outputs are packaged and submitted to meta-core for constitutional verification — the RE2-to-RE1 trust boundary crossing.
4. **v19.0 Gates**: The v19 promoter (692 lines) adds continuity gates (overlap preservation), J dominance gates (objective function must not decrease), and treaty gates (federation compatibility).
5. **Receipt Generation**: Every promotion outcome generates a canonical receipt with the decision, reason code, and cryptographic bindings to all inputs.

**Reason codes** (`CCAP_REJECTION`, `CONTINUITY_VIOLATION`, `BUDGET_EXHAUSTED`, `SCHEMA_MISMATCH`) are consumed by the Genesis Engine SH-1's receipt-driven learning system — the proposer learns from rejections.

## 2.8 Activation Phase

**Module**: `omega_activator_v1.py` (18,311 bytes) | **Entry**: `apply_activation()`, `rollback_activation()`

If promotion succeeds, activation wraps meta-core's commit process: Stage -> Canary (dry-run) -> Commit (atomic pointer swap) -> Ledger (crash-safe audit entry). Rollback is always available as a safety valve — it's an atomic pointer swap + ledger entry. Simulate mode (`OMEGA_META_CORE_ACTIVATION_MODE=simulate`) skips the actual state swap for testing.

## 2.9 Verification as Replay

**Module**: `verify_rsi_omega_daemon_v1.py` (96,356 bytes) | **Entry**: `verify()`

The Omega verifier can verify any tick by replaying the entire pipeline and confirming outputs match. It loads the observation report and confirms its hash, verifies the parent chain, replays decision logic, confirms execution outputs match schemas, and replays promotion logic. Any divergence between replay and recorded artifacts fails verification. This is the power of determinism: verification is simply re-execution.

## 2.10 The Runaway Escalation Protocol

**Module**: `omega_runaway_v1.py` (13,962 bytes)

When the system detects stagnation (flat or declining capability scores over multiple ticks), it enters runaway mode — controlled escalation through levels 0 to 5+, where each level increases compute budgets, shifts routing toward more aggressive strategies, and loosens non-constitutional constraints.

At level 5 with reason `TESTING`, the system prioritizes `OBJ_EXPAND_CAPABILITIES` and routes to the Genesis Engine SH-1 — maximum autonomy mode for active self-improvement. Critically, runaway never weakens constitutional constraints: CCAP allowlists, meta-core verification, and deterministic replay remain fully enforced.

`OMEGA_DISABLE_FORCED_RUNAWAY=1` prevents entry; `OMEGA_BLACKBOX` forces a specific level.

## 2.11 The Ignite Loop

**Script**: `ignite_runaway.sh` (307 lines)

The ignite script is the top-level entry point for autonomous operation — a bash loop executing one Omega v19.0 tick per iteration:

```bash
while :; do
  python3 -m orchestrator.rsi_omega_daemon_v19_0 \
    --campaign_pack $CAMPAIGN_PACK --out_dir $out_dir \
    --mode once --tick_u64 $tick_u64 --prev_state_dir $prev_state_dir
  emit_signals_for_tick $tick_u64 $state_dir $raw_log
  prev_state_dir=$state_dir; tick_u64=$((tick_u64 + 1))
done
```

Key behaviors: **Crash Resurrection** (retries failed ticks with `RESURRECT` signal, never exits), **Structured Signal Emission** (embedded Python parses outputs into signals: `RUNAWAY_ACTIVE`, `CAPABILITY_PRIORITY`, `REWRITE_ATTEMPT`, `CCAP_DECISION`, `REWRITE_COMMIT`, `ACTIVATION_COMMIT`, `HEARTBEAT`, `TIER_STATUS`), and **Tier Tracking** (Tier 1: system wants to self-improve; Tier 2: it generated a patch; Tier 3: the patch was accepted and activated). State chaining via `--prev_state_dir` maintains temporal continuity.

---

# Layer 3: Data Topography & State Management

## 3.1 The Content-Addressed Universe

Every persistent artifact in the AGI-Stack exists as a content-addressed object — a JSON document whose identity is its SHA-256 hash. This creates a universe of immutable, globally-unique objects. Once an artifact is created, its content can never change (changing it would change its hash, making it a different artifact).

The content-addressing chain works as follows:

1. **Raw data** (metrics, scores, configurations) is assembled into a JSON object.
2. The JSON is canonicalized using GCJ-1 (`canon_bytes()`), producing a deterministic byte sequence.
3. The bytes are hashed using SHA-256, producing a `sha256:<hex>` identifier.
4. The artifact is stored with its hash as the filename (e.g., `sha256_<hex>.omega_observation_v1.json`).

This naming convention — `sha256_<hex>.<schema_version>.json` — encodes both the content identity and the schema type in the filename. The underscore between `sha256` and the hex digest (rather than the colon used in internal references) is a filesystem-safe encoding.

**Store Locations**:
- `meta-core/store/`: Constitutional artifacts (bundles, ledger entries).
- `polymath/store/blobs/sha256/`: Domain data blobs.
- `polymath/store/receipts/`: Sealed fetch receipts.
- `polymath/store/indexes/`: Content indexes (JSONL format).
- `.omega_cache/`: Transient computation caches.
- `daemon/*/state/`: Per-campaign state directories.

The system's stores are **append-only by design** — existing blobs cannot be overwritten unless the new content's digest matches the old one (which means it's the same content). This immutability guarantee is critical for auditability: you can always reconstruct the system's state at any historical tick by collecting the referenced artifacts.

## 3.2 The State Object

**Module**: `omega_state_v1.py` (160 lines)

The Omega daemon's state is a small, highly-structured JSON object that captures the system's "brain state" between ticks. It contains:

```json
{
  "schema_version": "omega_state_v1",
  "tick_u64": 42,
  "parent_state_hash": "sha256:...",
  "active_manifest_hash": "sha256:...",
  "observation_hash": "sha256:...",
  "decision_hash": "sha256:...",
  "policy_hash": "sha256:...",
  "registry_hash": "sha256:...",
  "objectives_hash": "sha256:...",
  "goal_queue": { ... },
  "runaway_state": { ... }
}
```

**Key properties**:

- **Hash Chain**: `parent_state_hash` links each state to its predecessor, creating a blockchain-like chain. This chain is verified by meta-core during bundle commitment and makes forking detectable.

- **Bootstrapping**: When no previous state exists (tick 0), `omega_state_v1.bootstrap()` creates a genesis state with null parent hash and default configurations. This function is deterministic — the same bootstrap parameters always produce the same initial state.

- **State Advancement**: `omega_state_v1.next_state()` computes the successor state from the current state plus the tick's outputs. This is a pure function: `next_state(current_state, observation, decision, ...) -> new_state`. The new state's hash includes all input hashes, creating a commitment to the entire tick's computation.

- **Persistence**: `omega_state_v1.write_state()` writes the state using canonical JSON. `omega_state_v1.load_latest()` reads the most recent state from the state directory.

The state object is deliberately minimal — it doesn't contain observation data, decision plans, or campaign results. Instead, it contains *hashes* of those artifacts. This keeps the state small (a few hundred bytes) while maintaining cryptographic binding to all relevant data.

## 3.3 The Campaign Pack System

**Directory**: `campaigns/` (78+ campaign configurations)

Campaigns are the atomic units of work in the AGI-Stack. Each campaign is a configured instance of a campaign type, packaged as a "campaign pack" — a JSON file containing:

- `campaign_id`: Unique identifier (e.g., `rsi_ge_symbiotic_optimizer_sh1_v0_1`)
- `campaign_type`: The type of campaign (e.g., `GE_SYMBIOTIC_OPTIMIZER`)
- `verifier_module`: The CDEL-v2 verifier for this campaign type.
- `script_path`: The Python script to execute.
- `budget`: Compute budget constraints.
- `parameters`: Campaign-specific configuration.
- `schemas`: References to expected input/output schemas.

Examples of campaigns:
- `rsi_omega_daemon_v19_0_super_unified`: The super-unified Omega daemon campaign (used by ignite_runaway.sh)
- `rsi_ge_symbiotic_optimizer_sh1_v0_1`: Genesis Engine SH-1 proposer
- `rsi_polymath_scout_v1`: Polymath domain discovery
- `rsi_polymath_bootstrap_domain_v1`: Polymath domain bootstrapping
- `rsi_polymath_conquer_domain_v1`: Polymath domain conquest
- `rsi_sas_science_v13_0`: Scientific theory discovery
- `rsi_sas_code_v12_0`: Code-level self-amendment

The campaign pack system provides a level of indirection between the daemon and the actual campaign logic. The decider selects a campaign by ID; the executor loads the corresponding pack file to determine what script to run, what verifier to use, and what budget to allocate. This makes it possible to add new campaign types without modifying the daemon — you just add a new pack file and register it in the campaign registry.

## 3.4 The Authority Pin System

**File**: `authority/authority_pins_v1.json`

The authority pin system is the cryptographic root of trust. It contains SHA-256 hashes of every trusted system component:

| Pin | Purpose |
|-----|---------|
| `active_ek_id` | Active Evaluation Kernel hash |
| `active_op_pool_ids` | Active Operator Pool hashes |
| `active_dsbx_profile_ids` | Active Sandbox Profile hashes |
| `ccap_patch_allowlists_id` | CCAP Patch Allowlist hash |
| `re1_constitution_state_id` | meta-core Constitution State hash |
| `re2_verifier_state_id` | CDEL-v2 Verifier State hash |
| `toolchain_root_id` | Toolchain Merkle Root hash |
| `canon_version_ids` | Canonical version hashes (CCAP, IR, OBS, OP) |
| `env_contract_id` | Environment Contract hash |

When any component needs to verify trust in another component, it follows this chain:
1. Load `authority_pins_v1.json`.
2. Extract the relevant pin hash.
3. Load the referenced artifact (e.g., the patch allowlist).
4. Compute the artifact's SHA-256 hash.
5. Compare against the pin. If they don't match, fail closed.

This design means that even if an attacker modifies a trusted artifact, the pin mismatch will cause immediate rejection. The only way to compromise the system is to modify both the artifact *and* its pin — but the pins file itself is inside the `authority/` directory, which is forbidden from modification by the CCAP allowlist. This creates a self-reinforcing security boundary.

## 3.5 Schemas & the Genesis Specification Layer

**Directory**: `Genesis/schema/` (532+ schema files)

Every artifact in the system has a corresponding JSON schema in Genesis. Schemas define:
- Required and optional fields.
- Field types and value constraints.
- Allowed enum values.
- Inter-field dependencies.

Key schema families:
- **Omega State**: `omega_state_v1`, `omega_observation_v1`, `omega_decision_v1`
- **CCAP Protocol**: `ccap_bundle_v1`, `ccap_receipt_v1`, `ccap_refutation_cert_v1`
- **Genesis Engine**: `ge_config_v1`, `ge_pd_v1`, `ge_xs_snapshot_v1`, `ge_behavior_sig_v1`
- **Authority**: `authority_pins_v1`, `evaluation_kernel_v1`, `operator_pool_v1`, `dsbx_profile_v1`
- **Promotion**: `omega_promotion_bundle_v1`, `omega_promotion_bundle_ccap_v1`
- **Polymath**: `polymath_domain_registry_v1`, `polymath_void_report_v1`, `polymath_portfolio_v1`

Schema validation occurs at multiple checkpoints: when artifacts are created, when they're loaded, and when they're verified. The `validate_schema()` function (in `omega_common_v1.py`) performs lightweight schema checks, while the Genesis conformance harness (`Genesis/conformance/`) can perform full JSON Schema validation.

Genesis also contains 28 protocol specification documents (`Genesis/docs/`), 45 canonicalization test vectors (`Genesis/test_vectors/`), and example capsule files (`Genesis/examples/`). These provide a specification-only description of the system that is independent of any implementation.

## 3.6 The Polymath Domain Registry

**Directory**: `polymath/registry/`

The Polymath system maintains a registry of scientific domains that the system has discovered, bootstrapped, and potentially conquered:

- `polymath_domain_registry_v1.json`: Master registry of all known domains, with fields for `domain_id`, `domain_name`, `status`, `created_at_utc`, `domain_pack_rel`, `topic_ids`, `capability_id`, `ready_for_conquer`, and `conquered_b`.
- `polymath_scout_status_v1.json`: Status of the latest scouting run.
- `polymath_void_report_v1.jsonl`: JSONL file of candidate domains ranked by void score (a Q32 measure of how underexplored a domain is).
- `polymath_portfolio_v1.json`: Aggregated portfolio of conquered domains with a portfolio score.
- `void_topic_router_v1.json`: Maps topic IDs to campaign routes (e.g., `SCIENCE` -> `RSI_BOUNDLESS_SCIENCE_V9`).

The domain policy (`polymath/domain_policy_v1.json`) defines allowlist and denylist keywords for domain eligibility.

Polymath data is content-addressed and stored in `polymath/store/`, with SHA-256-indexed blobs and JSONL index files. The store is immutable — successful fetches are recorded as receipts in `polymath/store/receipts/`.

## 3.7 Q32 Fixed-Point Arithmetic

Q32 is used for all numerical computations requiring determinism. The implementation in `omega_common_v1.py` provides:

- `q32_from_float(f)`: Convert float to Q32 integer representation (multiply by 2^32, truncate).
- `q32_to_float(q)`: Convert Q32 back to float (divide by 2^32).
- `q32_mul(a, b)`: Multiply two Q32 values (multiply integers, shift right by 32).
- `q32_div(a, b)`: Divide two Q32 values (shift left by 32, then integer divide).

Q32 values appear throughout the codebase as fields with the `_q32` suffix: `void_score_q32`, `coverage_score_q32`, `portfolio_score_q32`, `budget_cost_hint_q32`, `accuracy_q32`. Count values use the `_u64` suffix: `tick_u64`, `rows_written_u64`, `topics_scanned_u64`.

The naming convention is a critical documentation mechanism. When you see `threshold_q32: 3865470566`, you know this is a Q32 fixed-point value equal to approximately `3865470566 / 2^32 ≈ 0.90` (a 90% accuracy threshold in the evaluation kernel).

## 3.8 Artifact Flow Through the System

The complete data flow for a single tick:

```
[tick N-1 state] --> OBSERVE --> observation_report
                                     |
                                     v
                              DIAGNOSE --> issues_report
                                     |
                                     v
                               DECIDE --> decision_plan
                                     |
                                     v
                              DISPATCH --> campaign_workspace
                                     |
                                     v
                              EXECUTE --> campaign_outputs
                                     |
                                     v
                              PROMOTE --> promotion_receipt
                                     |
                                     v
                             ACTIVATE --> [tick N state]

Each artifact is:
  1. Canonical JSON (GCJ-1)
  2. SHA-256 hashed
  3. Written to daemon/*/state/
  4. Hash included in successor artifacts
```

The trace hash chain binds all artifacts together: `tick_snapshot_hash` is computed from the hashes of the observation, decision, execution outputs, promotion receipt, and activation result. This single hash summarizes the entire tick's computation and is recorded in the `HEARTBEAT` signal by the ignite loop.

---

# Layer 4: The "Immune System" (Trust & Verification)

## 4.1 The Trust Hierarchy

The AGI-Stack implements a **strict, unidirectional trust hierarchy**. Trust flows inward: RE1 trusts nothing, RE2 trusts only RE1, RE3 trusts RE2 and RE1, RE4 trusts all layers. No layer can verify itself. No layer can modify a layer closer to the core.

This hierarchy is enforced at multiple levels:

- **Filesystem Access Control**: The CCAP allowlist prevents RE3 from modifying RE1, RE2, or RE4 directories. The allowlist itself is inside `authority/`, which is also forbidden from modification.
- **Cryptographic Pinning**: Authority pins bind the system's trust anchors to specific SHA-256 hashes. Modifying a trusted component without updating the pin (which is forbidden) causes immediate fail-closed rejection.
- **Verification Pipeline**: Every artifact produced by an outer layer must pass through the verification pipeline of every inner layer before acceptance. RE3 outputs go through RE2 (CDEL-v2) and then RE1 (meta-core).
- **Schema Enforcement**: RE4 (Genesis) defines the schemas that constrain all artifacts. Schema violations are caught at creation, loading, and verification time.

The key insight is that this hierarchy is **self-reinforcing**. The mechanisms that enforce the hierarchy (allowlists, pins, verifiers) are themselves protected by the hierarchy. An attacker would need to simultaneously compromise multiple independent mechanisms to breach any single trust boundary.

## 4.2 meta-core: The Constitutional Guardian

**Location**: `meta-core/engine/activation.py` (414 lines)

meta-core is the AGI-Stack's immune system's innermost barrier. Its `activation.py` module implements the full lifecycle:

### stage_bundle(meta_core_root, bundle_dir, work_dir)
Lines 71-164. Ingests a raw bundle directory and stages it for verification. Key operations:
- Reads the bundle manifest and validates its schema.
- Iterates through every declared file, computing SHA-256 hashes.
- Verifies that every hash matches the manifest's declared hash.
- Checks that no undeclared files exist in the bundle directory.
- Computes the bundle's Merkle root (recursive hash of all file hashes).
- Copies the validated bundle to the staging area.

### verify_staged(meta_core_root, stage_path, receipt_out_path)
Lines 167-212. Invokes the Rust kernel verifier to check constitutional constraints. The kernel verifier (`meta-core/kernel/verifier/`) checks:
- State transition legality (allowed paths, version compatibility).
- Constitutional invariant preservation.
- Parent chain validity.
The verification result is written as a receipt.

### canary_staged(meta_core_root, stage_path, work_dir)
Lines 215-288. Dry-run application to detect environmental issues before committing. Simulates the filesystem changes the bundle would make, checking for permission errors, path conflicts, and disk space issues without actually modifying the active state.

### commit_staged(meta_core_root, stage_path, receipt_path)
Lines 291-364. Atomically commits the verified bundle. Uses crash-safe atomic writes (`atomic_write_text`) to prevent half-committed states. Records the previous state hash for rollback capability. Appends a commit entry to the ledger.

### rollback_active(meta_core_root, reason=None)
Lines 367-413. Reverts to the previous state via atomic pointer swap. Records a rollback entry in the ledger with the reason.

The commit function's crash safety is worth examining closely. It uses a two-phase write:
1. Write the "previous" pointer (so rollback is possible even if the process crashes mid-commit).
2. Write the new "active" pointer.

The explicit failpoint `FAILPOINT_AFTER_PREV_WRITE` (imported from constants) allows testing what happens if the process crashes between steps 1 and 2. This level of crash-safety engineering is characteristic of database systems, not typical application code — reflecting the system's commitment to state integrity.

## 4.3 CDEL-v2: The Verification Engine

With 56 distinct verifiers across ~50,000+ lines, CDEL-v2 is the most extensive component. Its verification philosophy is simple but powerful:

**Deterministic Replay** = **Verification**

Rather than proving properties of a result, CDEL-v2 re-executes the computation and checks for bitwise identity. The replay verifier for the Omega daemon (`verify_rsi_omega_daemon_v1.py`, 1,886 lines) implements this comprehensively:

1. Load all input artifacts for the tick being verified.
2. Re-execute the observation phase with those inputs.
3. Compare the replayed observation report hash against the recorded hash.
4. Re-execute the decision phase with the replayed observation.
5. Compare the replayed decision hash against the recorded hash.
6. Continue through promotion and activation.
7. Any hash mismatch → reject.

This approach has a profound implication: **the verifier is the specification**. There is no separate specification document that the verifier checks against. The specification is the deterministic behavior of the computation itself. If you change the computation, the verifier will reject any tick computed by the old version. This is why old verifier versions are never deleted — they're needed to verify ticks computed under the old specification.

The verifier also checks structural properties:
- **Schema compliance** for every artifact.
- **Hash chain integrity** (parent references).
- **Budget compliance** (computation within declared bounds).
- **Runaway mode correctness** (proper entry/exit conditions).
- **Subverifier invocations** (correct verifier selected for campaign type).

## 4.4 The CCAP Protocol

**Module**: `verify_ccap_v1.py` (819 lines) + `ccap_runtime_v1.py` (313 lines)

CCAP (Certified Capsule Proposal) is the system's universal mechanism for verifying arbitrary code patches. It enables the Genesis Engine SH-1 (or any proposer) to generate code modifications that can be verified without the verifier needing to understand the specific intent of the patch.

### CCAP Bundle Structure

A CCAP bundle contains:
- `schema_version`: `ccap_bundle_v1`
- `ccap_id`: SHA-256 identifier
- `kind`: Patch type (e.g., `PATCH`)
- `base_tree_id`: SHA-256 of the repo state the patch applies to
- `ek_id`: Evaluation Kernel identifier (references `authority/evaluation_kernels/`)
- `op_pool_id`: Operator Pool identifier (references `authority/operator_pools/`)
- `build_recipe_id`: Build recipe for applying the patch
- `patch_blob_id`: SHA-256 of the actual diff/patch content
- `pd_id`: Promotion Density artifact reference
- `beh_id`: Behavior Signature artifact reference

### Three-Stage Verification Pipeline

1. **REALIZE**: The verifier applies the patch to a clean workspace copy. It first validates the patch against the CCAP allowlist (`authority/ccap_patch_allowlists _v1.json`) to ensure it only modifies permitted paths. The `ccap_runtime_v1.py` module provides git-based workspace operations: `materialize_snapshot()` creates a clean working copy, `apply_patch()` applies the diff, and `compute_tree_id()` computes the post-patch tree hash.

2. **SCORE**: The verifier runs the evaluation kernel referenced by the bundle's `ek_id`. The evaluation kernel is loaded from `authority/evaluation_kernels/` and defines a benchmark suite to run against the patched codebase. Scoring uses Q32 arithmetic for deterministic results.

3. **FINAL_AUDIT**: The verifier checks promotion gates defined in the evaluation kernel. For example, a gate with `kind: MIN_METRIC_Q32, metric_id: accuracy_q32, threshold_q32: 3865470566` requires that the accuracy metric exceeds ~90% (3865470566 / 2^32).

### Receipts and Refutations

If all three stages pass, the verifier emits a **CCAP receipt** (`ccap_receipt_v1`) certifying the patch. If any stage fails, it emits a **refutation certificate** (`ccap_refutation_cert_v1`) documenting the failure with a specific reason code and the exact point of failure.

The receipt/refutation mechanism is the foundation of the Genesis Engine SH-1's learning loop. SH-1 reads historical receipts and refutations to learn which types of patches succeed and which fail, adjusting its generation strategy accordingly.

## 4.5 The Allowlist Firewall

**File**: `authority/ccap_patch_allowlists_v1.json`

The CCAP allowlist is the system's filesystem-level access control:

```json
{
  "allow_prefixes": [
    "orchestrator/",
    "tools/genesis_engine/",
    "tools/omega/",
    "polymath/registry/",
    "campaigns/"
  ],
  "forbid_exact_paths": [
    "tools/omega/omega_benchmark_suite_v1.py",
    "authority/authority_pins_v1.json",
    "authority/evaluation_kernels/ek_active_v1.json"
  ],
  "forbid_prefixes": [
    "authority/",
    "meta-core/",
    "CDEL-v2/",
    "Genesis/",
    ".git/",
    "runs/",
    ".omega_cache/"
  ]
}
```

**Evaluation order**: Forbid rules take precedence over allow rules. A path must match at least one allow prefix and must not match any forbid prefix or exact path. This means:

- `tools/genesis_engine/ge_config_v1.json` → **ALLOWED** (matches `tools/genesis_engine/`, no forbid match)
- `authority/authority_pins_v1.json` → **FORBIDDEN** (matches `authority/` forbid prefix AND exact forbid path)
- `CDEL-v2/cdel/v18_0/verify_ccap_v1.py` → **FORBIDDEN** (matches `CDEL-v2/` forbid prefix)
- `meta-core/engine/activation.py` → **FORBIDDEN** (matches `meta-core/` forbid prefix)
- `tools/omega/omega_benchmark_suite_v1.py` → **FORBIDDEN** (matches exact forbid path, despite `tools/omega/` being allowed)

The last case is particularly interesting: the benchmark suite is explicitly protected even though its parent directory is allowed. This prevents a self-improving system from manipulating its own evaluation criteria — the benchmarks that determine whether patches are accepted cannot themselves be patched.

The allowlist's own hash is pinned in `authority_pins_v1.json` (`ccap_patch_allowlists_id`), creating a cryptographic guarantee that the allowlist hasn't been tampered with.

## 4.6 v19.0 Federation: Treaties, Continuity & Worlds

v19.0 introduces three interconnected verification subsystems for multi-system federation:

### Treaties (federation/check_treaty_v1.py — 825 lines)

A **treaty** defines the interoperability contract between two systems (or two versions of the same system). Treaty verification ensures that both parties agree on:
- **Overlap artifacts**: Which artifacts are shared between systems.
- **Translator bundles**: JSON Pointer-based operations that transform artifacts from one system's format to another's. Operations include `set` (create/replace value), `remove` (delete value), and `copy` (duplicate value). Each operation targets a specific JSON Pointer path within the artifact.
- **Totality certificates**: Proofs that every overlap artifact can be successfully translated in both directions (source→target via φ, target→source via ψ).
- **Refutation interop**: Verification that refutation certificates from one system are interpretable by the other.
- **ICAN identifiers**: `ok_ican_v1.py` provides canonical identifiers (ICAN = Interoperable Canonical Artifact Name) for cross-system artifact references.

The `check_treaty()` function (lines 349-821) orchestrates the full treaty verification pipeline, including overlap subset validation, bidirectional translation checks, totality certificate construction, and budget enforcement.

### Continuity (continuity/check_continuity_v1.py — 570 lines)

**Continuity checking** ensures that when the system upgrades from one regime (version) to another, overlap semantics are preserved. This means: if an artifact was valid under the old regime, it must remain valid (potentially after translation) under the new regime.

The `check_continuity()` function (lines 305-566) takes two regime references (old and new), two state snapshots (old and new), and a morphism reference (the translation between them). It verifies:
- The morphism correctly translates all overlap artifacts.
- Translated artifacts pass validation under both old and new regimes.
- The overlap accept set is correctly computed.

Internally, `apply_translator_bundle()` (lines 167-230) applies JSON Pointer-based transformations to translate artifacts between regimes. Operations support `set`, `remove`, `copy`, and `add` with depth limits and budget enforcement.

### World Snapshots (world/sip_v1.py — 346 lines)

The **Sealed Ingestion Protocol (SIP)** creates tamper-proof snapshots of the system's state:

The `run_sip()` function (lines 163-342) takes a manifest, artifact bytes, an SIP profile, world task bindings, and a budget specification. It:
1. Validates the manifest structure and content integrity.
2. Computes a Merkle root from all entries using `merkle_v1.compute_world_root()`.
3. Scans for information leakage using entropy analysis (`_entropy_q16()`) and forbidden pattern detection.
4. Verifies world task bindings (ensuring every task is bound to a known artifact).
5. Generates a sealed receipt binding all inputs to the computed world root.

The leakage scanner (`_scan_leakage()`, lines 56-88) is particularly interesting — it checks that ingested artifacts don't contain sensitive patterns and that their entropy doesn't exceed thresholds (high-entropy blobs might be encrypted data or binary payloads that bypass text-based policy checks).

## 4.7 Objective J: The Dominance Function

**Module**: `continuity/objective_J_v1.py` (191 lines) | **Entry**: `compute_J()`

Objective J is the system's formal measure of "goodness." When the v19 promoter checks whether a proposed state is better than the current state, it computes J for both states and requires that the new J ≥ old J (the "dominance gate").

J is a weighted sum of nine terms:

| Term | Symbol | Meaning |
|------|--------|---------|
| `UDC_BASE` | λ | Base Universal Description Complexity — cost of the system's core schedule |
| `UDC_META` | μ | Meta UDC — cost of the system's meta-level schedule |
| `INV` | ν | Invariant failures — count or weighted sum of violated invariants |
| `TDL` | α | Technical Debt Length — total size of technical debt artifacts |
| `KDL` | β | Knowledge Debt Length — total size of knowledge debt |
| `EDL` | γ | Experience Debt Length — total size of experience gap artifacts |
| `CDL` | δ | Complexity Debt Length — total size of complexity debt |
| `CoDL` | η | Coordination Debt Length — total size of coordination debt |
| `IDL` | - | Integration Debt Length — added directly without weight |

The computation:
```
J = λ*UDC_BASE + μ*UDC_META + ν*INV + α*TDL + β*KDL + γ*EDL + δ*CDL + η*CoDL + IDL
```

Debt terms (TDL, KDL, EDL, CDL, CoDL, IDL) are amortized over configurable horizons — dividing the raw debt length by the horizon to prevent large one-time debts from blocking all progress.

J's design reveals the system's values: it measures both the system's capability (UDC terms) and its technical health (debt terms). A change that improves capability but creates excessive technical debt will be rejected if the net J decreases.

The `compute_J()` function is fully deterministic and budget-tracked. Its output includes a `j_object_id` (content hash of the entire J computation), enabling verification that the dominance comparison used the correct J values.

## 4.8 Genesis Engine SH-1: Controlled Self-Modification

**Module**: `tools/genesis_engine/ge_symbiotic_optimizer_v0_3.py` (1,588 lines)

The Genesis Engine SH-1 (Symbiotic Harmony v1) is the system's primary self-improvement engine. It operates in RE3 (untrusted) and generates CCAP bundles that must pass through the full verification pipeline before acceptance.

### Receipt-Driven Meta-Learning

SH-1's defining innovation is learning from its own history. It reads historical promotion receipts and refutation certificates from `runs/` directories to compute:

- **PD (Promotion Density)**: `promotions / (promotions + rejections)` per file. High PD means a file is "hot" — changes to it tend to be accepted. Low PD means changes tend to be rejected.
- **XS (eXploration Score)**: `1.0 - PD` (simplified). High XS means the file is "cold" — it has unexplored improvement potential.
- **Behavior Signatures**: Fingerprints of patch effects that detect "novelty laundering" — patches that appear novel but are functionally equivalent to previously rejected patches.

### Bucket Planning

Based on PD/XS analysis, SH-1 allocates its patch generation budget across three buckets:

| Bucket | PD Range | Strategy | Allocation |
|--------|----------|----------|------------|
| HOTFIX | High PD | Exploit known-good files | ~20% |
| INCREMENTAL | Medium PD | Balanced exploration | ~40% |
| EXPLORATORY | Low PD, High XS | Explore untested files | ~40% |

The bucket fractions are configured in `tools/genesis_engine/ge_config_v1.json` as Q32 values.

### Template-Based Patch Generation

SH-1 generates patches using templates:
- `COMMENT_APPEND`: Add explanatory comments to files.
- `JSON_TWEAK_COOLDOWN`: Adjust cooldown parameters in campaign configs.
- `JSON_TWEAK_BUDGET_HINT`: Adjust budget hint values.

Template selection is influenced by the bucket assignment. HOTFIX patches tend to use conservative templates (COMMENT_APPEND), while EXPLORATORY patches use more aggressive parameter tweaks.

### Hard-Avoid Projection

To prevent degenerate optimization, SH-1 implements a **hard-avoid projection** system. When a patch is rejected, its behavior signature is added to an avoid list. Future patches are checked against this list — if a new patch's behavior signature is too similar to a previously rejected patch, it's filtered out before submission. This prevents the system from repeatedly submitting variations of the same bad idea (novelty laundering).

### CCAP Emission

SH-1's output is a CCAP bundle containing the generated patch, its PD/XS metrics, and its behavior signature. This bundle enters the standard CCAP verification pipeline: allowlist check → evaluation kernel scoring → promotion gate comparison → promotion or rejection.

The entire SH-1 pipeline — from receipt analysis through bucket planning, patch generation, and CCAP emission — is deterministic. Given the same historical receipts and configuration, SH-1 will always generate the same patches.

---

# Layer 5: Operational Mechanics & Tooling

## 5.1 The Orchestrator

**Directory**: `orchestrator/`

The orchestrator is the coordination layer that connects the Omega daemon's decision engine to the actual campaign infrastructure. It provides versioned entry points for each Omega version:

- `orchestrator/rsi_omega_daemon_v18_0.py`: Entry point for v18.0 ticks.
- `orchestrator/rsi_omega_daemon_v19_0.py`: Entry point for v19.0 ticks (used by `ignite_runaway.sh`).
- `orchestrator/omega_v18_0/`: v18.0-specific coordination logic (12 files).
- `orchestrator/omega_v19_0/`: v19.0-specific coordination logic (3 files).
- `orchestrator/common/`: Shared utilities (4 files).

When `ignite_runaway.sh` invokes `python3 -m orchestrator.rsi_omega_daemon_v19_0`, the orchestrator:

1. Loads the campaign pack from the specified path.
2. Initializes or loads the daemon state.
3. Calls the observation pipeline (observer + diagnoser).
4. Calls the decision pipeline (decider, including runaway logic).
5. Dispatches the selected campaign (executor).
6. Runs the promotion pipeline (promoter + subverifiers).
7. Handles activation or rollback based on promotion outcome.
8. Writes the updated state and tick artifacts.

The orchestrator also hosts specialized coordinators for different campaign families. For example, `orchestrator/rsi_sas_science_v13_0.py` coordinates scientific theory discovery campaigns, while `orchestrator/rsi_sas_kernel_v15_0.py` coordinates kernel-level verification campaigns.

Additional tools in the orchestrator:
- `omega_skill_generated_sh1_v1.py`: Skill generation for the SH-1 optimizer.
- `omega_skill_scaffold_generator_v1.py`: Scaffold generation for campaign skills.
- `verify_rsi_agi_orchestrator_llm_v1.py`: Verifier for LLM-based orchestration.

## 5.2 Campaign Configuration

Each campaign is configured through a **campaign pack** JSON file in the `campaigns/` directory. The **86+ campaigns** span multiple operational domains:

### Self-Improvement Campaigns
- `rsi_ge_symbiotic_optimizer_sh1_v0_1`: Genesis Engine SH-1 code generation.
- `rsi_omega_daemon_v18_0` / `rsi_omega_daemon_v18_0_prod`: Omega v18 daemon execution.
- `rsi_omega_daemon_v19_0` / `rsi_omega_daemon_v19_0_unified` / `rsi_omega_daemon_v19_0_super_unified`: v19 unified daemon.
- `rsi_omega_daemon_v19_0_llm_enabled`: Full LLM-integrated daemon for advanced reasoning.
- `rsi_self_optimize_core_v1`: Self-optimization of core Omega modules (hotspot patching).
- `rsi_shadow_proposal_v1`: Shadow-mode proposal testing.

### Scientific Campaigns
- `rsi_sas_science_v13_0`: Scientific theory discovery and validation.
- `rsi_boundless_science_v*`: Open-ended scientific exploration (v4 through v9).
- `rsi_boundless_math_v*`: Mathematical conjecture generation and proof.

### System Campaigns
- `rsi_sas_code_v12_0`: Code-level self-amendment.
- `rsi_sas_system_v14_0`: System-level self-amendment.
- `rsi_sas_kernel_v15_0`: Kernel-level verification.
- `rsi_sas_metasearch_v16_0` / `rsi_sas_metasearch_v16_1`: Search optimization.
- `rsi_sas_val_v17_0`: Native code lift verification.

### Polymath Campaigns
- `rsi_polymath_scout_v1`: Domain void discovery.
- `rsi_polymath_bootstrap_domain_v1`: New domain setup.
- `rsi_polymath_conquer_domain_v1`: Domain conquest and validation.

### EUDRS-U Campaigns
- `rsi_eudrs_u_vision_capture_v1`: Vision pipeline stage 0 — frame capture.
- `rsi_eudrs_u_vision_perception_v1`: Perception module execution.
- `rsi_eudrs_u_dmpl_plan_v1`: DMPL deterministic planning.
- `rsi_eudrs_u_qxrl_train_v1`: QXRL neural training replay.
- `rsi_eudrs_u_ontology_update_v1`: Ontology concept hierarchy update.
- `rsi_eudrs_u_ml_index_build_v1`: ML-Index rebuild.
- `rsi_eudrs_u_promote_v1`: EUDRS-U root-tuple promotion.

### Bid Market & Skill Campaigns
- `rsi_bid_market_toy_good_v1` / `rsi_bid_market_toy_bad_v1`: Bid-market test campaigns.
- `rsi_omega_skill_*_v1`: 11 skill campaign types (efficiency, ontology, persistence, thermo, transfer, etc.).
- `rsi_omega_native_module_v0_1`: Native module integration testing.

### Hardening & Resilience Campaigns
- `rsi_omega_phase0_immune_repair_ccap_v0_1`: Phase0 immune-system repair testing.
- `rsi_omega_phase0_victim_ccap_v0_1`: Deliberate adversarial CCAP testing.
- `rsi_survival_drill_v*`: Multi-scenario survival testing.
- `rsi_omega_daemon_hardening_v1`: Daemon hardening and stress testing.
- `rsi_omega_daemon_integrity_v*`: Integrity verification campaigns.

### Architecture Campaigns
- `rsi_arch_synthesis_v11_*`: Automated architecture proposals.
- `rsi_model_genesis_v10_0`: Model-level code generation.

Each campaign pack specifies its verifier module, ensuring that every campaign is verified by the appropriate CDEL-v2 verifier. The verifier module path is resolved by the promoter during the promotion phase.

## 5.3 Environment Variables & Runtime Configuration

The system uses environment variables for runtime configuration, keeping mutable configuration separate from the deterministic code:

### Core Variables
| Variable | Purpose |
|----------|---------|
| `AGI_ROOT` | Repository root path |
| `PYTHONPATH` | Must include `.:CDEL-v2:Extension-1/agi-orchestrator` |
| `OMEGA_META_CORE_ACTIVATION_MODE` | `simulate` or `live` — controls whether meta-core commits are real |
| `OMEGA_ALLOW_SIMULATE_ACTIVATION` | Enable/disable simulate mode |

### Runaway Variables
| Variable | Purpose |
|----------|---------|
| `OMEGA_BLACKBOX` | Force specific runaway escalation level |
| `OMEGA_DISABLE_FORCED_RUNAWAY` | Prevent all runaway mode entry |
| `OMEGA_RUN_SEED_U64` | Seed for deterministic offline fallbacks |

### Ignite Variables
| Variable | Purpose |
|----------|---------|
| `OMEGA_IGNITE_START_TICK` | Starting tick number (default: 1) |
| `OMEGA_IGNITE_OUT_ROOT` | Output directory root |
| `OMEGA_IGNITE_LOG_PATH` | Signal log file path |
| `OMEGA_IGNITE_SLEEP_SECONDS` | Pause between crash retries (default: 1) |

### Polymath Variables
| Variable | Purpose |
|----------|---------|
| `OMEGA_POLYMATH_STORE_ROOT` | Override store location |
| `OMEGA_TICK_U64` | Tick for scout/conquer reporting |
| `OMEGA_NET_LIVE_OK` | Enable live network fetches (default: cache-only) |

### Tick Variables
| Variable | Purpose |
|----------|---------|
| `OMEGA_TICK_U64` | Current tick number for tick-dependent behaviors |

## 5.4 The Polymath Lifecycle

Polymath implements autonomous domain discovery and conquest through a three-phase lifecycle:

### Phase 1: Scout
- **Script**: `tools/polymath/polymath_scout_v1.py`
- **Campaign**: `rsi_polymath_scout_v1`
- **Process**: Analyzes existing domain registry and policy rules to discover new candidate scientific domains. Computes a **void score** for each candidate — a Q32 measure of how underexplored a domain is relative to the system's knowledge. Outputs a JSONL void report ranking candidates and a scout status object.
- **Key metric**: `top_void_score_q32` — the best exploration opportunity.

### Phase 2: Bootstrap
- **Script**: `tools/polymath/polymath_domain_bootstrap_v1.py`
- **Campaign**: `rsi_polymath_bootstrap_domain_v1`
- **Process**: Takes the top candidate from the void report and creates a complete domain pack under `domains/<domain_id>/`. The domain pack includes layered data packs (L0, L1, L2), schemas, a solver, and a corpus. Updates the registry row to `ready_for_conquer=true, conquered_b=false`.
- **Content addressing**: All fetched data is stored in `polymath/store/blobs/sha256/` with SHA-256 filenames. Fetch operations are recorded as receipts in `polymath/store/receipts/`.

### Phase 3: Conquer
- **Script**: `tools/polymath/polymath_domain_corpus_v1.py` (and related)
- **Campaign**: `rsi_polymath_conquer_domain_v1`
- **Process**: Runs the system's models against the domain's corpus, producing baseline and improved outputs. Generates a conquest report comparing the system's performance against the domain's validation criteria. If conquest succeeds, the domain is marked `conquered_b=true` and added to the portfolio.
- **Key metrics**: `polymath_portfolio_score_q32`, `polymath_portfolio_domains_u64`, `polymath_portfolio_cache_hit_rate_q32`.

The Polymath lifecycle feeds back into the Omega daemon through the observation pipeline — domain coverage ratios and void scores influence the daemon's goal selection, potentially triggering more scouting when coverage drops.

## 5.5 Extension-1: The Proposer Layer

Extension-1 houses the untrusted proposer modules:

### Genesis Engine SH-1 (Active)
The primary self-improvement engine, detailed in Section 4.8. Located at `tools/genesis_engine/` with supporting modules:
- `sh1_pd_v1.py`: Promotion Density extraction from historical receipts.
- `sh1_xs_v1.py`: eXploration Score computation.
- `sh1_behavior_sig_v1.py`: Behavior signature computation for novelty detection.
- `ge_audit_report_sh1_v0_1.py`: Audit report generation for SH-1 runs.

### CAOE v1.1 (Legacy)
The Continuous Architecture Optimization Engine implements an autopoietic evolution cycle:
- **Wake Phase**: Anomaly mining — scanning the codebase for architectural inconsistencies, performance hotspots, and improvement opportunities.
- **Sleep Phase**: Candidate synthesis — generating proposed architectural changes based on wake-phase observations.
- **Dawn Phase**: Selection and learning — evaluating candidates, applying the best, and updating the system's architectural model.

CAOE represents an earlier generation of self-improvement that operated at the architectural level rather than the patch level. SH-1 superseded it for code-level modifications, but CAOE's architecture-level reasoning remains available.

### Self-Improve Code v1
An automated code improvement module with three subcomponents:
- `analyzer/`: Code analysis (identifying improvement targets).
- `transformer/`: Code transformation (generating patches).
- `validator/`: Validation logic (checking patch correctness).

### Security Constraints on Extension-1
All Extension-1 outputs are subject to:
1. **No Heldout Access** — Proposers cannot read evaluation data.
2. **Deterministic Outputs** — All candidates must be reproducible.
3. **Certificate Required** — All outputs verified by CDEL-v2.
4. **Quarantine on Failure** — Failed operators are quarantined.
5. **Forbidden Paths** — Cannot modify `authority/`, `meta-core/`, `CDEL-v2/`, `Genesis/`.

## 5.6 Operational Playbook

### Starting the System
```bash
# From repository root
export PYTHONPATH=".:CDEL-v2:Extension-1/agi-orchestrator"
./ignite_runaway.sh
```

The ignite loop will begin executing ticks, logging structured signals to `runaway_evolution.log`.

### Monitoring
- **Signal log**: `runaway_evolution.log` contains structured signals for each tick.
- **Run artifacts**: `runs/ignite_v19_super_unified_tick_NNNN/` contains full tick artifacts.
- **Tier status**: Watch for `TIER_STATUS` signals — all three tiers passing indicates successful self-improvement.

### Manual Tick Execution
```bash
python3 -m orchestrator.rsi_omega_daemon_v19_0 \
  --campaign_pack campaigns/rsi_omega_daemon_v19_0_super_unified/rsi_omega_daemon_pack_v1.json \
  --out_dir runs/manual_tick_001 \
  --mode once \
  --tick_u64 1
```

### Running Specific Campaigns
```bash
# Genesis Engine SH-1
python3 tools/genesis_engine/ge_symbiotic_optimizer_v0_3.py \
  --runs_root runs/rsi_omega_daemon_v18_0/ \
  --out_dir proposals/sh1_v0_1/

# Polymath Scout
python3 tools/polymath/polymath_scout_v1.py \
  --registry_path polymath/registry/polymath_domain_registry_v1.json \
  --store_root .omega_cache/polymath/store \
  --max_topics 12

# Polymath Domain Bootstrap
python3 -m cdel.v18_0.campaign_polymath_bootstrap_domain_v1 \
  --campaign_pack campaigns/rsi_polymath_bootstrap_domain_v1/rsi_polymath_bootstrap_domain_pack_v1.json \
  --out_dir /tmp/polymath_bootstrap_run
```

### Verification
```bash
# Verify all v18.0 Omega daemon tests
python3 -m pytest CDEL-v2/cdel/v18_0/tests_omega_daemon/ -v

# Verify CCAP tests
python3 -m pytest CDEL-v2/cdel/v18_0/tests_ccap/ -v

# Run Genesis conformance harness
cd Genesis/conformance && ./run.sh

# Validate canonical JSON test vectors
python3 Genesis/tools/validate_canon.py Genesis/test_vectors/
```

### Smoke Tests
```bash
CDEL-v2/scripts/smoke_e2e.sh
CDEL-v2/scripts/smoke_rebuild.sh
CDEL-v2/scripts/smoke_statcert_adopt.sh
```

## 5.7 The Native Module Router

**Module**: `orchestrator/native/native_router_v1.py` (595 lines, 21,122 bytes) | **Entry**: `route_native_call()`, `native_healthcheck()`

The **Native Module Router** provides a ctypes-based FFI bridge for compiled native modules (shared libraries), enabling performance-critical operations to run at native speed while remaining within the deterministic verification framework.

### Architecture

1. **ABI v1 Protocol**: Native modules expose a C ABI with structured input/output. The router handles bloblist encoding/decoding — serializing Python data into flat binary buffers, calling the native function, and deserializing the result.

2. **Shadow-Mode Dual Execution**: When a native module is first deployed, the router runs both the Python reference implementation and the native implementation in parallel, comparing outputs. Any divergence triggers an automatic disable of the native module and fallback to Python. This ensures that native compilation never introduces non-determinism.

3. **Healthcheck Vectors**: `native_healthcheck()` runs deterministic test vectors against each native module to verify correctness. Healthcheck results are content-addressed and hash-bound to the module's binary hash.

4. **Policy Registry**: A gating registry (`orchestrator/native/native_policy_v1.json`) controls which operations are eligible for native acceleration. Operations not in the registry always use the Python path.

5. **Caching & Statistics**: The router maintains a per-module LRU cache and collects runtime statistics (call count, total time, mismatch count) for observability.

Native modules are verified by `verify_rsi_omega_native_module_v0_1.py` (11,832 bytes), which replays healthcheck vectors and validates shadow-mode comparison results.

## 5.8 The Skill System

**Directory**: `CDEL-v2/cdel/v18_0/skills/` (7 files, ~21KB total)

The **Skill System** provides a generic framework for running modular analytical tasks ("skills") against the daemon's state, producing structured reports that feed back into the observation pipeline.

### Core Components

- **`skill_runner_v1.py`** (224 lines): The generic skill executor. Given a tick number, state root, config directory, and adapter module name, it:
  1. Discovers the authoritative state root (checking `OMEGA_DAEMON_STATE_ROOT_REL`, `OMEGA_DAEMON_STATE_ROOT`, or scanning `runs/`).
  2. Builds an `inputs_descriptor` by hashing the current snapshot, observation, state, trace chain, perf, stats, and scorecard.
  3. Invokes the adapter's `compute_skill_report()` function.
  4. Normalizes the output (Q32 metrics, flags, recommendations) into a canonical `omega_skill_report_v1` artifact.
  5. Writes the report content-addressed to disk.

- **Domain Adapters** (5 adapters): Each adapter implements a `compute_skill_report()` function for its domain:
  - `eff_flywheel_v2_0_adapter_v1.py`: Efficiency flywheel — measures throughput and resource utilization.
  - `ontology_v2_v1_6r_adapter_v1.py`: Ontology health — concept hierarchy completeness and stability.
  - `persistence_v6_adapter_v1.py`: State persistence — data durability and recovery readiness.
  - `thermo_v5_adapter_v1.py`: System thermodynamics — thermal budget and cooling efficiency.
  - `transfer_v1_6r_adapter_v1.py`: Knowledge transfer — cross-domain learning effectiveness.

Each skill report contains Q32 metrics (e.g., `{"throughput_q32": {"q": 2147483648}}`), boolean flags (e.g., `["HEALTHY", "BUDGET_OK"]`), and actionable recommendations (e.g., `{"kind": "OPTIMIZE", "detail": "Consider reducing batch size"}`). Skill campaigns in `campaigns/rsi_omega_skill_*_v1/` invoke these adapters through the orchestrator.

## 5.9 Self-Optimize-Core Campaign

**Module**: `campaign_self_optimize_core_v1.py` (342 lines, 12,219 bytes) | **Entry**: `run()`

The **Self-Optimize-Core** campaign enables the Omega daemon to optimize its own core modules through a controlled benchmark-driven process.

### How It Works

1. **Hotspot Identification**: The campaign scans the latest tick performance artifacts to find the slowest execution stage (highest median nanoseconds).

2. **Patch Generation**: A deterministic hotspot patch is generated targeting the identified bottleneck. The patch is constrained to only modify files within allowed prefixes (`CDEL-v2/cdel/v18_0/`, `tools/omega/`, `Genesis/schema/v18_0/`) and is explicitly forbidden from touching verifiers (`CDEL-v2/cdel/v18_0/verify_rsi_*`), meta-core engine (`meta-core/engine/`), or the kernel (`meta-core/kernel/`).

3. **Microbenchmark A/B Testing**: The campaign runs the Omega daemon for `N` ticks (default 20) on both the original and patched code, collecting timing data. It compares median stage timings to determine whether the patch actually improves performance.

4. **CCAP Emission**: If the patch passes the performance gate (new median < old median for the target stage), a CCAP bundle is emitted for verification. If the patch regresses performance, it is discarded with a documented reason.

This campaign is a key example of the system's self-optimizing capability — the daemon literally benchmarks and patches its own execution pipeline.

## 5.10 Phase0 CCAP & Survival Drill

### Phase0 CCAP — Adversarial Testing

**Modules**: `campaign_phase0_victim_ccap_v0_1.py` + `campaign_phase0_immune_repair_ccap_v0_1.py`

The **Phase0 CCAP** campaigns deliberately test the system's immune system by generating adversarial CCAP bundles:

- **Victim Campaign** (`phase0_victim_ccap`): Generates intentionally malformed or policy-violating CCAP bundles to verify that the verification pipeline correctly rejects them. This is adversarial red-teaming of the system's own defenses.
- **Immune Repair Campaign** (`phase0_immune_repair_ccap`): After a victim campaign, this campaign verifies that the immune system remains intact and can correctly process legitimate CCAP bundles. It serves as a regression test for the verification infrastructure.

Both campaigns are gated by authority pins and verified by their respective CDEL-v2 verifiers.

### Survival Drill Campaigns

**Directory**: `campaigns/rsi_survival_drill_v*/`

Survival drills stress-test the daemon's resilience by simulating failure scenarios: corrupted state, missing artifacts, budget exhaustion, and forced rollbacks. Each drill produces a survival report documenting which failure modes were handled correctly and which revealed weaknesses. The drill results feed into the observation pipeline, enabling the decider to route toward hardening campaigns when vulnerabilities are detected.

---

# Layer 6: The EUDRS-U Stack — Unified Hypothesis for Embodied Intelligence

## 6.1 What Is EUDRS-U?

**EUDRS-U** (Embodied Unified Decision & Reasoning System — Unified hypothesis) is the AGI-Stack's most ambitious subsystem: a complete, deterministic, replay-verifiable machine-learning and decision-planning stack that operates entirely within the RE1-RE4 trust model. It represents the system's path from *text-level self-improvement* (CCAP patches, campaign configs) to *neural-level self-improvement* — deterministic training, inference, planning, and world-modeling with full cryptographic verification.

EUDRS-U is implemented as a sub-package within RE2: `CDEL-v2/cdel/v18_0/eudrs_u/` containing **88 files** totaling over **800,000 bytes** of deterministic runtime and verification logic. It has its own orchestrator campaigns, schemas, verifiers, and a dedicated artifact namespace under `polymath/registry/eudrs_u/`.

### Why It Exists

Before EUDRS-U, the AGI-Stack's self-improvement was limited to text-level operations — generating Python patches, modifying JSON configurations, adjusting campaign parameters. EUDRS-U extends self-improvement to the neural level: the system can now train neural networks, run deterministic inference, plan actions in world models, and perceive structured environments — all with the same replay-verification guarantees that protect CCAP patches. This is the architectural bridge between "code that rewrites code" and "code that learns from experience."

## 6.2 The Root Tuple — EUDRS-U's State Object

**Schema**: `eudrs_u_root_tuple_v1` | **Module**: `eudrs_u_root_tuple_v1.py`

The Root Tuple is EUDRS-U's equivalent of the Omega state object — a compact, content-addressed JSON document that represents the complete state of the learning subsystem at a given epoch. It contains **8 component roots**:

| Root | Symbol | Manages |
|------|--------|---------|
| `SRoot` | S | **Strategy** — Active strategy cartridge and SLS-VM state |
| `ORoot` | O | **Ontology** — Concept hierarchy with stability gates |
| `KRoot` | K | **Knowledge** — ML-Index retrieval infrastructure state |
| `CRoot` | C | **CAC/UFC** — Certificate store for advantage and utility-flow proofs |
| `MRoot` | M | **Model** — QXRL neural weights manifest (Merkle-sharded Q32 tensors) |
| `IRoot` | I | **Inference** — DMPL planner state and action traces |
| `WRoot` | W | **World** — Vision pipeline perception state |
| `DRoot` | D | **Data** — Training dataset pack references |

Each root is a SHA-256 hash pointing to the corresponding subsystem's state artifact. The Root Tuple's own hash creates a single commitment to the entire EUDRS-U state.

**Epoch monotonicity**: The Root Tuple carries an `epoch_u64` field that must strictly increase with each promotion. The EUDRS-U promotion verifier (`verify_eudrs_u_promotion_v1.py`, 954 lines) checks that `staged_epoch > active_epoch`, preventing replay attacks where an old tuple could overwrite a newer one.

## 6.3 The DMPL Runtime — Deterministic Machine Planning & Learning

**Module**: `dmpl_planner_dcbts_l_v1.py` (641 lines) | **Entry**: `dmpl_planner_dcbts_l_v1()`

The DMPL (Deterministic Machine Planning & Learning) runtime provides the planning subsystem. Its core algorithm is **DCBTS-L** (Deterministic Constrained Beam-search Tree Search — Laddered):

### How DCBTS-L Plans

1. **Action Enumeration**: Given a Z-Vector (a deterministic state representation), the planner enumerates all legal actions from the current state. Each action is scored using the Q32 value function.

2. **Layered Expansion**: The search tree is expanded in layers (hence "Laddered"). At each layer, the top-K nodes by score are expanded (beam pruning), preventing exponential blowup. The beam width is configurable via budget parameters.

3. **Z-Vector Transitions**: Each action application produces a new Z-Vector through a deterministic state transition function. The transition function operates entirely in Q32 arithmetic — no floating-point at any stage.

4. **Trace Recording**: Every expansion step records: the parent node, action taken, resulting Z-Vector hash, and Q32 score. This trace is content-addressed and forms part of the promotion evidence.

5. **Plan Result**: The planner emits a `PlanResultV1` containing the best plan (sequence of actions), its total score, the full expansion trace, and budget consumption metrics. All values are deterministic and replay-verifiable.

The DMPL subsystem also includes: `dmpl_sgd_v1.py` (SGD optimizer for plan scoring), `dmpl_trace_v1.py` (trace management), `dmpl_retrieval_v1.py` (ML-Index integration), `dmpl_batch_v1.py` (batch planning), `dmpl_loss_v1.py` (loss computation), and `dmpl_forward_v1.py` (forward model).

## 6.4 The QXRL Training System — Deterministic Neural Training

**Module**: `qxrl_train_replay_v1.py` (1,144 lines) | **Entry**: `qxrl_train_replay_v1()`

QXRL (Q32 eXtensible Representation Learning) is the system's deterministic neural training framework. Unlike conventional ML frameworks that use IEEE 754 floating-point, QXRL operates entirely in **Q32 integer arithmetic**, making every training step bitwise-reproducible.

### Architecture

- **Weights Manifest**: Neural network weights are stored as a Merkle-sharded manifest. Each shard contains Q32 tensor blocks with deterministic layout. The manifest's Merkle root commits to all weights simultaneously.

- **Q32 Tensor Operations**: Forward and backward passes use Q32 `mul`, `add`, `div` operations. Activations, gradients, and optimizer state are all Q32 integers. This eliminates platform-dependent floating-point rounding.

- **Deterministic PRNG**: Batch selection, dropout masks, and any stochastic operations use a seeded PRNG (`run_seed`) that produces identical sequences across all platforms. The PRNG is pinned per epoch.

- **Training Loop**: Each training step follows a strict sequence:
  1. **Batch Selection**: Deterministic indexing from the dataset pack using the epoch's PRNG seed.
  2. **Forward Pass**: Q32 matrix multiplication, activation functions, and loss computation.
  3. **Backward Pass**: Q32 gradient computation via computational graph replay.
  4. **Optimizer Step**: Q32 SGD/Adam state update with deterministic learning rate schedule.
  5. **Step Digest**: A content-addressed digest of all inputs, intermediates, and outputs for verification.

### Verification

The QXRL verifier replays the entire training step from the same inputs and confirms that: (a) the weights manifest hashes match, (b) the PRNG produced the same batch indices, (c) the forward pass produced the same intermediate hashes, (d) the optimizer update produced the same new weights, and (e) the step digest matches.

## 6.5 The Vision Pipeline — Deterministic Perception

**Orchestrators**: `rsi_eudrs_u_vision_capture_v1.py` (504 lines), `rsi_eudrs_u_vision_perception_v1.py`

The Vision Pipeline provides EUDRS-U with structured world perception through a multi-stage deterministic process:

### Pipeline Stages

1. **Stage 0 — Capture** (`rsi_eudrs_u_vision_capture_v1.py`): Raw frame ingestion. The capture campaign reads from configured vision sources, decodes frames using deterministic codec parameters, and emits content-addressed frame artifacts. Each frame is bound to its source hash and capture parameters.

2. **Stage 1 — Perception**: Frame processing through deterministic vision modules. The perception stage applies feature extraction, object detection, and scene understanding — all using Q32 arithmetic. No stochastic components.

3. **Stage 2 — Index Build**: Processed perception outputs are indexed into the ML-Index for retrieval by the DMPL planner and QXRL trainer. Index entries are content-addressed and Merkle-committed.

The vision pipeline produces **17 distinct artifact types** across the capture, perception, and indexing stages, each with its own Genesis schema.

## 6.6 The CAC/UFC Certificates — Verified Advantage & Utility

**Modules**: `cac_v1.py` (180 lines) + `ufc_v1.py` (79 lines)

The **CAC** (Counterfactual Advantage Certificate) and **UFC** (Utility-Flow Certificate) subsystems provide deterministic structural verification for the system's self-improvement signals:

- **CAC** (`cac_v1.json` + `cac_episode_record_v1.bin`): Encodes counterfactual advantage estimates — "how much better would the outcome have been with a different action?" The CAC verifier checks schema-pinned structural invariants: field presence, type correctness, hash binding, and episode record binary format compliance.

- **UFC** (`ufc_v1.json`): Encodes utility-flow certificates — the net utility gain or loss from a sequence of actions. The UFC verifier focuses on schema-pinned structural invariants required for replay verification, with the full derivation logic defined in the OpSet.

Both certificates feed into the DMPL planner's scoring function and the QXRL trainer's loss computation, creating a verified feedback loop for learning.

## 6.7 The ML-Index — Deterministic Retrieval Infrastructure

**Modules**: `ml_index_v1.py`, `ml_index_build_v1.py`, `ml_index_query_v1.py`

The ML-Index provides deterministic nearest-neighbor retrieval for EUDRS-U's planning and training subsystems. Key properties:

- **Deterministic Insertion**: Index entries are ordered by content hash, ensuring identical insertion order regardless of ingestion timing.
- **Deterministic Query**: Similarity queries use Q32 distance metrics, producing identical result sets on all platforms.
- **Merkle-Committed**: The index state is committed via a Merkle root, enabling verification of both the index contents and query results.

The ML-Index is used by: DMPL (retrieving relevant experiences for planning), QXRL (sampling training data), and the Vision Pipeline (indexing perception outputs).

## 6.8 The Ontology — Hierarchical Concept Management

**Modules**: `ontology_v1.py`, `ontology_gate_v1.py`

The Ontology subsystem manages EUDRS-U's concept hierarchy — the structured knowledge representation that organizes learned concepts into a directed acyclic graph. Key features:

- **Stability Gates** (`ontology_gate_v1.py`): Before a concept can be added or modified in the ontology, it must pass stability gates — deterministic checks that the concept doesn't contradict existing knowledge, maintains hierarchical consistency, and has sufficient evidence support. Gates use Q32 confidence thresholds.
- **Content-Addressed Concepts**: Each concept node is identified by its content hash, making the ontology immutable and auditable.
- **ORoot Commitment**: The entire ontology state is committed via the ORoot hash in the Root Tuple.

## 6.9 The SLS-VM — Strategy Execution Engine

**Module**: `sls_vm_v1.py` (1,363 lines) | **Entry**: `SLSVirtualMachine.run()`

The **SLS-VM** (Strategy Logic System — Virtual Machine) is a deterministic typed stack machine that executes strategy cartridges. It's EUDRS-U's mechanism for executing complex, multi-step strategies.

### Architecture

- **SLS1 Binary Format**: Strategies are compiled into SLS1 cartridge binaries — a custom bytecode format with a header, instruction stream, and constant pool.
- **Typed Stack Machine**: The VM operates on a typed stack with operations for integers (Q32), booleans, strings, and structured data. Type mismatches are fatal (fail-closed).
- **Budget Enforcement**: Every instruction consumes budget units. When the budget is exhausted, the VM halts with `BUDGET_EXHAUSTED`. This prevents infinite loops and bounds computation time.
- **Deterministic Log Chain**: Every VM execution step appends a log entry with the instruction pointer, stack state hash, and operation result. The log chain is hash-linked, creating a verifiable execution trace.
- **31 Instruction Opcodes**: Including arithmetic (`ADD_Q32`, `MUL_Q32`, `DIV_Q32`), control flow (`JMP`, `JZ`, `CALL`, `RET`), stack manipulation (`PUSH`, `POP`, `DUP`), comparison (`CMP_Q32`, `CMP_EQ`), and I/O operations that read from the deterministic environment.

## 6.10 The URC-VM — Universal Reasoning Capsule VM

**Module**: `urc_vm_v1.py`

The **URC-VM** executes universal reasoning capsules — portable, deterministic reasoning programs that can perform logical inference, constraint satisfaction, and deductive reasoning. The URC-VM differs from the SLS-VM in that it operates on logical propositions rather than numerical computations, and it provides built-in support for unification, backtracking, and constraint propagation — all in deterministic Q32.

## 6.11 The VPVM STARK Prover — Proof-Carrying Code

**Module**: `vpvm_stark_prover_v1.py` (1,016 lines) | **Entry**: `prove()`, `verify_proof()`

The **VPVM STARK Prover** generates cryptographic proofs of correct computation, enabling **Proof-Carrying Code** for the PCLP (Proof-Carrying Logic Protocol) fast-path.

### Cryptographic Stack

1. **Goldilocks Field**: All arithmetic operates in the Goldilocks prime field (p = 2⁶⁴ − 2³² + 1), chosen for its efficient reduction on 64-bit hardware.
2. **Poseidon Hash**: The prover uses Poseidon for Merkle tree commitments, optimized for algebraic circuits.
3. **AIR Constraints**: Computation correctness is expressed as Algebraic Intermediate Representation constraints — polynomial equations that the execution trace must satisfy.
4. **FRI Protocol**: The Fast Reed-Solomon Interactive Oracle Proof provides the core soundness guarantee, proving that the committed polynomials are close to low-degree polynomials.

### How It Works

1. The prover takes an execution trace (e.g., a QXRL training step or a DMPL planning pass) and expresses it as an AIR table.
2. It commits to the trace using Poseidon-based Merkle trees.
3. It constructs the composition polynomial from the AIR constraints.
4. It runs the FRI protocol to prove that the composition polynomial is low-degree.
5. It emits a proof artifact that can be verified without re-executing the computation.

This enables a dramatic verification speedup: instead of replaying an entire training step (which could take minutes), the verifier checks a STARK proof (which takes milliseconds). The VPVM prover is the only component in the AGI-Stack that uses modern cryptographic proof systems.

## 6.12 EUDRS-U Campaigns & Verification

### 7 Omega-Dispatchable Campaigns

EUDRS-U is operated through 7 dedicated campaigns, each responsible for one stage of the embodied intelligence pipeline:

| Campaign | Stages | Function |
|----------|--------|----------|
| `rsi_eudrs_u_vision_capture_v1` | Capture | Raw frame ingestion from vision sources |
| `rsi_eudrs_u_vision_perception_v1` | Perception | Feature extraction and scene understanding |
| `rsi_eudrs_u_dmpl_plan_v1` | Planning | DCBTS-L deterministic planning |
| `rsi_eudrs_u_qxrl_train_v1` | Training | Deterministic neural network training |
| `rsi_eudrs_u_ontology_update_v1` | Knowledge | Concept hierarchy maintenance |
| `rsi_eudrs_u_ml_index_build_v1` | Indexing | Retrieval infrastructure rebuild |
| `rsi_eudrs_u_promote_v1` | Promotion | Root Tuple advancement |

Each campaign is orchestrated via `orchestrator/rsi_eudrs_u_*_v1.py` scripts and follows the standard Omega tick lifecycle: observe → decide → dispatch → execute → promote → activate.

### Verification Surface

EUDRS-U's verification surface is massive — over **250,000 bytes** of verifier code. The central verifier `verify_eudrs_u_promotion_v1.py` (954 lines) orchestrates:

- Root Tuple epoch monotonicity checks.
- Per-root hash verification (each SRoot, ORoot, KRoot, etc. must match its referenced artifact).
- QXRL training step deterministic replay.
- DMPL planning trace replay.
- ML-Index Merkle root verification.
- VPVM STARK proof verification (fast-path when proofs are available).
- CAC/UFC certificate structural validation.
- Budget compliance for all component executions.

### EUDRS-U Schemas

EUDRS-U defines **40+ Genesis layer schemas** for its artifacts, including:
- `eudrs_u_root_tuple_v1`: The master state object.
- `eudrs_u_dmpl_plan_v1`, `eudrs_u_dmpl_trace_v1`: Planning artifacts.
- `eudrs_u_qxrl_weights_manifest_v1`, `eudrs_u_qxrl_step_digest_v1`: Training artifacts.
- `eudrs_u_vision_frame_v1`, `eudrs_u_perception_report_v1`: Vision artifacts.
- `eudrs_u_cac_v1`, `eudrs_u_ufc_v1`: Certificate artifacts.
- `eudrs_u_sls_cartridge_v1`, `eudrs_u_sls_exec_log_v1`: Strategy artifacts.
- `eudrs_u_vpvm_proof_v1`: STARK proof artifacts.

## 6.13 Why EUDRS-U Matters

EUDRS-U is the architectural embodiment of the AGI-Stack's ultimate goal: **neural-level self-improvement with constitutional guarantees**. Before EUDRS-U, the system could modify its own code — but code modification is inherently limited by the creativity of text-based patch generation. With EUDRS-U, the system can:

1. **Learn from experience**: Train neural networks on observation data, creating learned representations that improve planning quality over time.
2. **Plan deterministically**: Use learned models to plan multi-step actions in world models, evaluating plans via verified advantage certificates.
3. **Perceive structured environments**: Process visual data through a deterministic vision pipeline, building indexed knowledge bases.
4. **Prove correctness**: Generate STARK proofs of computation, enabling fast verification without full replay.
5. **Maintain constitutional control**: Every EUDRS-U operation — training, planning, perception, strategy execution — is replay-verifiable and fail-closed, operating within the same RE1-RE4 trust hierarchy that protects CCAP patches.

This makes EUDRS-U not just a machine learning library, but a **constitutionally-governed learning system** — perhaps the first of its kind. The system can learn and grow, but its learning is bounded by the same verification infrastructure that prevents code-level self-modification from going wrong.

---

# Appendix A: Critical File Reference

| File | Lines | Purpose |
|------|-------|---------|
| `meta-core/engine/activation.py` | 414 | Constitutional guardian — stage, verify, canary, commit, rollback |
| `CDEL-v2/cdel/v18_0/verify_rsi_omega_daemon_v1.py` | 1,886 | Main Omega tick verifier (deterministic replay) |
| `CDEL-v2/cdel/v18_0/omega_promoter_v1.py` | 1,535 | Promotion and multi-layer verification orchestration |
| `CDEL-v2/cdel/v18_0/omega_observer_v1.py` | 1,195 | Metric observation and capability frontier computation |
| `CDEL-v2/cdel/v18_0/verify_ccap_v1.py` | 819 | CCAP universal patch verifier |
| `CDEL-v2/cdel/v18_0/omega_decider_v1.py` | 789 | Policy-based decision engine |
| `CDEL-v2/cdel/v19_0/federation/check_treaty_v1.py` | 825 | Federation treaty verification |
| `CDEL-v2/cdel/v19_0/omega_promoter_v1.py` | 692 | v19 promoter with continuity/J gates |
| `CDEL-v2/cdel/v19_0/continuity/check_continuity_v1.py` | 570 | Overlap continuity verification |
| `tools/genesis_engine/ge_symbiotic_optimizer_v0_3.py` | 1,588 | SH-1 receipt-driven meta-learning optimizer |
| `CDEL-v2/cdel/v18_0/omega_common_v1.py` | 394 | Q32 arithmetic, GCJ-1, shared utilities |
| `CDEL-v2/cdel/v18_0/omega_runaway_v1.py` | 360 | Runaway escalation protocol |
| `CDEL-v2/cdel/v18_0/omega_executor_v1.py` | 349 | Campaign dispatch and workspace management |
| `CDEL-v2/cdel/v18_0/omega_activator_v1.py` | 332 | meta-core activation/rollback wrapper |
| `CDEL-v2/cdel/v18_0/ccap_runtime_v1.py` | 313 | CCAP runtime helpers (git ops, patches) |
| `ignite_runaway.sh` | 307 | Top-level autonomous execution loop |
| `CDEL-v2/cdel/v18_0/omega_diagnoser_v1.py` | 253 | Issue diagnosis and severity assignment |
| `CDEL-v2/cdel/v19_0/continuity/objective_J_v1.py` | 191 | Objective J dominance function |
| `CDEL-v2/cdel/v18_0/omega_state_v1.py` | 160 | State management (bootstrap, advance, persist) |
| `authority/authority_pins_v1.json` | 1 | Cryptographic root of trust pins |
| `authority/ccap_patch_allowlists_v1.json` | 1 | Filesystem-level access control for patches |

---

# Appendix B: Glossary

| Term | Definition |
|------|-----------|
| **CCAP** | Certified Capsule Proposal — universal verification protocol for code patches |
| **CDEL** | Certified Definitional Extension Ledger — the verification layer (RE2) |
| **GCJ-1** | Guaranteed Canonical JSON version 1 — deterministic JSON serialization |
| **Omega Daemon** | The tick-based autonomous controller (v18.0/v19.0) |
| **PD** | Promotion Density — success rate per file in SH-1 |
| **Q32** | 32-bit fixed-point arithmetic for deterministic computation |
| **RE1-RE4** | Runtime Envelope layers 1-4 (decreasing trust) |
| **SH-1** | Symbiotic Harmony v1 — Genesis Engine's receipt-driven optimizer |
| **SIP** | Sealed Ingestion Protocol — tamper-proof world snapshots |
| **TCB** | Trusted Computing Base — meta-core (RE1) |
| **XS** | eXploration Score — exploration potential per file in SH-1 |
| **Axis Bundle** | Verification package submitted from RE2 to RE1 |
| **Canary** | Dry-run application phase before commitment |
| **Dominance Gate** | J_new >= J_old requirement for v19.0 promotion |
| **Fail-Closed** | Reject on any error instead of attempting recovery |
| **Goal Queue** | Ordered list of system objectives |
| **Morphism** | Translation between artifact formats across regime transitions |
| **Regime** | A version of the system's verification rules |
| **Runaway Mode** | Controlled escalation to break out of performance stalls |
| **Tick** | Atomic unit of daemon operation (one observe-decide-execute cycle) |
| **Treaty** | Federation interoperability contract between systems |
| **Void Score** | Q32 measure of how underexplored a domain is |

---

# Appendix C: The Self-Improvement Loop — End to End

The complete self-improvement cycle:

```
1. IGNITE LOOP starts a new tick
   └── orchestrator.rsi_omega_daemon_v19_0 is invoked

2. OBSERVE: Observer reads metrics from all campaign sources
   └── Produces: observation_report (hash: obs_hash)

3. DIAGNOSE: Diagnoser checks observation against objectives
   └── Produces: issues_report (severity-ranked problems)

4. DECIDE: Decider analyzes observation + diagnosis + policy
   ├── If stalled → enters RUNAWAY MODE (escalation level 5)
   ├── Selects: OBJ_EXPAND_CAPABILITIES goal
   ├── Routes to: rsi_ge_symbiotic_optimizer_sh1_v0_1
   └── Produces: decision_plan (hash: dec_hash)

5. EXECUTE: Executor dispatches Genesis Engine SH-1
   ├── SH-1 reads historical receipts
   ├── Computes PD/XS per file
   ├── Plans HOTFIX/INCREMENTAL/EXPLORATORY buckets
   ├── Generates code patches from templates
   ├── Applies hard-avoid projection (filters novelty laundering)
   └── Produces: CCAP bundle with patch

6. PROMOTE: Promoter orchestrates verification
   ├── CCAP Verifier checks:
   │   ├── Allowlist compliance (path restrictions)
   │   ├── REALIZE: applies patch to workspace
   │   ├── SCORE: runs evaluation kernel benchmarks
   │   └── FINAL_AUDIT: checks promotion gates
   ├── v19 gates:
   │   ├── Continuity gate (overlap preservation)
   │   ├── J dominance gate (J_new >= J_old)
   │   └── Treaty gate (federation compatibility)
   ├── Axis bundle → meta-core verification
   │   ├── stage_bundle (hash verification)
   │   ├── verify_staged (constitutional constraints)
   │   └── canary_staged (dry-run application)
   └── Produces: promotion_receipt (PROMOTED or REJECTED)

7. ACTIVATE (if PROMOTED):
   ├── commit_staged (atomic state swap)
   ├── Ledger entry (crash-safe audit)
   └── The system's code has been modified

8. VERIFY: The next tick's verifier can replay this tick
   └── Deterministic replay confirms bitwise-identical outputs

9. SIGNAL: Ignite loop emits structured signals
   ├── REWRITE_COMMIT (code was successfully modified)
   ├── ACTIVATION_COMMIT (modification is now live)
   └── TIER_STATUS tier1=pass tier2=pass tier3=pass

10. LOOP: tick_u64++ → Go to step 1
    └── The improved system now runs the next tick
```

This is the system improving itself: generating patches, verifying them through multiple trust layers, committing the verified changes, and then running the improved version to generate better patches. Each cycle is fully deterministic, fully auditable, and fully reversible.

---

*End of Source of Truth document.*
*Total coverage: 5 Universal Context layers, 56+ verifiers, 78+ campaigns, 4 trust layers.*
*Generated from comprehensive analysis of over 25,000+ lines of core source code across 10+ major components.*

---

# Deep Dive: Hidden Mechanics & Cross-Cutting Concerns

This section expands on the mechanics that cut across all five layers — the subtle design decisions, implicit contracts, and emergent behaviors that are not immediately obvious from reading any single module.

## D.1 The Hash Chain as Blockchain

The AGI-Stack implements what is effectively a private blockchain. The state object's `parent_state_hash` field creates a linked list of states extending back to the genesis state at tick 0. Each state cryptographically commits to its predecessor, its observation, its decision, and its outcomes. Tampering with any historical state would change its hash, which would break the parent reference in the next state, which would break the next reference, and so on — the classic blockchain tamper-detection property.

But the analogy goes deeper. In a public blockchain, consensus is achieved through proof-of-work or proof-of-stake. In the AGI-Stack, consensus is achieved through **deterministic replay**. Any party can verify the entire chain by re-executing every tick from the genesis state. If their replayed chain produces the same state hashes as the recorded chain, the chain is valid. If not, the divergence point identifies the corrupted tick.

The difference from a public blockchain is that the AGI-Stack's chain has a single producer — the Omega daemon — and the verification is not distributed (any single verifier can validate the entire chain). This is appropriate because the system's threat model is not Byzantine faults (multiple dishonest nodes), but rather self-corruption (a single evolving system that might generate harmful mutations).

The chain serves three purposes:
1. **Tamper detection**: Any modification to historical state is detectable.
2. **Fork prevention**: The parent hash check prevents the system from maintaining multiple inconsistent timelines.
3. **Rollback**: The chain enables reverting to any historical state by following parent pointers backward.

## D.2 The Budget System: Computational Accountability

Throughout the codebase, you encounter "budget" parameters: `budget_spec`, `make_budget_tracker()`, `BudgetMeter`, `BudgetExhausted`, `tracker.consume_items()`, `tracker.consume_bytes_read()`. This pervasive budget system ensures that every computation is bounded — no verifier, translator, or checker can run indefinitely.

The budget system works as follows:
1. Each operation receives a `budget_spec` declaring maximum items processed, bytes read, and bytes written.
2. A `BudgetMeter` (or equivalent tracker) is created from the spec.
3. As the operation proceeds, each significant step calls `consume_items(1)` or `consume_bytes_read(N)`.
4. If consumption exceeds the budget, `BudgetExhausted` is raised, causing fail-closed rejection.
5. The final `budget_outcome()` is recorded in the output receipt.

This mechanism prevents denial-of-service through crafted inputs. A malicious proposer cannot construct an artifact that causes the verifier to run for an unbounded time — the budget will halt it. The budget spec is declared in advance and included in the cryptographic commitment, so both the producer and verifier agree on the computational bounds.

Budget tracking is particularly critical in the v19.0 federation modules:
- Treaty verification (`check_treaty_v1.py`) tracks items per overlap artifact and bytes per translator operation.
- Continuity checking (`check_continuity_v1.py`) tracks items per overlap set and bytes per translation.
- SIP verification (`sip_v1.py`) tracks entries per manifest and bytes per artifact.

The budget system is also a performance engineering tool. By tracking consumption at granular levels, developers can identify which operations dominate verification cost and optimize accordingly.

## D.3 The Canonicalization Pipeline: GCJ-1 Deep Dive

The `canon.py` module in `CDEL-v2/cdel/v1_7r/` is one of the most critical files in the entire codebase, despite its modest size. Every security guarantee in the system ultimately depends on canonical serialization producing identical bytes for identical logical content.

The canonicalization pipeline:
1. **Input**: Any Python object (dict, list, str, int, float, bool, None).
2. **Normalization**: Floats are converted to a canonical string representation. Dictionaries are sorted by key. Lists preserve order.
3. **Serialization**: The normalized object is serialized using `json.dumps()` with `sort_keys=True`, `ensure_ascii=False`, `indent=2`, and `separators=(',', ': ')`.
4. **Encoding**: The resulting string is encoded as UTF-8 bytes.
5. **Hashing**: `sha256_prefixed()` computes `sha256:<hex_digest>` from the canonical bytes.

Key subtleties:
- **Float handling**: Python's `json.dumps` can produce different string representations for the same float value depending on the Python version and platform. GCJ-1 avoids this by using Q32 integers instead of floats for all determinism-critical values. Where floats must appear, they're converted to a canonical string form.
- **Unicode normalization**: Different Unicode representations of the same character (e.g., NFC vs NFD) produce different bytes. GCJ-1 does not perform Unicode normalization — instead, the system avoids Unicode-sensitive comparisons and relies on byte-level identity.
- **Key ordering**: `sort_keys=True` uses Python's default string comparison, which is Unicode codepoint order. This is the same across all Python implementations and platforms.
- **Indent style**: 2-space indent with no trailing whitespace. This is enforced by the `separators` parameter.

The canonical JSON module also provides:
- `load_canon_json(path)`: Load and parse a canonical JSON file, returning the deserialized object.
- `write_canon_json(path, obj)`: Serialize an object to canonical JSON and write it atomically to a file.
- `canon_hash_obj(obj)`: Convenience function that canonicalizes an object and returns its SHA-256 hash.

## D.4 The Verifier Module Registry: How Campaigns Find Their Verifiers

When the promoter needs to verify a campaign's output, it must select the appropriate verifier module. This selection is not hardcoded — it goes through a registry:

1. The campaign pack declares a `verifier_module` field (e.g., `cdel.v18_0.verify_ccap_v1`).
2. The promoter imports this module dynamically.
3. The module's `verify()` function is called with the campaign's outputs.

This dynamic dispatch mechanism allows the system to add new campaign types without modifying the promoter. It also enables version migration — a campaign can switch to a newer verifier module by updating its pack file, without affecting other campaigns.

The verifier registry in the Omega daemon verifier (`verify_rsi_omega_daemon_v1.py`) maps campaign IDs to verifier module paths. Constants like `_SUBVERIFIER_MODULE_*` define these mappings. When verifying a tick, the verifier confirms that the promoter used the correct subverifier for the campaign that was executed.

## D.5 The Trace Hash Chain: Cryptographic Audit Trail

Each tick produces a **tick_snapshot_hash** that commits to the entire tick's computation. This hash is computed from:
- The observation report hash.
- The decision plan hash.
- The promotion receipt hash.
- The activation receipt hash (if activation occurred).

The trace hash chain is a running hash that incorporates each tick's snapshot hash into a cumulative chain. The `trace_hash_chain_hash` at tick N incorporates the hash chain from tick N-1 plus the snapshot from tick N. This creates a single hash value that commits to the entire history of the system.

The ignite loop emits this hash in every `HEARTBEAT` signal:
```
SIGNAL=HEARTBEAT action_kind=DISPATCH_GE_SH1 decision_plan_hash=sha256:abc... trace_hash_chain_hash=sha256:def... tick_snapshot_hash=sha256:ghi...
```

This enables continuous monitoring: if the trace hash chain ever diverges from an expected value, it indicates that the system's behavior has deviated from the expected trajectory. A monitor can compare the trace hash against a known-good value to detect tampering or corruption in real-time.

## D.6 The Fail-Closed Error Model: OmegaV18Error

The `OmegaV18Error` exception class (defined in `omega_common_v1.py`) is the system's universal error type for fail-closed exits. When any component encounters an unexpected condition, it raises `OmegaV18Error` with a reason code and message.

The error model is designed so that **all error paths lead to rejection**:
- If the observer fails to read metrics: the tick is rejected (no observation, no decision possible).
- If the decider encounters an unknown state: the decision plan is rejected.
- If the executor's subprocess crashes: the campaign output is rejected.
- If the promoter's subverifier throws: the promotion is rejected.
- If meta-core's verification fails: the bundle is rejected.

There is no "retry" logic within a single tick. If any phase fails, the entire tick fails. The ignite loop's crash resurrection mechanism handles retries at the tick level — but each retry starts the tick fresh, not from a partial state.

This simplifies reasoning about the system's behavior enormously. At any point in the pipeline, you only need to consider two outcomes: success (proceed to next phase) or failure (reject the entire tick). There are no partial successes, no best-effort modes, no degraded operation states.

## D.7 The Workspace Isolation Model

The executor creates an isolated workspace for each campaign run. This workspace is not a filesystem sandbox (there's no `chroot` or container involved) — it's a **materialized subset** of the repository:

1. The executor creates a fresh directory.
2. It copies specific files and directories from the repository into the workspace, guided by the campaign pack's declared inputs.
3. Pruning rules remove unnecessary files (large binaries, historical runs, caches).
4. The campaign script is executed with its working directory set to the workspace.

This provides a form of information isolation: the campaign can only access files that were explicitly materialized into its workspace. It can't read arbitrary files from the repository root (assuming it doesn't escape the working directory — but since it's an untrusted component, its outputs are verified rather than its behavior trusted).

The materialized workspace also provides reproducibility: the workspace contents are deterministic (determined by the campaign pack and repository state), so replaying the same campaign with the same workspace produces the same outputs.

## D.8 The v19.0 JSON Pointer Transformation System

Both the treaty checker and the continuity checker use a JSON Pointer-based transformation system to translate artifacts between different regimes or systems. This system is worth examining in detail because it's the mechanism by which the AGI-Stack maintains compatibility across version transitions.

A **translator bundle** is a list of operations, each targeting a specific JSON Pointer path:

```json
{
  "operations": [
    {"op": "set", "path": "/schema_version", "value": "v19_0"},
    {"op": "remove", "path": "/deprecated_field"},
    {"op": "set", "path": "/new_field", "value": "default_value", "create_only": true}
  ]
}
```

Operations supported:
- **set**: Set a value at the specified path. With `create_only: true`, only creates the path if it doesn't exist. With `replace_only: true`, only replaces if the path already exists.
- **remove**: Remove the value at the specified path. Raises an error if the path doesn't exist.
- **copy**: (Implicit through set with reference) Copy a value from one path to another.
- **add**: Insert a value at a specific position in an array.

The transformation system enforces **depth limits** (`_max_pointer_depth()`) to prevent deeply nested operations that could consume excessive memory or CPU. The depth limit is derived from the budget specification.

The `apply_translator_bundle()` function in `check_continuity_v1.py` (lines 167-230) applies a translator bundle to a payload, producing a translated result and tracking all transformations for the audit trail. The function is deterministic and budget-tracked.

Translations must be **total** for treaty compliance — every overlap artifact must be translatable in both directions. The `_build_totality_cert()` function constructs a certificate proving that all artifacts were successfully translated. If any artifact fails translation, the totality certificate records the failure, and the treaty check fails.

## D.9 The SIP Leakage Scanner: Information Security at the Data Layer

The Sealed Ingestion Protocol's leakage scanner (`_scan_leakage()` in `sip_v1.py`, lines 56-88) implements information security at the data ingestion layer. When the system ingests external data (e.g., scientific datasets for Polymath domains), the leakage scanner checks for:

1. **Forbidden patterns**: The SIP profile defines a list of string patterns that must not appear in ingested artifacts. This prevents accidental ingestion of sensitive data (API keys, passwords, internal identifiers).

2. **Entropy analysis**: `_entropy_q16()` (lines 40-53) computes the Shannon entropy of artifact bytes using Q16 fixed-point arithmetic (not Q32 — a smaller format for this simpler computation). High-entropy artifacts may be encrypted data, compressed binaries, or other opaque payloads that bypass text-based policy checks. If an artifact's entropy exceeds the threshold defined in the SIP profile, it's flagged.

3. **Content ID verification**: `_ensure_bytes_by_content_id()` (lines 25-37) verifies that every artifact's bytes match its declared SHA-256 content ID. This prevents substitution attacks where an attacker provides artifact bytes that don't match the declared identity.

The combination of pattern scanning, entropy analysis, and content verification creates a three-layer defense against data-level attacks. This is particularly important because Polymath can ingest data from external sources (when `OMEGA_NET_LIVE_OK=1`), making the ingestion boundary a potential attack surface.

## D.10 The Deterministic Tie-Breaking Mechanism

When the decider faces ambiguity — multiple goals with equal priority, multiple campaigns matching the criteria equally, or multiple candidate patches with similar PD scores — it uses a deterministic tie-breaking mechanism.

The tie-breaking algorithm:
1. Compute a "tie-break seed" from the current state hash, tick number, and the set of tied candidates.
2. Hash each candidate's identifier with the seed.
3. Sort candidates by their seed-hash.
4. Select the candidate with the lowest hash.

This produces a deterministic selection that appears random (it depends on the state hash, which is effectively unpredictable without replaying the entire history) but is fully reproducible. The `tie_break_path` field in the decision plan records the entire tie-breaking chain, including the seed, the candidates, and the selected winner.

The tie-breaking mechanism is important for two reasons:
1. **Determinism**: Without it, different verifier implementations might select different candidates from a tie, causing verification failures.
2. **Fairness**: The hash-based selection ensures that no candidate is systematically preferred or disadvantaged.

## D.11 The Polymath Void Score: Quantifying the Unknown

The void score is Polymath's signature metric — a Q32 quantification of how much unexplored potential a domain offers. It's computed from:

- **Trend score** (`trend_score_q32`): How rapidly the domain's field is evolving (higher = more active research area).
- **Coverage score** (`coverage_score_q32`): How much of the domain the system already covers (higher = less void).
- **Source evidence**: The quality and diversity of data sources confirming the domain's relevance.

The void score formula combines these factors such that high trend + low coverage = high void (a rapidly evolving domain the system doesn't cover well is a high-value exploration target).

Void scores are computed per candidate domain in the scout phase and recorded in `polymath_void_report_v1.jsonl`. The bootstrap phase selects the highest-void candidate for development. Over time, as the system conquers domains, their coverage scores increase, their void scores decrease, and the system's attention shifts to new, unexplored domains.

The void-to-goals pipeline (`tools/polymath/polymath_void_to_goals_v1.py`) converts high-void domains into goal queue entries for the Omega daemon. This creates a feedback loop: Polymath discovers opportunities → goals enter the queue → the daemon prioritizes Polymath campaigns → Polymath conquers domains → the daemon's capabilities expand.

## D.12 The CAOE Wake/Sleep/Dawn Cycle: A Biological Metaphor

The legacy CAOE (Continuous Architecture Optimization Engine) module uses a biological metaphor for its three-phase cycle:

### Wake Phase (Anomaly Mining)
The system scans its own codebase for anomalies — patterns that deviate from its architectural model. Anomalies include dead code, inconsistent naming conventions, unused API surfaces, performance hotspots, and structural violations. The wake phase uses static analysis and pattern matching to identify these anomalies without executing the code.

The wake phase produces an "anomaly report" — a ranked list of issues that the sleep phase can address. Each anomaly includes a severity, location, and proposed category (e.g., "unused import", "inconsistent error handling", "missing validation").

### Sleep Phase (Candidate Synthesis)
Given the anomaly report, the sleep phase synthesizes candidate modifications — patches that address the identified anomalies. Candidate synthesis uses templates and heuristics to generate patches that are likely to be valid and improve the codebase.

The sleep phase produces a set of candidate patches, each with metadata describing the targeted anomaly, the modification strategy, and the expected impact. These candidates are not yet verified — they're proposals.

### Dawn Phase (Selection & Learning)
The dawn phase evaluates candidates, selects the best ones, and updates the system's learning model. Selection uses a combination of static analysis (does the patch compile? does it break tests?) and heuristic scoring (how significant is the improvement? how risky is the change?).

After selection, the dawn phase updates the system's architectural model — learning which anomaly patterns are most common, which synthesis strategies work best, and which parts of the codebase are most amenable to optimization. This learning persists across epochs, allowing the CAOE to improve its own optimization strategy over time.

The CAOE is labeled "legacy" because the Genesis Engine SH-1 has superseded it for code-level modifications. However, CAOE's architecture-level reasoning (analyzing structural patterns rather than individual lines) remains conceptually distinct from SH-1's receipt-driven approach. CAOE operates top-down (identify architectural issues, then generate patches), while SH-1 operates bottom-up (analyze historical success/failure, then generate patches for high-potential areas).

## D.13 The Evaluation Kernel System: Benchmarking Self-Improvement

The evaluation kernel system defines the benchmarks that determine whether a code change is an improvement. This is one of the most critical mechanisms in the entire system, because **the evaluation criteria determine the direction of self-improvement**.

An evaluation kernel (`authority/evaluation_kernels/ek_*_v1.json`) specifies:
- **Schema version**: `evaluation_kernel_v1`
- **EK ID**: A unique identifier for the kernel.
- **Scoring implementation**: The code that runs the benchmarks. For the Omega daemon, this is `omega_benchmark_suite_v1.py`.
- **Stages**: The three-stage REALIZE/SCORE/FINAL_AUDIT pipeline.
- **Gates**: Per-stage requirements. For example, the FINAL_AUDIT stage might require `accuracy_q32 >= 3865470566` (~90%).

The evaluation kernel is pinned in `authority_pins_v1.json` (`active_ek_id`), meaning it cannot be modified by the self-improving system. This is a foundational safety mechanism: the system can change its code, but it cannot change the criteria by which its changes are evaluated. If the evaluation kernel could be self-modified, the system could trivially achieve "improvement" by weakening its benchmarks.

The benchmark suite itself is also protected — `tools/omega/omega_benchmark_suite_v1.py` is on the CCAP exact-forbid list, preventing it from being patched even though its parent directory (`tools/omega/`) is otherwise allowed.

This creates a stable reference frame for improvement. No matter how many self-improvement cycles the system runs, it's always evaluated against the same fixed benchmarks. Progress is genuine — higher scores on the same benchmarks mean the system is actually getting better, not just gaming its own metrics.

## D.14 The Operator Pool and Sandbox Profile

The operator pool system defines the execution environment for CCAP verification:

An **operator pool** (`authority/operator_pools/operator_pool_core_v1.json`) lists the available operators and their configurations:
- **Operator ID**: Unique identifier.
- **DSBX Profile ID**: Reference to a sandbox profile.
- **Build Recipe ID**: How to build/apply the patch.

A **sandbox profile** (`dsbx_profile_v1`) defines the isolation constraints for executing code during CCAP verification. This includes:
- Allowed system calls.
- Memory limits.
- Network access restrictions.
- Filesystem access restrictions.

Together, the operator pool and sandbox profile ensure that CCAP verification runs in a controlled environment. Even if a patch contains malicious code, the sandbox prevents it from escaping the verification environment.

## D.15 Cross-System Interactions: How Components Compose

The AGI-Stack's components are highly composable. Here's how key interactions work:

### Polymath → Observer → Decider → Polymath
1. Polymath campaigns produce metrics (void scores, domain coverage).
2. The observer reads these metrics and includes them in the observation report.
3. The decider notices high void scores and prioritizes Polymath scouting/bootstrapping goals.
4. The executor dispatches the Polymath campaign.
5. The Polymath campaign discovers new domains, increasing capability.
6. The observer sees improved coverage, reducing Polymath priority.

### Genesis Engine → CCAP → meta-core → Genesis Engine
1. SH-1 reads historical CCAP receipts (past successes/failures).
2. SH-1 generates new patches based on learned patterns.
3. SH-1 emits a CCAP bundle.
4. The CCAP verifier checks the bundle against allowlists and evaluation kernels.
5. If promoted, meta-core verifies the bundle constitutionally.
6. If committed, the system's code is updated.
7. The next SH-1 run reads the new receipt (success), learning that this type of patch works.

### Runaway → Decision → Campaign Selection
1. The observer detects stagnation (no improvement over N ticks).
2. The diagnoser raises a capability-regression issue.
3. The decider enters runaway mode, escalating through levels.
4. At level 5, the decider routes to the Genesis Engine SH-1.
5. SH-1 generates exploratory patches (high XS, low PD files).
6. If a patch succeeds, the system breaks out of the stall.
7. If all patches fail, runaway continues at maximum level until external intervention.

### Treaty → Continuity → World Snapshot
1. A federation treaty defines the overlap between two systems.
2. Continuity checking verifies that version upgrades preserve overlap semantics.
3. World snapshots capture the system state with SIP tamper-proofing.
4. The v19 promoter gates promotion on all three: treaty compliance, continuity preservation, and world snapshot integrity.

## D.16 The Implicit Contract System

Beyond explicit schemas, the AGI-Stack relies on numerous implicit contracts — conventions that are enforced by code rather than schema:

1. **Filename convention**: `sha256_<hex>.<schema_version>.json`. The filename encodes both identity and type. Loading code parses this convention to determine the artifact type without reading the file.

2. **Path relativity**: All paths in artifacts are POSIX-relative (no leading `/`). The `verify_ccap_v1.py` explicitly checks for and rejects absolute paths in patches.

3. **Schema version field**: Every artifact has a `schema_version` field as the first key (by alphabetical sort). This field is checked before any other processing.

4. **Hash prefix format**: All hashes use the `sha256:<hex>` format internally, converted to `sha256_<hex>` for filenames (changing `:` to `_` for filesystem compatibility).

5. **Error reporting**: All errors include a reason code (machine-readable) and a message (human-readable). The reason code is always a SCREAMING_SNAKE_CASE string.

6. **Budget specs**: Every bounded operation receives an explicit budget spec. No operation runs without declared bounds.

7. **Immutability**: Content-addressed stores never overwrite existing entries. The store layer rejects writes where the content doesn't match the declared hash.

These contracts are not documented in any single location — they're distributed across the codebase as assertions, type checks, and convention-following code. Together, they form the system's "common law" — the unwritten rules that every component follows.

## D.17 The Security Boundary: What CAN'T the System Do?

Understanding the system's limits is as important as understanding its capabilities:

1. **Cannot modify its own verifiers**: CCAP allowlists forbid modification of `CDEL-v2/`, `meta-core/`, `Genesis/`, and `authority/`. The system's verification infrastructure is immutable from the system's perspective.

2. **Cannot change evaluation criteria**: The evaluation kernel is pinned in authority pins. The benchmark suite is on the exact-forbid list. The system cannot weaken its own quality gates.

3. **Cannot bypass content addressing**: All artifacts are SHA-256 hashed. Substituting or modifying an artifact without updating its hash (and all referencing hashes) is detectable.

4. **Cannot operate non-deterministically**: Q32 arithmetic, canonical JSON, and deterministic tie-breaking ensure that all operations are reproducible. Non-deterministic operations would be detected during verification replay.

5. **Cannot exceed budgets**: Every bounded operation has a declared budget. Exceeding it triggers fail-closed rejection.

6. **Cannot fork its own history**: The parent-chain hash mechanism prevents maintaining multiple timelines.

7. **Cannot make the system worse** (v19.0): The J dominance gate requires that the objective function for the new state is at least as good as the old state.

These constraints are not bugs or limitations — they are the design. The system's freedom to self-improve is precisely bounded by these immutable constraints. The system can improve anything within its allowed modification paths, using any strategy that passes its fixed evaluation criteria, as long as the improvement is verifiably better than the status quo. This is the "unchained" in "AGI-Stack-Unchained": maximum autonomy within constitutional bounds.

---

# Detailed Module Analysis: Function-Level Anatomy

This section provides function-level documentation for key modules, explaining not just what each function does but why it exists and how it relates to the broader system.

## M.1 omega_observer_v1.py — The System's Eyes

The observer (1,195 lines) is the largest module by raw data surface area — it touches more input sources than any other component. Its structure reveals the system's sensory architecture.

### Core Constants (Lines 1-100)

The observer defines extensive constants for metric sources and campaign identifiers:
- `METRIC_SOURCE_METASEARCH`: Performance data from search optimization campaigns.
- `METRIC_SOURCE_HOTLOOP`: Real-time performance from active campaign execution.
- `METRIC_SOURCE_SCIENCE`: Results from scientific discovery campaigns.
- `METRIC_SOURCE_POLYMATH`: Polymath domain coverage and void analytics.
- `METRIC_SOURCE_GENESIS_ENGINE`: PD (Promotion Density) and XS (eXploration Score) from SH-1.

Each metric source has a corresponding reader function that handles the specific file format and path conventions for that source. The reader functions are designed to be independent — failure to read one source doesn't prevent reading others.

Window size constants control the temporal analysis:
- `WINDOW_SIZE_CAP_FRONTIER`: The number of historical ticks used to compute the capability frontier. This bounds the observer's memory and prevents unbounded retrospection.
- Campaign-specific window sizes for per-campaign metric smoothing.

### observe() — The Main Entry Point

The `observe()` function orchestrates the complete observation pipeline:

1. **Load previous observations**: Read previous ticks' observation reports to compute deltas. The number of previous ticks read is bounded by the maximum window size across all metric sources. Each loaded observation is validated against the `omega_observation_v1` schema.

2. **Read current metrics**: For each metric source, call the corresponding reader function. If a reader fails (source file doesn't exist, schema mismatch, etc.), record a null observation for that source with the reason code.

3. **Compute deltas**: For each metric that has both current and previous values, compute the difference. Deltas use Q32 subtraction to maintain fixed-point precision.

4. **Compute capability frontier**: The capability frontier is the rolling maximum of a composite capability score over the window. If the current capability exceeds the frontier, the system is improving. If it's below the frontier, the system may be regressing.

5. **Assemble observation report**: Combine all metric readings, deltas, and frontier values into a canonical JSON document. Hash it and return both the report and its hash.

The observation report is deliberately over-inclusive — it captures every available metric, even metrics that the current decision policy doesn't use. This provides a complete audit trail and allows future policies to use historical metrics without re-running observations.

### Metric Reading Functions

Each metric source has a specialized reader:

- **Metasearch reader**: Parses performance metrics from SAS metasearch campaign outputs. Reads from specific paths in the previous run's output directory. Handles version differences between metasearch reporting formats.

- **Hotloop reader**: Reads real-time performance counters from the active campaign's execution environment. These counters include timing data (how long did the campaign take?), resource usage (memory, CPU), and throughput metrics.

- **Science reader**: Parses scientific discovery campaign outputs. These include theory quality scores, novel theory counts, validation rates, and cross-validation metrics.

- **Polymath reader**: Reads the Polymath registry and computes aggregate metrics: total domains, domains ready for conquest, conquered domains, domain coverage ratio, portfolio score, scout age (ticks since last scout). The scout age metric creates urgency — if the system hasn't scouted recently, the void may be growing.

- **Genesis Engine reader**: Reads SH-1's output artifacts to extract PD and XS values. These metrics tell the system how effective its self-improvement has been: high PD means patches are being accepted; high XS means there's unexplored territory.

## M.2 omega_decider_v1.py — The System's Brain

The decider (789 lines) transforms observations into actions. Its structure reveals the system's decision-making architecture.

### Policy Application

The policy is a JSON document defining rules that map observation conditions to actions. Each rule has:
- A **condition**: A set of metric tests (e.g., "capability_frontier_delta_q32 < 0").
- An **action template**: The type of campaign to run and its parameterization.
- A **priority**: Rules are evaluated in priority order; the first matching rule wins.

Policy evaluation is deterministic — the same observation against the same policy always selects the same rule. There are no probabilistic rules or random selections. When the user observes the system making unexpected decisions, they can replay the decision logic with the same observation and policy to understand exactly why that decision was made.

### Goal Queue Management

The goal queue is an ordered list of objectives that the system is currently pursuing. Goals have:
- **Priority**: Higher-priority goals are selected first.
- **Campaign ID**: The campaign to run when this goal is selected.
- **Completion criteria**: Conditions under which the goal is removed from the queue.
- **Expiry**: Optional tick-based expiry after which the goal is automatically removed.

Goals can be generated by the decider itself (in response to diagnoses), by the Polymath void-to-goals pipeline, or by the runaway escalation system. Goal generation is deterministic — the same inputs produce the same goal queue modifications.

### Temperature Band System

The temperature band system controls the system's exploration-exploitation tradeoff without using randomness:

| Temperature | PD Range | XS Range | Behavior |
|-------------|----------|----------|----------|
| Cold | High PD (>0.7) | Low XS (<0.3) | Exploit: run campaigns on files with high acceptance rates |
| Warm | Medium PD | Medium XS | Balance: mix exploitation and exploration |
| Hot | Low PD (<0.3) | High XS (>0.7) | Explore: target files that haven't been successfully modified |

Temperature is computed from the capability frontier's trajectory:
- Stagnating frontier → higher temperature (system needs to explore).
- Improving frontier → lower temperature (system should exploit what's working).
- Regressing frontier → maximum temperature (system needs radical exploration).

This creates an adaptive exploration strategy that responds to the system's performance trajectory without any random number generation.

## M.3 omega_promoter_v1.py — The System's Judge

The promoter (1,535 lines) is the largest single module. Its size reflects the complexity of multi-layer verification orchestration.

### Subverifier Registry

The promoter maintains a mapping from campaign IDs to verifier modules:
```
rsi_ge_symbiotic_optimizer_sh1_v0_1 → cdel.v18_0.verify_ccap_v1
rsi_polymath_scout_v1 → cdel.v18_0.verify_rsi_polymath_scout_v1
rsi_polymath_bootstrap_domain_v1 → cdel.v18_0.verify_rsi_polymath_bootstrap_v1
rsi_polymath_conquer_domain_v1 → cdel.v18_0.verify_rsi_polymath_conquer_v1
rsi_sas_science_v13_0 → cdel.v13_0.verify_rsi_sas_science_v1
... (and many more)
```

This registry is defined as constants in the module. The verifier for each tick confirms that the promoter used the correct subverifier by checking the registry mapping.

### The Promotion Pipeline (Detailed)

1. **Input Validation**: Load the campaign's outputs and validate against expected schemas. Check that all required artifacts exist and their hashes match.

2. **Subverifier Selection**: Look up the campaign ID in the registry. Import the verifier module dynamically. If the module doesn't exist or fails to import, reject the promotion.

3. **Subverifier Execution**: Call the verifier's `verify()` function with the campaign outputs. The subverifier performs campaign-specific checks (e.g., CCAP verifier checks allowlists and runs evaluation kernels).

4. **Result Processing**: Parse the subverifier's output. If the subverifier rejected the campaign, the promotion is rejected (with the subverifier's reason code forwarded).

5. **Upgrade Checks** (v19.0): If running the v19 promoter, additional gates are checked:
   - Compute J for the current state (J_old).
   - Compute J for the proposed state (J_new).
   - Require J_new >= J_old - epsilon (the epsilon allows small regressions to keep the system from getting stuck).
   - Check continuity preservation for all overlap artifacts.
   - Check treaty compliance with federated peers.

6. **Axis Bundle Assembly**: Package the verified outputs into an axis bundle — a structured directory containing the full set of artifacts ready for meta-core verification.

7. **meta-core Submission**: Call `stage_bundle()` → `verify_staged()` → read the verification receipt. If meta-core rejects the bundle, the promotion is rejected.

8. **Receipt Generation**: Create the promotion receipt containing:
   - `result.status`: `PROMOTED` or `REJECTED`.
   - `result.reason_code`: Machine-readable reason.
   - `subverifier_outcome`: The subverifier's result.
   - `meta_core_outcome`: meta-core's verification result.
   - `j_comparison` (v19.0): J_old vs J_new values.
   - Input artifact hashes for full cryptographic binding.

### Error Handling

The promoter's error handling follows the fail-closed doctrine with a twist: **different failure modes produce different reason codes**. This is critical for the learning loop — SH-1 needs to know *why* a patch was rejected to adjust its strategy:

- `CCAP_ALLOWLIST_VIOLATION`: The patch tried to modify a forbidden path.
- `CCAP_EVAL_KERNEL_FAILURE`: The patch failed the evaluation kernel's benchmarks.
- `CCAP_SCORE_BELOW_GATE`: The patch's score was below the minimum threshold.
- `CONTINUITY_VIOLATION`: The proposed state breaks overlap continuity.
- `J_DOMINANCE_VIOLATION`: The proposed state is worse than the current state.
- `BUDGET_EXHAUSTED`: The verification ran out of budget.
- `SCHEMA_MISMATCH`: An artifact didn't match its expected schema.
- `META_CORE_REJECTION`: meta-core's constitutional verification failed.
- `SUBVERIFIER_REJECTION`: The campaign-specific verifier rejected the outputs.

Each reason code tells SH-1 something different about what went wrong and how to adjust. For example, `CCAP_ALLOWLIST_VIOLATION` means "don't try to modify those paths again." `CCAP_SCORE_BELOW_GATE` means "the change was valid but not good enough — try harder." `J_DOMINANCE_VIOLATION` means "the overall system got worse — this direction is counterproductive."

## M.4 The v19.0 Continuity System: Formal Regime Transitions

The v19.0 continuity system (`continuity/check_continuity_v1.py`, 570 lines) implements a formalized approach to version transitions that is inspired by category theory.

### The Core Insight: Regimes as Categories

In the v19.0 model, each version of the system defines a "regime" — a set of:
- **Artifacts**: The objects that exist in the system.
- **Validators**: The functions that determine whether an artifact is valid.
- **Relationships**: How artifacts relate to each other.

A version transition is modeled as a **morphism** between regimes — a structure-preserving map from one version's artifacts to another's. If the morphism is valid (preserves all relationships and validation outcomes), the transition is "continuous" — existing artifacts remain valid.

### The check_continuity() Function

The function takes:
- `sigma_old_ref`, `sigma_new_ref`: State snapshots from old and new regimes.
- `regime_old_ref`, `regime_new_ref`: Regime definitions.
- `morphism_ref`: The translation between regimes.
- `budgets`: Computational bounds.

It proceeds through these steps:

1. **Load all references**: Deserialize the regime definitions, state snapshots, and morphism. Validate these against their schemas.

2. **Compute overlap**: Identify which artifacts exist in both regimes (the "overlap set"). These are the artifacts that must remain valid across the transition.

3. **Apply translation**: For each overlap artifact, apply the morphism's translator bundle to translate it from old-regime format to new-regime format.

4. **Validate translated artifacts**: Check that translated artifacts are valid under the new regime's validators.

5. **Verify preservation**: Confirm that the translated artifacts' semantic content is preserved — that the translation didn't introduce or remove meaningful information.

6. **Generate continuity certificate**: If all checks pass, produce a certificate binding the two regime references, the morphism, and the validation outcomes.

### _accept_under_regime_overlap() — The Overlap Acceptance Function

This function (lines 233-261) checks whether a specific artifact is acceptable under the overlap policy defined by a regime. The regime defines which artifacts are part of the overlap set (shared between versions) and which are version-specific. Only overlap artifacts need continuity verification — version-specific artifacts are free to change.

### Loaders and Common Utilities

The continuity module has its own loader system (`loaders_v1.py`, 4,492 bytes) providing:
- `ArtifactRef`: A reference to a content-addressed artifact (path + hash + optional payload).
- `RegimeRef`: A reference to a regime definition.
- `BudgetBundleV1`: Budget constraints for continuity checking.
- `load_artifact_ref()`: Load and validate an artifact reference.
- `load_regime_ref()`: Load and validate a regime reference.
- `load_budget_bundle()`: Load budget constraints.

The common utilities (`common_v1.py`, 7,476 bytes) provide:
- `canon_hash_obj()`: Hash any JSON-serializable object through GCJ-1.
- `canonical_json_size()`: Compute the wire size of a canonical JSON document.
- `fail()`: Raise an error with a reason code (fail-closed exit).
- `make_budget_tracker()`: Create a budget tracking object.
- `sorted_by_canon()`: Sort a list of objects by their canonical hashes.
- `validate_schema()`: Lightweight schema validation.
- `verify_declared_id()`: Check that an artifact's content matches its declared hash.

## M.5 The Genesis Engine SH-1: Receipt Analysis Pipeline

The Genesis Engine's receipt analysis pipeline (`ge_symbiotic_optimizer_v0_3.py`, 1,588 lines) is worth examining in detail because it reveals how the system learns from its own history.

### Stage 1: Receipt Collection

SH-1 scans the `runs/` directory for historical Omega daemon ticks. For each tick, it looks for CCAP receipts and refutation certificates. It builds a per-file history:

```python
{
  "tools/genesis_engine/ge_config_v1.json": {
    "promotions": 7,
    "rejections": 15,
    "reason_codes": {
      "CCAP_SCORE_BELOW_GATE": 8,
      "J_DOMINANCE_VIOLATION": 4,
      "CCAP_EVAL_KERNEL_FAILURE": 3
    },
    "last_patch_tick": 38,
    "behavior_sigs": ["sha256:abc...", "sha256:def..."]
  },
  "campaigns/rsi_polymath_scout_v1/rsi_polymath_scout_pack_v1.json": {
    "promotions": 12,
    "rejections": 3,
    ...
  }
}
```

### Stage 2: PD/XS Computation

From the per-file history, PD and XS are computed:
- `PD = promotions / (promotions + rejections)` — the success rate.
- `XS = 1.0 - PD` — the exploration potential (simplified; the actual computation may include age factors and novelty bonuses).

Files with no history receive a default XS of 1.0 (fully exploratory) and PD of 0.0.

### Stage 3: Bucket Planning

Files are sorted into three buckets based on PD:
- **HOTFIX** (PD > 0.7): These files accept patches readily. Safe for exploitation.
- **INCREMENTAL** (0.3 <= PD <= 0.7): Mixed history. Worth trying with moderate-risk patches.
- **EXPLORATORY** (PD < 0.3): These files reject most patches. Only explore if XS indicates untapped potential.

The fraction of total patches allocated to each bucket is configured in `ge_config_v1.json` using Q32 values (e.g., `858993459` ≈ 20% for HOTFIX).

### Stage 4: Patch Generation

For each file in each bucket, SH-1 selects an appropriate template:
- HOTFIX files → conservative templates (COMMENT_APPEND — add explanatory comments).
- INCREMENTAL files → moderate templates (JSON_TWEAK_COOLDOWN — adjust timing parameters).
- EXPLORATORY files → aggressive templates (JSON_TWEAK_BUDGET_HINT — change budget allocations).

Template selection is deterministic: given the file's PD, XS, and the current tick number, the same template is always selected.

The patch itself is generated by an LLM interaction (when available) or by deterministic template expansion. For template-based generation:
- `COMMENT_APPEND`: Generates a comment string based on the file's history and recent rejection reasons, then appends it to the file.
- `JSON_TWEAK_COOLDOWN`: Parses the file as JSON, finds `cooldown_ticks_u64` fields, and adjusts them by a factor derived from the file's PD.
- `JSON_TWEAK_BUDGET_HINT`: Similar, but targets `budget_cost_hint_q32` fields.

### Stage 5: Hard-Avoid Filtering

Before emitting a patch, SH-1 checks it against the hard-avoid list. The behavior signature (`sh1_behavior_sig_v1.py`) computes a fingerprint of the patch's effects:
- Which files are modified?
- What is the type of modification (add, remove, change)?
- What is the approximate magnitude of change?

If the new patch's behavior signature is too similar to a previously rejected patch's signature (cosine similarity above a threshold), the patch is filtered out. This prevents novelty laundering — submitting slightly modified versions of the same bad idea.

### Stage 6: CCAP Bundle Emission

Surviving patches are packaged into CCAP bundles:
- The patch is serialized as a diff blob.
- The blob is SHA-256 hashed and stored.
- A CCAP bundle document is created referencing the blob, the base tree ID, the evaluation kernel, and the PD/XS metrics.
- The bundle document is canonicalized and hashed.
- The bundle is written to the output directory for the promoter to process.

## M.6 The meta-core Ledger: Crash-Safe Audit Trail

meta-core maintains a crash-safe audit ledger that records every commit and rollback. The ledger implementation (in `ledger.py`, referenced from `activation.py`) provides:

- `append_entry_crash_safe()`: Write a ledger entry using atomic file operations. The entry is first written to a temporary file, then atomically renamed to its final destination. This ensures that the ledger is never in a half-written state — even if the process crashes mid-write, the entry is either fully present or fully absent.

- `make_commit_entry()`: Create a ledger entry for a successful commit. The entry includes the bundle hash, the previous state hash, the timestamp, and the verification receipt hash.

- `make_rollback_entry()`: Create a ledger entry for a rollback. The entry includes the reason for rollback, the state being reverted to, and the state being reverted from.

- `read_last_entry()`: Read the most recent ledger entry to determine the current state.

The ledger is append-only — entries can never be modified or deleted. This creates an immutable audit trail of every state transition the system has undergone. Combined with the hash chain in the state object, the ledger provides two independent records of the system's history that can be cross-validated for consistency.

---

# Design Rationale: Why This Architecture?

## R.1 Why Determinism Over Probability?

Most AI/ML systems use probabilistic methods — random sampling, stochastic gradient descent, probabilistic inference. The AGI-Stack deliberately rejects all randomness in favor of total determinism. Why?

The answer is **verifiability**. A probabilistic system produces different outputs on each run, making replay-based verification impossible. You can't verify that yesterday's run was correct by re-running it today, because you'll get different results. Deterministic verification requires deterministic computation.

This has real costs. The system cannot use random exploration (as in epsilon-greedy reinforcement learning). It cannot use dropout or stochastic depth in any neural architectures. It cannot use random seeds for diversity in patch generation (seeds must be derived from state hashes). In exchange, it gains the ability to verify every computation it has ever performed — a property no probabilistic system can achieve.

## R.2 Why Fail-Closed Over Fail-Safe?

Fail-safe systems attempt to reach a known-good state when errors occur. Fail-closed systems simply reject the current operation. The AGI-Stack chose fail-closed because fail-safe requires defining what "safe" means — and in a self-modifying system, the definition of "safe" might itself be compromised.

Consider a fail-safe verifier that, when encountering an error, falls back to "accept the bundle unchanged." An adversarial proposer could craft inputs that trigger errors in the verification path, causing the verifier to accept unverified bundles. Fail-closed eliminates this attack vector entirely: the only way through the verifier is a clean pass.

The cost is false rejections — valid operations might be rejected due to bugs in the verification code. But false rejections are safely recoverable (retry the operation, fix the verifier bug), while false acceptances could be catastrophic (compromised state, corrupted trust chain).

## R.3 Why Q32 Over IEEE 754?

IEEE 754 floating-point is the industry standard for numerical computation. The AGI-Stack rejects it because IEEE 754 allows implementation-defined behavior at several points:
- Rounding mode (round-to-nearest-even by default, but configurable).
- Extended precision (80-bit intermediates on x87 FPUs).
- FMA (fused multiply-add) optimization (changes rounding behavior).
- NaN payload handling (implementation-specific).

Any of these differences between machines would cause replay verification to fail. Q32 eliminates all of them by reducing numerical computation to integer arithmetic, which is fully specified by every hardware platform and language standard.

## R.4 Why Tick-Based Over Event-Driven?

Event-driven architectures process events as they arrive, with concurrency and asynchronous execution. Tick-based architectures process one work unit at a time in a strict sequence. The AGI-Stack chose ticks for three reasons:

1. **Determinism**: Event processing order in concurrent systems is non-deterministic. Ticks enforce a total order on all operations.
2. **Auditability**: Each tick produces a complete, self-contained artifact directory. There are no inter-tick race conditions or partial states.
3. **Rollback simplicity**: Reverting one tick requires only restoring the previous state. Reverting concurrent events requires understanding their causal dependencies.

The cost is throughput — the system can only process one operation at a time. But since the system's primary goal is safe self-improvement (not high-throughput transaction processing), this tradeoff is favorable.

## R.5 Why Content Addressing Over Naming?

Content-addressed systems identify objects by their content hash. Naming systems use human-assigned labels. Content addressing provides three properties that naming cannot:

1. **Immutability**: An object's identity is bound to its content. Changing the content changes the identity.
2. **Global uniqueness**: SHA-256 collisions are practically impossible. Two objects with the same hash are the same object.
3. **Integrity verification**: Loading an object and comparing its hash to its identifier verifies integrity in a single operation.

The cost is human readability — `sha256:a77ce5f4879113175bb2edf6f442d64afd12294941c43ac9be9f4e0b1758139d` is not a readable identifier. The system mitigates this through the filename convention (`sha256_<hex>.<schema_version>.json`) and through reference objects that map human-readable names to content hashes.

---

# Appendix D: The Complete Version Evolution

The AGI-Stack's version history tells the story of its evolution from a simple campaign runner to a self-verifying, self-improving, federated AI system.

## v1.5r — The Foundation

v1.5r established the RSI (Recursive Self-Improvement) infrastructure:
- Basic campaign runner with schema validation.
- First verifier: `verify_rsi_v1.py`.
- Tracker framework for monitoring campaign state.
- Test suite infrastructure.
- The `CDEL` concept introduced: every campaign run is a "definitional extension" of the system's capabilities, and the ledger records these extensions.

At this stage, the system could run campaigns and verify their outputs, but it had no decision-making capability — campaigns were selected manually.

## v2.0-v2.2 — Self-Amendment

These versions introduced code-level self-modification:
- `autocode_patch`: Automatic code patching (precursor to CCAP).
- `csi_meter`: Code Similarity Index for detecting redundant patches.
- New verifiers: `verify_rsi_csi_v1.py`, `verify_rsi_demon_v8.py`.
- Campaign count grew from 5 to 15.

The system could now propose and apply code changes, but the modification process was not yet cryptographically verified.

## v3.0-v5.0 — Expansion Phase

Rapid campaign development:
- Scientific theory campaigns (`boundless_science`, `sas_science`).
- Mathematical conjecture campaigns (`boundless_math`, `sas_math`).
- Architecture synthesis campaigns (`arch_synthesis`).
- Campaign count reached 30+.
- Multiple CDEL versions: v3.0 through v5.0.

This period focused on breadth — adding new capability domains rather than deepening the verification infrastructure.

## v6.0-v8.0 — Verification Hardening

Focus shifted to verification robustness:
- Multiple specialized verifiers per domain.
- Schema validation infrastructure formalized.
- Deterministic replay for all campaign types.
- Canon format (precursor to GCJ-1) introduced.
- CDEL versions v6.0 through v8.0.

## v9.0-v11.1 — Architecture Maturation

The system's architecture solidified:
- Evaluation kernel system formalized.
- Operator pool and sandbox profile systems.
- Model genesis: automated model-level code generation.
- Architecture synthesis: automated architecture proposals.
- 40+ campaigns.
- CDEL versions through v11.1.

## v12.0-v14.0 — Daemon Architecture

The Omega daemon concept emerged:
- Code-level self-amendment campaigns (v12.0).
- Scientific discovery campaigns (v13.0).
- System-level self-amendment campaigns (v14.0).
- The observe-decide-execute model began to crystallize.
- CDEL versions through v14.0.

## v15.0-v16.1 — Deep Verification

Verification deepened dramatically:
- Kernel-level verification (v15.0): verifying at the lowest code level.
- SAS metasearch (v16.0-v16.1): search optimization with full verification.
- Native code lift verification (v17.0): verifying compiled code.
- 60+ campaigns.

## v18.0 — The Omega Daemon (Current Production)

The transformative release that unified everything into the tick-based Omega daemon:
- **Observer**: Multi-source metric collection with capability frontier.
- **Diagnoser**: Severity-based issue detection.
- **Decider**: Policy-based goal selection with temperature bands.
- **Executor**: Workspace-isolated campaign dispatch.
- **Promoter**: Multi-layer verification orchestration (1,535 lines).
- **Activator**: Crash-safe meta-core integration.
- **Verifier**: Complete deterministic replay (1,886 lines).
- **Runaway Mode**: Controlled escalation for breaking stalls.
- **CCAP Protocol**: Universal patch verification.
- **Q32 Arithmetic**: Deterministic fixed-point computation.
- **GCJ-1**: Guaranteed Canonical JSON.
- **Authority System**: Cryptographic trust pinning.
- **Genesis Engine SH-1**: Receipt-driven meta-learning self-improvement.
- **Polymath**: Autonomous domain discovery and conquest.
- 78+ campaigns across all domains.

## v19.0 — Federation (Current Development)

Building on v18.0's foundation:
- **Treaty Verification**: Formal interoperability contracts between systems.
- **Continuity Checking**: Mathematically verified regime transitions.
- **World Snapshots (SIP)**: Tamper-proof state captures with leakage detection.
- **Objective J**: Formal dominance function for state transitions.
- **Overlap Semantics**: Category-theoretic artifact preservation.
- **Morphisms**: Structure-preserving maps between system versions.
- **ICAN Identifiers**: Canonical cross-system artifact naming.
- **Super-Unified Campaign**: Single entry point for the complete daemon.
- **Team-1 Replay Verifier**: Lazy-loaded advanced replay verification.

---

# Appendix E: The Complete Directory Map

```
AGI-Stack-Unchained/
├── README.md                    # High-level project overview
├── ignite_runaway.sh           # Top-level autonomous execution loop (307 lines)
├── SOURCE_OF_TRUTH.md          # This document
│
├── meta-core/                  # RE1: Trusted Computing Base
│   ├── engine/
│   │   ├── activation.py       # Stage/verify/canary/commit/rollback (414 lines)
│   │   ├── constants.py        # System constants and failpoints
│   │   ├── gcj1_min.py         # Minimal GCJ-1 canonical JSON
│   │   ├── atomic_fs.py        # Crash-safe atomic file operations
│   │   ├── ledger.py           # Crash-safe audit ledger
│   │   ├── store.py            # Bundle storage operations
│   │   ├── verifier_client.py  # Interface to Rust kernel verifier
│   │   └── merkle.py           # Merkle tree computation
│   ├── kernel/
│   │   └── verifier/           # Rust-based constitutional verifier
│   └── store/                  # Active bundles and historical state
│       ├── active/             # Currently active state
│       └── staged/             # Staging area for pending bundles
│
├── CDEL-v2/                    # RE2: Verification Layer (~50,000+ lines)
│   ├── cdel/
│   │   ├── v1_7r/              # v1.7r: Canonical format (canon.py)
│   │   ├── v18_0/              # v18.0: Production Omega verifiers
│   │   │   ├── omega_observer_v1.py      # 1,195 lines
│   │   │   ├── omega_diagnoser_v1.py     # 253 lines
│   │   │   ├── omega_decider_v1.py       # 789 lines
│   │   │   ├── omega_executor_v1.py      # 349 lines
│   │   │   ├── omega_promoter_v1.py      # 1,535 lines
│   │   │   ├── omega_activator_v1.py     # 332 lines
│   │   │   ├── omega_common_v1.py        # 394 lines (Q32, GCJ-1)
│   │   │   ├── omega_state_v1.py         # 160 lines
│   │   │   ├── omega_runaway_v1.py       # 360 lines
│   │   │   ├── ccap_runtime_v1.py        # 313 lines
│   │   │   ├── verify_rsi_omega_daemon_v1.py   # 1,886 lines
│   │   │   ├── verify_ccap_v1.py               # 819 lines
│   │   │   ├── verify_rsi_polymath_scout_v1.py
│   │   │   ├── verify_rsi_polymath_bootstrap_v1.py
│   │   │   ├── verify_rsi_polymath_conquer_v1.py
│   │   │   ├── tests_omega_daemon/       # Omega daemon tests
│   │   │   └── tests_ccap/              # CCAP verification tests
│   │   ├── v19_0/              # v19.0: Federation verifiers
│   │   │   ├── omega_promoter_v1.py       # 692 lines (continuity/J gates)
│   │   │   ├── federation/
│   │   │   │   ├── check_treaty_v1.py     # 825 lines
│   │   │   │   ├── check_treaty_coherence_v1.py
│   │   │   │   ├── check_ok_overlap_signature_v1.py
│   │   │   │   ├── check_refutation_interop_v1.py
│   │   │   │   ├── ok_ican_v1.py          # ICAN identifiers
│   │   │   │   ├── portability_protocol_v1.py
│   │   │   │   └── pins/                 # Federation pins
│   │   │   ├── continuity/
│   │   │   │   ├── check_continuity_v1.py  # 570 lines
│   │   │   │   ├── check_meta_law_v1.py    # 8,551 bytes
│   │   │   │   ├── objective_J_v1.py       # 191 lines
│   │   │   │   ├── check_constitution_upgrade_v1.py
│   │   │   │   ├── check_kernel_upgrade_v1.py
│   │   │   │   ├── check_env_upgrade_v1.py
│   │   │   │   ├── check_translator_totality_v1.py
│   │   │   │   ├── check_backrefute_v1.py
│   │   │   │   ├── common_v1.py            # 7,476 bytes
│   │   │   │   └── loaders_v1.py           # 4,492 bytes
│   │   │   └── world/
│   │   │       ├── sip_v1.py               # 346 lines (SIP)
│   │   │       ├── check_world_snapshot_v1.py
│   │   │       ├── check_world_task_binding_v1.py
│   │   │       └── merkle_v1.py            # World root Merkle tree
│   │   └── [v3.0 through v17.0]/           # Historical verifier versions
│   └── scripts/
│       ├── smoke_e2e.sh
│       ├── smoke_rebuild.sh
│       └── smoke_statcert_adopt.sh
│
├── Extension-1/                # RE3: Proposer Layer (Untrusted)
│   ├── agi-orchestrator/
│   │   └── caoe_v1_1/          # Legacy CAOE optimizer
│   │       ├── wake/           # Anomaly mining
│   │       ├── sleep/          # Candidate synthesis
│   │       └── dawn/           # Selection & learning
│   └── self_improve_code/
│       ├── analyzer/           # Code analysis
│       ├── transformer/        # Code transformation
│       └── validator/          # Validation logic
│
├── Genesis/                    # RE4: Specification Layer
│   ├── schema/                 # 532+ JSON schemas
│   │   ├── omega_state_v1.json
│   │   ├── ccap_bundle_v1.json
│   │   ├── evaluation_kernel_v1.json
│   │   └── [530+ more schemas]
│   ├── docs/                   # 28 protocol specifications
│   ├── test_vectors/           # 45 canonicalization test vectors
│   ├── conformance/            # Conformance test harness
│   ├── examples/               # Example capsule files
│   └── tools/                  # Validation utilities
│
├── authority/                  # Trust Anchor Directory
│   ├── authority_pins_v1.json  # SHA-256 root of trust
│   ├── ccap_patch_allowlists_v1.json  # CCAP path restrictions
│   ├── evaluation_kernels/     # EK definitions
│   │   └── ek_active_v1.json   # Active evaluation kernel
│   ├── operator_pools/         # Operator pool configs
│   └── dsbx_profiles/          # Sandbox profiles
│
├── orchestrator/               # Campaign Coordination Layer
│   ├── rsi_omega_daemon_v18_0.py  # v18.0 entry point
│   ├── rsi_omega_daemon_v19_0.py  # v19.0 entry point
│   ├── omega_v18_0/            # v18.0 coordination (12 files)
│   ├── omega_v19_0/            # v19.0 coordination (3 files)
│   ├── common/                 # Shared utilities (4 files)
│   ├── omega_skill_generated_sh1_v1.py
│   ├── omega_skill_scaffold_generator_v1.py
│   └── [15+ campaign-specific orchestrators]
│
├── tools/                      # Operational Tools
│   ├── genesis_engine/         # Genesis Engine SH-1
│   │   ├── ge_symbiotic_optimizer_v0_3.py  # 1,588 lines
│   │   ├── ge_config_v1.json              # SH-1 configuration
│   │   ├── sh1_pd_v1.py                   # Promotion Density
│   │   ├── sh1_xs_v1.py                   # eXploration Score
│   │   ├── sh1_behavior_sig_v1.py         # Behavior signatures
│   │   └── ge_audit_report_sh1_v0_1.py    # Audit reports
│   ├── omega/                  # Omega tools
│   │   └── omega_benchmark_suite_v1.py    # [PROTECTED] Benchmarks
│   └── polymath/               # Polymath tools
│       ├── polymath_scout_v1.py           # Domain void discovery
│       ├── polymath_domain_bootstrap_v1.py # Domain setup
│       ├── polymath_domain_corpus_v1.py   # Domain conquest
│       └── polymath_void_to_goals_v1.py   # Void-to-goal conversion
│
├── polymath/                   # Polymath Data Layer
│   ├── registry/               # Domain registry
│   │   ├── polymath_domain_registry_v1.json
│   │   ├── polymath_scout_status_v1.json
│   │   └── polymath_void_report_v1.jsonl
│   ├── domain_policy_v1.json   # Allowlist/denylist for domains
│   └── store/                  # Content-addressed blob store
│       ├── blobs/sha256/       # SHA-256 indexed blobs
│       ├── receipts/           # Fetch receipts
│       └── indexes/            # Content indexes (JSONL)
│
├── campaigns/                  # Campaign Configurations (78+)
│   ├── rsi_omega_daemon_v19_0_super_unified/
│   ├── rsi_ge_symbiotic_optimizer_sh1_v0_1/
│   ├── rsi_polymath_scout_v1/
│   ├── rsi_polymath_bootstrap_domain_v1/
│   ├── rsi_polymath_conquer_domain_v1/
│   ├── rsi_sas_science_v13_0/
│   └── [72+ more campaign packs]
│
├── domains/                    # Polymath Domain Data
│   └── [domain_id]/
│       ├── domain_pack_v1.json
│       ├── L0/, L1/, L2/       # Layered data packs
│       ├── solver/
│       └── corpus/
│
├── daemon/                     # Daemon State Directory
│   └── [campaign_id]/
│       └── state/              # Per-campaign state files
│
├── runs/                       # Historical Tick Outputs
│   └── [run_id]/
│       └── [tick_artifacts]
│
└── .omega_cache/               # Transient Computation Cache
```

---

# Appendix F: Emergent Properties — What Arises From the Design

The AGI-Stack's architecture produces several emergent properties that are not explicitly coded but arise from the interaction of its components:

## F.1 Self-Stabilizing Improvement

The combination of the SH-1 learning loop and the CCAP rejection signal creates a self-stabilizing improvement process. When a type of patch consistently fails, SH-1's PD score for that file drops, reducing the proportion of patches targeting it. When a type of patch consistently succeeds, PD rises, increasing exploitation. This creates a natural equilibrium — the system converges toward patches that are accepted, without any explicit convergence criterion.

## F.2 Knowledge Accumulation

Each conquered Polymath domain permanently increases the system's capability, and this capability is reflected in higher observation scores, which influence the decider's goal selection, which prioritizes different campaigns. Over many ticks, the system accumulates a growing portfolio of mastered domains, shifting its attention toward increasingly novel and challenging territories.

## F.3 Replay as Specification

Because the verifier works by replay, the specification of "correct behavior" is the behavior itself. This means the system's specification evolves with its code — new verifier versions define new specifications. Old artifacts can always be verified against old verifier versions (which are preserved). This creates a living specification that grows with the system.

## F.4 Constitutional Immutability as Safety

The immutability of the authority layer, meta-core, CDEL-v2, and Genesis under CCAP restrictions means that no matter how many self-improvement cycles the system runs, its safety properties are preserved. The system can become arbitrarily more capable within its allowed domains, but it cannot weaken its own verification infrastructure.

## F.5 Crash Resilience as Liveness

The ignite loop's crash resurrection mechanism ensures that the system always eventually makes progress. A single tick failure doesn't stop the system — it retries, and the deterministic nature of the computation means that transient failures (disk full, memory pressure, network timeout) are automatically resolved on retry. Only permanent failures (bug in the code) require human intervention, and even those are safely contained by the fail-closed doctrine.

## F.6 Federated Consistency

The v19.0 treaty and continuity systems allow multiple instances of the system (or different versions of the same instance) to interoperate while maintaining consistency guarantees. Each instance can evolve independently as long as it maintains its treaty obligations — shared artifacts must remain translatable, overlap semantics must be preserved, and refutation certificates must be interoperable. This creates a federated network of self-improving systems that can cooperate without sacrificing autonomy.

---

*This Source of Truth document provides a complete reconstruction manual for the AGI-Stack-Unchained system. An external intelligence reading this document should be able to understand the system's intent, architecture, mechanics, constraints, and operational patterns with sufficient depth to reason about any aspect of the system's behavior.*

*The five Universal Context layers—Architectural Philosophy, Control Flow, Data Topography, Trust & Verification, and Operational Mechanics—together form a complete mental model of a system that can observe its world, reason about what to do, act on its decisions, verify that its actions were correct, and learn from the outcomes to improve its future actions. All within an immutable constitutional framework that ensures improvement is genuine and safe.*

---

# Appendix G: Deep Analysis of the Campaign Inventory

The 78+ campaigns represent the system's complete repertoire of actions. Each campaign type embodies a specific capability and integrates differently with the verification pipeline.

## G.1 The Genesis Engine Campaign Family

The Genesis Engine campaigns form the core of the system's self-improvement capability:

### rsi_ge_symbiotic_optimizer_sh1_v0_1
- **Type**: GE_SYMBIOTIC_OPTIMIZER
- **Verifier**: `cdel.v18_0.verify_ccap_v1`
- **Escalation**: Activated at runaway level 5 with reason TESTING
- **Learning**: Receipt-driven via PD/XS analysis
- **Output**: CCAP bundles containing code patches
- **Targets**: Files matching CCAP allowlist (orchestrator/, tools/genesis_engine/, tools/omega/, polymath/registry/, campaigns/)
- **Template Types**: COMMENT_APPEND, JSON_TWEAK_COOLDOWN, JSON_TWEAK_BUDGET_HINT
- **Budget**: Configurable via `ge_config_v1.json` bucket fractions

This campaign represents the system's most sophisticated self-improvement mechanism. Unlike simple code generators, SH-1 is informed by its own history — it knows which files accept changes, which reject them, and what types of rejections occur. This makes it progressively more effective over time, as it learns the statistical landscape of patch acceptance.

The symbiotic relationship referenced in the name is between the proposer (SH-1) and the verifier (CCAP). The verifier provides rejection signals that the proposer uses to improve; the proposer generates candidates that test the verifier's boundaries. This creates a co-evolutionary dynamic where both components drive each other's development.

### Genesis Engine Configuration Deep Dive

The `ge_config_v1.json` file controls SH-1's behavior:
```json
{
  "schema_version": "ge_config_v1",
  "bucket_fractions_q32": {
    "hotfix": 858993459,
    "incremental": 1717986918,
    "exploratory": 1717986918
  },
  "max_patches_per_run": 5,
  "hard_avoid_similarity_threshold_q32": 3865470566,
  "min_history_ticks": 3,
  "pd_smoothing_alpha_q32": 2147483648
}
```

Breaking down these Q32 values:
- `858993459 / 2^32 ≈ 0.20` → 20% of patches go to hotfix bucket
- `1717986918 / 2^32 ≈ 0.40` → 40% to incremental, 40% to exploratory
- `3865470566 / 2^32 ≈ 0.90` → 90% similarity threshold for hard-avoid filtering
- `2147483648 / 2^32 = 0.50` → 50% exponential smoothing for PD computation

The `min_history_ticks` parameter prevents SH-1 from making decisions with insufficient data — at least 3 historical ticks must be available before PD/XS computation is considered reliable.

## G.2 The Polymath Campaign Family

The Polymath campaigns implement autonomous scientific domain discovery:

### rsi_polymath_scout_v1
- **Type**: POLYMATH_SCOUT
- **Verifier**: `cdel.v18_0.verify_rsi_polymath_scout_v1`
- **Input**: Current domain registry, domain policy, store root
- **Output**: Updated void report (JSONL), scout status, optional registry updates
- **Key Metric**: `top_void_score_q32` — highest-void candidate found
- **Network**: Uses `OMEGA_NET_LIVE_OK` for optional live fetches

The scout campaign is the system's curiosity engine. It systematically scans for scientific domains that the system doesn't yet cover, quantifying the "void" — the gap between what the system knows and what exists in the broader scientific landscape. High void scores represent high-value exploration targets.

The scout's domain policy (`polymath/domain_policy_v1.json`) defines allowlist and denylist keywords. Domains matching denylist keywords are excluded regardless of void score. This provides a human-configurable filter on the system's exploration scope.

### rsi_polymath_bootstrap_domain_v1
- **Type**: POLYMATH_BOOTSTRAP
- **Verifier**: `cdel.v18_0.verify_rsi_polymath_bootstrap_v1`
- **Input**: Void report (highest-void candidate), store root, registry
- **Output**: Complete domain pack under `domains/<domain_id>/`
- **Content**: L0 (raw data), L1 (processed), L2 (structured), solver, corpus
- **Network**: Requires data fetching for domain bootstrapping

Bootstrapping creates a complete domain pack from scratch. This involves:
1. Fetching reference data for the domain (from cache or network).
2. Processing the data into layered packs (L0 raw, L1 clean, L2 structured).
3. Creating a domain solver (validation logic specific to this domain).
4. Building a correspondence corpus (examples for the domain's concepts).
5. Recording all fetch operations as receipts in `polymath/store/receipts/`.

### rsi_polymath_conquer_domain_v1
- **Type**: POLYMATH_CONQUER
- **Verifier**: `cdel.v18_0.verify_rsi_polymath_conquer_v1`
- **Input**: Bootstrapped domain pack, system models
- **Output**: Conquest report, updated registry
- **Key Metric**: Domain-specific accuracy/coverage scores

Conquest runs the system's models against the domain's corpus to establish baseline performance, then iterates to improve. A domain is "conquered" when the system's performance exceeds the domain's validation thresholds.

## G.3 The Science Campaign Family

Scientific discovery campaigns generate and validate theories:

### rsi_sas_science_v13_0
- **Type**: SAS_SCIENCE
- **Verifier**: `cdel.v13_0.verify_rsi_sas_science_v1`
- **Input**: Scientific problem specification, existing theory base
- **Output**: New theories, validation results, cross-validation metrics
- **Key Achievement**: Discovers theories that the system didn't previously know

### rsi_boundless_science_v*
- **Type**: BOUNDLESS_SCIENCE
- **Open-ended**: No fixed problem specification
- **Output**: Novel scientific insights and their validation
- **Purpose**: Expand the system's scientific knowledge without predefined goals

## G.4 The Code Amendment Campaign Family

Code-level self-modification campaigns:

### rsi_sas_code_v12_0
- **Type**: SAS_CODE
- **Verifier**: `cdel.v12_0.verify_rsi_sas_code_v1`
- **Scope**: Code-level modifications to the system's implementation
- **Constraint**: All modifications go through CCAP verification

### rsi_sas_system_v14_0
- **Type**: SAS_SYSTEM
- **Verifier**: `cdel.v14_0.verify_rsi_sas_system_v1`
- **Scope**: System-level modifications (more comprehensive than code-level)

### rsi_sas_kernel_v15_0
- **Type**: SAS_KERNEL
- **Verifier**: `cdel.v15_0.verify_rsi_sas_kernel_v1`
- **Scope**: Kernel-level verification of the system's deepest layers

## G.5 The Metasearch Campaign Family

Search optimization campaigns that improve the system's ability to find information:

### rsi_sas_metasearch_v16_0 / rsi_sas_metasearch_v16_1
- **Type**: SAS_METASEARCH
- **Verifier**: `cdel.v16_0.verify_rsi_sas_metasearch_v1` / `v16_1`
- **Scope**: Optimizing search algorithms and index structures
- **Metric**: Search accuracy, recall, latency

## G.6 Campaign Interaction Patterns

Campaigns don't operate in isolation — they interact through the daemon's observation pipeline:

**Science → Scout feedback**: When science campaigns produce low novelty scores, the observer records low science metrics. The decider may respond by prioritizing Polymath scouting to discover new domains for scientific exploration.

**Scout → Bootstrap chain**: High void scores trigger bootstrap campaigns. The bootstrap campaign updates the domain registry, which the scout reads in its next run — the scout's void report reflects the newly bootstrapped domain.

**SH-1 → CCAP → SH-1 feedback**: SH-1's generated patches go through CCAP verification. The receipts (acceptance or rejection) become input to SH-1's next run. Accepted patches shift PD upward; rejected patches shift PD downward and add behavior signatures to the hard-avoid list.

**Runaway → SH-1 escalation**: When the decider enters runaway mode at level 5, it routes to SH-1 with expanded budgets and exploration parameters. This gives SH-1 more resources to try aggressive patches that it might not attempt under normal operation.

---

# Appendix H: The Trust Model in Mathematical Terms

For readers with a formal verification background, the AGI-Stack's trust model can be expressed precisely:

## H.1 Trust as a Partial Order

Define a partial order on system layers: RE1 < RE2 < RE3 < RE4, where L1 < L2 means "L1 is more trusted than L2."

**Verification axiom**: ∀ artifact a produced by layer L_i, ∃ verification function v_j at layer L_j where j < i such that v_j(a) must return ACCEPT before a is integrated.

**Modification axiom**: ∀ layer L_i, L_i cannot modify any layer L_j where j ≤ i. (A layer cannot modify itself or any more-trusted layer.)

**Fail-closed axiom**: ∀ verification function v, ∀ input x, if v(x) encounters any error condition, v(x) returns REJECT.

## H.2 Determinism as Verifiability

Define a computation C as deterministic if: ∀ inputs x_1 = x_2, C(x_1) = C(x_2) (same inputs always produce same outputs).

**Replay theorem**: If computation C is deterministic, then verify(C, inputs, recorded_outputs) = (replay(C, inputs) == recorded_outputs).

This theorem reduces verification to replay. No complex proof system is needed — just re-execution. The cost is that C must be deterministic, which is why Q32, canonical JSON, and deterministic tie-breaking exist.

## H.3 J Dominance as Progress Guarantee

Define J: SystemState → ℤ₃₂ as the objective function (Section 4.7).

**Dominance gate**: A state transition s → s' is allowed only if J(s') ≥ J(s).

This creates a monotonically non-decreasing sequence of J values across ticks. Combined with the bounded nature of the J function (all terms are bounded by their debt horizons), this guarantees eventual convergence — the system must eventually reach a state where no further improvement is possible, or continue improving indefinitely.

## H.4 Content Addressing as Integrity

Define hash: Bytes → {0,1}^256 as SHA-256.

**Content address**: An artifact a has identity id(a) = hash(canon(a)).

**Integrity lemma**: If an artifact a is loaded from storage and hash(canon(a)) ≠ id(a), then a has been corrupted or substituted.

**Chain integrity theorem**: If state s has parent_hash p, and state s' has parent_hash hash(canon(s)), then s' is a valid successor of s. The complete chain from genesis to current state forms a hash-linked list that is tamper-evident.

## H.5 CCAP Allowlist as Access Control

Define A_allow = {path | ∃ prefix p ∈ allow_prefixes : path starts with p}
Define A_forbid = {path | ∃ prefix p ∈ forbid_prefixes : path starts with p} ∪ forbid_exact_paths

**Access control function**: allowed(path) = (path ∈ A_allow) ∧ (path ∉ A_forbid)

**Self-reinforcement theorem**: The allowlist file itself is in A_forbid (it's under `authority/`), and the forbid_prefixes include `authority/`, `meta-core/`, `CDEL-v2/`, and `Genesis/`. Therefore, no CCAP-verified patch can modify the access control rules, the verification infrastructure, or the specification layer.

---

# Final Notes: Reading the System

To understand any behavior of the AGI-Stack, follow this reading order:

1. **Start with the ignite loop** (`ignite_runaway.sh`) to understand the top-level control flow.
2. **Read the orchestrator entry point** (`orchestrator/rsi_omega_daemon_v19_0.py`) to see how a single tick is structured.
3. **Follow the pipeline**: observer → diagnoser → decider → executor → promoter → activator.
4. **Examine the verifier** (`verify_rsi_omega_daemon_v1.py`) to understand what "correct behavior" means for each phase.
5. **Study the CCAP protocol** (`verify_ccap_v1.py` + `ccap_runtime_v1.py`) to understand how code patches are verified.
6. **Read the Genesis Engine SH-1** (`ge_symbiotic_optimizer_v0_3.py`) to understand how patches are generated.
7. **Examine the authority system** (`authority_pins_v1.json`, `ccap_patch_allowlists_v1.json`) to understand the immutable constraints.
8. **Study meta-core** (`meta-core/engine/activation.py`) to understand the constitutional guarantee.
9. **For federation**: read the v19.0 promoter, then treaties, then continuity, then SIP.

Each module is self-contained enough to be understood independently, but the system's full behavior emerges from their composition. This document has attempted to make that composition explicit — showing not just what each component does, but how they interact, why they were designed this way, and what properties emerge from their combination.

*The AGI-Stack is a system that can safely improve itself. This document explains how.*

---

# Appendix I: Detailed Data Flow Examples

This appendix traces specific data flows through the system to demonstrate how the abstract architecture manifests in concrete operation.

## I.1 A Successful Self-Improvement Tick

Let us trace tick 42 of a running ignite loop, where the system successfully generates, verifies, and commits a code patch.

**Pre-conditions**: Tick 41 completed with a runaway level of 5 (the system has been stagnating for several ticks). The previous state hash is `sha256:aaa...`. The Genesis Engine SH-1 has produced 12 patches in the last 10 ticks, with 3 accepted and 9 rejected.

**Step 1: Ignite Loop Entry**
```bash
python3 -m orchestrator.rsi_omega_daemon_v19_0 \
  --campaign_pack campaigns/rsi_omega_daemon_v19_0_super_unified/rsi_omega_daemon_pack_v1.json \
  --out_dir runs/ignite_v19_super_unified_tick_42 \
  --mode once --tick_u64 42 --prev_state_dir runs/ignite_v19_super_unified_tick_41/state
```

**Step 2: Observation**
The observer reads metric sources:
- Metasearch: accuracy_q32 = 3865470566 (~0.90), latency_u64 = 1200
- Polymath: portfolio_score_q32 = 2576980378 (~0.60), void_score_q32 = 1717986918 (~0.40), conquered_domains_u64 = 4
- Genesis Engine: PD for `tools/genesis_engine/ge_config_v1.json` = 858993459 (~0.20), XS = 3435973837 (~0.80)
- Capability frontier: frontier_q32 = 3435973837 (~0.80), current_q32 = 3221225472 (~0.75), delta = -214748365 (declining)

The observation report is canonicalized: `obs_hash = sha256:bbb...`

**Step 3: Diagnosis**
The diagnoser identifies:
- CRITICAL: Capability regression (current below frontier by 5%).
- WARNING: Stall detected (3 consecutive ticks with declining capability).
- INFO: Polymath void score suggests unexplored domains.

Issues report written with severity assignments.

**Step 4: Decision**
The decider evaluates:
- Runaway level check: still at level 5 (from tick 41, stagnation continues).
- Policy rule match: "capability regression + runaway level 5" → action template: `DISPATCH_GE_SYMBIOTIC`.
- Goal selection: `OBJ_EXPAND_CAPABILITIES` (forced by runaway level 5).
- Campaign routing: `rsi_ge_symbiotic_optimizer_sh1_v0_1`.
- Temperature: HOT (declining frontier → maximum exploration).

Decision plan canonicalized: `dec_hash = sha256:ccc...`

**Step 5: Execution**
The executor materializes a workspace from the repository, pruning runs/, .omega_cache/, and large binary files. It invokes SH-1:

SH-1 reads 41 historical receipts:
- `tools/genesis_engine/ge_config_v1.json`: PD = 0.20 (3/15). XS = 0.80. Bucket: EXPLORATORY.
- `campaigns/rsi_polymath_scout_v1/rsi_polymath_scout_pack_v1.json`: PD = 0.80 (12/15). XS = 0.20. Bucket: HOTFIX.
- `orchestrator/omega_v18_0/coordinator.py`: PD = 0.50 (5/10). XS = 0.50. Bucket: INCREMENTAL.

SH-1 generates 3 patches:
1. COMMENT_APPEND on `campaigns/rsi_polymath_scout_v1/rsi_polymath_scout_pack_v1.json` (HOTFIX: safe, likely accepted)
2. JSON_TWEAK_COOLDOWN on `orchestrator/omega_v18_0/coordinator.py` (INCREMENTAL: moderate risk)
3. JSON_TWEAK_BUDGET_HINT on `tools/genesis_engine/ge_config_v1.json` (EXPLORATORY: high risk, but high potential)

Hard-avoid check: Patch 3's behavior signature is compared against 9 rejected signatures. No match above the 90% similarity threshold. All 3 patches survive.

SH-1 emits 3 CCAP bundles with unique `ccap_id` values.

**Step 6: Promotion**
The promoter selects the first CCAP bundle (deterministic ordering by ccap_id hash). It invokes `verify_ccap_v1.py`:

- **REALIZE**: Apply the patch to a clean workspace. The patch targets `campaigns/rsi_polymath_scout_v1/rsi_polymath_scout_pack_v1.json`. CCAP allowlist check: the path starts with `campaigns/` (allowed) and doesn't match any forbid rule. PASS.
- **SCORE**: Run the evaluation kernel. The patched workspace is benchmarked against `omega_benchmark_suite_v1.py`. Results: accuracy_q32 = 3908374036 (~0.91). PASS (above 90% gate).
- **FINAL_AUDIT**: Check promotion gates. The gate requires `accuracy_q32 >= 3865470566`. 3908374036 >= 3865470566 → PASS.

CCAP receipt emitted: `ccap_receipt_hash = sha256:ddd...`

v19.0 gates:
- Continuity gate: Overlap artifacts unchanged by this patch → PASS.
- J dominance gate: J_new = J_old + small improvement from accuracy gain → J_new > J_old → PASS.
- Treaty gate: No active treaties → PASS (vacuously).

Axis bundle assembled. meta-core verification:
- `stage_bundle()`: All file hashes match manifest. Merkle root computed. PASS.
- `verify_staged()`: Constitutional constraints satisfied. Parent chain valid. PASS.
- `canary_staged()`: Dry-run application succeeds. No path conflicts. PASS.

Promotion receipt: `status = PROMOTED`, `reason_code = ACCEPTED`.

**Step 7: Activation**
- `commit_staged()`: Previous pointer written (sha256:aaa...). Active pointer atomically swapped to the new bundle. Ledger entry appended.
- System state now reflects the campaign pack modification.

**Step 8: State Update**
New state written:
```json
{
  "schema_version": "omega_state_v1",
  "tick_u64": 42,
  "parent_state_hash": "sha256:aaa...",
  "observation_hash": "sha256:bbb...",
  "decision_hash": "sha256:ccc...",
  "active_manifest_hash": "sha256:eee...",
  ...
}
```

**Step 9: Signal Emission**
The ignite loop's embedded Python emits:
```
SIGNAL=RUNAWAY_ACTIVE level=5 reason=TESTING tick=42
SIGNAL=CAPABILITY_PRIORITY tick=42
SIGNAL=REWRITE_ATTEMPT files=campaigns/rsi_polymath_scout_v1/rsi_polymath_scout_pack_v1.json tick=42
SIGNAL=CCAP_DECISION action=ACCEPT ccap_id=sha256:ddd... tick=42
SIGNAL=REWRITE_COMMIT files=campaigns/rsi_polymath_scout_v1/rsi_polymath_scout_pack_v1.json tick=42
SIGNAL=ACTIVATION_COMMIT ledger_hash=sha256:fff... tick=42
SIGNAL=TIER_STATUS tier1=pass tier2=pass tier3=pass tick=42
SIGNAL=HEARTBEAT tick=42 decision_plan_hash=sha256:ccc... tick_snapshot_hash=sha256:ggg...
```

All three tiers passed: the system wanted to improve (tier 1), generated a patch (tier 2), and the patch was accepted and activated (tier 3). The system has successfully improved itself.

## I.2 A Failed Self-Improvement Tick

Now trace tick 43, where the system attempts another improvement but is rejected:

**Step 1-5**: Similar to tick 42. SH-1 generates a JSON_TWEAK_BUDGET_HINT patch targeting `tools/genesis_engine/ge_config_v1.json`.

**Step 6: Promotion FAILURE**
- **REALIZE**: Patch applied. Path check: `tools/genesis_engine/ge_config_v1.json` starts with `tools/genesis_engine/` (allowed). PASS.
- **SCORE**: Evaluation kernel run. Results: accuracy_q32 = 3650722201 (~0.85). FAIL — below 90% gate.

CCAP refutation certificate emitted:
```json
{
  "schema_version": "ccap_refutation_cert_v1",
  "reason_code": "CCAP_SCORE_BELOW_GATE",
  "metric_id": "accuracy_q32",
  "actual_value_q32": 3650722201,
  "required_value_q32": 3865470566,
  "affected_path": "tools/genesis_engine/ge_config_v1.json"
}
```

Promotion receipt: `status = REJECTED`, `reason_code = CCAP_SCORE_BELOW_GATE`.

**Step 7: No Activation**
Since the promotion was rejected, no activation occurs. The system state remains at tick 42's committed state.

**Step 8: Signal Emission**
```
SIGNAL=RUNAWAY_ACTIVE level=5 reason=TESTING tick=43
SIGNAL=CAPABILITY_PRIORITY tick=43
SIGNAL=REWRITE_ATTEMPT files=tools/genesis_engine/ge_config_v1.json tick=43
SIGNAL=CCAP_DECISION action=REJECT reason=CCAP_SCORE_BELOW_GATE tick=43
SIGNAL=TIER_STATUS tier1=pass tier2=pass tier3=fail tick=43
SIGNAL=HEARTBEAT tick=43 ...
```

Tier 3 failed: the self-improvement attempt was rejected. The refutation certificate will inform SH-1 in the next tick that budget hint tweaks to `ge_config_v1.json` with this magnitude of change are counterproductive. SH-1's PD for this file drops from 0.20 to 0.19. Its behavior signature is added to the hard-avoid list — if SH-1 generates a similar patch in the future, it will be filtered before submission.

## I.3 A Polymath Domain Discovery Flow

Trace a Polymath scouting run:

1. The observer reads Polymath metrics and notices that `scout_age_ticks_u64 = 15` (15 ticks since last scout). Scout age creates urgency.

2. The decider selects `rsi_polymath_scout_v1` as the next campaign (scout age threshold exceeded, Polymath goal inserted into queue).

3. The scout script (`tools/polymath/polymath_scout_v1.py`) reads the current domain registry and domain policy. It identifies 5 candidate domains not yet in the registry. For each candidate, it computes a void score based on trend analysis and coverage gaps.

4. The void report is written: the top candidate, "Bacterial Quorum Sensing," has `void_score_q32 = 3865470566` (~0.90 — highly underexplored).

5. The promotion pipeline verifies the void report against the `verify_rsi_polymath_scout_v1` verifier: schema compliance, score computation correctness, policy compliance (no denylist matches), and deterministic replay.

6. The scout status is updated, and the registry is modified to note the new domain candidate.

7. In the next observation, the observer reads the updated Polymath metrics. The decider notices the high void score and queues a `rsi_polymath_bootstrap_domain_v1` campaign for "Bacterial Quorum Sensing."

8. The bootstrap campaign creates `domains/bacterial_quorum_sensing/` with L0-L2 packs, a solver, and a corpus. All fetched data goes through content-addressed storage with sealed receipts.

9. Eventually, `rsi_polymath_conquer_domain_v1` runs, verifies the system's mastery of the domain, and updates the registry to `conquered_b: true`.

10. The portfolio score increases, the void score for this domain drops to near-zero, and the system's attention shifts to the next highest-void candidate.

This entire flow — from noticing a gap in knowledge to discovering, bootstrapping, and conquering a scientific domain — happens autonomously through the tick pipeline. No human intervention is required at any step.

---

# Appendix J: Invariants and Assertions

The following invariants are enforced throughout the system. Any violation constitutes a system failure:

## Structural Invariants
1. Every artifact has a `schema_version` field matching a known schema.
2. Every content-addressed artifact's SHA-256 hash matches its declared identifier.
3. Every state object's `parent_state_hash` matches the hash of the previous state.
4. Every tick's artifacts are contained within a single directory.
5. No tick's artifacts reference artifacts from future ticks.

## Temporal Invariants
6. `tick_u64` is monotonically increasing (never decreases or repeats).
7. The capability frontier is correctly computed from the previous N ticks' observations.
8. Runaway escalation levels increase monotonically during a stall period.
9. PD values are bounded to [0, 1] in Q32 representation [0, 2^32].
10. Budget consumption never exceeds the declared budget.

## Security Invariants
11. No CCAP-verified patch modifies a path matching any forbid rule.
12. Every CCAP bundle references a pinned evaluation kernel.
13. Every committed bundle has a valid meta-core verification receipt.
14. The authority pins file is never modified by automated processes.
15. The CCAP allowlist file is never modified by automated processes.

## Determinism Invariants
16. Given identical inputs, all computation produces bitwise-identical outputs.
17. No computation uses randomness (no `random`, no `uuid4()`, no system clock for logic).
18. All numerical computation uses Q32 or Q16 fixed-point arithmetic.
19. All serialization uses GCJ-1 canonical JSON.
20. All hash computation uses SHA-256.

## Federation Invariants (v19.0)
21. Overlap artifacts are translatable in both directions via declared morphisms.
22. J_new >= J_old for every promoted state transition.
23. World snapshot Merkle roots are correctly computed from all entries.
24. SIP ingested artifacts pass leakage scanning (entropy and pattern checks).
25. Treaty totality certificates cover all overlap artifacts.

These 25 invariants collectively define "correct" operation. A system satisfying all 25 invariants is operating within its design envelope. A violation of any single invariant triggers fail-closed rejection and halts the current tick.

---

# Appendix K: The Meta-Architecture — Patterns and Anti-Patterns

This appendix documents the architectural patterns used throughout the AGI-Stack and the anti-patterns that the design deliberately avoids.

## K.1 Patterns Employed

### The Pipeline Pattern
Every major operation in the AGI-Stack follows a pipeline architecture: data flows linearly through a sequence of stages, each stage consuming the output of the previous one. This pattern appears at multiple scales:

- **Tick pipeline**: OBSERVE → DIAGNOSE → DECIDE → DISPATCH → EXECUTE → PROMOTE → ACTIVATE × VERIFY
- **CCAP pipeline**: REALIZE → SCORE → FINAL_AUDIT
- **Polymath pipeline**: SCOUT → BOOTSTRAP → CONQUER
- **SH-1 pipeline**: COLLECT_RECEIPTS → COMPUTE_PD_XS → PLAN_BUCKETS → GENERATE_PATCHES → FILTER_AVOID → EMIT_CCAP
- **meta-core pipeline**: STAGE → VERIFY → CANARY → COMMIT
- **SIP pipeline**: VALIDATE_MANIFEST → COMPUTE_MERKLE → SCAN_LEAKAGE → VERIFY_BINDINGS → SEAL

The pipeline pattern enforces several properties automatically:
- **Composability**: Each stage can be tested independently with mocked inputs.
- **Auditability**: The output of each stage is a persistent, hashable artifact.
- **Determinism**: Stages are pure functions (input → output, no side effects).
- **Fail-closed**: Any stage failure terminates the pipeline.

### The Registry Pattern
Components discover each other through registries rather than hardcoded references. Key registries in the system:
- **Campaign registry**: Maps campaign IDs to campaign packs.
- **Verifier registry**: Maps campaign IDs to verifier modules.
- **Subverifier registry**: Maps campaign types to specialized verifiers within the promoter.
- **Metric reader registry**: Maps metric source IDs to reader functions in the observer.
- **Goal-to-campaign mapping**: Maps goal types to campaign selection rules in the decider.
- **Domain policy registry**: Maps domain keywords to eligibility decisions in Polymath.
- **Template registry**: Maps bucket types to patch generation templates in SH-1.
- **Void topic router**: Maps topic IDs to campaign routes in Polymath.

These registries provide extensibility — new capabilities can be added by registering new entries without modifying existing code. They also provide auditability — the registry itself is a declarative record of the system's capabilities.

### The Receipt Pattern
Every operation produces a receipt — a canonical JSON document certifying the operation's outcome. Receipts serve dual purposes:
- **Audit trail**: Receipts form a permanent record of what happened and why.
- **Learning signal**: Receipts are consumed by SH-1 to learn from successes and failures, and by the promoter to make gating decisions.

Receipt types in the system:
- CCAP receipt / refutation certificate
- Promotion receipt
- meta-core verification receipt
- Polymath fetch receipt
- SIP sealed receipt
- Commit/rollback ledger entry

### The Content-Address Pattern
Every persistent artifact is identified by its SHA-256 hash. This eliminates naming conflicts, provides integrity verification, and enables deduplication. The pattern is applied universally — from individual metric readings to complete system state snapshots.

### The Budget-Bounded Computation Pattern
Every computation receives an explicit budget and is terminated if the budget is exceeded. This provides denial-of-service protection and enables performance analysis. The budget system encourages implementations to be efficient (high budget consumption suggests optimization opportunities) without requiring complex static analysis.

## K.2 Anti-Patterns Avoided

### Mutable Global State
There is no mutable global state in the AGI-Stack. All state is either passed explicitly through function parameters or stored in content-addressed artifacts. This eliminates a class of bugs related to state corruption and makes all functions effectively pure (given the same inputs, they produce the same outputs).

### Implicit Ordering
The system never relies on implicit execution ordering. Directory listing order, dictionary iteration order, and file modification timestamps are never used for logic. All ordering is explicit — either through sorted keys, explicit sequence numbers (tick_u64), or hash-based ordering.

### Error Recovery Within Ticks
The system does not attempt error recovery within a single tick. Any error terminates the current tick's pipeline. Recovery happens at the tick level (the ignite loop retries failed ticks) or at the human intervention level (developers fix bugs). This simplifies reasoning about error behavior — there are no partially-recovered states to consider.

### Dynamic Code Loading (Except Verifier Registry)
The only dynamic code loading in the system is the verifier registry's module import. All other code paths are statically determined. This prevents a class of attacks where malicious artifacts cause arbitrary code execution through dynamic dispatch.

### Non-Deterministic Scheduling
There is no concurrency, no threading, no async/await, and no event-driven processing. All operations execute sequentially in a single thread. This eliminates all race conditions, deadlocks, and non-deterministic scheduling-dependent behavior.

### Self-Referential Trust
No component validates itself. The observer doesn't verify its own observations — the verifier does. The promoter doesn't validate its own receipts — meta-core does. The Genesis Engine doesn't evaluate its own patches — the CCAP verifier does. Every validation is performed by a component at a higher trust level than the component being validated.

---

# Appendix L: Numerical Examples

## L.1 Q32 Conversion Examples

| Human-Readable | Q32 Integer | Computation |
|----------------|-------------|-------------|
| 0.0 | 0 | 0 × 2^32 |
| 0.10 | 429496730 | 0.10 × 4294967296 |
| 0.20 | 858993459 | 0.20 × 4294967296 |
| 0.25 | 1073741824 | 0.25 × 4294967296 |
| 0.40 | 1717986918 | 0.40 × 4294967296 |
| 0.50 | 2147483648 | 0.50 × 4294967296 |
| 0.60 | 2576980378 | 0.60 × 4294967296 |
| 0.75 | 3221225472 | 0.75 × 4294967296 |
| 0.80 | 3435973837 | 0.80 × 4294967296 |
| 0.85 | 3650722201 | 0.85 × 4294967296 |
| 0.90 | 3865470566 | 0.90 × 4294967296 |
| 0.95 | 4080218931 | 0.95 × 4294967296 |
| 1.0 | 4294967296 | 1.0 × 2^32 |

## L.2 Hash Chain Example

```
genesis_state (tick 0):
  parent_state_hash: null
  state_hash: sha256:genesis_hash_000

tick 1 state:
  parent_state_hash: sha256:genesis_hash_000
  observation_hash: sha256:obs_001
  decision_hash: sha256:dec_001
  state_hash: sha256(canon({parent: genesis_hash_000, obs: obs_001, dec: dec_001, ...}))
            = sha256:state_hash_001

tick 2 state:
  parent_state_hash: sha256:state_hash_001
  observation_hash: sha256:obs_002
  decision_hash: sha256:dec_002
  state_hash: sha256(canon({parent: state_hash_001, obs: obs_002, dec: dec_002, ...}))
            = sha256:state_hash_002
```

Each state includes all hash inputs needed to re-derive the state hash from the raw data. Verification walks backward through the chain, re-computing each state hash from its recorded inputs, and confirms that parent pointers link correctly.

## L.3 CCAP Allowlist Evaluation Examples

| Path | allow_match? | forbid_match? | Result |
|------|-------------|---------------|--------|
| `orchestrator/omega_v18_0/coord.py` | ✓ (orchestrator/) | ✗ | **ALLOWED** |
| `tools/genesis_engine/ge_config_v1.json` | ✓ (tools/genesis_engine/) | ✗ | **ALLOWED** |
| `campaigns/rsi_scout/pack.json` | ✓ (campaigns/) | ✗ | **ALLOWED** |
| `polymath/registry/registry.json` | ✓ (polymath/registry/) | ✗ | **ALLOWED** |
| `tools/omega/omega_benchmark_suite_v1.py` | ✓ (tools/omega/)* | ✓ (exact_forbid) | **FORBIDDEN** |
| `authority/authority_pins_v1.json` | ✗ | ✓ (authority/) | **FORBIDDEN** |
| `CDEL-v2/cdel/v18_0/verify_ccap_v1.py` | ✗ | ✓ (CDEL-v2/) | **FORBIDDEN** |
| `meta-core/engine/activation.py` | ✗ | ✓ (meta-core/) | **FORBIDDEN** |
| `Genesis/schema/omega_state_v1.json` | ✗ | ✓ (Genesis/) | **FORBIDDEN** |
| `.git/config` | ✗ | ✓ (.git/) | **FORBIDDEN** |
| `runs/tick_42/state.json` | ✗ | ✓ (runs/) | **FORBIDDEN** |
| `README.md` | ✗ | ✗ | **FORBIDDEN** (no allow match) |

*Note: `tools/omega/` as a prefix is in `allow_prefixes` (via `tools/`), but the benchmark suite is explicitly forbidden. Forbid rules always take precedence over allow rules.

---

*End of Source of Truth: Appendices complete.*

---

# Appendix M: The System's Mental Model — A Unified View

This final appendix synthesizes all preceding sections into a single, unified mental model of the AGI-Stack. This is the view that an external intelligence would need to reconstruct the project's thinking.

## M.1 The Core Insight

The AGI-Stack is built on a single core insight: **self-improvement is only safe when the improvement mechanism cannot modify the criteria by which improvements are evaluated**. This insight manifests as the RE1-RE4 trust hierarchy, the CCAP allowlist, the pinned evaluation kernels, and the fail-closed verification pipeline.

Every design decision in the system flows from this insight:
- Why deterministic? Because non-deterministic improvements can't be verified.
- Why tick-based? Because each improvement must be individually verifiable.
- Why content-addressed? Because modified artifacts must be detectable.
- Why fail-closed? Because false acceptances are more dangerous than false rejections.
- Why Q32? Because floating-point non-determinism would break verification.
- Why budget-bounded? Because unbounded verification creates denial-of-service vectors.
- Why hash-chained? Because history tampering must be detectable.

## M.2 The Three Loops

The system operates through three nested loops:

### Loop 1: The Tick Loop (seconds to minutes)
The innermost loop, driven by `ignite_runaway.sh`. Each iteration:
- Observe → Decide → Execute → Promote → Activate
- Produces one tick's worth of artifacts
- May or may not improve the system

This loop is the system's heartbeat. It runs continuously, processing one work unit at a time.

### Loop 2: The Learning Loop (ticks to tens of ticks)
SH-1's receipt-driven meta-learning. Over multiple ticks:
- Accumulates success/failure data (PD/XS)
- Adjusts patch generation strategy
- Filters previously rejected approaches (hard-avoid)
- Converges toward effective improvement strategies

This loop is the system's learning. It doesn't change the system's code directly — it changes the strategy by which code changes are proposed.

### Loop 3: The Evolution Loop (tens to hundreds of ticks)
The system's capability trajectory. Over many ticks:
- Polymath discovers and conquers new domains
- Runaway mode breaks through performance plateaus
- Successfully committed patches accumulate
- The system's observation scores reflect growing capability
- New goals enter the queue based on expanded capability

This loop is the system's growth. It represents genuine capability expansion — the system can do things it couldn't do before.

## M.3 The Information Architecture

Information flows through four channels:

1. **Artifact channel**: Content-addressed JSON documents, flowing forward through the pipeline. Each artifact is immutable and hashable. This is the system's primary data path.

2. **Hash chain channel**: SHA-256 hashes linking artifacts to their predecessors and their inputs. This is the system's integrity backbone.

3. **Signal channel**: Structured log entries emitted by the ignite loop. Signals provide a real-time, machine-readable summary of system behavior. This is the system's monitoring interface.

4. **Receipt channel**: Verification outcomes (accept/reject with reason codes). Receipts flow from verifiers back to proposers, creating the feedback loop that drives learning. This is the system's learning signal.

These four channels are sufficient to describe the system's complete behavior at any point in time. An external observer with access to all four channels can reconstruct the system's full history, understand every decision, and predict future behavior (given knowledge of future inputs).

## M.4 The Invariant Set as Constitution

The 25 invariants in Appendix J form the system's constitution. They define the boundaries within which the system is free to operate. Unlike a software specification (which describes desired behavior), the invariants describe required behavior — violations are not bugs to be fixed but fundamental system failures.

The constitution is hierarchical:
- **Structural invariants** (1-5): Define what the system IS.
- **Temporal invariants** (6-10): Define how the system CHANGES.
- **Security invariants** (11-15): Define what the system CANNOT DO.
- **Determinism invariants** (16-20): Define HOW the system computes.
- **Federation invariants** (21-25): Define how systems INTERACT.

This hierarchy mirrors the RE1-RE4 trust layers: structural and security invariants are enforced by RE1 (meta-core), temporal invariants by RE2 (CDEL-v2), determinism invariants by RE2's canonical computation, and federation invariants by RE2's v19.0 modules.

## M.5 What Success Looks Like

The AGI-Stack succeeds when:
1. The ignite loop runs continuously without human intervention.
2. Tier 3 signals appear regularly (patches are being committed).
3. Observation scores trend upward across ticks.
4. Polymath portfolio expands with new conquered domains.
5. PD trends upward for targeted files (patches are getting better).
6. No invariant violations occur.
7. All verification passes on replay.

The system fails when:
1. Runaway mode persists at level 5 indefinitely (no successful patches).
2. All PD values trend toward zero (all patches are rejected).
3. Budget exhaustion becomes systematic (computation is too expensive).
4. Invariant violations occur (fundamental system corruption).

Between success and failure is the normal operating range: some patches succeed, some fail, the system learns from both, and capability slowly improves. The system is designed to operate in this range indefinitely, with the improvement rate determined by the quality of its patch generation (SH-1) and the strictness of its evaluation criteria (evaluation kernels).

## M.6 The Ultimate Question

The AGI-Stack answers a fundamental question in AI safety: **Can a system improve itself safely?**

The answer, as embodied by this codebase, is: **Yes, if the improvement criteria are outside the system's modification boundary.**

This is not a theoretical claim — it is an architectural fact. The evaluation kernels are pinned. The benchmark suite is protected. The verification infrastructure is immutable. The allowlists are self-reinforcing. The hash chains are tamper-evident. The deterministic computation is replay-verifiable. The fail-closed error model prevents silent corruption.

Within these constraints, the system is free to improve anything it can access. It can generate code patches, optimize configurations, discover scientific domains, synthesize architectural proposals, and expand its own capabilities — all while maintaining provable compliance with its constitutional invariants.

This is what "AGI-Stack-Unchained" means: **maximum freedom within constitutional bounds**. The system is unchained in its ability to grow, learn, and improve. It is constitutionally bound in its inability to compromise its own verification, evaluation, or safety infrastructure.

*The Source of Truth is complete.*

---

*Document: AGI-Stack-Unchained Source of Truth*
*Total sections: 6 Layers + Deep Dive + Detailed Module Analysis + Design Rationale + 12 Appendices*
*Generated from analysis of 25,000+ lines of core source code across 10+ major components*
