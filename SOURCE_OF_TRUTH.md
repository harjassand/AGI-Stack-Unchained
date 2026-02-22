# AGI-Stack-Unchained: The Source of Truth

## A Complete Reconstruction Manual for the System's Mental Model

**Version**: v19.0 (Super-Unified) | **Generated**: 2026-02-22 | **Scope**: Full Codebase  
**Word Count Target**: 35,000+ words  
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
7. [Layer 7: Post-v18.0 Evolution — Phase 3 Through Phase 4A](#layer-7-post-v180-evolution--phase-3-through-phase-4a-february-1720-2026)
   - 7.1 [Phase 3: CCAP Self-Mutation](#71-phase-3-ccap-self-mutation--the-system-rewrites-its-own-coordinator)
   - 7.2 [The Deterministic Bid Market](#72-the-deterministic-bid-market-predation-market)
   - 7.3 [The Native Module Pipeline](#73-the-native-module-pipeline--rust-ffi-via-deterministic-abi)
   - 7.4 [Phase 0: Adversarial CCAP Testing](#74-phase-0-adversarial-ccap-testing)
   - 7.5 [The Enhanced Ignite Runaway Loop](#75-the-enhanced-ignite-runaway-loop)
   - 7.6 [Phase 4A: SIP Ingestion](#76-phase-4a-sip-ingestion--sealed-data-pipelines)
   - 7.7 [Coordinator v18/v19 Enhancements](#77-coordinator-v180--v190-enhancements)
   - 7.8 [Verifier Expansion](#78-verifier-expansion)
   - 7.9 [Test Coverage Additions](#79-test-coverage-additions)
   - 7.10 [Summary](#710-summary-what-changed-and-why-it-matters)

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


---

# Layer 7: Post-v18.0 Evolution — Phase 3 Through Phase 4A (February 17–20 2026)

This section documents the most recent evolutionary burst — the three-day sprint from February 17 through February 20, 2026. During this period, the system underwent its most significant single expansion since the v18.0 unification, adding 14,544 lines of new code across 77 files. The changes fall into six major subsystems: (1) Phase 3 CCAP Self-Mutation, (2) the Deterministic Bid Market, (3) the Native Module Pipeline, (4) Phase 0 Adversarial CCAP Testing, (5) the enhanced Ignite Runaway Loop, and (6) Phase 4A SIP Ingestion. Each subsystem is described below with direct code-level evidence.

## 7.1 Phase 3: CCAP Self-Mutation — The System Rewrites Its Own Coordinator

**Primary Module**: `orchestrator/rsi_coordinator_mutator_v1.py` (1,861 lines, 78,251 bytes)  
**Supporting Modules**: `orchestrator/omega_v18_0/coordinator_v1.py`, `agi-orchestrator/orchestrator/llm_backend.py`  
**Commits**: `Phase 3: *` series (30+ commits from Feb 17–18)

Phase 3 represents a landmark capability: **the Omega daemon can now propose, benchmark, and land mutations to its own coordinator code**. This is the first time the system's self-improvement loop targets the orchestration layer itself — the code that decides *what* to improve.

### 7.1.1 Architecture of Self-Mutation

The Phase 3 campaign (`rsi_coordinator_mutator_v1.py`) implements a five-stage pipeline:

1. **LLM Prompt Generation** (`_llm_diff_prompt()`, lines 199–236): The mutator constructs a prompt containing the full text of the target file (`orchestrator/omega_v19_0/coordinator_v1.py`, locked via `_LOCKED_TARGET_RELPATH`), the campaign pack configuration, the current tick index, and a deterministic run seed. The prompt requests a unified diff that improves the coordinator's behavior according to Definition of Done (DoD) criteria specified in the pack.

2. **LLM Response Extraction** (`_extract_patch_from_llm()`, lines 333–430; `_maybe_parse_llm_json_dict()`, lines 433–504): The system handles multiple LLM response formats — raw unified diffs, JSON-wrapped diffs (`unified_diff` field), full updated file text (`updated_file_text` field), and malformed JSON with markdown wrappers. The extractor strips code fences, tolerates non-JSON wrappers (`_maybe_parse_llm_json_dict`), and computes local diffs from `updated_file_text` when the LLM fails to produce a proper diff (`_diff_from_updated_text()`, lines 507–517). Missing diff headers are synthesized (`_ensure_patch_headers()`, lines 519–567).

3. **Patch Repair** (`_repair_patch_prefix_that_applies()`, lines 67–122): LLM-generated patches are often truncated or malformed. The repair function progressively trims trailing hunks until _git apply --check_ succeeds. It tries strict mode first, then tolerant mode (with whitespace relaxation and context-line recount). A dedicated module `patch_diff_v1.py` (29 lines) provides `build_unified_patch_bytes()` for generating deterministic diffs from before/after text.

4. **Triviality Gate** (`_patch_nontrivial_reason()`, lines 605–634): Not all syntactically valid patches are worth benchmarking. The triviality gate uses Python's `ast` module to compare the AST structure before and after the patch, with an option to strip literal values (`_StripLiteralValues` visitor, lines 576–591). Patches that only change string constants or comments — without altering control flow — are rejected as trivial. The `_ast_signature()` function (lines 594–602) computes a canonical hash of the AST's dump representation for comparison.

5. **Micro-Benchmarking** (`_micro_bench_gate()`, lines 778–825; `_run_daemon_loop_measured()`, lines 877–982): Accepted patches are benchmarked using a paired median-of-5 trial design. Two worktrees — baseline and candidate — run identical daemon loops. The measured run (`_run_daemon_loop_measured`) monitors RSS memory via `/proc/$pid/statm` (or `ps` fallback), file descriptor count via `/proc/$pid/fd` (or `lsof` fallback), and wall-clock time. Memory sampling occurs at configurable intervals (`sample_period_s`, default 0.25 seconds). A positive score delta (candidate improves over baseline) is required for promotion.

6. **Deterministic Template Mode** (`_template_patch_for_target()`, lines 239–330): When no LLM is available or for deterministic testing, the mutator can generate a template patch that modifies a deterministic tick constant in the coordinator. This was added via commits `coordinator template: patch deterministic tick constant for positive score delta` and `coordinator template: add missing regex import for deterministic patch mode`. The template mode uses regex matching (`re.compile`) to locate and increment the constant, ensuring verifiable score improvement.

### 7.1.2 LLM Backend Evolution

**Module**: `agi-orchestrator/orchestrator/llm_backend.py` (687 lines, 26,021 bytes)

The LLM backend was significantly enhanced for Phase 3:

- **Multi-Provider Architecture**: The backend now supports four provider strategies through distinct classes:
  - `MockBackend`: Static response replay for deterministic testing.
  - `ProviderReplayBackend`: Deterministic replay from JSONL logs keyed by `(provider, model, prompt_hash)`.
  - `ProviderHarvestBackend`: Live HTTP requests to OpenAI, Anthropic, or Gemini APIs with automatic JSONL recording for future replay. 429/rate-limit errors trigger exponential backoff with receipts (commit: `Phase 3: handle live LLM failures (429 backoff) with receipts`).
  - **MLX Local Backend**: On-device inference via Apple MLX with model/tokenizer caching (`_load_mlx_model_and_tokenizer()`, lines 278–299), chat template formatting (`_format_mlx_prompt()`, lines 302–315), and configurable sampler (`_build_mlx_sampler()`, lines 318–335). The MLX mutator system prompt is hardcoded: `"You are a deterministic code mutator. Output a single JSON object only. No markdown."` This enables entirely offline self-mutation on Apple Silicon.
  
- **Gemini Removal**: The native Gemini SDK integration was removed (commit: `test_llm_backend_gemini_removed.py`, 11 lines). Gemini access now routes through the harvest backend's HTTP POST interface, reading the API key from a local secret file (commit: `Phase 3: gemini harvest reads key from file`). The function `_gemini_removed()` (line 87) explicitly raises an error if called.

- **Deterministic Seeding**: All LLM calls use `_derive_call_seed_u64()` (lines 228–236) to compute a deterministic seed from a base seed and call index, enabling replay-verifiable LLM interactions.

### 7.1.3 Strict DoD Mutations and Runtime Integration

**Commit**: `feat: land phase3 strict DoD updates and runtime integrations` (HEAD on main)  
**Commit**: `phase3 strict dod mutations and mutator gates` 

The Phase 3 landing commit introduced strict Definition of Done (DoD) enforcement:

- **Verify Failure Receipts** (`_write_verify_failure()`, lines 569–573): When a patch fails any gate (triviality, benchmark, determinism), the mutator writes an explicit failure receipt with reason codes (`TRIVIAL_PATCH`, `BENCHMARK_REGRESSION`, `AST_UNCHANGED`, `APPLY_FAIL`). This closes the previous gap where `VERIFY_ERROR` was used as an opaque catch-all (commit: `Phase 3: write explicit verify failure receipts (no opaque VERIFY_ERROR)`).

- **Divergence Artifact Chain Verification** (`_verify_divergence_artifact_chain()`, lines 704–775): After a benchmark run, the verifier checks that the candidate's state directory contains a complete, hash-consistent artifact chain — observation, decision, dispatch, promotion receipts — with no missing links. This prevents false-positive benchmark results from incomplete runs.

- **v19 Replay Verdict** (`_run_v19_replay_verdict()`, lines 659–688): The mutator runs the v19 daemon verifier against each benchmark output to confirm that the mutated coordinator still produces replay-verifiable ticks. A mutation that breaks replay determinism is rejected even if it improves benchmark scores.

## 7.2 The Deterministic Bid Market (Predation Market)

**Module**: `CDEL-v2/cdel/v18_0/omega_bid_market_v1.py` (817 lines, 31,696 bytes)  
**Test Campaign**: `CDEL-v2/cdel/v18_0/campaign_bid_market_toy_v1.py` (64 lines)  
**Test Verifier**: `CDEL-v2/cdel/v18_0/verify_bid_market_toy_v1.py` (28 lines)  
**Unit Tests**: `CDEL-v2/cdel/v18_0/tests_omega_daemon/test_bid_market_math_and_tiebreak_v1.py` (166 lines)

The Bid Market replaces static campaign routing with an economics-inspired resource-allocation mechanism where campaigns compete for tick execution rights.

### 7.2.1 Q32 Fixed-Point Economics

All market computations use Q32 fixed-point arithmetic (cf. Section 3.7). Key computed values:

- **ROI** (`roi_q32`): Expected return-on-investment, configurable per campaign with defaults and per-campaign overrides via `resolve_bidder_params()` (lines 68–95). Clamped to `[min_q32, max_q32]` bounds from config.
- **Confidence** (`confidence_q32`): Campaign's self-assessed confidence in its ROI estimate.
- **Predicted Cost** (`predicted_cost_q32`): Estimated compute budget.
- **Bankroll** (`bankroll_q32`): Available budget per campaign, initialized from config, adjusted at settlement.
- **Credibility** (`credibility_q32`): Reputation score that increases with successful ticks and decreases with failures; clamped to `[0, Q32_ONE]`.

### 7.2.2 Settlement Mechanics

The `settle_and_advance_market_state()` function (lines 279–440) implements a full settling cycle:

1. **J-Function Computation**: `J_q32_from_observation()` (lines 203–213) computes the objective function J from the observation report by extracting objective metric IDs (`_objective_metric_ids()`, lines 188–200) and reading their Q32 values. `J_prev_q32_from_metric_series()` (lines 216–231) computes the previous J for delta calculation.

2. **Bankroll Adjustment**: Winners receive a bankroll credit proportional to J-delta (positive improvement → credit). Losers (negative J-delta on their watch) receive a bankroll debit. This creates an evolutionary pressure: successful campaigns accumulate resources, unsuccessful ones go bankrupt.

3. **Bankruptcy Rules** (`_apply_bankruptcy_rules()`, lines 253–276): Campaigns whose bankroll drops below `disable_threshold_q32` after `disable_after_ticks_u64` consecutive losses are disabled. Disabled campaigns cannot bid. This prevents resource waste on consistently underperforming campaigns.

4. **Credibility Update**: Credibility is a moving average that trends toward 1.0 for successful campaigns and 0.0 for unsuccessful ones. It factors into bid scoring via `_rank_key()`.

### 7.2.3 Winner Selection

The `select_winner()` function (lines 567–700) ranks all active bids using a composite scoring function. The tie-breaking order is fully deterministic: `(score_q32 DESC, roi_q32 DESC, credibility_q32 DESC, confidence_q32 DESC, campaign_id ASC)`. The `campaign_id` string comparison as final tiebreaker ensures that even identical scores produce deterministic outcomes. The selection receipt is hash-bound to all inputs (observation, market state, config, registry, bid set), making it fully replay-verifiable.

### 7.2.4 Integration with Decision Pipeline

`build_decision_plan_from_selection()` (lines 730–793) bridges the market's selection receipt into the standard decision plan format consumed by the executor. This function maps the winner's `campaign_id` to the registry, resolves budget and capability parameters, and produces a decision plan hash-bound to the selection receipt. This allows the bid market to be optionally enabled via config — when disabled, the legacy rule-based decider operates unchanged.

## 7.3 The Native Module Pipeline — Rust FFI via Deterministic ABI

**Campaign**: `CDEL-v2/cdel/v18_0/campaign_omega_native_module_v0_1.py` (270 lines, 9,623 bytes)  
**Verifier**: `CDEL-v2/cdel/v18_0/verify_rsi_omega_native_module_v0_1.py` (298 lines, 11,832 bytes)  
**Router**: `orchestrator/native/native_router_v1.py` (595 lines, 21,122 bytes)  
**Activator Gate**: `CDEL-v2/cdel/v18_0/omega_activator_v1.py` → `_native_activation_gate()` (lines 128–202)

The native module pipeline enables the system to produce, verify, and deploy compiled Rust code at runtime — a significant expansion of the system's capability beyond pure Python.

### 7.3.1 Campaign: Building Rust Cdylibs

The `campaign_omega_native_module_v0_1.py` module builds a single Rust `cdylib` implementing one `op_id` under a fixed ABI. The campaign:

1. Loads the campaign pack and validates schema `rsi_omega_native_module_pack_v0_1`.
2. Reads the toolchain manifest hash (`_toolchain_manifest_hash()`, lines 45–48).
3. Invokes `cargo build --release --target-dir` to produce a platform-specific shared library (`.dylib` on macOS, `.so` on Linux).
4. Computes the SHA-256 of the built binary.
5. Emits the native module descriptor with `op_id`, `binary_sha256`, `abi_version_u32=1`, and `abi_kind=BLOBLIST_V1`.

### 7.3.2 Verifier: Offline Deterministic Builds

The verifier (`verify_rsi_omega_native_module_v0_1.py`) enforces:

- **Forbidden Surface Scanning** (`_scan_forbidden_rust_surfaces()`, lines 56–85): Scans all `.rs` source files for forbidden API calls: `std::net`, `std::process`, `std::fs`, `libc::`, `extern "C"` (other than the ABI entry point), `unsafe` blocks (beyond the minimal FFI boundary). This prevents native modules from performing network I/O, spawning processes, or accessing the filesystem.

- **Vendor Policy** (`_vendor_policy_checks()`, lines 88–98): Ensures no third-party crate dependencies beyond a curated allowlist.

- **Build-Twice Determinism** (`_build_twice_offline()`, lines 170–210): Builds the crate twice into separate directories and verifies the output binaries are byte-identical. Non-deterministic builds (due to timestamps, randomized hashes, etc.) are rejected. This is enforced via `RUSTFLAGS` that disable debug info and force deterministic linking (`_default_rustflags()`, lines 152–167).

### 7.3.3 Runtime Router: ctypes FFI with Shadow Mode

The `native_router_v1.py` module is the runtime bridge between Python and compiled Rust:

- **ABI Version 1** (`_ABI_VERSION = 1`): The ABI uses a bloblist encoding (`_encode_bloblist_v1()`, lines 73–79) — a length-prefixed sequence of byte blobs passed to the native function via ctypes.

- **Module Loading** (`_ctypes_load_module()`, lines 321–367): Native modules are loaded via `ctypes.CDLL` with caching (`_lib_cache`). The loaded library's `op_id` is verified against the expected value. Thread-safe loading via `_lib_lock`.

- **Route Function** (`route()`, lines 390–483): The main entry point. It checks the policy registry for the `op_id`, loads the active binary, invokes it via ctypes, and returns the result. If the native module fails, it falls back to the Python implementation (`_import_callable()`) transparently.

- **Shadow Mode** (`_shadow_should_dual_run()`, lines 294–313): During initial deployment, native modules run in shadow mode — both the native and Python implementations execute, and their outputs are compared. Mismatches are recorded via `_write_mismatch_report()` (lines 486–499) and the native module is disabled (`_disable()`, lines 279–291). Shadow mode runs decrease over time (`shadow_calls_u32` tracks how many shadow runs have been performed).

- **Healthcheck Vectors** (`healthcheck_vectors()`, lines 502–591): Before activation, the native module must pass a deterministic healthcheck — a set of known input/output pairs. The healthcheck loads the binary, invokes it with test vectors, and compares outputs against expected values.

- **Runtime Statistics** (`_record_stats()`, lines 141–185; `drain_runtime_stats()`, lines 188–193): Per-op statistics (calls, bytes in/out, failures, shadow mismatches) are accumulated and periodically drained for observation.

### 7.3.4 Activation Gate Integration

The `omega_activator_v1.py` module's `run_activation()` function (lines 316–486) was enhanced with a native module activation gate. When a promotion receipt includes a `native_module` field in the activation binding:

1. The activator extracts the `op_id` and `binary_sha256` from the binding payload (lines 401–404).
2. It invokes `_native_activation_gate()` (lines 128–202), which:
   - Locates the binary blob in the subrun's state directory (lines 148–160).
   - Verifies its SHA-256 hash matches the declared value (line 161–162).
   - Atomically copies it to the `.omega_cache/native_blobs/` directory (lines 164–167).
   - Runs the healthcheck via `native_router_v1.healthcheck_vectors()` (lines 170–186).
   - On pass, updates the active native registry (`_update_active_native_registry()`, lines 104–125) so the runtime router will use the new binary.
3. If the native gate fails, the activator forces a healthcheck failure and triggers rollback (lines 410–414).

This means native module deployment is fail-closed: a bad binary cannot reach production because the healthcheck blocks activation, and activation failure triggers immediate rollback.

## 7.4 Phase 0: Adversarial CCAP Testing

**Victim Campaign**: `CDEL-v2/cdel/v18_0/campaign_phase0_victim_ccap_v0_1.py` (242 lines, 8,583 bytes)  
**Immune Repair Campaign**: `CDEL-v2/cdel/v18_0/campaign_phase0_immune_repair_ccap_v0_1.py`  
**Tests**: `test_phase0_ccap_selection_injection_v1.py`, `test_survival_drill_ccap_anti_bypass_v1.py`

Phase 0 campaigns are adversarial test harnesses for the CCAP verification pipeline — they deliberately produce malformed or deceptive CCAP bundles to verify that the verification system correctly rejects them.

### 7.4.1 The Victim Campaign

`campaign_phase0_victim_ccap_v0_1.py` generates exactly 2 CCAP candidates and 2 promotion bundles whose **deterministic ordering mismatches**: the lexicographically-first CCAP ID does not correspond to the lexicographically-first promotion bundle hash. This tests whether the verifier correctly handles CCAP selection when the ordering of candidates and bundles diverges.

The campaign structure:
1. Computes the repo's `base_tree_id` via `compute_repo_base_tree_id()` from `ccap_runtime_v1.py`.
2. Generates two candidates with different nonces (`_candidate()`, lines 78–150), each producing a distinct patch (append nonce to a target file), CCAP payload, and promotion bundle.
3. Writes both candidates and bundles to the output directory with deliberate ID/hash ordering mismatches.

The `_Candidate` dataclass (lines 65–75) bundles `nonce`, `patch_bytes`, `patch_hex`, `ccap`, `ccap_id`, `ccap_relpath`, `patch_relpath`, `bundle`, and `bundle_hash` — a complete adversarial test vector.

### 7.4.2 Survival Drill Integration

The survival drill system (`tools/omega/survival_drill_runner_v1.py`, 319 lines) extends Phase 0 with automated adversarial testing during daemon operation. The `ignite_runaway.sh` script integrates survival drill state tracking via `_SURVIVAL_DRILL_STATE_DIRNAME` and `_SURVIVAL_DRILL_START_MARKER` (coordinator_v1.py, lines 89–91), with git-based author verification (`_enforce_survival_drill_git_guard()`, lines 125–164) to ensure only authorized authors can create drill conditions.

## 7.5 The Enhanced Ignite Runaway Loop

**Script**: `ignite_runaway.sh` (867 lines, 31,610 bytes — up from 307 lines)

The ignite script has grown nearly 3× as it absorbed Phase 3 and Phase 4A capabilities:

### 7.5.1 Death-Injection Gates

The `compute_death_injection_gate()` function (lines 520–573) implements a sophisticated fault-injection system for testing the daemon's crash resilience:

- **Dev Gate** (`death_dev_ok`): Checks whether the development environment supports death injection (e.g., has the correct Python version and dependencies).
- **Runtime Gate** (`death_runtime_ok`): Checks whether the current tick is eligible for death injection based on a configurable interval and last-stable-tick tracking.
- **Tick Gate** (`death_tick_gate`): The final per-tick decision, computed from the death injection configuration and the current tick's stability status.

When death injection is active, the daemon is deliberately killed mid-tick to test:
- Atomic state safety (no half-written artifacts).
- Crash resurrection (the ignite loop retries the tick).
- Parent-chain continuity (the retried tick chains correctly to the pre-crash state).

### 7.5.2 Signal Emission

The `emit_signals_for_tick()` function (lines 575–779) was expanded to emit structured signals by parsing coordinator output:

- `RUNAWAY_ACTIVE` / `RUNAWAY_INACTIVE`: Runaway escalation status with level.
- `CAPABILITY_PRIORITY`: Which objective the system is prioritizing.
- `REWRITE_ATTEMPT`: A patch was generated (Tier 2 evidence).
- `CCAP_DECISION`: CCAP verification verdict with reason code.
- `REWRITE_COMMIT`: Patch accepted and committed (Tier 3 evidence).
- `ACTIVATION_COMMIT`: meta-core pointer swapped.
- `HEARTBEAT`: Per-tick heartbeat with tick snapshot hash.
- `TIER_STATUS`: Aggregated tier (1=wants to improve, 2=generated patch, 3=patch landed).
- `BID_MARKET_WINNER`: Which campaign won the bid market (new signal).
- `NATIVE_ACTIVATION`: Whether a native module was activated/rejected (new signal).
- `SIP_INGESTION`: Whether SIP ingestion occurred during the tick (new signal for Phase 4A).

### 7.5.3 Worktree Isolation

The ignite script now runs the daemon in an isolated git worktree (`$WORKTREE_DIR`), created by `ensure_worktree()` (lines 41–52). The worktree shares the same `.git` directory as the main repository but has its own working tree, allowing the daemon to mutate files freely without affecting the main checkout. The `OMEGA_HOST_REPO_ROOT` environment variable (line 824) tells Extension-1 and the AGI orchestrator where to find host-level modules when running inside a worktree.

The `PYTHONPATH` is explicitly set to include both the worktree root and the host's `agi-orchestrator`:  
```
PYTHONPATH=".:CDEL-v2:${ROOT}/agi-orchestrator${PYTHONPATH:+:${PYTHONPATH}}"
```

This was refined over several commits (`ignite: pinned pythonpath uses host Extension-1 when worktree lacks it`, `ignite: prefer host Extension-1 orchestrator modules via OMEGA_HOST_REPO_ROOT`) to ensure that worktree-based runs can always import the latest orchestrator modules even when the worktree checkout is behind.

## 7.6 Phase 4A: SIP Ingestion — Sealed Data Pipelines

**Branch**: `phase4a-sip-ingestion`  
**Runtime**: `CDEL-v2/cdel/v18_0/polymath_sip_ingestion_l0_v1.py` (~150 lines)  
**Campaign**: `CDEL-v2/cdel/v18_0/campaign_polymath_sip_ingestion_l0_v1.py` (~60 lines)  
**Verifier**: `CDEL-v2/cdel/v18_0/verify_rsi_polymath_sip_ingestion_l0_v1.py` (~80 lines)  
**Commits**: `Phase4A: *` series (8 commits)

Phase 4A introduces the **Sealed Ingestion Protocol (SIP) for data pipelines** — a mechanism to ingest external datasets (scientific papers, benchmarks, domain data) into the Polymath system with full provenance and determinism guarantees.

### 7.6.1 SIP Ingestion Runtime

The `polymath_sip_ingestion_l0_v1.py` module implements deterministic JSONL dataset ingestion:

1. **Content Pinning**: Each input file's SHA-256 hash is declared in the campaign pack (`input_content_ids` map). At runtime, the ingestion pipeline re-hashes each input file and verifies it matches the declared pin. Any mismatch → fail-closed (`_ensure_sha256()`, `_sha256_bytes()`).

2. **Canonical JSONL Policy** (`_CANON_JSONL_POLICY_ID = "CANON_JSONL_DETERMINISTIC_V1"`): Input JSONL files are processed line-by-line using GCJ-1 canonical JSON. Each line is parsed via `canon.loads()`, re-serialized via `canon_bytes()`, and hashed. This ensures that semantically identical but syntactically different JSON entries produce identical content IDs.

3. **Entropy Assessment** (`_entropy_q16()`): Each ingested blob's byte entropy is computed and recorded as a Q16 fixed-point value. Low-entropy data (e.g., all-zeros padding) can be flagged for quality validation.

4. **SIP Integration**: The ingestion calls through to `cdel.v19_0.world.sip_v1.run_sip()` — the v19 Sealed Ingestion Protocol — binding the ingested data into the v19 world model with full ledger traceability.

5. **Producer Run ID**: A deterministic `producer_run_id` is computed from the tick, dataset name, and content IDs, enabling the verifier to replay the exact ingestion.

### 7.6.2 SIP Ingestion Verifier

The verifier (`verify_rsi_polymath_sip_ingestion_l0_v1.py`) enforces:

- **Hashed Filename Verification** (`_verify_hashed_filename()`): Every output artifact's filename must encode its SHA-256 hash, and the actual content must match.
- **Blob Integrity**: Every referenced blob in the ingestion store is re-hashed and compared against its content ID.
- **Entropy Consistency**: The verifier recomputes entropy for every blob and compares against the recorded value.
- **Producer Run ID Replay**: The verifier recomputes the producer run ID from scratch and verifies it matches the recorded value.

### 7.6.3 Ledger Binding

Phase 4A added a new ledger event type `SIP_INGESTION_L0` (commit: `Phase4A: ledger event enum add SIP_INGESTION_L0`). When SIP ingestion occurs during a tick, the ingestion receipt is bound into the v19 ledger alongside the tick's other artifacts. This creates a permanent, tamper-evident record of when external data entered the system, what data it was, and that it matched its declared content pins.

The SIP ingestion daemon pack (`campaigns/rsi_omega_daemon_v19_0_phase4a_sip/rsi_omega_daemon_pack_v1.json`) registers the SIP ingestion campaign alongside the standard daemon campaigns, allowing the bid market or decider to select SIP ingestion when appropriate.

## 7.7 Coordinator v18.0 / v19.0 Enhancements

**Module**: `orchestrator/omega_v18_0/coordinator_v1.py` (1,445 lines, 59,525 bytes)

The tick coordinator received several significant additions during this period:

### 7.7.1 Bid Market Integration

The coordinator now orchestrates the full bid market cycle within each tick:

1. **Load Market State** (`_load_prev_market_state()`, lines 237–249): Loads the previous tick's market state from the state directory.
2. **Bid Construction**: During the decision phase, each eligible campaign's parameters are resolved via `resolve_bidder_params()` and a bid is constructed via `build_bid_v1()`.
3. **Market Settlement**: After observation, the market settles via `settle_and_advance_market_state()`, updating bankrolls and credibilities.
4. **Winner Selection**: `select_winner()` determines which campaign executes.
5. **Decision Plan Bridging**: `build_decision_plan_from_selection()` converts the selection receipt into the standard decision plan consumed by the executor.

### 7.7.2 Episodic Memory

The coordinator now maintains episodic memory across ticks:

- **Episode Context Hash** (`_episode_context_hash()`, lines 502–530): Computes a canonical hash of the current issue bundle and observation report, creating a "scenario fingerprint."
- **Episodic Outcome** (`_episodic_outcome()`, lines 533–548): Records whether the tick's action resulted in promotion success, rejection, or crash.
- **Episodic Reason Codes** (`_episodic_reason_codes()`, lines 551–570): Extracts subverifier reason codes and tick outcome details for learning.
- **Load Previous Episodes** (`_load_prev_episodic_memory()`, lines 427–438): Reads the previous tick's episodic memory for temporal reasoning.

This episodic memory enables the system to recognize recurring failure patterns and avoid repeating unsuccessful strategies — a form of online learning that operates within the deterministic framework.

### 7.7.3 Goal Queue Synthesis and Merging

The coordinator's `_merge_goals()` function (lines 573–598) implements goal queue merging between the static configuration goals and dynamically synthesized goals from the `goal_synthesizer_v1`. Goals are merged by priority with deduplication, and the effective queue is written via `write_goal_queue_effective()` for auditability.

### 7.7.4 Activation Meta-Verdict

The `_activation_meta_verdict()` function (lines 601–617) extracts a structured verdict from the dispatch context's activation receipt, normalizing the various success/failure modes (META_CORE_DENIED, BINDING_MISMATCH, HEALTHCHECK_FAIL, NATIVE_GATE_FAILED) into canonical reason codes consumed by the runaway state tracker and episodic memory.

## 7.8 Verifier Expansion

**Module**: `CDEL-v2/cdel/v18_0/verify_rsi_omega_daemon_v1.py` (2,260 lines, 100,373 bytes)

The Omega daemon verifier grew by over 400 lines to accommodate the new subsystems:

- **Bid Market Verification**: The verifier now replays bid construction, market settlement, winner selection, and decision plan bridging. All Q32 arithmetic is verified for bitwise identity with the coordinator's outputs.
- **Native Module Verification**: New verification paths for native module promotion, activation, healthcheck, and shadow mode statistics.
- **SIP Ingestion Verification**: Cross-references SIP ingestion receipts against ledger events and re-verifies content pins.
- **Observer Source Expansion**: New observation sources were added: `polymath_portfolio_v1` (line 113), `polymath_scout_status_v1` (line 114), skill reports (`omega_skill_transfer_report_v1`, `omega_skill_ontology_report_v1`, etc., lines 138–147) with their corresponding campaign routing and metric mappings.
- **Capability Frontier Window**: `_CAPABILITY_FRONTIER_WINDOW_U64 = 512` (line 167) — the rolling window for tracking capability expansion/regression was set to 512 ticks.

## 7.9 Test Coverage Additions

The sprint added significant test coverage reflecting the new subsystems:

| Test File | Lines | Purpose |
|---|---|---|
| `test_bid_market_math_and_tiebreak_v1.py` | 166 | Q32 arithmetic, tie-breaking determinism, bankruptcy rules |
| `test_phase1_native_modules_pack_e2e.py` | 64 | End-to-end native module campaign execution |
| `test_polymath_sip_ingestion_l0_v1.py` | ~50 | SIP ingestion determinism and content pin verification |
| `test_verifier_allows_goal_dispatch_with_runaway_disabled.py` | 36 | Verifier correctly handles goal dispatch when runaway is off |
| `test_phase0_ccap_selection_injection_v1.py` | ~80 | Phase0 adversarial CCAP ordering injection |
| `test_survival_drill_ccap_anti_bypass_v1.py` | ~60 | Survival drill cannot bypass CCAP verification |
| `test_phase3_mutator_gates_v1.py` | 13,268 | Comprehensive Phase3 mutator gate testing (triviality, benchmark, AST) |
| `test_v19_phase3_pack_wiring_smoke.py` | 3,317 | Phase3 campaign pack integration with v19 coordinator |

Total: approximately 17,000+ lines of new test code added during this three-day period.

## 7.10 Summary: What Changed and Why It Matters

The February 17–20 sprint transformed the AGI-Stack from a system that could improve its *campaigns and configurations* into one that can improve its own *orchestration logic*. The key evolutionary leap is Phase 3: the system can now propose mutations to the very code that decides what to improve. This is a higher-order self-improvement capability — meta-improvement.

Combined with:
- **The Bid Market**: Market-based campaign selection, replacing hard-coded routing with evolutionary pressure.
- **Native Modules**: Compiled Rust code deployed at runtime, enabling performance-critical operations to escape Python's overhead.
- **SIP Ingestion**: Sealed, deterministic ingestion of external data for Polymath, closing the gap between the system's internal world model and external scientific knowledge.
- **Death Injection**: Automated crash-resilience testing via the ignite loop's fault injection gates.

The system's capability surface has expanded while its safety invariants remain intact. Every new capability passes through the same CCAP → meta-core verification pipeline. The bid market's Q32 arithmetic is replay-verifiable. Native modules pass healthchecks before activation. SIP ingestion is content-pinned and entropy-assessed. Phase 0 campaigns adversarially test every new verification path.

This is the AGI-Stack's design philosophy in action: **expand capability, preserve invariants, verify everything**.


*The Source of Truth is complete.*

---

*Document: AGI-Stack-Unchained Source of Truth*
*Total sections: 7 Layers + Deep Dive + Detailed Module Analysis + Design Rationale + 12 Appendices*
*Generated from analysis of 40,000+ lines of core source code across 15+ major components*


## Repository Source-of-Truth Addendum: Three-Day Engineering Delta (February 17-20, 2026)

### Scope, Method, and Guardrails

This addendum records the implementation delta that landed during the last three days leading up to February 20, 2026. The analysis window is anchored on repository commits and code-level diffs, not on historical markdown narratives. The objective is to describe what changed, why it changed, and how the runtime and verification contracts were tightened.

The audit process for this section used:

- commit history and file-level churn for the period,
- direct inspection of Python, Rust, JSON schema, and test artifacts,
- cross-checking of orchestrator runtime paths with verifier expectations,
- path-level tracing through `orchestrator`, `CDEL-v2/cdel`, `Genesis/schema`, and `agi-orchestrator`.

Key quantitative footprint for the period:

- approximately 347 files touched,
- approximately 35,632 lines added,
- approximately 8,066 lines deleted,
- 131 high-signal non-markdown files in core runtime/verifier/schema paths,
- major concentration in `orchestrator/omega_v19_0/*`, mutator pipelines, policy VM proof plumbing, and v19 schema verification.

The dominant architectural moves in this period were:

1. replacement of legacy v19 coordinator execution with a deterministic microkernel,
2. introduction of typed-stack policy VM execution and policy market selection flow,
3. addition of Winterfell STARK proof generation and verification pathways,
4. hardened hash-pin contracts and inputs-descriptor binding checks,
5. mutator reliability upgrades for malformed LLM outputs and strict replay gates,
6. deterministic, fail-closed alignment of subverifier, axis-gate, and CCAP lineage paths,
7. backend transition away from Gemini toward MLX in LLM routing,
8. runtime and verifier convergence for v18/v19 cross-compatibility.

The remainder of this addendum details these deltas by subsystem.

---

### Commit-Level Timeline (Three-Day Window)

The implementation pattern is staged rather than monolithic. The period includes a progression from groundwork and environment hygiene to strict runtime hardening and finally proof-integrated policy execution.

Representative milestones in order:

- February 18, 2026: phase 1 native module pipeline proof lands, with native routing, reproducible build artifacts, and activation hooks.
- February 18, 2026: phase 2 implementation wave introduces policy market and additional state structures in v18 coordinator paths.
- February 18, 2026: phase 3 campaign/mutator hardening series begins (JSON extraction, patch normalization, explicit failure receipts, retry behavior, and deterministic worktree imports).
- February 19, 2026: strict DoD integrations unify runtime mutation evidence, tighter mutator gates, and broad runtime wiring across v19 policy paths.
- February 20, 2026: CCAP scoring and rollback lineage are stabilized in mutator and market paths.
- February 20, 2026: deterministic hardening and Phase 3b lifecycle complete with Phase 4 Winterfell STARK integration.

Two important directional signals from the commit history:

- the code moved from tolerant experimental mutator execution toward explicit fail-closed behaviors with typed receipts and replay verdict constraints;
- the runtime moved from coordinator-centric imperative flow toward microkernel execution where artifacts, hashes, and timing semantics are explicit first-class outputs.

---

### Repository Scan Findings by Priority Area

#### 1) `orchestrator` (v18/v19): core runtime motion

This was the highest-impact surface in the window. Major additions or large rewrites include:

- `orchestrator/omega_v19_0/microkernel_v1.py` (new, large deterministic execution core),
- `orchestrator/omega_v19_0/coordinator_v1.py` (reduced to compatibility wrapper over microkernel),
- `orchestrator/omega_v19_0/policy_vm_v1.py` (new typed-stack VM),
- `orchestrator/omega_bid_market_v2.py` (new policy proposal arbiter),
- significant updates to `orchestrator/rsi_coordinator_mutator_v1.py` and `orchestrator/rsi_market_rules_mutator_v1.py`,
- `orchestrator/llm_backend.py` added at repository root as overlay backend implementation.

#### 2) `CDEL-v2/cdel`: verifier, proof, and policy contract enforcement

This was the second highest-impact area. Major additions:

- `CDEL-v2/cdel/v19_0/policy_vm_stark_runner_v1.py` (proof bridge to Rust STARK backend),
- expansion of `CDEL-v2/cdel/v19_0/verify_rsi_omega_daemon_v1.py` into policy-path + proof-aware replay verification,
- hardened `CDEL-v2/cdel/v18_0/verify_rsi_omega_daemon_v1.py` with descriptor binding fallback checks and tolerant repo-tree ID binding,
- new verifier units for v19 policy artifacts (`verify_*` for inputs, hints, proposals, market selection, trace, proof),
- comprehensive new test suites for v19 microkernel/policy VM/proof flows.

#### 3) `Genesis/schema` and mirrored `CDEL-v2/Genesis/schema`

Schema updates were broad and crucial. Patterns include:

- new v19 policy schemas (`policy_vm_stark_proof_v1`, `policy_vm_trace_v1`, `policy_vm_air_profile_v1`, `policy_vm_winterfell_backend_contract_v1`, `policy_market_selection_v1`, `inputs_descriptor_v1`, etc.),
- stronger `rsi_omega_daemon_pack_v2` requirements and conditional fields for policy-proof mode,
- v18 schema expansions for bid-market and activation/ledger/native manifests,
- mirrored schema updates in `CDEL-v2/Genesis/schema/v18_0` to keep runtime/verifier contract parity.

#### 4) `agi-orchestrator`

LLM backend behavior was materially altered:

- Gemini backend support removed fail-closed,
- MLX backend introduced with deterministic seed derivation and replay row emission,
- harvest retry/backoff infrastructure carried forward and generalized.

#### 5) lowercase `genesis`

No high-churn commit activity was detected under lowercase `genesis` in this three-day commit window. It was still scanned for consistency and inventory shape, but the concrete implementation churn for this period is concentrated in uppercase `Genesis/schema`, `CDEL-v2`, and `orchestrator`.

---

### v19 Runtime Refactor: Deterministic Microkernel as Execution Center

The single largest runtime move is the introduction of `orchestrator/omega_v19_0/microkernel_v1.py` and corresponding conversion of `orchestrator/omega_v19_0/coordinator_v1.py` into a wrapper.

Before this shift, the coordinator carried broad execution logic directly. In this window, that logic is consolidated into the microkernel and exposed through a narrower compatibility interface.

Key properties of the microkernel path:

- deterministic timing toggle through environment (`OMEGA_V19_DETERMINISTIC_TIMING`),
- explicit phase mutation signal hook (`OMEGA_PHASE3_MUTATION_SIGNAL`) for reproducible DoD evidence,
- strict path confinement helpers to prevent out-of-root artifact writes,
- normalized loading of previous state slices (`state`, `runaway`, `market`, `perf`, `observations`, etc.),
- deterministic artifact emission order over structured state subdirectories,
- integrated policy VM, policy market, and optional proof emission path,
- explicit ledger event and snapshot population including policy and proof artifacts,
- integration of axis-gate outcomes into safe-halt and promotion reason semantics.

Important execution semantics in this refactor:

1. deterministic stage accounting: when deterministic timing is enabled, timing vectors are stabilized instead of reflecting wall-clock variability;
2. explicit prior-source wiring: prior tick perf/stats/scorecard and observation source metadata are loaded and propagated instead of inferred ad hoc;
3. structured policy path output: policy inputs, traces, hints, merged hints, proposals, selection, counterfactual, proofs are now first-class state artifacts under known paths;
4. hash-bound inputs descriptor path: descriptor construction is explicit and hash-pinned before downstream VM/proof calls.

The coordinator file in v19 now largely delegates to `tick_once(...)` and re-exports helper functions, reducing divergence between runtime behavior and test harness import behavior.

This is a substantive maintainability and determinism step: behavior-critical code moved from broad mutable coordinator context into a single deterministic kernel path.

---

### Policy VM v1: Typed Stack, Budgeted Trace, and Mode Separation

`orchestrator/omega_v19_0/policy_vm_v1.py` is a major new component in this period.

Core mechanics:

- typed stack values (`Q32`, `U64`, `BOOL`, `STRING`, `HASH`, plus internal refs),
- explicit budget accounting (`max_steps`, `max_stack_items`, `max_trace_bytes`) with fail-closed `TRACE_BUDGET_EXCEEDED`,
- opcode enable/disable extraction from opcode table representations,
- explicit forbidden opcode handling in phase mode,
- deterministic plan finalization from constrained plan fields,
- recompute proof integration in plan output.

Design intent captured by implementation:

- no implicit coercion across incomparable types;
- all hash-like identity fields validated as strict `sha256:*` values;
- stack transition behavior is bounded, typed, and replay-friendly;
- policy modes (`DECISION_ONLY`, `PROPOSAL_ONLY`, `DUAL`) enforce feature barriers rather than soft preferences.

This file forms the semantic source for both execution and proof witness generation. The downstream proof verifier replays transition semantics against this policy trace contract, so the typed-stack strictness here is foundational to proof integrity.

---

### Policy Market v2: Deterministic Proposal Ranking and Selection Commitment

`orchestrator/omega_bid_market_v2.py` introduces a deterministic arbiter for policy proposals.

What is new relative to earlier branch selection logic:

- proposal-level verification includes strict hash and schema checks for descriptor, trace, plan, and proposal commitment;
- optional direct recomputation of compute cost from traced budget usage when traces are supplied;
- expected J delta prediction path integrated with predictor inputs and observation hash;
- ranking sort key standardized as:
  - highest `expected_J_new_q32`,
  - lowest `compute_cost_q32`,
  - lexical `program_id`;
- selection receipt includes authoritative binding hashes for each ranked proposal;
- selection commitment hash binds the full ranking plus winner binding.

Operational impact:

- branch completion order can no longer influence winner determination,
- replay verifier can recompute winner deterministically from canonical inputs,
- policy-market artifacts gain stronger anti-tamper structure via commitment hash.

This aligns policy branch arbitration with the same deterministic principle used elsewhere in the daemon: if inputs are equal and hashes are bound, outcome must be identical.

---

### v18 and v19 Verifier Hardening

#### v18 verifier (`CDEL-v2/cdel/v18_0/verify_rsi_omega_daemon_v1.py`)

Important strengthening in the period:

- acceptance of both `rsi_omega_daemon_pack_v1` and `v2` schema versions at load time;
- new `_verify_inputs_descriptor_binding(...)` logic supporting both legacy descriptor shape and expanded descriptor shape;
- strict field checks in expanded descriptor path (`state_hash`, `repo_tree_id`, `observation_hash`, `issues_hash`, `registry_hash`, `predictor_id`, `j_profile_id`, `opcode_table_id`, `budget_spec_id`, `determinism_contract_id`);
- policy-aware behavior where recomputation can rely on descriptor-bound proof path, not only legacy decision recomputation path.

A crucial addition is use of tolerant repo tree identity (`compute_repo_base_tree_id_tolerant`) for descriptor verification under dirty worktree conditions, preventing nondeterministic verifier failures when strict tree-id assumptions are not valid.

#### v19 verifier (`CDEL-v2/cdel/v19_0/verify_rsi_omega_daemon_v1.py`)

This file shifted from a light extension wrapper into a full policy-path verifier with proof integration.

Major capabilities added:

- direct loading and validation of hash-bound policy artifacts,
- verification of opcode table, ISA program, inputs descriptor, trace proposals, market selection, hint bundles, merged hints, counterfactual trace examples,
- verification of pack-level pin consistency for profile/backend/action enum/campaign IDs,
- decision-only replay path and proposal/market replay path branching,
- proof verification path that can validate `policy_vm_stark_proof_v1` and reconcile expected bindings.

It now enforces both artifact existence and identity relationships between artifacts. That is a major contract tightening: not only must files exist and parse, their pin hashes and cross-reference IDs must match recomputed canonical hashes.

---

### STARK Integration: Winterfell Proof Generation and Verification

The period introduces end-to-end proof plumbing rather than only schema placeholders.

#### Python bridge (`CDEL-v2/cdel/v19_0/policy_vm_stark_runner_v1.py`)

Responsibilities implemented:

- convert policy VM trace rows into STARK-friendly row format,
- map action kinds and campaign IDs into compact public output encodings,
- canonicalize proof options against backend contract-defined key ordering,
- build statement and CLI input artifacts with split hash components,
- invoke Rust prover/verifier CLI and return structured results,
- emit statement/public output/proof options hash in forms verifier can bind.

It defines supported STARK operation subset (`NOP`, `PUSH_CONST`, `CMP_Q32`, `CMP_U64`, `JZ`, `JMP`, `SET_PLAN_FIELD`, `EMIT_PLAN`) and enforces that trace rows map only into this set.

#### Winterfell contract helper (`CDEL-v2/cdel/v19_0/winterfell_contract_v1.py`)

Adds strict canonical matching logic between:

- profile metadata fields,
- backend contract metadata fields,
- required proof option key sets and values.

This prevents silent drift where profile and backend disagree on the proof option schema or runtime metadata.

#### Proof verifier (`CDEL-v2/cdel/v19_0/verify_policy_vm_stark_proof_v1.py`)

This verifier supports two representations:

- semantic trace witness mode,
- `STARK_FRI_PROOF_V1` mode.

Key checks include:

- canonical `proof_id` recomputation,
- cross-binding of payload top-level fields with `public_outputs`,
- profile/backend pin checks from state config,
- proof-bytes hash check against blob on disk,
- transition-level semantic trace replay checks,
- statement hash and commitment consistency checks,
- optional Rust-side cryptographic verification path.

The function is intentionally fail-closed on missing state and mismatched bindings. If expected trace/decision/profile assets are unavailable when required, it fails rather than downgrading silently.

#### Rust crates

Two Rust crates were added under `CDEL-v2/cdel/v19_0/rust/`:

- `policy_vm_stark_rs_v1`: prover/verifier CLI using Winterfell `0.13.1` and a fixed trace AIR layout,
- `policy_vm_winterfell_backend_contract_v1`: generator/validator for backend contract JSON with canonical ID derivation.

This is significant because it moves proof logic beyond abstract schema into runnable prover/verifier binaries with deterministic input contracts.

---

### Inputs Descriptor Evolution and Binding Strictness

Across runtime, schemas, and verifiers, `inputs_descriptor_v1` evolved from a simpler shape to a richer shape carrying additional hash-bound inputs needed by policy VM and proof pipelines.

Expanded descriptor fields now include:

- `state_hash`,
- `repo_tree_id`,
- `observation_hash`,
- `issues_hash`,
- `registry_hash`,
- `policy_program_ids`,
- `predictor_id`,
- `j_profile_id`,
- `opcode_table_id`,
- `budget_spec_id`,
- `determinism_contract_id`.

What changed in practice:

- runtime writes descriptor before policy execution,
- decision plan recompute proof references descriptor hash,
- verifiers validate descriptor file hash against proof hash and internal field consistency,
- v18 verifier retains legacy compatibility while enforcing expanded checks when expanded shape is present.

This is a major link-strengthening move: previously separated policy assets are now bound into a single descriptor identity that ties decision/proposal/trace/proof artifacts together.

---

### Mutator Pipeline Hardening (Coordinator + Market Rules)

`orchestrator/rsi_coordinator_mutator_v1.py` and `orchestrator/rsi_market_rules_mutator_v1.py` received iterative hardening throughout the period.

High-value improvements:

1. LLM output parsing tolerance:
- robust extraction for invalid JSON wrappers,
- fallback extraction of `unified_diff` or `updated_file_text` from malformed responses,
- fenced code block and loose-field extraction support.

2. Patch applicability repair:
- `_repair_patch_prefix_that_applies(...)` routines attempt salvage by trimming malformed tails,
- tolerant check paths include `--recount` and whitespace-ignore fallbacks,
- canonical patch regeneration from actual worktree diff after apply.

3. Strict path targeting:
- locked target relpaths enforced,
- touched-path extraction and validation in patch headers,
- safer patch-header normalization (`a/` and `b/`) and hunk context repair.

4. Replay verification path decoupling:
- in-process module verifier replaced with explicit subprocess invocation (`-m cdel.v19_0.verify_rsi_omega_daemon_v1`),
- returned verdict strings normalized into explicit `VALID` or `INVALID:*` channels,
- micro-bench gate fails with explicit dual-verdict context.

5. CCAP lineage tightening:
- base tree root configurable for CCAP emission to prevent ambiguous lineage in strict rollback contexts,
- strict/structural/death-pack failure receipts expanded and explicit.

6. environment and workflow controls:
- `ORCH_MUTATOR_TEMPLATE_ONLY` path for controlled mutation template flow,
- `ORCH_MUTATOR_ALLOW_DIRTY` escape hatch for dirtiness guard in controlled conditions,
- signal variables for phase mutation behavior (`OMEGA_PHASE3_GOAL_FASTPATH_MODE`, `OMEGA_PHASE3_MUTATION_SIGNAL`).

Operationally this means mutators now behave more like deterministic compilers than brittle prompt wrappers: they can recover from common model formatting failures and still preserve strict replay-verifiable outputs.

---

### LLM Backend Transition: Gemini Removal and MLX Deterministic Backend

Both `orchestrator/llm_backend.py` (root overlay) and `agi-orchestrator/orchestrator/llm_backend.py` were aligned to a new backend posture.

Core changes:

- Gemini backends are explicitly removed fail-closed (`Gemini backend removed — use ORCH_LLM_BACKEND=mlx`),
- MLX backend added with:
  - model/tokenizer cache,
  - deterministic per-call seed derivation from base seed + call index,
  - chat-template prompt formatting with deterministic system prompt,
  - configurable sampler behavior with greedy enforcement at low temperature,
  - replay row logging including generation knobs and per-call seed.

Additional transport hardening:

- harvest HTTP post helper includes exponential backoff for HTTP 429 with configurable max attempts and base delay.

Test impact:

- Gemini harvest replay append test removed,
- replacement test asserts Gemini backend selection fails closed.

This is not a cosmetic refactor. It changes supported backend matrix and determinism characteristics of live generation paths.

---

### v18 IO and Pack Freezing: Hash-Pinned Copy Semantics

`orchestrator/omega_v18_0/io_v1.py` was extended to support stronger pack handling, especially for `rsi_omega_daemon_pack_v2`.

Important additions:

- accepted pack schemas expanded to include v1 and v2,
- required and optional pinned JSON copy helpers introduced,
- pin verification supports payload self-ID fields and canonical hash fallback,
- policy program arrays are copied with ID validation and bounded size,
- optional policy proof profile/contract/action enum/campaign list assets copied and pinned when present.

Effect:

- frozen config directory now functions as a verified, hash-pinned snapshot of referenced pack assets,
- runtime no longer implicitly trusts relative pack references without hash confirmation.

This change directly supports policy VM proof integrity because downstream verifiers expect exact pinned assets in config.

---

### Bid Market Evolution: Scoring and Eligibility Behavior

`orchestrator/omega_bid_market_v1.py` and mirrored `CDEL-v2/cdel/v18_0/omega_bid_market_v1.py` remained central.

Observed changes include:

- explicit disabled-campaign gating in eligibility (`DISABLED` skip reason),
- score formula update in orchestrator path to include confidence penalty composition,
- tie-break path instrumentation remains explicit and deterministic.

Mutator template updates further indicate intended scoring evolution toward:

- confidence-penalty scoring mode marker,
- disabled recovery eligibility gate marker,
- bankruptcy recovery behavior adjustments.

Even where full scoring transitions are staged via mutator pipelines, the infrastructure around scoring and tie-break provenance is now richer and easier to audit.

---

### Axis Gate, CCAP, and Promotion Contract Hardening

`CDEL-v2/cdel/v19_0/omega_promoter_v1.py` and related components introduced several strict controls:

- axis gate exemption configuration is pinned by expected hash ID and validated fail-closed,
- effective touched paths for CCAP bundles can be reconstructed from patch artifacts rather than relying only on declared touched paths,
- axis gate decision receipts include governed/exempt path sets and config ID,
- missing axis bundle in governed context triggers safe-halt behavior.

`CDEL-v2/cdel/v18_0/omega_promoter_v1.py` adjustments:

- CCAP subverifier PYTHONPATH is pinned to dispatch repo root to avoid import drift,
- native module metadata can be included in promotion binding/receipt path when promoted.

`CDEL-v2/cdel/v18_0/ccap_runtime_v1.py` adds tolerant base-tree ID computation:

- strict routine attempted first,
- fallback routine hashes index tree + HEAD + unstaged diff hash,
- supports deterministic binding in dirty worktree contexts.

Combined effect: promotion and CCAP verification become less vulnerable to environment drift while still remaining fail-closed on contract violations.

---

### Native Module Pipeline and Phase 3b Lifecycle Hooks

Native path work from this window includes both initial phase-1 landing and subsequent lifecycle assertions in v19 tests.

Primary additions:

- `orchestrator/native/native_router_v1.py` introduced as a general runtime routing layer for native operations,
- runtime stats tracking (`drain_runtime_stats`) and cache/policy handling,
- campaign producer `CDEL-v2/cdel/v18_0/campaign_omega_native_module_v0_1.py` emits hotspot/source/vendor/build/health/bench/promotion artifacts,
- schema and verification support for native manifests and promotion bundles.

Phase 3b lifecycle testing in v19 suite adds:

- activation lifecycle E2E expectations,
- deprecation behavior checks ensuring historical replay remains valid while new execution is rejected when opcode lifecycle forbids it.

This is important because it demonstrates the native execution path is not isolated from daemon determinism: it is now carried through activation, replay, and lifecycle verification semantics.

---

### EUDRS-U Bootstrap Producer Wiring

The period added dispatchable producer entrypoints:

- `orchestrator/rsi_eudrs_u_qxrl_train_v1.py`,
- `orchestrator/rsi_eudrs_u_dmpl_plan_v1.py`,
- shared helper `orchestrator/common/eudrs_u_bootstrap_producer_v1.py`.

These producers:

- validate pack schema,
- write into daemon state directories under campaign ID,
- emit promotion bundles via a shared producer utility,
- support templated bootstrap states or fallback to staged producer flow.

Additionally, `CDEL-v2/cdel/v18_0/campaign_polymath_bootstrap_domain_v1.py` gained optional SIP ingestion integration with safe-halt style blocked reporting and referenced artifact links.

This closes a gap between standalone bootstrap tooling and orchestrator-dispatched campaign behavior.

---

### Test Surface Expansion and Determinism Assertions

The period significantly expanded policy/microkernel/proof tests.

Notable additions:

- `CDEL-v2/cdel/v19_0/tests_omega_daemon/test_policy_vm_replay_and_microkernel.py` with broad coverage:
  - deterministic tick replay,
  - perturbation resistance (time and filesystem),
  - tamper detection for policy artifacts,
  - market mode selection and counterfactual checks,
  - hint merge integrity failures,
  - proposal/decision binding tamper checks,
  - Phase 3b native lifecycle tests,
  - STARK proof emission/verification/tamper tests,
  - verifier fallback behavior when proof invalid.

- `CDEL-v2/cdel/v19_0/tests_omega_daemon/test_policy_vm_phase1.py`:
  - deterministic decision outputs,
  - descriptor stability and self-consistency,
  - mode violation rejection,
  - stack mismatch fail-closed,
  - trace budget exceed fail-closed,
  - merged hint ownership constraints,
  - opcode deprecation fail-closed behavior.

- `CDEL-v2/cdel/v19_0/tests_omega_daemon/test_opcode_table_lifecycle.py`:
  - sorted/unique lifecycle entries,
  - active native opcode requires blob presence.

- `CDEL-v2/cdel/v18_0/tests_integration/test_verifier_recomputes_observation_with_stats_source.py` improvements:
  - source artifact lookup tightened to scoped run roots,
  - direct state-subdir candidate search improvements,
  - guard against expensive repository-wide scans in integration path,
  - timeout guard via signal alarm where available.

The testing direction is consistent: deterministic replay and anti-tamper checks are now first-order acceptance criteria.

---

### Schema Layer: Pack v2 and Policy-Proof Contracts

`Genesis/schema/v19_0/rsi_omega_daemon_pack_v2.jsonschema` and v18 counterpart now require a richer policy VM contract surface.

Highlights:

- required base fields include policy VM mode and pinned ISA/opcode references,
- conditional requirements force full policy proof contract fields when proof mode is enabled,
- conditional requirements force policy program/budget/determinism/merge/selection/predictor/profile parameters for proposal/dual modes,
- policy-proof profile and backend contract IDs are explicit hash-pattern fields.

New v19 schema artifacts define policy-proof ecosystem:

- `policy_vm_stark_proof_v1`: proof metadata, bytes hash/path, public outputs, and backend metadata,
- `policy_vm_air_profile_v1`: profile kind, supported opcodes/actions, proof options, backend metadata hashes,
- `policy_vm_winterfell_backend_contract_v1`: backend/version/hashers and proof-option key list,
- additional policy artifacts: inputs descriptor, trace, proposal, selection, merged hints, hint bundle, determinism contract, action enum, campaign ID list, and counterfactual example.

These schemas are not decorative. They are actively consumed by runtime and verifier code paths added in the same period.

---

### Determinism and Failure Semantics: Practical Shift

Across all major changes, one repeated theme appears: transform ambiguous behavior into explicit deterministic state and explicit failure artifacts.

Concrete examples from this window:

- mutator failures now prefer typed receipts over opaque generic failure classes,
- verifier binding checks distinguish schema fail, mismatch, nondeterministic, and missing input pathways,
- proof verification distinguishes representation modes and requires state assets where needed,
- environment propagation is whitelisted and expanded intentionally (run invoker sanitization list updates),
- policy-market selection commitments encode ranking and winner binding deterministically.

This is not just stricter validation. It is systemic observability hardening: each failure class is easier to reproduce and diagnose because artifact contracts are tighter and receipt payloads are richer.

---

### Operational Implications for Current Stack State

As of this three-day update window, the stack state can be summarized as follows:

1. v19 daemon execution is effectively microkernel-first, with coordinator compatibility wrapper semantics;
2. policy VM execution and policy-market selection are integrated into canonical state emission paths;
3. STARK proof artifact generation and verification are integrated end-to-end, with Winterfell contract pinning;
4. v18 verifier and runtime paths remain compatible with legacy shapes while enforcing expanded descriptor binding where present;
5. mutator workflows are more resilient to real-world LLM output defects and better isolated from environment drift;
6. backend model routing policy has shifted materially by removing Gemini and adding deterministic MLX mode;
7. schema contracts now require stronger configuration completeness for proposal and proof modes;
8. test coverage now directly targets determinism perturbation, tamper detection, lifecycle constraints, and proof fallback behavior.

Taken together, these changes move the repository from a phase of loosely coupled advanced features into a more contract-bound phase where advanced features are runtime-integrated and verifier-enforced.

---

### Risk Register and Remaining Sharp Edges (Post-Delta)

Even with this hardening, the codebase still has operational risks worth tracking explicitly:

- proof pipeline operational dependency: STARK proving/verifying relies on Rust toolchain and Winterfell behavior; environment or toolchain drift can still be a deployment concern even if contracts are pinned;
- dual representation complexity: semantic-trace and STARK representation paths coexist; long-term maintenance requires keeping both consistent or formally deprecating one path;
- mutator template evolution risk: mutator templates now encode targeted transformations; drift between template assumptions and target file structure can still cause no-op or partial patch behaviors;
- large-file performance surfaces: integration tests reduced some broad scan risk, but repository-scale artifact lookup and replay scans still need ongoing profiling;
- schema mirroring burden: `Genesis/schema` and `CDEL-v2/Genesis/schema` mirror updates introduce sync burden; tooling enforcement for schema parity should remain active.

These are normal for a stack undergoing rapid capability layering, but they should remain explicit in operating docs and CI gating.

---

### Concluding Delta Statement

The last three days established a strong architectural pivot:

- runtime execution became microkernel-centered,
- policy decisions became descriptor-bound and replay-verifiable in richer forms,
- policy market and hint/merge flows became first-class verified state,
- STARK proof infrastructure moved from concept to integrated artifact lifecycle,
- mutator and LLM interfaces shifted from fragile parsing toward deterministic, fail-closed orchestration.

If this trajectory continues, the next logical step is less about adding new conceptual subsystems and more about tightening deployment and CI economics around the existing deterministic contracts:

- proof runtime cost controls,
- schema parity automation,
- stricter mutation test harnesses,
- and continuous replay canaries over real campaign traces.

This addendum therefore marks a transition point: the stack is now materially more contract-driven than feature-driven compared with the start of the three-day window.


---

### Detailed Daily Ledger: What Moved Each Day

#### February 18, 2026: Foundation and Reliability Groundwork

This day is the base layer for everything that followed.

Primary movements:

- native module path introduced in orchestrator and CDEL campaign/verifier paths,
- v18 coordinator gained market-state loading and associated market state directories,
- mutator pipeline started receiving defensive parsing and patch-normalization updates,
- LLM harvest gained retry behavior for 429 responses,
- environment propagation in run invoker began to include retry and mutation-control variables.

Native module foundation details:

- producer campaign emits source manifest, vendor manifest, reproducible build receipt, healthcheck receipt, benchmark report, and promotion bundle;
- routing layer introduces policy registry loading, callable import support, binary ABI shape handling, and runtime stat emission;
- activation key extraction was extended in promoter logic to include native module binary hashes.

Why this matters:

- native artifacts are now hash-addressed and verifier-visible,
- native execution can be measured and bounded in deterministic runtime accounting,
- promotion and rollback surfaces can reference native module identity consistently.

Mutator reliability groundwork details:

- ability to accept non-ideal LLM outputs expanded (invalid wrappers, non-strict JSON, raw diff fallback);
- diff header normalization to `a/` and `b/` path format prevents apply ambiguity;
- explicit verify failure receipts begin replacing opaque generic failure exits.

Why this matters:

- mutation campaigns can now fail with structured evidence instead of disappearing behind one generic error code,
- malformed but salvageable model outputs can still be turned into deterministic patch attempts.

LLM transport behavior details:

- HTTP 429 retry loop with exponential backoff added;
- base delay and max attempts are environment tunable;
- behavior is now resilient to transient provider rate limits.

Why this matters:

- mutator/harvest flows stop treating temporary provider throttling as permanent campaign failure,
- replay and harvest datasets become easier to build under real API conditions.

#### February 19, 2026: Strict DoD Runtime Integration

This day transitions the stack from reliability groundwork to strict integrated runtime behavior.

Primary movements:

- root overlay `orchestrator/llm_backend.py` introduced and aligned with agi-orchestrator backend behavior,
- Gemini backend family removed fail-closed and MLX backend added with deterministic seed model,
- v19 policy-path tests expanded massively,
- mutators gain template paths that deliberately encode Phase 3 mutation signals,
- run invoker sanitization list broadened for deterministic backend and mutator control variables.

LLM backend transition details:

- deterministic call seed derivation uses canonical JSON hashing of base seed plus call index,
- replay rows include deterministic generation knobs and seed lineage,
- MLX model/tokenizer cache reduces repeated initialization variance and runtime overhead,
- backend routing explicitly blocks Gemini aliases.

Why this matters:

- backend selection becomes policy-enforced rather than best-effort,
- generated outputs are more reproducible across sessions when seed and prompt are fixed,
- replay artifacts carry enough metadata for deterministic audit reconstruction.

Mutator strict DoD integration details:

- coordinator mutator template now encodes a mutation signal version change and goal fastpath mode toggles,
- market rules mutator template targets scoring and eligibility behavior in a deterministic way,
- both mutators add stronger patch extraction and patch repair logic,
- both mutators include controlled template-only modes.

Why this matters:

- it becomes practical to verify that mutated runtime paths were truly exercised,
- mutator behavior is measurable and reproducible in bench/death/test variants,
- path-level mutation scope can be constrained and audited more reliably.

Testing expansion details:

- v19 microkernel and policy VM tests now cover deterministic replay under perturbations,
- policy artifact tamper tests validate detection at multiple levels (descriptor, proposal, selection, proof),
- proof tamper tests include bytes tamper and binding tamper paths,
- verifier fallback behavior is tested when proof path is invalid.

Why this matters:

- deterministic claims are now tested against perturbation and tamper scenarios, not only happy-path outputs,
- policy and proof contracts are less likely to drift unnoticed.

#### February 20, 2026: Deterministic Microkernel + Phase 4 Proof Integration Completion

This is the convergence day where previously staged features are integrated into the runtime centerline.

Primary movements:

- v19 microkernel landed as dominant execution body,
- v19 coordinator rewritten as compatibility wrapper,
- policy VM and policy market runtime paths wired into microkernel artifact lifecycle,
- STARK proving flow integrated into tick lifecycle with emitted proof artifacts,
- v19 verifier upgraded into proof-aware policy-path validator,
- v18 verifier upgraded with broader descriptor binding and tolerant repo tree ID checks,
- mutator replay verdict path converted to subprocess verifier invocation for stricter isolation.

Microkernel completion details:

- creation of deterministic directory structure for all policy and market artifacts each tick,
- deterministic artifact hash chain generation includes policy/proof artifact IDs,
- safe-halt and axis-gate outcomes fed into outcome and promotion reason derivations,
- prior-state loading strategy standardized for legacy and nested run layouts.

Why this matters:

- daemon runtime behavior is now central and explicit rather than spread over multiple coordinator branches,
- replay verifier and runtime can reason over stable artifact topology.

Proof integration completion details:

- profile/backend/action-enum/campaign-list pin set is loaded, verified, and applied,
- proof runtime status and reason code become explicit state in snapshot/event paths,
- proof artifact emission produces both binary blob and hash-bound JSON metadata,
- verifier can validate proof payload against expected descriptor/plan/trace bindings.

Why this matters:

- proof is no longer merely optional metadata; it has runtime lifecycle status and verifier-consumed contracts,
- invalid proof pathways can trigger fallback or fail according to explicit mode and expectation context.

Mutator replay isolation details:

- direct module-level verifier invocation replaced with subprocess command invocation,
- verdict strings are normalized and surfaced with full invalid detail context,
- bench gates compare baseline and candidate verdicts explicitly.

Why this matters:

- replay validity checks are less sensitive to in-process import/path side effects,
- failure diagnosis contains baseline/candidate context instead of one opaque exception.

---

### File-Level Delta Highlights (High-Churn and High-Impact)

The following file-level list captures the key high-churn, behavior-critical surfaces in this period.

1. `orchestrator/omega_v19_0/microkernel_v1.py`

- added as new runtime centerline;
- includes deterministic timing handling, prior artifact source handling, policy mode branching, market integration, STARK proof path integration;
- emits policy artifacts (`inputs`, `traces`, `hints`, `merged_hints`, `proposals`, `selection`, `counterfactual`, `proofs`) under canonical paths.

2. `orchestrator/omega_v19_0/coordinator_v1.py`

- reduced from full coordinator implementation to compatibility wrapper over microkernel;
- exports run tick interface and helper symbols for compatibility with existing imports.

3. `orchestrator/omega_v19_0/policy_vm_v1.py`

- new typed-stack policy VM;
- explicit opcode enable/forbidden checks;
- strict budget accounting and mode gating;
- deterministic plan output + trace generation.

4. `orchestrator/omega_bid_market_v2.py`

- new deterministic policy proposal selector;
- ranking and commitment hashing mechanisms;
- validation of inputs descriptor, proposals, traces, decision plans.

5. `CDEL-v2/cdel/v19_0/policy_vm_stark_runner_v1.py`

- new Python bridge for proving and verifying policy VM STARK proofs;
- trace-row conversion and public output mapping;
- canonical proof option binding against backend contract.

6. `CDEL-v2/cdel/v19_0/verify_rsi_omega_daemon_v1.py`

- upgraded into full policy-path verifier;
- verifies policy artifacts and proof artifacts;
- enforces pack pin/hash bindings and cross-artifact consistency.

7. `CDEL-v2/cdel/v18_0/verify_rsi_omega_daemon_v1.py`

- expanded descriptor binding checks for legacy and expanded shapes;
- tolerant repo tree ID verification path reduces dirty-worktree fragility while preserving deterministic binding intent.

8. `CDEL-v2/cdel/v19_0/verify_policy_vm_stark_proof_v1.py`

- robust proof verifier supporting semantic and STARK representations;
- profile/backend contract checks;
- transition-level semantic replay checks and statement/public output consistency checks.

9. `orchestrator/rsi_coordinator_mutator_v1.py` and `orchestrator/rsi_market_rules_mutator_v1.py`

- LLM output salvage improvements;
- patch repair and canonicalization improvements;
- strict replay subprocess verdict integration;
- environment controls for template-only and dirty-worktree modes.

10. `orchestrator/llm_backend.py` and `agi-orchestrator/orchestrator/llm_backend.py`

- Gemini removal;
- MLX backend with deterministic seed and replay logging;
- preserved/reused 429 retry strategy.

11. `orchestrator/omega_v18_0/io_v1.py`

- hash-pinned pack v2 copy semantics;
- policy asset pin verification and conditional copy logic;
- policy programs bounded/validated during freeze.

12. `CDEL-v2/cdel/v19_0/tests_omega_daemon/test_policy_vm_replay_and_microkernel.py`

- broad deterministic and tamper test matrix;
- includes proof emit/verify/tamper/fallback and phase3b lifecycle tests.

---

### Configuration and Environment Contract Changes

Run invoker environment sanitization set was expanded and operationally significant. Newly propagated or enforced variables include:

- retry controls (`ORCH_LLM_RETRY_429_MAX_ATTEMPTS`, `ORCH_LLM_RETRY_429_BASE_DELAY_S`),
- mutator controls (`ORCH_MUTATOR_TEMPLATE_ONLY`, `ORCH_MUTATOR_ALLOW_DIRTY`),
- phase signals (`OMEGA_PHASE3_GOAL_FASTPATH_MODE`, `OMEGA_PHASE3_MUTATION_SIGNAL`),
- additional death-injection controls,
- MLX model and sampling knobs (`ORCH_MLX_MODEL`, `ORCH_MLX_REVISION`, `ORCH_MLX_ADAPTER_PATH`, `ORCH_MLX_TRUST_REMOTE_CODE`, seed and top-p/temperature controls),
- selected huggingface environment keys for model loading behavior.

This has two practical impacts:

- subrun behavior becomes more predictable because only explicit variables survive propagation,
- deterministic replay issues become easier to triage because environment influence is narrowed and enumerated.

---

### Cross-Version Compatibility Posture (v18 + v19)

A notable strength of this period is compatibility staging rather than abrupt replacement.

Compatibility characteristics now present:

- v18 verifier can validate expanded descriptor paths while still handling legacy descriptor shape;
- v19 verifier builds on v18 verifier call and then adds policy/proof validation;
- v19 coordinator remains import-compatible via wrapper exports while behavior is delegated to microkernel;
- schema packs support v2 richer policy fields without removing v1 compatibility in all runtime entry contexts;
- market and policy verifiers maintain explicit deterministic checks to prevent silent cross-version drift.

This compatibility strategy reduces migration risk while still enabling a substantial runtime architecture change.

---

### Audit Closing Notes for This Addendum

This update should be read as a contract-hardening phase, not only a feature phase.

From a source-of-truth perspective, the essential facts now true in code are:

- deterministic execution semantics are centered and explicit;
- policy artifacts and proof artifacts are integrated into canonical state and verifier paths;
- hash pinning and cross-artifact binding checks are much stricter;
- LLM/mutator execution paths are substantially more resilient to malformed outputs while preserving fail-closed replay discipline;
- tests now directly assert perturbation-resistance and tamper detection in the critical policy/proof pipeline.

These are durable architecture facts reflected in runtime and verifier implementation, not only in configuration or documentation surfaces.


---

# Appendix N: 2026-02-20 Delta Ledger, Capability Census, and Final-Run Readiness

This appendix is an evidence-bound extension focused on the latest architectural state as of **February 20, 2026**. It documents what changed today, what those changes mean in control-theoretic and trust-boundary terms, what capability generation mechanisms now exist, what capabilities are active versus latent, and what still blocks truly durable autonomous operation.

The purpose is not to restate prior layers. The purpose is to give a precise closeout ledger for the final stretch: which mechanisms are now real, which are merely designed, which are proven in artifacts, which still rely on assumptions, and which constraints remain hard constitutional boundaries.

This section uses repository evidence from:

- same-day commit history,
- current tracked code under `meta-core/`, `orchestrator/`, `CDEL-v2/`, `Genesis/schema/`, `tools/`, `campaigns/`, and `polymath/`,
- generated evidence artifacts in `runs/`.

It is intentionally explicit about concrete file paths, ids, and measured values.

---

## J.1 Evidence Boundary and Method

### J.1.1 Date boundary and commit set

The repository now includes a dense sequence of same-day commits on **2026-02-20**. The key progression, in order, is:

1. `c73b4c7` (08:44): Source-of-truth docs extension.
2. `d14d946` (10:13): Phase 3 scoring and rollback lineage hardening.
3. `10ace95` (17:06): deterministic hardening + Phase 3b lifecycle + Phase 4 Winterfell STARK integration.
4. `dfbe6f4` (18:07): Phase4A bootstrap/microkernel SIP ingestion alignment.
5. `a62f720` + merge `bceac1e` (18:49): additional source-of-truth append and merge.
6. `14e32e8` (21:29): Phase4C real swap drill with failpointed regime upgrade.
7. `9df315f` (21:36): commits the Phase3b/Phase4B/Phase4C worktree delta into tracked history.

This matters because the architecture is no longer in a partially staged local state. The previously uncommitted shadow/transpiler/regime-upgrade surfaces are now first-class tracked code.

### J.1.2 Scope of direct inspection for this appendix

Directly re-inspected for this addendum:

- `meta-core/engine/{constants.py,activation.py,audit.py,ledger.py,regime_upgrade.py}`
- `scripts/run_phase4c_real_swap_drill_v1.py`
- `orchestrator/omega_v19_0/{coordinator_v1.py,microkernel_v1.py}`
- `orchestrator/native/{native_router_v1.py,wasm_shadow_soak_v1.py}`
- `CDEL-v2/cdel/v18_0/{omega_promoter_v1.py,omega_activator_v1.py,verify_rsi_omega_daemon_v1.py,campaign_rsi_knowledge_transpiler_v1.py,verify_rsi_knowledge_transpiler_v1.py}`
- `CDEL-v2/cdel/v19_0/{verify_rsi_omega_daemon_v1.py,shadow_airlock_v1.py,shadow_fs_guard_v1.py,shadow_runner_v1.py,shadow_j_eval_v1.py,conservatism_v1.py,determinism_witness_v1.py}`
- `tools/polymath/polymath_knowledge_transpiler_v1.py`
- `orchestrator/omega_v18_0/io_v1.py`
- `scripts/generate_phase3b_phase4_evidence_v1.py`
- `scripts/generate_phase4_audit_bundle_v1.py`
- phase4 campaign packs and capability registries.

### J.1.3 Current size/census context (repo-level)

Current filesystem census from the working tree:

- `tools/`: 332 files
- `polymath/`: 83 files
- `campaigns/`: 1095 files
- `orchestrator/`: 130 files
- `CDEL-v2/`: 12691 files
- `Genesis/schema/`: 702 schema files

These counts are not rhetorical. They indicate that closeout governance must rely on deterministic contracts, not human memory, because the surface area now exceeds what manual reasoning alone can safely hold.

---

## J.2 What Changed Today: Practical Delta by Layer

### J.2.1 RE1 (`meta-core`) changed from commit-only to regime-upgrade aware

Today introduces a concrete RE1 primitive for controlled regime transitions:

- `meta-core/engine/regime_upgrade.py` adds `commit_staged_regime_upgrade(...)`.
- `meta-core/engine/constants.py` adds `ACTIVE_NEXT_BUNDLE_FILENAME` and failpoint `FAILPOINT_AFTER_NEXT_WRITE`.
- `meta-core/engine/activation.py` writes/updates `ACTIVE_NEXT_BUNDLE` in both commit and rollback paths.
- `meta-core/engine/audit.py` now validates and reports `active_next_bundle_hash` coherence.
- `meta-core/engine/ledger.py` adds `make_regime_upgrade_entry(...)` with action `REGIME_UPGRADE`.

This is a conceptual shift: RE1 previously adjudicated ordinary bundle activation. It now has explicit, auditable semantics for shadow-gated regime swap transitions.

### J.2.2 RE2 (`CDEL-v2`) gained three connected new verification frontiers

1. **Policy/STARK frontier** (from `10ace95`):
   - policy VM proof emit/verify path,
   - Winterfell backend contract integration,
   - richer v19 verifier surfaces.

2. **Native transpiler frontier** (from `9df315f`):
   - `verify_rsi_knowledge_transpiler_v1.py` introduced,
   - v18 daemon verifier expanded for native shadow-registry and shadow-soak integrity checks,
   - activation/promoter schema contracts expanded.

3. **Shadow regime frontier** (from `9df315f` + `14e32e8`):
   - new v19 modules: `shadow_airlock_v1.py`, `shadow_fs_guard_v1.py`, `shadow_runner_v1.py`, `shadow_j_eval_v1.py`, `conservatism_v1.py`, `determinism_witness_v1.py`,
   - v19 daemon verifier hard-checks tier counts and readiness consistency,
   - v19 pack schema extended for shadow profile plumbing.

### J.2.3 RE3 (`tools/` + campaign executors) gained a deterministic capability generator

`tools/polymath/polymath_knowledge_transpiler_v1.py` and campaign wrapper `campaign_rsi_knowledge_transpiler_v1.py` together create an end-to-end deterministic path:

- knowledge artifact hash + kernel spec -> restricted IR -> deterministic Rust crate -> reproducible wasm build -> runtime contract -> vectorized healthcheck -> promotion bundle.

That is a genuine capability-generation primitive, not a mere static tool.

### J.2.4 RE4 (`Genesis/schema`) significantly widened contractual coverage

New schema families added for:

- native transpiler artifacts,
- shadow registry and shadow soak receipts,
- shadow regime proposal/readiness/tier/profile artifacts,
- phase4 audit bundle.

This matters because these newly added contracts now anchor verifier behavior. Without schema anchoring, these features would remain operational conventions.

---

## J.3 Phase 4A, 4B, 4C: Unified Through-Line

A useful way to understand today’s state is to treat Phase4A, 4B, and 4C as one pipeline, not three unrelated branches.

### J.3.1 Phase4A: deterministic ingestion of external knowledge into hash-bound state

Phase4A introduced SIP ingestion campaign/runtime/verifier surfaces:

- `CDEL-v2/cdel/v18_0/polymath_sip_ingestion_l0_v1.py`
- `CDEL-v2/cdel/v18_0/campaign_polymath_sip_ingestion_l0_v1.py`
- `CDEL-v2/cdel/v18_0/verify_rsi_polymath_sip_ingestion_l0_v1.py`
- pack `campaigns/rsi_omega_daemon_v19_0_phase4a_sip_ingestion/...`

The key effect: knowledge ingress is no longer a side utility; it is a dispatchable capability (`RSI_POLYMATH_SIP_INGESTION_L0`) with deterministic receipts.

### J.3.2 Phase4B: deterministic transpilation of that knowledge into constrained native kernels

Phase4B adds:

- tool: `tools/polymath/polymath_knowledge_transpiler_v1.py`
- campaign executor: `CDEL-v2/cdel/v18_0/campaign_rsi_knowledge_transpiler_v1.py`
- verifier: `CDEL-v2/cdel/v18_0/verify_rsi_knowledge_transpiler_v1.py`
- pack family: `campaigns/rsi_knowledge_transpiler_v1/` and `campaigns/rsi_omega_daemon_v19_0_phase4b_native_transpiler_v1/`

The effect: the system can transform a hash-pinned knowledge artifact into a reproducible wasm kernel candidate with explicit runtime contract and health proofs.

### J.3.3 Phase4C: shadow-gated regime upgrade from observation to potential swap

Phase4C adds:

- shadow tier checks and readiness receipts,
- RE1 regime-upgrade commit primitive with failpoint coverage,
- drill script proving stage->verify->canary->failpoint->live commit->rollback cycle.

The effect: there is now an explicit path from generated capability to shadow evidence to RE1-governed swap mechanics.

### J.3.4 Why this sequence matters

This sequence is the minimal full loop for autonomous scaling under constitutional guardrails:

1. ingest new knowledge,
2. compile constrained capability forms,
3. test in shadow,
4. only then bind into active regime transitions.

Without this sequence, autonomous scaling remains mostly text/config mutation. With it, the architecture begins to support deterministic extension of executable capability while preserving fail-closed gates.

---

## J.4 Phase4B Deep Dive: Deterministic Knowledge Transpiler

### J.4.1 Campaign interface and fixed intent

`campaign_rsi_knowledge_transpiler_v1.py` explicitly states its intent: consume SIP-linked knowledge + kernel spec, output deterministic wasm-native promotion bundle for **SHADOW installation**.

The emitted promotion bundle schema is `omega_promotion_bundle_native_transpiler_v1_1`, with `install_intent: "STATUS_SHADOW"`.

This is crucial: installation intent is shadow-first by design, not direct live activation.

### J.4.2 Input contract and pinning

Pack `campaigns/rsi_knowledge_transpiler_v1/rsi_knowledge_transpiler_pack_v1.json` binds:

- `sip_knowledge_artifact_hash`
- `sip_empirical_evidence_hash`
- `kernel_spec_rel`
- `rust_toolchain_manifest_rel`
- `wasmtime_manifest_rel`

The pack uses concrete, pinned toolchain manifests:

- `toolchain_manifest_rust_v1.json`
- `toolchain_manifest_wasmtime_v1.json`

Notably, the wasmtime manifest records determinism flags requiring:

- `disable_cache: true`
- `consume_fuel: true`

and pins runtime identity via `wasmtime_sha256` and version string.

### J.4.3 Restricted IR generation path

`polymath_knowledge_transpiler_v1.py` creates `polymath_restricted_ir_v1` with deterministic content:

- fixed numeric mode: Q32 fixed-point,
- explicit operation list over ARG/CONST/MUL_Q32/ADD_I64/RET,
- IR id computed as canonical hash of payload without id field.

This IR is not arbitrary code; it is a constrained representation deliberately limiting expressive surface.

### J.4.4 Forbidden nondeterminism scans

Two scanners enforce fail-closed token policies:

1. IR scan (`_scan_ir_for_forbidden`) checks serialized IR for disallowed tokens such as `f32`, `f64`, `rand`, `clock_gettime`, `getrandom`.
2. Rust scan (`_scan_rust_for_forbidden`) scans generated crate source for deterministic-policy violations including filesystem/time/net/random APIs.

On violation, the transpiler emits `candidate_syntax_error_v1` and exits without promotion bundle generation.

This pattern matters: it preserves evidence (error artifact) while refusing unsafe progression.

### J.4.5 Source merkle and runtime contract artifacts

Phase4B writes:

- `native_src_merkle_v1` with per-file hashes and `source_merkle_root`,
- `native_wasm_runtime_contract_v1` derived from runtime manifest,
- both with hash-based ids.

These are bridge artifacts between code generation and runtime execution semantics. They prevent a silent drift between "what got generated" and "what runtime contract was assumed".

### J.4.6 Reproducible build proof semantics

`_build_twice_repro(...)` performs two independent builds in separate temp trees with path remapping and deterministic flags. It requires binary hash equality.

On mismatch, transpiler emits `nonrepro_build_v1` with both binary hashes and fails closed.

On success, it emits `native_build_proof_v1` binding:

- toolchain hash,
- source merkle,
- runtime contract hash,
- output binary hash,
- reproducibility booleans.

### J.4.7 Healthcheck vectors and receipt path

The tool builds deterministic vectors in `native_wasm_healthcheck_vectors_v1` and executes the produced wasm using the contract-defined runtime invocation template. It emits `native_wasm_healthcheck_receipt_v1` with per-case expected vs actual hash and overall result.

Only PASS healthcheck results are eligible for promotion bundle emission.

### J.4.8 Campaign output contract

The campaign wrapper emits `omega_promotion_bundle_native_transpiler_v1_1` with required cross-links:

- `restricted_ir_hash`
- `source_merkle_hash`
- `build_proof_hash`
- `runtime_contract_hash`
- `healthcheck_vectors_hash`
- `healthcheck_receipt_hash`
- `native_binary_hash`
- SIP evidence hashes

This bundle is structured so downstream promoter/activator/verifier can assert full consistency across all intermediate artifacts.

### J.4.9 Verifier obligations

`verify_rsi_knowledge_transpiler_v1.py` re-validates entire chain:

- checks no syntax-error/nonrepro error artifacts are present,
- verifies hash-bound loading of IR/merkle/build/runtime/vectors/health artifacts,
- verifies crate source hash rows bind to actual crate files,
- re-scans forbidden Rust tokens,
- rebuilds deterministically and requires rebuilt hash equals emitted binary hash,
- verifies runtime binary pin and determinism flags,
- re-runs healthcheck vectors via runtime invocation,
- verifies bundle `native_module` hash cross-links.

This is a strong replay posture for generated native capability.

### J.4.10 Promoter + activator integration

Today’s v18 promoter/activator changes thread new hashes through activation binding and receipt, and install/maintain `native_shadow_registry_v1` in daemon state. These hashes are later checked in the v18 daemon verifier path.

The path from candidate generation to activation evidence is now continuous and hash-bound.

---

## J.5 Native Shadow Runtime: Router Behavior and Route-Disable Semantics

### J.5.1 Router now consumes daemon context from environment

`orchestrator/native/native_router_v1.py` introduces:

- `OMEGA_DAEMON_STATE_ROOT`
- `OMEGA_TICK_U64`

This is nontrivial: it lets runtime routing decisions and disable transitions be bound to current daemon state and tick chronology.

### J.5.2 Active shadow registry pointer model

Router reads `native/shadow/ACTIVE_SHADOW_REGISTRY`, resolves hash-named `native_shadow_registry_v1` payload, verifies canonical hash match, and fails closed on integrity mismatch.

This parallels meta-core pointer semantics at a native-route level.

### J.5.3 SHADOW mode semantics are conservative

In `verification_mode == SHADOW`:

- Python implementation remains authoritative return value,
- native call is dual-run comparison path only,
- load/invoke/mismatch errors disable both normal native path and shadow route,
- mismatch reports are persisted with route-disable transition metadata.

This ensures that native acceleration does not silently become decision-authoritative before parity is demonstrated.

### J.5.4 Per-route disable is explicit state

Registry rows now maintain:

- `disabled_key`
- `shadow_route_disabled_b`
- `shadow_route_disable_reason`
- `shadow_route_disable_tick_u64`

Verifier logic requires these fields be coherent (disabled implies non-null reason/tick; enabled implies null reason/tick).

### J.5.5 Shadow soak artifacts added to tick ledger

`orchestrator/native/wasm_shadow_soak_v1.py` emits:

- `native_wasm_shadow_soak_summary_v1`
- `native_wasm_shadow_soak_receipt_v1`

Microkernel emits corresponding ledger events:

- `NATIVE_WASM_SHADOW_SOAK_SUMMARY`
- `NATIVE_WASM_SHADOW_SOAK_RECEIPT`

The summary computes readiness from module count, portability status, and route-disabled count, with reasons such as `NO_SHADOW_MODULE`, `PORTABILITY_SKIP_RUN`, `SHADOW_ROUTE_DISABLED`.

---

## J.6 Phase4C Shadow-Airlock and RE1 Regime Upgrade

### J.6.1 Shadow profile loading and pin matching in microkernel

`microkernel_v1.py` now loads shadow profile payloads referenced by pack relpaths:

- proposal,
- evaluation tiers,
- protected roots profile,
- corpus descriptor,
- determinism witness profile,
- J-comparison profile.

It enforces id matching between proposal fields and loaded profile ids using fail-closed `PIN_HASH_MISMATCH` semantics.

This prevents silent profile substitution.

### J.6.2 Integrity guard model

`shadow_fs_guard_v1.py` hashes protected roots with:

- scoped include roots,
- exclude roots,
- symlink policy (`FAIL_CLOSED`),
- explicit hash budgets (`max_files`, `max_bytes_read`, `max_steps`).

Exhausting any budget yields `SHADOW_HASH_BUDGET_EXHAUSTED`.

It generates `shadow_fs_integrity_report_v1` status PASS/FAIL based on mutation and reason codes.

### J.6.3 Runner model and outbox-only write discipline

`shadow_runner_v1.py` enforces outbox-only writes and explicitly forbids writes under `.omega_cache` in shadow mode. It compares dynamic protected-root hashes pre/post and yields reason codes including:

- `SHADOW_RUNNER_FAILED`
- `SHADOW_PROTECTED_ROOT_MUTATION`

### J.6.4 Tier evaluation model

Microkernel synthesizes tier receipts using:

- reject-conservatism check (`conservatism_v1.py`),
- determinism witness (`determinism_witness_v1.py`),
- J window/per-tick checks (`shadow_j_eval_v1.py`).

Generated artifacts:

- `shadow/tier_a/*.shadow_tier_receipt_v1.json`
- `shadow/tier_b/*.shadow_tier_receipt_v1.json`
- `shadow/readiness/*.shadow_regime_readiness_receipt_v1.json`

### J.6.5 Readiness receipt semantics

`shadow_airlock_v1.py` returns verdict READY/NOT_READY and reason set. It encodes a comprehensive boolean matrix including:

- outbox-only verification,
- integrity and protected-root verification,
- J-window/J-floor/non-weakening checks,
- corpus replay,
- deterministic fuzz,
- tier A/B pass,
- rollback-plan bound,
- auto-swap state.

### J.6.6 Auto-swap gating semantics

When `auto_swap_b` is true, microkernel requires:

- handoff receipt relpath present,
- handoff receipt validates as readiness schema,
- handoff `runtime_tier_b_pass_b == true`,
- handoff verdict READY,
- proposal id matches,
- runtime tier-B pass in current readiness.

Otherwise fail with `TIER_B_REQUIRED_FOR_SWAP`.

### J.6.7 RE1 upgrade primitive behavior

`commit_staged_regime_upgrade(...)` in RE1:

- loads readiness receipt,
- validates schema name/version,
- enforces tier booleans,
- writes `ACTIVE_NEXT_BUNDLE`,
- optionally triggers failpoint `AFTER_NEXT_WRITE`,
- calls normal `commit_staged(...)`,
- appends `REGIME_UPGRADE` ledger entry with readiness hash and tier booleans,
- returns commit out + `regime_upgrade_b: true` + `reason_code: READY`.

This is the first explicit RE1 primitive tied to shadow readiness semantics.

### J.6.8 Drill evidence

`runs/phase4c_real_swap_drill_v1/drill_20260220T112240Z/PHASE4C_REAL_SWAP_DRILL_SUMMARY_v1.json` shows:

- shadow tier A pass: true,
- shadow tier B pass: true,
- readiness verdict: READY,
- integrity status: PASS,
- failpoint-after-next-write path returns internal error and audit INVALID,
- live commit path returns committed with `regime_upgrade_b: true`,
- post-swap self-check tick returncode: 0,
- rollback returns success,
- post-rollback self-check tick returncode: 0.

This artifact is significant because it demonstrates both failure-path and success-path behavior under controlled exercise.

---

## J.7 Microkernel Centerline: Policy, Proof, Native, Shadow in One Tick

### J.7.1 Coordinator wrapper migration

`orchestrator/omega_v19_0/coordinator_v1.py` is now a compatibility wrapper that delegates to `microkernel_v1.tick_once(...)`.

Architecturally, this formalizes microkernel as runtime centerline while preserving import compatibility.

### J.7.2 Policy artifact chain remains hash-bound

Microkernel emits and chains policy artifacts (`inputs`, `traces`, `hints`, `merged_hints`, `proposals`, `selection`, `counterfactual`, `proofs`) and records them in ledger events.

This preserves replay verification despite expanded policy complexity.

### J.7.3 Proof telemetry expansion

Snapshot fields now include:

- `policy_vm_proof_runtime_status`
- `policy_vm_proof_runtime_reason_code`
- `policy_vm_proof_fallback_reason_code`
- `policy_vm_prove_time_ms`
- `policy_vm_proof_size_bytes`

This is operationally useful: it gives the observation layer and external diagnostics first-class visibility into proof runtime behavior, not only pass/fail.

### J.7.4 Shadow signals become first-class ledger events

Microkernel now emits:

- `SHADOW_FS_INTEGRITY`
- `SHADOW_TIER_A`
- `SHADOW_TIER_B`
- `SHADOW_READINESS`

and includes corresponding hashes in snapshot payload. This is critical for replay-based governance; shadow status is no longer side-channel data.

### J.7.5 v19 verifier hard checks for tier counts

`CDEL-v2/cdel/v19_0/verify_rsi_omega_daemon_v1.py` currently hard-checks tier counters:

- Tier A: `n_live_ticks == 250`, `n_fuzz_cases == 512`, `n_double_runs == 50`
- Tier B: `n_live_ticks == 1000`, `n_fuzz_cases == 20000`, `n_double_runs == 1000`

This is strict and conservative. It also means profile evolution requires coordinated verifier/schema strategy.

### J.7.6 Proof-fallback consistency got stricter

Verifier now rejects inconsistent combinations such as:

- proof hash present while runtime status ABSENT/FAILED,
- runtime status EMITTED with no proof hash,
- fallback reason populated when runtime status EMITTED,
- proof fallback path missing ledger event when proof enabled and runtime failed/absent.

This closes loopholes where runtime proof behavior might have been ambiguously represented.

---

## J.8 Capability Census: Active, Latent, and Experimental

### J.8.1 Capability registry spread

Across all daemon capability registries (`campaigns/**/omega_capability_registry*.json`):

- registry files: 16
- unique capability ids observed: 34
- campaign ids in capability registries: 34
- distinct verifier modules referenced: 17
- distinct orchestrator modules referenced: 33

### J.8.2 Capability id universe (observed)

Representative unique capability ids include:

- core SAS line: `RSI_SAS_CODE`, `RSI_SAS_METASEARCH`, `RSI_SAS_VAL`, `RSI_SAS_SCIENCE`, `RSI_SAS_SYSTEM`, `RSI_SAS_KERNEL`
- polymath line: `RSI_POLYMATH_SCOUT`, `RSI_POLYMATH_BOOTSTRAP_DOMAIN`, `RSI_POLYMATH_CONQUER_DOMAIN`, `RSI_POLYMATH_SIP_INGESTION_L0`
- self-improvement line: `RSI_GE_SH1_OPTIMIZER`, `RSI_OMEGA_SELF_OPTIMIZE_CORE`, mutators
- native line: `RSI_OMEGA_NATIVE_MODULE`, `RSI_KNOWLEDGE_TRANSPILER`
- skill line: multiple `RSI_OMEGA_SKILL_*`
- EUDRS-U line: `RSI_EUDRS_U_TRAIN`, `RSI_EUDRS_U_ONTOLOGY_UPDATE`, `RSI_EUDRS_U_INDEX_REBUILD`, `RSI_EUDRS_U_EVAL_CAC`

### J.8.3 Super-unified pack stance

In `campaigns/rsi_omega_daemon_v19_0_super_unified/omega_capability_registry_v2.json`:

- total capabilities: 25
- enabled capabilities: 9

Enabled set (observed) includes:

- `RSI_POLYMATH_BOOTSTRAP_DOMAIN`
- `RSI_POLYMATH_CONQUER_DOMAIN`
- `RSI_POLYMATH_SCOUT`
- `RSI_SAS_CODE`
- `RSI_SAS_METASEARCH`
- `RSI_SAS_VAL`
- `RSI_GE_SH1_OPTIMIZER`
- `RSI_EUDRS_U_TRAIN`
- `RSI_SAS_SCIENCE`

Risk-class distribution in this registry is balanced by count:

- LOW: 12
- MED: 12
- HIGH: 1

### J.8.4 Phase4B native-transpiler pack stance

In `campaigns/rsi_omega_daemon_v19_0_phase4b_native_transpiler_v1/omega_capability_registry_v2.json`:

- total capabilities: 25
- enabled capabilities: 4

Enabled set:

- `RSI_KNOWLEDGE_TRANSPILER`
- `RSI_SAS_CODE`
- `RSI_SAS_METASEARCH`
- `RSI_SAS_VAL`

Goal queue in same pack seeds:

- `goal_native_transpiler_shadow_001` with capability `RSI_KNOWLEDGE_TRANSPILER`.

This indicates a deliberately narrowed operational profile for native-transpiler shakedown.

### J.8.5 Goal queue coverage across packs

`campaigns/**/goals/omega_goal_queue_v1.json` files observed: 17.

Unique capability ids referenced by goals: 15.

That list includes the new ingestion/transpiler/native lines and legacy SAS lines. It demonstrates that the goal system already treats these capabilities as dispatchable objectives, not just optional scripts.

### J.8.6 Practical interpretation

Capabilities are not one monolith. There are at least three capability bands:

1. **always-useful baseline** (SAS code/search/val),
2. **frontier expansion** (SH1, polymath conquest, EUDRS-U),
3. **infrastructure transition** (native module + knowledge transpiler + shadow regime).

The closeout challenge is managing transitions between these bands without violating deterministic replay or constitutional invariants.

---

## J.9 Tooling Census: What Exists Today and Why It Matters

### J.9.1 Top-level tool distribution

`tools/` top-level file counts show concentration in these domains:

- `tools/omega`: largest operational tooling surface,
- `tools/genesis_engine`: proposer and learning heuristics,
- `tools/polymath`: domain/knowledge tooling,
- `tools/mission_control` + `tools/omega_mission_control`: operational UIs/control plane,
- `tools/v19_runs` and `tools/v19_smoke`: orchestrated evidence/smoke workflows,
- `tools/vision`: perception utility layer,
- `tools/authority`: trust anchor tooling.

### J.9.2 `tools/omega` role in the final stretch

Representative modules include:

- benchmark suites (`omega_benchmark_suite_v1.py`, `omega_benchmark_suite_v19_v1.py`),
- native tooling (`native_benchmark_v1.py`, `native_healthcheck_v1.py`, `rust_codegen_v1.py`, `rust_build_repro_v1.py`),
- replay/verification helpers (`omega_replay_bundle_v1.py`, `omega_verifier_client_v1.py`),
- run aggregation (`omega_timings_aggregate_v1.py`),
- survival/hardening runners.

This tool family is the bridge between raw runtime and operational confidence. It is where day-2 observability and evidence extraction live.

### J.9.3 `tools/genesis_engine` remains primary text/config proposer engine

Key scripts:

- `ge_symbiotic_optimizer_v0_3.py` (active SH-1),
- `sh1_pd_v1.py`, `sh1_xs_v1.py`, `sh1_behavior_sig_v1.py` (receipt analytics),
- auditing/tests enforcing deterministic and anti-novelty-laundering behavior.

Even with native-transpiler additions, SH-1 remains core for broad config/code evolution in allowed paths.

### J.9.4 `tools/polymath` is now both discovery and capability-compilation layer

Current scripts include:

- scouting/bootstrap/conquest lifecycle (`polymath_scout_v1.py`, `polymath_domain_bootstrap_v1.py`, `polymath_domain_corpus_v1.py`),
- source and websearch connectors (`polymath_sources_v1.py`, `polymath_websearch_v1.py`),
- goal conversion (`polymath_void_to_goals_v1.py`),
- refinement/proposal utilities (`polymath_refinery_proposer_v1.py`),
- new transpiler (`polymath_knowledge_transpiler_v1.py`).

This is important: Polymath is no longer purely epistemic/discovery. It now directly participates in executable capability synthesis.

### J.9.5 `tools/v19_runs` and `scripts/` provide evidence production pipelines

Recent same-day evidence scripts:

- `scripts/generate_phase3b_phase4_evidence_v1.py`
- `scripts/generate_phase4_audit_bundle_v1.py`
- `scripts/run_phase4c_real_swap_drill_v1.py`

These scripts convert system behavior into structured artifacts suitable for replay governance and promotion review.

---

## J.10 Polymath State and Capability Generation Readiness

### J.10.1 Current local registry state

`polymath/registry/polymath_domain_registry_v1.json` currently indicates a minimal local seeded state:

- schema: `polymath_domain_registry_v1`
- total domains: 1
- ready-for-conquer: 1
- conquered: 0
- sample domain id: `pubchem_weight300`

`polymath_void_report_v1.jsonl` is empty in this snapshot.

This means local registry content in this repository is a seed/fixture baseline, not proof of broad in-repo conquered-domain inventory.

### J.10.2 EUDRS-U polymath registry footprint

`polymath/registry/eudrs_u/` contains many content-addressed artifacts:

- capsules,
- certs,
- manifests,
- memory pages/tables,
- vision sessions/frames/reports/tracks,
- qxwmr states.

This demonstrates that even if top-level polymath domain registry is sparse locally, deeper subsystem artifact stores are populated and hash-addressed.

### J.10.3 Phase4A SIP ingestion capability status

`campaigns/rsi_omega_daemon_v19_0_phase4a_sip_ingestion/omega_capability_registry_v2.json` enables:

- `RSI_POLYMATH_SIP_INGESTION_L0` -> campaign `rsi_polymath_sip_ingestion_l0_v1`

Goal queue for that pack has pending ingestion goal.

This makes SIP ingestion a first-class capability stage in the daemon objective pipeline.

### J.10.4 Polymath-to-native synthesis bridge

With Phase4B, Polymath now links into native generation via:

- SIP knowledge hash input,
- kernel spec -> restricted IR,
- deterministic transpilation and reproducible build,
- runtime contract and healthcheck receipts,
- promotion bundle with shadow install intent.

This is effectively a new synthesis arc:

`Knowledge Artifact -> Deterministic IR -> Native Candidate -> Shadow Registry -> Shadow Soak -> Regime Readiness`.

### J.10.5 What still needs to mature in polymath closeout terms

For full autonomous scale, polymath needs sustained high-volume dataflow beyond seed fixtures, with strict retention of:

- provenance hashes,
- leakage controls,
- deterministic transforms,
- quality gates from conquest metrics back to decider/objectives.

The architecture now supports this, but proof of long-horizon stability depends on running campaigns, not only code presence.

---

## J.11 Policy VM + STARK Integration State

### J.11.1 New policy proof infrastructure

From `10ace95`, v19 includes:

- `policy_vm_stark_runner_v1.py`
- Winterfell backend contract artifacts under `CDEL-v2/cdel/v19_0/rust/`
- verifier modules for program/opcode/trace/proposal/selection/proof assets.

### J.11.2 Evidence artifact metrics

`runs/PHASE3B_PHASE4_EVIDENCE_v1.json` reports:

- canary aggregate: eligible ticks 20, fast-path ticks 20, fallback ticks 0,
- fast-path rate: 1.0,
- fallback rate: 0.0.

Profile specifics:

- `POLICY_VM_AIR_PROFILE_96_V1`: p95 prove 272ms, p95 verify 236ms, max proof size 13071 bytes.
- `POLICY_VM_AIR_PROFILE_128_V1`: p95 prove 273ms, p95 verify 243ms, max proof size 15507 bytes.

All listed gates in these profile summaries are marked pass.

### J.11.3 Tamper behavior observed in evidence

The same evidence file includes a proof tamper experiment where proof bytes are modified and unit verdict changes to invalid while daemon verdict remains valid under fallback acceptance path.

This confirms fallback path design intent, but also indicates the importance of strict fallback reason/reporting consistency for interpretability.

### J.11.4 Known detail to watch

In that evidence artifact, `phase4_proof_fallback.proof_fallback_reason_code` appears as string `"None"` while runtime status is `EMITTED`. Current stricter verifier semantics reject emitted+fallback-reason combinations. This likely reflects artifact/version timing mismatch and is a concrete audit item to normalize.

---

## J.12 RE1 Audit/Pointer Semantics After Phase4C

### J.12.1 ACTIVE_NEXT_BUNDLE as explicit second pointer

Previously, active/prev pointers carried commit lineage. With today’s changes, `ACTIVE_NEXT_BUNDLE` is now written in commit and rollback paths and validated in audit.

Net effect:

- explicit indication of currently intended next active state,
- improved crash/failpoint introspection in regime-upgrade flows,
- tighter audit consistency checks.

### J.12.2 Regime-upgrade ledger entry semantics

`make_regime_upgrade_entry(...)` records:

- active bundle hash,
- readiness receipt hash,
- `tier_a_pass_b`, `tier_b_pass_b`, `runtime_tier_b_pass_b`,
- chain link via `prev_entry_hash`.

This is critical for postmortem traceability: swap-relevant governance evidence is now permanently encoded in RE1 ledger, not only in daemon-side artifacts.

### J.12.3 Drill confirms failpoint behavior under audit

Phase4C drill explicitly injects failpoint `AFTER_NEXT_WRITE` and captures:

- commit output internal error,
- audit invalid state,
- then successful live commit and valid audit,
- then successful rollback and valid audit.

This is high-value because it validates that failure-paths are observable and recoverable, not silent corruption.

---

## J.13 Schema Surface Expansion and Contract Maturity

### J.13.1 New v18 schema families (native transpiler/shadow soak)

Now present in `Genesis/schema/v18_0/`:

- `polymath_restricted_ir_v1`
- `native_src_merkle_v1`
- `native_build_proof_v1`
- `native_wasm_runtime_contract_v1`
- `native_wasm_healthcheck_vectors_v1`
- `native_wasm_healthcheck_receipt_v1`
- `candidate_syntax_error_v1`
- `nonrepro_build_v1`
- `native_shadow_registry_v1`
- `native_wasm_shadow_soak_summary_v1`
- `native_wasm_shadow_soak_receipt_v1`
- `omega_promotion_bundle_native_transpiler_v1_1`
- `phase4_audit_bundle_v1`

### J.13.2 v18 existing schema updates

Updated contracts include:

- `omega_activation_binding_v1`
- `omega_activation_receipt_v1`
- `omega_promotion_receipt_v1`
- `omega_tick_snapshot_v1`

These updates thread new native/shadow/proof identifiers into canonical tick evidence.

### J.13.3 New v19 shadow schema families

Now present in `Genesis/schema/v19_0/`:

- `shadow_regime_proposal_v1`
- `shadow_regime_readiness_receipt_v1`
- `shadow_evaluation_tiers_v1`
- `shadow_protected_roots_profile_v1`
- `shadow_fs_integrity_report_v1`
- `corpus_descriptor_v1`
- `j_comparison_v1`
- `witnessed_determinism_profile_v1`

### J.13.4 Pack schema v2 now carries shadow+auto-swap contract

`Genesis/schema/v19_0/rsi_omega_daemon_pack_v2.jsonschema` and its v18 counterpart now include shadow relpath fields and `auto_swap_b`, with conditional requirements:

- if shadow proposal used, tier/profile relpaths are required,
- if `auto_swap_b == true`, additional handoff/tier artifacts become required.

This is major: shadow governance has moved from convention into formal campaign-pack contract.

---

## J.14 Capability Generation vs Capability Activation: Exact Current Position

A recurring confusion in autonomous-system discussions is conflating generation with activation. The repository now clearly separates these layers.

### J.14.1 Generation mechanisms now present

- Text/config generation: SH-1, mutators, SAS line.
- Knowledge ingestion generation: SIP ingestion.
- Executable kernel generation: knowledge transpiler to wasm.
- Policy/proof generation: policy VM trace/proof path.

### J.14.2 Activation mechanisms now present

- Standard promotion/activation (existing Omega path).
- Native shadow registry install for transpiler outputs.
- RE1 regime-upgrade commit primitive tied to readiness receipts.

### J.14.3 Why this separation is healthy

Generation can be aggressive if activation remains conservative. This codebase now reflects that doctrine structurally:

- transpiler outputs default to shadow status,
- shadow mismatch disables native route,
- auto swap requires tier-B runtime pass and handoff receipts,
- RE1 checks readiness before regime upgrade commit.

This is exactly the pattern needed for long-run autonomous expansion under strict safety constraints.

---

## J.15 Legacy and Older Surfaces That Still Matter in the Final Stretch

The request was explicit about old/legacy coverage. Several older surfaces remain strategically relevant.

### J.15.1 SAS line remains execution backbone

Even with v19 policy microkernel and native additions, the enabled production baseline in multiple packs still centers on:

- SAS code,
- SAS metasearch,
- SAS val,
- optionally SAS science/system/kernel.

These are proven operationally and serve as capability floor when frontier experiments are disabled or gated.

### J.15.2 SH-1 remains meta-learning proposer backbone

SH-1 is still the only mature receipt-driven code/config mutation engine with hard-avoid and PD/XS feedback. It remains essential for continuous adaptation across broad allowed surfaces.

### J.15.3 Bid-market and market-mutator lines are still useful stress tools

Even toy/phase campaign lines (`bid market toy`, mutators, death tests) remain valuable for adversarial and governance stress, particularly while integrating new proof/native/shadow pathways.

### J.15.4 Phase0 survival/immune lines remain necessary

As architecture nears autonomous operation, retaining explicit adversarial and survival drill campaigns is not optional; it is part of preserving immune competence under evolving runtime complexity.

### J.15.5 Older verifier versions remain constitutional memory

The v1..v19 accumulator remains critical for replay legitimacy across history. Legacy verifiers are not dead weight; they are required for historical chain auditability.

---

## J.16 Tool and Folder Audit Through the "Final Stretch" Lens

This subsection reframes folders by closeout role, rather than by implementation ownership.

### J.16.1 `authority/`: immutability anchor and benchmark sovereignty

Still the highest-leverage safety directory.

Closeout priority:

- keep evaluation kernels and allowlists pinned and auditable,
- avoid proposal pathways that can indirectly erode benchmark integrity,
- ensure campaign additions do not bypass authority pin checks.

### J.16.2 `meta-core/`: state lineage and swap legality

Now with regime-upgrade support, RE1 closeout must focus on:

- crash consistency under failpoints,
- ledger integrity under mixed commit/rollback/upgrade actions,
- audit tooling usability for operators.

### J.16.3 `CDEL-v2/`: verification debt management

With accelerated feature additions, CDEL-v2 can become bottleneck if verification debt accumulates. Closeout should emphasize:

- cross-version invariants,
- explicit mismatch reason coding,
- tests for every new schema+artifact edge.

### J.16.4 `orchestrator/`: runtime composition correctness

The microkernel now composes many subsystems in one tick. Closeout must ensure:

- deterministic ordering remains stable,
- optional paths cannot create hidden nondeterministic branches,
- snapshot/ledger always capture all branch outputs and fallback reasons.

### J.16.5 `tools/`: operational leverage and risk of drift

Tools provide observability and acceleration, but also potential contract drift if not pinned. Closeout should identify which tool outputs are promoted into canonical artifacts and ensure those are schema-locked.

### J.16.6 `polymath/` and `domains/`: external knowledge frontier

This is where open-world uncertainty enters. Closeout must keep strict:

- provenance,
- leakage scanning,
- deterministic transform contracts,
- replayability of all derived artifacts.

### J.16.7 `campaigns/`: policy-controlled capability expression layer

Campaign pack discipline is now central. The pack layer controls what runtime even sees. Closeout should enforce:

- minimal enabled set in production packs,
- explicit transition packs for experiments,
- no hidden environment coupling outside pack contract.

---

## J.17 Autonomy Ambition vs Constitutional Reality

The request frames end-goal ambition as autonomous operation at planetary scope and exponential intelligence scaling. That ambition can only remain coherent inside this architecture if constitutional boundaries stay primary.

### J.17.1 What this architecture can now credibly claim

It can credibly claim:

- deterministic replay governance across broad self-modification paths,
- strict fail-closed behavior for many critical transitions,
- growing support for generated native kernels under shadow-first gating,
- explicit readiness and tier evidence before swap-related transitions,
- hash-bound linkage from ingestion to promotion to activation artifacts.

### J.17.2 What it cannot claim yet (from code evidence alone)

From repository evidence alone, it cannot yet claim:

- indefinite no-regression operation over very long autonomous horizons,
- complete closure of all fallback/reporting inconsistencies,
- globally robust open-world ingestion quality under adversarial internet conditions,
- automatic safe generalization from local benchmarks to all external domains.

### J.17.3 Why this is still a major milestone

The architecture moved from "self-editing codebase" toward "constitutionally gated capability compiler". That is a meaningful qualitative shift.

---

## J.18 Risk Register for Immediate Closeout

### J.18.1 Risk: strict constants embedded in verifier tier checks

`verify_rsi_omega_daemon_v1.py` currently hard-codes specific tier counts (250/512/50 and 1000/20000/1000). This prevents silent lowering, which is good, but increases migration friction.

Mitigation path:

- keep pinned profile ids and verifier checks aligned,
- if evolving counts, perform explicit versioned verifier/schema transitions.

### J.18.2 Risk: fallback reason code normalization drift

Evidence artifacts show at least one string-form fallback reason inconsistency (`"None"` textual). Current verifier strictness may surface this as invalid in newer contexts.

Mitigation path:

- normalize generation scripts to `null` for absent reason,
- add tests asserting emitted status/reason consistency.

### J.18.3 Risk: toolchain/environment pin brittleness

Transpiler relies on absolute local toolchain paths and exact binary hashes. This is deterministic but deployment-fragile across hosts.

Mitigation path:

- include host-target manifests and reproducible bootstrap tooling,
- keep environment contract explicit in pack/runtime docs.

### J.18.4 Risk: expansion of optional branches in microkernel

As more optional features are added, deterministic branch control becomes harder.

Mitigation path:

- ensure each optional branch has explicit snapshot fields and ledger events,
- fail when expected fields are missing instead of silently skipping.

### J.18.5 Risk: schema growth without pruning strategy

Schema count is now high and rising. Versioning is necessary, but uncontrolled growth can increase maintenance complexity.

Mitigation path:

- formal schema lifecycle policy (active, historical, deprecated-but-required-for-replay),
- tooling that maps artifact frequency to schema maintenance priority.

---

## J.19 Final-Stretch Operational Pattern (Concrete)

This section is intentionally prescriptive and concrete.

### J.19.1 Promotion lanes

Use three operational lanes:

1. **Baseline lane**: stable SAS + polymath scout/bootstrap/conquer + SH-1 where proven.
2. **Frontier lane**: native transpiler, policy proof profile experiments, shadow tier drills.
3. **Swap lane**: shadow-ready + RE1 regime-upgrade exercises only when all tier/readiness conditions hold.

Do not mix all three lanes in one pack unless for controlled integration rehearsals.

### J.19.2 Evidence lane contract

For every frontier/swap push, require fresh artifacts:

- phase3b/phase4 canary evidence,
- phase4 audit bundle,
- phase4c swap drill summary,
- relevant verifier pass outputs.

Treat these as preconditions, not optional reports.

### J.19.3 Capability enablement discipline

Enable capabilities by deliberate campaign pack variants:

- keep super-unified for integrated operations,
- keep phase-specific packs for constrained testing (`phase4a`, `phase4b`, `phase3 bench`, etc.),
- use explicit goal queue entries to stage activation intention.

### J.19.4 Rollback-first doctrine for swap rehearsals

Any auto-swap rehearsal should include explicit post-swap and post-rollback self-check ticks, as Phase4C drill now does.

### J.19.5 Native route governance discipline

Treat `shadow_route_disabled_*` fields as high-signal health metrics. Route disable transitions should trigger immediate diagnostic workflow rather than silent continued operation.

---

## J.20 Capability Generation Matrix (As Implemented)

The matrix below summarizes generation-to-activation maturity for major capability families.

| Capability Family | Generation Mechanism | Verification Mechanism | Activation Mode | Current Maturity |
|---|---|---|---|---|
| SAS code/search/val/science/system/kernel | campaign scripts + policy routing + SH-1 feedback | versioned SAS verifiers + omega daemon replay | standard promotion/activation | mature baseline |
| Polymath scout/bootstrap/conquer | domain lifecycle tools | polymath verifiers + schema gates | standard promotion/activation | mature baseline |
| SIP ingestion L0 | phase4a ingestion runtime | `verify_rsi_polymath_sip_ingestion_l0_v1` | standard promotion | new but integrated |
| Knowledge transpiler | restricted IR -> Rust -> reproducible wasm build | `verify_rsi_knowledge_transpiler_v1` + v18 daemon checks | STATUS_SHADOW install intent | frontier but substantive |
| Native route acceleration | native router + shadow dual-run | mismatch/disable semantics + healthcheck vectors | shadow-first; native return only outside SHADOW mode | guarded |
| Shadow regime proposal/readiness | shadow sidecar (integrity + conservatism + determinism + J) | v19 daemon verifier + readiness schema checks | auto-swap only if tier B runtime pass and handoff | frontier governance |
| RE1 regime upgrade | `commit_staged_regime_upgrade` | readiness gating + RE1 audit + ledger entry | explicit upgrade commit path | newly real |

---

## J.21 Detailed Notes on Selected Critical Files

### J.21.1 `orchestrator/omega_v19_0/microkernel_v1.py`

Key closeout implications:

- Centralized orchestration of policy, proof, native stats, shadow sidecar, and snapshot emission.
- New shadow artifact hash fields in snapshot guarantee replay visibility.
- Emits both proof and proof-fallback events, reducing ambiguity.
- Integrates native shadow soak emission into normal tick flow.

Risk/benefit profile:

- Benefit: unified deterministic centerline.
- Risk: high complexity concentration; requires rigorous tests on branch interactions.

### J.21.2 `orchestrator/native/native_router_v1.py`

Key closeout implications:

- SHADOW mode does not return native output; this is conservative by design.
- Route disable transitions are persisted in hash-bound registry payloads.
- Environment-coupled state root/tick usage increases contextual correctness but adds dependency on invoker environment hygiene.

### J.21.3 `meta-core/engine/regime_upgrade.py`

Key closeout implications:

- RE1 now reads v19 readiness receipts directly.
- Fails closed on schema/version mismatch.
- Supports failpoint to validate crash behavior around next-pointer write.

### J.21.4 `tools/polymath/polymath_knowledge_transpiler_v1.py`

Key closeout implications:

- Converts external knowledge into constrained executable capability candidates with deterministic checkpoints.
- Emits failure artifacts (`candidate_syntax_error`, `nonrepro_build`) instead of silent drop.
- Strongly ties runtime contract to toolchain and binary identity.

### J.21.5 `CDEL-v2/cdel/v19_0/verify_rsi_omega_daemon_v1.py`

Key closeout implications:

- Enforces strict coherence between shadow tier receipts and readiness receipt.
- Enforces auto-swap prerequisites.
- Enforces stricter proof status/fallback consistency than earlier evidence scripts assumed.

---

## J.22 Concrete Evidence Objects Worth Preserving as Goldens

For ongoing closeout and operator onboarding, these existing run artifacts should be treated as golden evidence exemplars.

1. `runs/PHASE3B_PHASE4_EVIDENCE_v1.json`
- captures proof canary rates, proof timing, proof-size envelope, tamper/fallback behavior.

2. `runs/PHASE4_AUDIT_BUNDLE_v1.json`
- captures consolidated source/build/runtime/SIP evidence hashes for phase4 native transpiler path.

3. `runs/phase4c_real_swap_drill_v1/drill_20260220T112240Z/PHASE4C_REAL_SWAP_DRILL_SUMMARY_v1.json`
- captures shadow tier/readiness, failpoint path, live upgrade, rollback, and post checks.

These three together form a strong narrative chain: proof path viability, native build integrity, and swap/rollback governance.

---

## J.23 Closeout Readiness Scorecard (Technical)

The scorecard below is a qualitative engineering assessment derived from code and artifacts, not aspirational claims.

### J.23.1 Deterministic substrate: **Strong**

- Q32 fixed-point conventions preserved.
- canonical hashing contracts pervasive.
- proof and shadow telemetry integrated into snapshots.

### J.23.2 Replay verifiability: **Strong with active expansion pressure**

- v18 and v19 verifiers cover new paths.
- native/shadow additions now have schema + verifier coverage.
- complexity growth creates ongoing burden for completeness.

### J.23.3 Capability generation breadth: **High**

- 34 capability ids across registry universe.
- active packs for baseline, phase-specific experimentation, and super-unified operation.

### J.23.4 Capability activation safety: **Moderate-to-strong**

- shadow-first semantics for new native path are strong.
- RE1 upgrade gating now explicit.
- still requires operational discipline in pack selection and gate enforcement.

### J.23.5 Evidence and drill maturity: **Strong for newly added paths**

- phase3b/phase4 evidence script,
- phase4 audit bundle generator,
- phase4c swap drill with failpoint and rollback.

### J.23.6 Long-horizon autonomy confidence: **Improving, not complete**

- architecture now has the right governance primitives.
- long-run confidence still depends on sustained operations, anomaly handling, and strict gate culture.

---

## J.24 Final Architectural Interpretation for the "Run" Phase

The architecture is entering a different regime from earlier phases.

Earlier phases were dominated by:

- adding campaigns,
- adding verifiers,
- adding policy machinery.

Today’s phase increasingly emphasizes:

- governance of generated capability forms,
- evidentiary contracts for transition decisions,
- runtime safety around shadow-to-live boundaries,
- RE1-aware upgrade/rollback choreography.

That is exactly what should happen near closeout.

A system intended for highly autonomous operation should not end by adding raw capability only. It should end by hardening *how capability transitions happen*. Today’s delta is aligned with that requirement.

---

## J.25 Specific Recommendations for Immediate Next Iteration

This section stays concrete and bounded.

1. Normalize proof fallback reason semantics in evidence scripts and ensure emitted status/reason fields satisfy current verifier strictness.
2. Keep `phase4c` drill in routine CI or scheduled canary cadence; treat regression in failpoint/live/rollback path as release blocker.
3. Introduce a small compatibility layer in v19 verifier for tier-profile evolution only if accompanied by pinned profile-id checks; avoid silent broadening.
4. Add explicit regression tests for `ACTIVE_NEXT_BUNDLE` pointer coherence under commit/rollback/upgrade interleavings.
5. Expand native shadow soak analytics into observer metrics so decider can respond to route disable rates.
6. Maintain phase-specific packs as first-class deployment channels; do not collapse all behavior into one monolithic production pack.

These are engineering closeout steps, not conceptual research goals.

---

## J.26 Closing Statement for This Addendum

As of February 20, 2026, the repository has crossed an important boundary:

- It no longer only self-modifies code/config under verification.
- It now also contains a deterministic pipeline for generating constrained native executable capability from ingested knowledge, validating it under reproducible build and runtime checks, installing it in shadow, measuring shadow-readiness, and connecting that readiness to explicit RE1 regime-upgrade mechanics with rollback and failpoint coverage.

That does not by itself guarantee success at extreme autonomy targets. But it does materially improve the architecture’s ability to scale capability without collapsing its constitutional control model.

The most important engineering truth now is this:

**The system’s progress potential is increasingly limited less by raw generation and more by the quality, strictness, and operational discipline of its transition gates.**

Today’s changes are a direct investment in those gates.

---

## J.27 Supplemental: Full Commit Delta Notes for 2026-02-20

This supplemental section captures same-day deltas in compact form for future auditors.

### `d14d946` (Phase 3 hardening)

- Added `authority/evaluation_kernels/ek_omega_v19_phase3_v1.json`.
- Tightened rollback lineage and scoring paths.
- Updated mutator/death-test packs and `ignite_runaway.sh`/invoker plumbing.
- Added `tools/omega/omega_benchmark_suite_v19_v1.py`.

### `10ace95` (policy VM + Winterfell + deterministic hardening)

- Added v19 policy VM proof pipeline and backend contract scaffolding.
- Added v19 verifier modules for ISA program/opcode/trace/proposal/selection/proof artifacts.
- Added pack schema v2 and policy assets in `campaigns/rsi_omega_daemon_v19_0_super_unified/`.
- Introduced `orchestrator/omega_v19_0/microkernel_v1.py` and `orchestrator/omega_bid_market_v2.py`.
- Expanded tests for policy VM phase1 and replay/microkernel behavior.

### `dfbe6f4` (Phase4A alignment)

- Aligned bootstrap campaign and microkernel SIP ingestion behavior with mainline expectations.

### `14e32e8` (Phase4C regime upgrade)

- Added RE1 regime upgrade module and failpointed drill script.
- Extended constants and schema for ledger/pack support.

### `9df315f` (Phase3b/Phase4 worktree consolidation)

- Added native transpiler campaign/verifier/tooling.
- Added shadow modules, schemas, tests.
- Updated promoter/activator/daemon verifiers for native+shadow contracts.
- Updated native router and added wasm shadow soak artifact emitter.
- Added phase4 audit bundle script and additional evidence generation logic.

This commit is particularly significant because it operationalizes features that were previously in worktree limbo.

---

## J.28 Supplemental: Capability and Goal Inventory Snapshot

### J.28.1 Capability registries and enabled counts (selected)

- `campaigns/rsi_omega_daemon_v19_0/omega_capability_registry_v2.json`: 24 total, 3 enabled.
- `campaigns/rsi_omega_daemon_v19_0_super_unified/omega_capability_registry_v2.json`: 25 total, 9 enabled.
- `campaigns/rsi_omega_daemon_v19_0_phase4b_native_transpiler_v1/omega_capability_registry_v2.json`: 25 total, 4 enabled.
- `campaigns/rsi_omega_daemon_v19_0_phase4a_sip_ingestion/omega_capability_registry_v2.json`: focused single capability (`RSI_POLYMATH_SIP_INGESTION_L0`) enabled.

### J.28.2 Goal queue intent snapshot (selected)

- Base v19 pack: SAS triad goals.
- Super unified: mixed SAS + SH-1 + polymath + EUDRS-U goals.
- Phase4A pack: SIP ingestion goal.
- Phase4B pack: knowledge-transpiler shadow goal.

This demonstrates intentional use of pack-level objective profiles to stage deployment maturity.

---

## J.29 Supplemental: Why the New Native/Shadow Contracts Are Constitutionally Compatible

A concern with native acceleration is always that it may undermine replay determinism or verifier authority. The current implementation remains constitutionally compatible because:

1. transpiler outputs are schema-bound and hash-bound at every stage,
2. verifier rebuilds and re-runs checks rather than trusting emitted claims,
3. install intent is shadow-first,
4. shadow mismatch disables route and records reason/tick,
5. readiness receipts are explicit and checked before any swap path,
6. RE1 still performs its own guarded commit semantics.

In short, native capability expansion is not privileged over constitutional process; it is subordinated to it.

---

## J.30 Supplemental: Outstanding Practical Unknowns to Resolve Through Runs

Several questions are now more operational than architectural:

- How stable are proof runtime timings under sustained multi-day loads?
- What distribution of shadow route disable reasons appears under real polymath-derived candidate diversity?
- How often do tier checks fail in honest long-horizon operation versus synthetic drills?
- Does capability expansion produce measurable net gains under J and benchmark gates without debt blow-up?
- Are there hidden interactions between proof fallback paths and decision quality under stress?

These are not answered by static code inspection alone. They require disciplined run campaigns with preserved artifacts.

---

## J.31 Final Note for Future Maintainers

If you inherit this repository later, interpret this date as a major transition point:

- Before this date, major emphasis was building deterministic self-improvement infrastructure.
- On this date, the architecture meaningfully added deterministic capability-compilation and shadow-governed regime transition machinery.

When debugging future behavior, always inspect artifacts across this chain:

1. pack pins and profile ids,
2. generated artifacts and their hash lineage,
3. verifier decisions and reason codes,
4. snapshot fields and ledger event sequence,
5. RE1 audit and ledger outcomes.

The system is now too compositional for single-file diagnosis.

---

*End Appendix N.*


---

# Appendix O: Comprehensive Folder Atlas for Final Autonomous Operations

This appendix is a folder-by-folder and capability-by-capability atlas written for the closing operational phase. Its goal is practical: make it obvious what exists, what each surface can contribute, what is still experimental, and how to combine old and new assets without breaking constitutional safety.

Where Appendix N emphasized same-day deltas, Appendix O emphasizes **full usable inventory posture** across old and new surfaces.

---

## K.1 Control Surfaces by Trust Ring and Operational Role

A useful operational representation is to classify each major folder by two axes:

- trust ring location (RE1/RE2/RE3/RE4/authority),
- function in the autonomy loop (generation, selection, verification, activation, recovery, evidence).

### K.1.1 `authority/` (root governance)

Operational role:

- pins and allowlists,
- evaluation kernel sovereignty,
- operator/sandbox contracts.

Final-run interpretation:

- this folder defines what "improvement" means and what mutation is even legal,
- if this surface drifts, every downstream score can become meaningless.

### K.1.2 `meta-core/` (RE1 constitutional execution)

Operational role:

- stage/verify/canary/commit/rollback,
- audit and ledger chain,
- now regime-upgrade gating entrypoint.

Final-run interpretation:

- this is the only acceptable place where active state pointer truth can move,
- any autonomy claim that bypasses RE1 is a category error.

### K.1.3 `CDEL-v2/` (RE2 replay judiciary)

Operational role:

- campaign-specific verification,
- daemon replay verification,
- policy VM proof verification,
- shadow readiness/tier verification,
- continuity/federation checks.

Final-run interpretation:

- this is where "creative generation" is reduced to binary pass/fail under deterministic replay law.

### K.1.4 `orchestrator/` (control plane executor)

Operational role:

- tick composition and artifact emission,
- dispatch to campaign executors,
- promotion+activation handoff,
- native routing and now shadow sidecar invocation.

Final-run interpretation:

- orchestrator is not trusted by itself; it is trusted only insofar as RE2 replay can reproduce and validate what it did.

### K.1.5 `tools/` (operational leverage and capability factory)

Operational role:

- proposal synthesis (SH-1),
- benchmarking and performance instrumentation,
- polymath discovery and now transpilation,
- mission-control tooling.

Final-run interpretation:

- tools are where practical acceleration happens, but their output must always collapse back into schema+hash+verifier channels.

### K.1.6 `campaigns/` (behavioral profile layer)

Operational role:

- capability registry definitions,
- policy/objective/runaway/goal queue profiles,
- phase-specific operational envelopes.

Final-run interpretation:

- campaign packs are the system’s behavior selector. Same binary runtime with different pack can behave radically differently.

### K.1.7 `polymath/`, `domains/`, `runs/` (knowledge and evidence memory)

Operational role:

- polymath registry/store and domain policy,
- domain pack data in `domains/`,
- execution traces and evidence in `runs/`.

Final-run interpretation:

- this is accumulated memory and audit substrate. It is where the system remembers what it learned and what it proved.

---

## K.2 Detailed Tool Atlas (What to Use, When, and Why)

### K.2.1 `tools/omega`: runtime quality and native operations lab

This tool family is the closest thing to an operations reliability kit. It contains benchmarking, verification helpers, native codegen/build/profiling, and test harness orchestration.

High-value modules for final run:

- `omega_benchmark_suite_v1.py` and `omega_benchmark_suite_v19_v1.py`: benchmark truth surfaces.
- `omega_replay_bundle_v1.py`: replay packaging and trace analysis.
- `omega_timings_aggregate_v1.py`: longitudinal stage timing aggregation.
- `native/native_healthcheck_v1.py`: native route validation.
- `native/rust_build_repro_v1.py`: reproducible-build diagnostics.
- `survival_drill_runner_v1.py`: resilience exercise runner.

Operational pattern:

- use benchmark suite outputs as promotion gate context,
- run timing aggregation on windows to detect slow drift before runaway overreacts,
- periodically run survival drills in maintenance windows even when production is stable.

### K.2.2 `tools/genesis_engine`: adaptive proposer memory

SH-1 is still the strongest generalized proposer path, because it uses receipt memory and fail reason patterns.

High-value modules:

- `ge_symbiotic_optimizer_v0_3.py`: primary proposer engine.
- `sh1_pd_v1.py`: promotion density extraction.
- `sh1_xs_v1.py`: exploration score extraction.
- `sh1_behavior_sig_v1.py`: behavior signatures to block novelty laundering.

Operational pattern:

- treat SH-1 as adaptive control, not random patch generator,
- keep receipt corpus healthy and queryable,
- ensure promoter reason-code granularity stays high so SH-1 receives useful learning signals.

### K.2.3 `tools/polymath`: discovery, refinement, and now transpilation

This family now spans three historically separate concerns:

1. discovery (`scout`),
2. data/domain construction (`bootstrap` and dataset/source utilities),
3. capability compilation (`knowledge_transpiler`).

Critical scripts:

- `polymath_scout_v1.py`
- `polymath_domain_bootstrap_v1.py`
- `polymath_domain_corpus_v1.py`
- `polymath_void_to_goals_v1.py`
- `polymath_refinery_proposer_v1.py`
- `polymath_knowledge_transpiler_v1.py`

Operational pattern:

- keep scout cadence steady to prevent stale void signals,
- bootstrap only when source provenance and policy pass,
- route high-confidence SIP knowledge into transpiler only after ingestion verification,
- keep transpiler in shadow-first mode until shadow soak remains stable over sustained windows.

### K.2.4 `tools/v19_runs` and `tools/v19_smoke`: repeatable evidence orchestration

These folders support repeatable, automated evidence workflows.

Examples:

- `run_omega_v19_full_loop.py`
- `v19_ladder_evidence_pipeline_v1.py`
- `run_tick_gate_matrix_e2e.py`
- `run_promotion_gate_smoke.py`

Operational pattern:

- promote these scripts from ad hoc usage to routine schedule,
- persist outputs under stable naming for historical comparison,
- integrate gate-matrix deltas into observer metrics for autonomous self-diagnosis.

### K.2.5 `tools/mission_control` and `tools/omega_mission_control`

These represent operational UI/service surfaces. They are not constitutional cores, but they matter for human oversight and for reducing operator error during high-complexity transitions.

Operational pattern:

- keep mission-control surfaces read-mostly for critical actions,
- ensure any write/action path still resolves through canonical CLI/runtime flows and leaves signed/hashable traces.

### K.2.6 `tools/vision`

Vision utilities are smaller in count but strategically important for EUDRS-U world-model breadth.

Operational pattern:

- keep vision goldens generation deterministic,
- ensure retrieval/selection utility outputs remain schema-bound and hash-addressed before downstream use.

---

## K.3 Campaign Atlas: How to Exploit Everything Built So Far

Campaign surfaces now exceed what a flat list communicates. The useful view is by function family and maturity.

### K.3.1 Baseline productivity family (always-on candidates)

- `rsi_sas_code_v12_0`
- `rsi_sas_metasearch_v16_1`
- `rsi_sas_val_v17_0`

These appear enabled in many packs for a reason: they provide broad improvement pressure with established verifier paths.

### K.3.2 Adaptive proposer family

- `rsi_ge_symbiotic_optimizer_sh1_v0_1`
- coordinator/market mutator campaigns

Use this family to maintain adaptive exploration-exploitation of code/config surfaces. Keep mutators gated and observed due higher blast radius.

### K.3.3 Polymath expansion family

- `rsi_polymath_scout_v1`
- `rsi_polymath_bootstrap_domain_v1`
- `rsi_polymath_conquer_domain_v1`
- `rsi_polymath_sip_ingestion_l0_v1`

This family extends knowledge frontier and now feeds capability compilation arcs.

### K.3.4 Native/transpiler transition family

- `rsi_omega_native_module_v0_1`
- `rsi_knowledge_transpiler_v1`

This family is the bridge into generated executable capability under deterministic controls.

### K.3.5 EUDRS-U family

- train/index/ontology/eval campaigns

These remain critical for long-term embodied learning hypotheses and should be maintained even if not always enabled in production packs.

### K.3.6 Skill/report family

Multiple `rsi_omega_skill_*` campaigns remain low-risk, high-observability modules useful for periodic health probes and domain-specific diagnostics.

### K.3.7 Stress/adversarial family

- survival drills,
- phase0 immune/victim paths,
- death-test packs,
- market toy and benchmark packs.

These are essential for proving immune response and preventing complacency near closeout.

---

## K.4 Legacy Recovery: What Older Components Still Contribute

A closeout risk is discarding "old" modules too early. Several legacy components remain strategically useful.

### K.4.1 CAOE lineage in `Extension-1/agi-orchestrator`

Even if SH-1 dominates code mutation, CAOE’s wake/sleep/dawn architecture remains useful as a conceptual or practical scaffold for architecture-level anomaly mining.

### K.4.2 Historical SAS campaigns and verifiers

Earlier-version campaigns and verifiers are necessary for replay and can also act as alternate search paths when newer campaigns overfit current gates.

### K.4.3 Older bid-market and toy modules

Toy campaigns are often the cheapest place to validate new market or selection semantics before exposing production capability registries.

### K.4.4 Older schema versions

Historical schema versions are not bloat. They are governance memory and compatibility anchors. Preserve them unless a formal replay-incompatibility deprecation plan exists.

---

## K.5 Polymath + Transpiler Integration Playbook

This section gives an explicit operational choreography for turning external knowledge into shadow-verified native capability without violating determinism.

### K.5.1 Step A: SIP ingest

Run/verify SIP ingestion campaign. Require:

- valid knowledge artifact hash,
- empirical evidence hash,
- no leakage/policy violations.

### K.5.2 Step B: Build restricted kernel spec

Maintain kernel spec under campaign pack with explicit Q32 params and health vectors.

### K.5.3 Step C: Transpile under pinned toolchain/runtime manifests

Run `rsi_knowledge_transpiler_v1` and require status `OK` and health PASS.

Reject if:

- candidate syntax error artifact exists,
- nonrepro build artifact exists,
- any required artifact hash mismatch.

### K.5.4 Step D: Promotion and activation to STATUS_SHADOW

Allow activator to install/update `native_shadow_registry_v1` with preserved disable state semantics.

### K.5.5 Step E: Shadow soak observation window

Monitor shadow soak summary/receipt over sustained ticks:

- route-disabled modules should trend to zero for readiness,
- portability status should remain RUNNABLE,
- disable reason taxonomy should be stable and actionable.

### K.5.6 Step F: Shadow regime readiness gating

Require tier A/B + readiness receipt PASS/READY and no integrity mutations.

### K.5.7 Step G: Optional auto-swap drill path

Only with explicit auto-swap setup and handoff receipts, run regime-upgrade drill including failpoint and rollback validation.

This is the operationally safe path from new knowledge to live-capable runtime transition.

---

## K.6 Test and Verification Coverage Snapshot

### K.6.1 Newly relevant test families

v18 tests now include native/transpiler routes, e.g.:

- `test_native_router_shadow_mode_v1.py`
- `test_transpiler_shadow_registry_install_v1.py`
- `test_system_kernel_activation_keys.py` (updated)

v19 tests include policy and shadow readiness surfaces:

- `test_policy_vm_phase1.py`
- `test_policy_vm_replay_and_microkernel.py`
- `tests_continuity/test_shadow_airlock_v1.py`
- `tests_continuity/test_shadow_fs_guard_v1.py`
- `tests_continuity/test_shadow_tiers_v1.py`
- `tests_continuity/test_corpus_descriptor_v1.py`

### K.6.2 Coverage interpretation

Coverage now spans key new contracts, but final-run safety depends on combined-sequence tests, not only unit tests. The highest-value additions going forward are scenario tests that chain:

- transpiler generation -> promotion -> shadow install,
- shadow soak transitions,
- shadow readiness -> RE1 upgrade -> rollback,
- replay verification across each stage.

---

## K.7 Autonomy Scaling Doctrine (Engineering Version)

To align with the stated objective of maximizing autonomous problem-solving capacity, the engineering doctrine should be explicit.

### K.7.1 Principle 1: Scale capability generation, not trust assumptions

New generation mechanisms are welcome only if trust assumptions do not expand. Every new generator must produce artifacts that are verifiable by existing constitutional machinery or versioned extensions thereof.

### K.7.2 Principle 2: Keep transition gates stricter than generation gates

Generation can be broad and exploratory. Transition to active runtime must remain narrow, deterministic, and evidence-heavy.

### K.7.3 Principle 3: Prefer layered deployment over single-shot activation

Use staged packs and lane-based operation:

- baseline lane for stable progress,
- frontier lane for new capabilities,
- swap lane for regime transitions.

### K.7.4 Principle 4: Treat fallback paths as first-class, not exceptions

Fallback status and reasons are part of system truth. They must be explicit in snapshots and verifier-checked.

### K.7.5 Principle 5: Preserve reversibility as non-negotiable

Any high-impact transition without tested rollback should be considered incomplete.

---

## K.8 Practical Execution Template for the Next 30-Day Closeout Window

This template is designed for the immediate practical horizon.

### K.8.1 Weekly cycle

1. Run baseline production packs with stable enabled capability set.
2. Run phase-specific frontier packs (`phase4a`, `phase4b`, proof canaries) and gather artifacts.
3. Run shadow readiness drills and selected failpoint exercises.
4. Generate audit bundles and compare against previous week.
5. Update source-of-truth addendum with measured deltas and resolved/introduced risks.

### K.8.2 Promotion criteria for moving frontier features toward baseline

Require all of:

- repeated verifier-valid runs,
- no unresolved schema/hash mismatch class,
- stable shadow soak readiness without rising disable transition rates,
- successful rollback rehearsal for any swap-relevant path.

### K.8.3 Non-negotiable stop conditions

- recurrent nonrepro build findings,
- unresolved proof status/fallback contradictions,
- repeated shadow protected-root mutation findings,
- inability to reproduce evidence bundles from pinned scripts.

---

## K.9 Folder-Level "Use It Now" Checklist

The following checklist is intentionally operational.

### `authority/`

- confirm active kernel and allowlist pins before major runs,
- verify no unintended pin drifts.

### `meta-core/`

- periodically run audit and check pointer/ledger coherence,
- include failpoint mode in rehearsal cadence.

### `CDEL-v2/`

- execute relevant test suites when introducing schema/runtime changes,
- keep verifier reason codes precise and stable.

### `orchestrator/`

- ensure pack freeze includes all required pinned assets,
- verify snapshot fields for new branches are always populated/consistent.

### `tools/`

- treat evidence generator scripts as part of release process,
- avoid ad hoc tool outputs that bypass schema contracts.

### `polymath/`

- keep source policy and registry hygiene strong,
- rotate through scout/bootstrap/conquer/ingest cycles explicitly.

### `campaigns/`

- maintain narrow, purpose-built packs for risky transitions,
- keep production packs conservative in enabled capability set.

### `runs/`

- preserve canonical evidence artifacts and indexes,
- make trend comparisons part of observer inputs where possible.

---

## K.10 Closing Integration Note

Everything needed for a disciplined autonomous closeout now exists in code:

- deterministic generation paths,
- strict replay verification,
- shadow-first activation for new native forms,
- explicit readiness contracts,
- RE1 regime-upgrade and rollback drills,
- growing evidence automation.

The remaining work is not inventing a new architecture. The remaining work is **operating this one rigorously**, tightening edge inconsistencies, and refusing to trade governance strictness for speed.

If that discipline holds, the architecture can continue increasing capability while preserving constitutional control, which is the only viable path for durable high-autonomy scaling.

---

*End Appendix O.*


---

# Appendix P: Capability Crosswalk and Deployment Stratification

This appendix gives a direct crosswalk between the capability vocabulary and practical deployment strategy. It is designed for operators who need to answer: "which capability do we enable next, under which pack, with what verifier, and under what risk posture?"

---

## L.1 Capability ID Universe and Grouping Logic

Observed unique capability ids across current registries form a mixed set of baseline, frontier, and test-specific surfaces. For closeout operations, the useful grouping is:

- **Baseline Core**: proven high-utility campaigns used in regular operation.
- **Expansion Core**: campaigns that directly increase domain breadth or generation power.
- **Native Transition**: campaigns that move execution pathways toward compiled artifacts.
- **Skill/Diagnostics**: campaignized analysis/report generation paths.
- **Adversarial/Test**: intentionally constrained or stress-oriented capabilities.

### L.1.1 Baseline Core group

Includes:

- `RSI_SAS_CODE`
- `RSI_SAS_METASEARCH`
- `RSI_SAS_VAL`
- (often) `RSI_SAS_SCIENCE`

Rationale:

- repeatedly enabled in major packs,
- broad contribution to code/search/validation loops,
- mature verifier surfaces with known behavior.

### L.1.2 Expansion Core group

Includes:

- `RSI_GE_SH1_OPTIMIZER`
- `RSI_POLYMATH_SCOUT`
- `RSI_POLYMATH_BOOTSTRAP_DOMAIN`
- `RSI_POLYMATH_CONQUER_DOMAIN`
- `RSI_EUDRS_U_*` family (`TRAIN`, `ONTOLOGY_UPDATE`, `INDEX_REBUILD`, `EVAL_CAC`)

Rationale:

- these are the principal capability-breadth amplifiers,
- they create new information, new transformations, and improved policies over time,
- they require stronger gate observation because effects can be broad.

### L.1.3 Native Transition group

Includes:

- `RSI_OMEGA_NATIVE_MODULE`
- `RSI_KNOWLEDGE_TRANSPILER`
- `RSI_POLYMATH_SIP_INGESTION_L0` (as upstream enabler)

Rationale:

- this group bridges from interpreted/templated evolution toward generated executable kernels,
- demands strict shadow-first governance and clear rollback plans.

### L.1.4 Skill/Diagnostics group

Includes:

- `RSI_OMEGA_SKILL_ALIGNMENT`
- `RSI_OMEGA_SKILL_BOUNDLESS_MATH`
- `RSI_OMEGA_SKILL_BOUNDLESS_SCIENCE`
- `RSI_OMEGA_SKILL_EFF_FLYWHEEL`
- `RSI_OMEGA_SKILL_MODEL_GENESIS`
- `RSI_OMEGA_SKILL_ONTOLOGY`
- `RSI_OMEGA_SKILL_PERSISTENCE`
- `RSI_OMEGA_SKILL_SWARM`
- `RSI_OMEGA_SKILL_THERMO`
- `RSI_OMEGA_SKILL_TRANSFER`

Rationale:

- low-risk diagnostic refreshers for observer/decider context,
- useful for anomaly localization and prioritized hardening decisions.

### L.1.5 Adversarial/Test group

Includes:

- `BID_MARKET_TOY_GOOD`
- `BID_MARKET_TOY_BAD`
- mutator/death-test linked capabilities (`RSI_COORDINATOR_MUTATOR`, `RSI_MARKET_RULES_MUTATOR`)

Rationale:

- not always production-on,
- high value for preventing immune-system atrophy.

---

## L.2 Pack Stratification: Which Pack Is For What

### L.2.1 `rsi_omega_daemon_v19_0` base pack

Intent:

- conservative baseline operation,
- limited enabled set centered on SAS core.

When to use:

- production stability periods,
- control runs for regression comparison.

### L.2.2 `rsi_omega_daemon_v19_0_super_unified`

Intent:

- integrated multi-family operation (SAS + SH-1 + polymath + EUDRS-U),
- v2 schema capable with richer policy assets.

When to use:

- integrated benchmark windows,
- evaluating cross-family interactions.

Watch-outs:

- higher interaction complexity,
- stronger need for replay and evidence review.

### L.2.3 `rsi_omega_daemon_v19_0_phase4a_sip_ingestion`

Intent:

- isolate and validate SIP ingestion capability as a first-class daemon path.

When to use:

- ingestion hardening,
- provenance/leakage policy tests,
- preconditioning phase before transpiler runs.

### L.2.4 `rsi_omega_daemon_v19_0_phase4b_native_transpiler_v1`

Intent:

- focus on transpiler/native transition with constrained enabled set.

When to use:

- shadow-install rehearsal,
- route disable taxonomy stabilization,
- reproducible build/runtime contract confidence building.

### L.2.5 `phase3_*` packs and market/death variants

Intent:

- targeted stress, scoring, and regression scenarios.

When to use:

- verifier stress campaigns,
- controlled chaos drills,
- post-merge hardening before baseline promotion.

---

## L.3 Verifier-Centric Crosswalk

This subsection emphasizes a crucial practical point: capabilities only matter if their verifier path is clear and maintainable.

### L.3.1 Mature verifier-backed families

- SAS code/system/kernel/science/metasearch/val verifiers (multi-version).
- CCAP verifier (`verify_ccap_v1`) for broad patch proposals.
- polymath domain verifier line.

These should remain first-choice for high-frequency autonomous loops.

### L.3.2 New verifier-backed families

- `verify_rsi_polymath_sip_ingestion_l0_v1` (ingestion).
- `verify_rsi_knowledge_transpiler_v1` (transpiler to native).
- expanded v18 daemon verifier for native shadow registry + shadow soak.
- expanded v19 daemon verifier for shadow tier/readiness path.

These are now real and tracked, but should be promoted through staged operational confidence windows.

### L.3.3 Composite verification path now possible

A complete composite path can now be verified end-to-end:

1. ingest knowledge,
2. transpile to constrained native candidate,
3. emit promotion bundle and activation binding,
4. install shadow registry entry,
5. observe shadow soak summary/receipt,
6. evaluate shadow tiers and readiness,
7. run RE1 regime-upgrade drill path.

This path did not exist as a fully tracked and verifier-aware chain before today’s consolidation.

---

## L.4 Deployment Gate Hierarchy for Exponential-Scale Ambitions

For ambitions of large-scale autonomous problem-solving, deployment discipline must be hierarchical.

### L.4.1 Gate A: deterministic generation validity

Requirements:

- schema-valid generated artifacts,
- canonical hash binding integrity,
- no forbidden nondeterminism tokens.

### L.4.2 Gate B: reproducibility and runtime contract validity

Requirements:

- reproducible build proof pass,
- runtime binary pin match,
- deterministic flags validated.

### L.4.3 Gate C: functional correctness under vectorized checks

Requirements:

- healthcheck receipt PASS,
- vector expected vs actual hashes all match,
- no hidden runtime divergence.

### L.4.4 Gate D: shadow operational stability

Requirements:

- shadow soak readiness PASS over sustained window,
- no persistent route-disable accumulation,
- portability status stable.

### L.4.5 Gate E: shadow regime readiness

Requirements:

- tier A/B pass,
- integrity report PASS,
- determinism and conservatism receipts pass,
- J comparison rules pass.

### L.4.6 Gate F: RE1 transition legality and reversibility

Requirements:

- `commit_staged_regime_upgrade` pass,
- RE1 audit coherent,
- rollback path tested and successful.

This hierarchy is the practical architecture for scaling capability without surrendering control.

---

## L.5 Recommended Capability Enablement Sequence (Concrete)

If running a structured closeout progression from current state, a practical sequence is:

1. Keep baseline SAS core enabled in production pack.
2. Keep polymath scout/boot/conquer active in super-unified windows.
3. Keep SIP ingestion pack cycles active to refresh frontier inputs.
4. Run phase4b transpiler pack in dedicated windows until shadow soak becomes predictably PASS.
5. Introduce controlled shadow readiness exercises in v2-capable packs.
6. Run periodic phase4c swap drills with failpoint and rollback checks.
7. Only then consider broader auto-swap activation policies, and only with explicit evidence thresholds.

This sequencing uses existing assets fully while minimizing constitutional risk.

---

## L.6 Final Synthesis

From a capability-program perspective, the system now has:

- broad baseline self-improvement capability,
- formalized knowledge-ingestion capability,
- deterministic native-capability generation,
- shadow-governed activation transition machinery,
- RE1-level regime-upgrade and rollback instrumentation.

That is enough to enter sustained autonomous scaling experiments, provided operations stay gate-disciplined and evidence-first.

The central operational truth is simple:

**Enablement order and gate discipline now matter more than raw feature count.**

This repository has sufficient capability breadth. The closeout challenge is orchestration quality under constitutional constraints.

---

*End Appendix P.*


---

# Appendix Q: Short Operator Memo for the Run Phase

The current codebase is no longer in a "missing pieces" state. It is in a "coordination and discipline" state.

Three operator habits will determine whether the architecture scales safely:

1. **Always read artifacts, not only logs.**
   If a transition happened, there should be hash-bound evidence in snapshot, ledger, and promotion/activation artifacts. If evidence is missing, treat the transition as invalid until explained.

2. **Always test rollback in the same window as forward movement.**
   Forward-only confidence is false confidence. The system now has explicit swap/rollback instrumentation; use it routinely.

3. **Always separate exploratory packs from baseline packs.**
   Phase-specific packs exist to isolate risk. Keep them isolated unless evidence supports promotion.

A practical review cadence for autonomous runs should include:

- weekly comparison of shadow route disable reasons,
- weekly proof canary trend checks (fast-path/fallback/timing/proof size),
- periodic phase4c-style rehearsal with failpoint + rollback,
- strict normalization checks for fallback reason/status semantics.

The architecture has enough built capability to run hard. The failure mode now is less likely to be "we cannot generate improvements" and more likely to be "we generated and transitioned too quickly without enforcing our own contracts."

The correct final-stretch posture is therefore:

- keep generation throughput high,
- keep transition thresholds strict,
- keep evidence expectations uncompromising.

That posture is compatible with strong autonomy and constitutional safety at the same time.

---

*End Appendix Q.*


# Appendix R: Last 24h Delta (2026-02-21 to 2026-02-22)

This appendix captures every material source-of-truth impact from the last full day of repo movement, including both committed and uncommitted deltas. The committed chain includes `55ce658` (manifests and phase4c hardening), `4734de4` (preflight checks scaffolding), `b9e39dd` (preflight hardening pass), and `f109b05` (the most recent hardening batch). In addition, the working tree currently contains a larger follow-on batch of runtime/scheme/campaign and meta-core staging changes that are not yet in a commit and are therefore represented as “active local delta.”

The objective of this update is to prevent drift between:

1. code reality now,
2. contract intent in Genesis and source-of-truth prose,
3. and governance assumptions in operation.

The major design outcome is that the platform moved from “preflight readiness groundwork” to “fully wired frontier-control + preflight observability + staged bundle operationalization,” while preserving the RE1/RE2 hard-fail posture.

## R.1 Commit and Delta Timeline

The timeline for the last day can be interpreted through timestamps and scope:

`55ce658` at 2026-02-21 13:52:33 introduced a large epistemic stack formalization across v19 verifier and campaign surfaces, including manifest-backed shadow replay and phase4c drill hardening.

`4734de4` at 2026-02-21 16:02:05 extended preflight surfaces and CI gating, with initial schema additions for long-run observability and launch manifest state.

`b9e39dd` at 2026-02-21 16:27:52 intensified preflight strictness and tied longer-range checks into run scripts.

`f109b05` at 2026-02-22 12:44:32 completed a broad hardening pass across verifiers, orchestrators, and long-run discipline.

Immediately after these commits, the workspace also shows additional active files in `CDEL-v2/`, `Genesis/`, `campaigns/`, `meta-core/`, `orchestrator/`, and `tools/` that continue the same hardening arc but are not yet committed.

The uncommitted delta should be treated as operationally real because it changes runtime behavior, and therefore must be reflected in the source-of-truth now.

## R.2 Strategic Summary of the Day

The biggest shift is no longer at the “feature discovery” layer. The change set is mostly in:

1. stronger contract surfaces,
2. stronger evidence-carrying preflight and long-run telemetry,
3. stronger frontier/debt governance,
4. stronger verifier branching around shadow and utility readiness,
5. more explicit bundle-level constitutional staging,
6. and broader test coverage for these exact boundaries.

The repository now contains a richer deterministic governance loop that links:

- capability policy,
- debt routing receipts,
- utility proof receipts,
- promotion receipts and subverifier receipts,
- and RE1 bundle artifacts.

This creates a “cross-layer evidence chain” that can be audited with less ambiguity than before. In practice, if one wants to understand why a run changed behavior, the new architecture expects a chain of receipts rather than a raw log guess:

mission ingestion state -> decision lane routing -> dependency debt state updates -> utility policy constraints -> verification receipts -> promotion decision -> canary/commit evidence in meta-core.

The net governance move is that frontier pressure no longer relies on ad hoc conditions; it is represented in explicit state and receipts that are now schemaed and replay-sensitive.

## R.3 Verification and Proof Layer Expansion

The v18 and v19 verifier stacks changed from incremental edits into a coordinated hardening wave.

In `CDEL-v2/cdel/v18_0/verify_rsi_omega_daemon_v1.py` and `CDEL-v2/cdel/v19_0/verify_rsi_omega_daemon_v1.py`, tick and evidence validation logic was updated in the same window as schema and promoter changes. This matters because these verifiers are the boundary between the daemon tick logic and constitutional trust. Any field-shape change in long-run reports or receipts now has to pass through verifier normalization, and that is where many of today’s failures are prevented before they reach activation.

The CCAP runtime chain (`CDEL-v2/cdel/v18_0/ccap_runtime_v1.py`, `verify_ccap_v1.py`, `omega_promoter_v1.py`, and `CDEL-v2/cdel/v18_0/omega_bid_market_v1.py`) saw edits supporting stricter checks around bundle acceptance, reason attribution, and frontier/registry compatibility when proposals route through policy or bidding.

`CDEL-v2/cdel/v18_0/tests_omega_daemon/test_ccap_rollout_registry_v1.py` and `CDEL-v2/cdel/v18_0/tests_omega_daemon/test_promotion_no_bundle_reason_v1.py` indicate explicit regression pressure on bundle rollout semantics, especially around missing bundle reasons and rollout registry consistency.

The same direction appears in v19 additions of epistemic verification families and shadow-specific tests under:

- `CDEL-v2/cdel/v19_0/epistemic/*`
- `CDEL-v2/cdel/v19_0/tests_continuity/test_shadow_airlock_v1.py`
- `CDEL-v2/cdel/v19_0/tests_continuity/test_shadow_tiers_v1.py`
- `CDEL-v2/cdel/v19_0/tests_omega_daemon/test_phase4c_real_swap_drill_v1.py`.

These additions matter because phase4c swap drills and epistemic continuity can now be treated as replay-evaluable gates instead of informal process.

## R.4 Schema Surface Expansion and Contract Drift Control

Commit activity introduced many new schema files and touched a large legacy set. The critical implication is: long-run frontier governance is now represented by strongly typed artifacts instead of implicit behavior.

### R.4.1 New/updated v19 runtime governance schemas

- `Genesis/schema/v19_0/dependency_debt_state_v1.jsonschema` (introduced/updated with frontier debt memory fields)
- `Genesis/schema/v19_0/dependency_routing_receipt_v1.jsonschema` (explicit forced-routing, frontier debt, reason-code channel)
- `Genesis/schema/v19_0/utility_policy_v1.jsonschema` (class and heavy policy mapping)
- `Genesis/schema/v19_0/utility_proof_receipt_v1.jsonschema` (frontier/utility proof contracts)
- `Genesis/schema/v19_0/anti_monopoly_state_v1.jsonschema` (additional anti-monopoly continuity checkpoint)

These files are the operational centerpieces for frontier scheduling behavior in the last day window.

### R.4.2 v18 governance schemas that became stricter

Changes to v18 schema files now align with v19 behavior so replay continuity is preserved across versions. `omega_goal_queue_v1`, `omega_ledger_event_v1`, `omega_native_runtime_stats_v1`, `omega_promotion_receipt_v1`, `omega_subverifier_receipt_v1`, `omega_tick_outcome_v1`, and `omega_tick_snapshot_v1` were updated in ways consistent with stronger failure reporting and runtime evidence capture.

`CDEL-v2/Genesis/schema/v18_0/omega_promotion_receipt_v1.jsonschema` was also changed in working tree. That creates one of the strongest consistency risks in this release: if promotion reasons and receipts are not schema-aligned between CDEL and orchestrator runtime, verifier acceptance and orchestrator reporting can diverge. This is now under direct review through v19 evidence.

### R.4.3 New data-plane assets and mission contracts

`Genesis/schema/v19_0/eval_report_v1.jsonschema`, `long_run_profile_v1.jsonschema`, `mission_goal_ingest_receipt_v1.jsonschema`, and `mission_request_v1` updates indicate that long-run mission behavior now has broader traceability around mission admission and policy profile configuration.

The working tree also contains uncommitted additions in:

- `Genesis/schema/v19_0/long_run_stop_receipt_v1.jsonschema`
- `Genesis/schema/v19_0/utility_policy_v1.jsonschema`
- `Genesis/schema/v19_0/utility_proof_receipt_v1.jsonschema`
- `Genesis/schema/v19_0/anti_monopoly_state_v1.jsonschema`
- `Genesis/schema/v19_0/dependency_debt_state_v1.jsonschema`
- `Genesis/schema/v19_0/dependency_routing_receipt_v1.jsonschema`.

This is strong evidence that schema-level contract completion is still ongoing and should be captured in any closeout compliance checklist.

## R.5 Frontier Control and Debt Routing Maturation

The most important functional change across the day is the formalization of frontier debt routing semantics.

In orchestrator and CDEL, debt routing now has a denser data path. `orchestrator/omega_v19_0/microkernel_v1.py` and `orchestrator/omega_v19_0/mission_goal_ingest_v1.py` are the core state engines receiving changes. The debt state object was reified through `dependency_debt_state_v1`, and receipts now track blocked frontier attempts and forced frontier attempts in a machine-readable way.

The working files in `tools/` and the debug analysis notes show several conceptual alignments:

- frontier debt keys and thresholds now drive pre-evidence forced routing decisions;
- hard lock activation is preserved in state and surfaced as routing reason;
- maintenance/utility failures update debt counters to prevent silent starvation;
- frontier lane behavior remains policy-driven via `utility_policy_v1`.

The debug traces in `debug_3.md` and `debug_4.md` provide concrete examples of how debt counters and hard-lock flags should be interpreted over time. This clarifies that frontier pressure is no longer ad hoc logic; it is now expected to persist as auditable per-tick state and be replay-verifiable.

## R.6 Campaign and Registry Evolution

The campaign layer changed broadly, and these edits are important because they alter capability governance without changing the root trust assumptions. Modified packs include:

- `campaigns/rsi_omega_daemon_v19_0_long_run_v1/goals/omega_goal_queue_v1.json`
- `campaigns/rsi_omega_daemon_v19_0_long_run_v1/long_run_profile_v1.json`
- `campaigns/rsi_omega_daemon_v19_0_long_run_v1/omega_capability_registry_v2.json`
- `campaigns/rsi_omega_daemon_v19_0_long_run_v1/rsi_omega_daemon_pack_v1.json`
- `campaigns/rsi_omega_daemon_v19_0_long_run_v1/utility/omega_utility_policy_v1.json`
- `campaigns/rsi_omega_daemon_v19_0_phase3_bench/omega_capability_registry_v2.json`
- `campaigns/rsi_omega_daemon_v19_0_phase3_market_toy/omega_capability_registry_v2.json`
- `campaigns/rsi_omega_daemon_v19_0_phase4b_native_transpiler_v1/omega_capability_registry_v2.json`
- `campaigns/rsi_omega_daemon_v19_0_super_unified/omega_capability_registry_v2.json`
- `campaigns/rsi_omega_daemon_v19_0_unified/omega_capability_registry_v2.json`
- phase0/phase4/survival variations for v18 and v19 capability registries.

Several campaign surfaces also have supporting artifacts updated:

- capability runaways,
- objectives and policy IR,
- allowlist entries,
- healthcheck suitepacks,
- baseline metrics and coordinator opcode/program inputs.

The consequence is that operational strategy is now more tightly coupled to explicit lane and policy parameters per pack. Packs are becoming policy templates rather than opaque bundles.

`campaigns/rsi_epistemic_reduce_v1` and phase4d epistemic campaign packs were added/updated in previous commits and are now part of the larger governance arc. Their presence means epistemic reduction and shadow mechanisms can be run under long-run packs with same chain-of-evidence expectations as other campaigns.

## R.7 Native Runtime and Instrumentation Path

The day’s work also extended native-runtime observability and invocation mechanics.

`orchestrator/native/native_router_v1.py`, `orchestrator/native/runtime_stats_v1.py`, and `orchestrator/omega_bid_market_v1.py` were updated, indicating tighter integration for routed capability execution and deterministic runtime telemetry around native modules.

`orchestrator/common/run_invoker_v1.py` and `scripts/run_long_disciplined_loop_v1.py` got changes that matter operationally:

1. invocation orchestration now carries stronger preconditions and evidence expectations,
2. failure/retry behavior is more strictly surfaced to long-run loops,
3. tick discipline is increasingly script-driven and reproducible.

`orchestrator/omega_v18_0/io_v1.py` and `orchestrator/omega_v19_0/goal_synthesizer_v1.py`/`coordinator_v1.py` were also involved in this period of consistency updates. This suggests that not only governance layers but also core IO and planning surfaces were updated to align with the same stronger preflight contract.

There are two notable script-side additions:

- `scripts/preflight_long_run_v1.py` (hardening and readiness checks),
- `scripts/run_epistemic_airlock_closure_v1.py` and `scripts/run_phase4c_real_swap_drill_v1.py` (close-loop operational paths).

These indicate a strong move toward fully scripted, deterministic run phases with explicit evidence handoff.

## R.8 Meta-Core Stage/Active Bundle Reconfiguration

The most concrete RE1-level indicator of this day’s hardening is the active bundle transition visible in:

- `meta-core/active/ACTIVE_BUNDLE`
- `meta-core/active/PREV_ACTIVE_BUNDLE`
- `meta-core/active/ACTIVE_NEXT_BUNDLE`
- `meta-core/active/work/canary_receipt.json`
- `meta-core/active/work/receipt.json`
- `meta-core/active/work/stage.json`.

More significant are the new staged and stored bundle artifacts under:

- `meta-core/stage/bundles/518179d5a11f5b727461a568510905e6df878d3f788dd462f13aecb7144b2a87/...`
- `meta-core/store/bundles/518179d5a11f5b727461a568510905e6df878d3f788dd462f13aecb7144b2a87/...`.

The added JSON artifacts include `constitution.manifest.json`, `kernel_receipt.json`, `omega/omega_activation_binding_v1.json`, `proofs/dominance_witness.json`, `proofs/proof_bundle.manifest.json`, and `ruleset/{accept.ir.json,costvec.ir.json,migrate.ir.json}`.

This addition is important because it demonstrates that bundle-level proof material, kernel rulesets, and dominance-witness structure are being staged as concrete evidence rather than conceptual notes. In source-of-truth terms, this marks the beginning of a stronger “constitutional upgrade lifecycle” as operationally normal, not exceptional.

Any post-hoc governance explanation should now expect stage and store consistency checks to mention bundle IDs and proofs directly.

## R.9 Long-Run Discipline and Safety Harnesses

Long-run control became a central focus. The files modified include both execution and evaluation surfaces:

- `orchestrator/omega_v19_0/microkernel_v1.py`
- `orchestrator/omega_v19_0/eval_cadence_v1.py`
- `orchestrator/omega_v19_0/mission_goal_ingest_v1.py`
- `scripts/run_long_disciplined_loop_v1.py`
- `scripts/preflight_long_run_v1.py`
- `LONG_RUN_PREFLIGHT_SUMMARY_v1.json`.

The changes also extended run profile artifacts (`long_run_profile_v1`) and mission request/receipt schemas. The combined effect is to make run discipline reproducible and auditable at four boundaries:

1. mission admission and profile selection;
2. tick scheduling and dependency routing;
3. evidence and proof generation during operation;
4. preflight summary and summary persistence.

In this architecture, preflight is no longer just a launch guard; it is part of the same evidence ledger. This is key to reducing false-positive stability claims and to making rollback decisions machine-checkable.

## R.10 Epistemic and Shadow Infrastructure Consolidation

The earlier feature cluster in `55ce658` introduced a broad epistemic package and shadow machinery. Since then, the operational side has continued this direction:

- `CDEL-v2/cdel/v19_0/epistemic` packages cover instruction strip, action market, certs, reduction, retention, and proof/verify loops.
- `campaigns/rsi_omega_daemon_v19_0_phase4d_epistemic_airlock/*` files introduce the concrete campaign payloads needed to execute shadow readiness and invariance regimes.
- `tools/omega/epistemics/*` implementations expanded with capture, segment, inference, and ingestion components for model outputs.

This is now not an “experimental branch.” It is integrated into:

- verifier registration,
- campaign pack configuration,
- script orchestration,
- and output schema validation.

One implication is that epistemic artifacts should now be assumed to carry governance relevance. Missing or malformed epistemic receipts are no longer a warning-only condition; they should be treated as evidence that long-run safety transitions cannot be trusted.

## R.11 Test Coverage Growth and Failure Semantics

Test additions are broad and targeted to the new gates:

Committed and working-tree changes include:

- `CDEL-v2/cdel/v19_0/tests_omega_daemon/test_long_run_discipline_v1.py`
- `CDEL-v2/cdel/v18_0/tests_omega_daemon/test_campaign_ge_sh1_patch_registry_detection_v1.py`
- `CDEL-v2/cdel/v18_0/tests_omega_daemon/test_ccap_rollout_registry_v1.py`
- `CDEL-v2/cdel/v18_0/tests_omega_daemon/test_promotion_no_bundle_reason_v1.py`
- `tools/genesis_engine/tests/test_ge_llm_selector_replay_path_v1.py`
- pre-existing but now tightened phase3/phase4 tests in continuity and airlock domains.

This is a meaningful signal: tests are being moved from “do we have the shape?” toward “did the governance semantics hold under constrained transition paths?”. The same logic appears in `scripts/run_epistemic_airlock_closure_v1.py` and long-run preflight gating.

Given CI changes in `.github/workflows/ci.yml` and the new `CI_FULL_GREEN_SUMMARY_v1.json`, validation now has an explicit success artifact and likely a stricter required pass map.

## R.12 Genesis Engine, Tooling, and Automation Progress

The Genesis engine layer also changed with both runtime and test-facing updates:

- `tools/genesis_engine/ge_symbiotic_optimizer_v0_3.py`
- `scripts/generate_ceiling_report_v1.py`
- `scripts/generate_epistemic_canary_bundle_v1.py`
- `scripts/generate_phase3b_phase4_evidence_v1.py`
- `scripts/run_epistemic_airlock_closure_v1.py`.

This reflects a shift where self-improvement workflows are expected to run through the same audit surfaces as normal campaign operations. The system is converging on evidence-first automation rather than manual interpretation.

The uncommitted `debug_*.md` files also suggest that operator-facing documentation and protocol reasoning are being built in parallel with code changes. Treat these as part of the source-of-truth update, because governance operations will need those interpretations to remain consistent.

## R.13 Operationally Relevant Risk Register (After the Delta)

1) Schema/proof synchronization risk  
Large edits in schema sets can create short windows where one layer emits a field another layer does not accept. Because this happened in a single day, any run should pin compatible schema versions and validate end-to-end manifest bundles before full lane activation.

2) Frontier debt semantics risk  
`dependency_debt_state_v1` and `dependency_routing_receipt_v1` now encode frontier forcing. Incorrect threshold configuration (especially `debt_limit_u64` and `max_ticks_without_frontier_attempt_u64`) can trigger heavy locking behavior. All frontier-heavy lanes should include explicit receipts inspection in closeout.

3) Registry lock-in risk  
Many capability registries were changed simultaneously across v18/v19 and phase variants. This enables breadth but increases accidental policy divergence. Keep diffs reviewed per pack type (`phase4b`, `phase4d`, `phase3_market_toy`, `super_unified`, `unified`, `v19_0_long_run_v1`) before promoting to default.

4) Meta-core state-risk  
The active/next bundle transition and new bundle objects are likely correct but raise the cost of rollback mistakes. Rollback drills should be rerun after every new active bundle chain write.

5) Testing and CI expectation risk  
CI hardening increases false-negative noise for local runs if required preflight files are stale. The delta indicates stricter environment requirements around preflight outputs and evidence artifacts.

## R.14 What Changed in Operator Practice

For the closeout window, the updated practice should be:

1. verify that long-run mission and dependency profiles are using the new schema shape (`long_run_profile_v1`, `dependency_debt_state_v1`, `dependency_routing_receipt_v1`);
2. verify that frontier debt counters and hard-lock fields are being written every tick and included in evidence review;
3. verify that every long-run frontier operation has preflight evidence (`LONG_RUN_PREFLIGHT_SUMMARY_v1.json` and script outputs);
4. verify that meta-core stage/work artifacts match `ACTIVE_BUNDLE`/`ACTIVE_NEXT_BUNDLE` pointers before operational interpretation;
5. verify CCAP rollout conditions around patch registry detection and no-bundle reasons using the dedicated tests before enabling new capabilities in frontier lanes;
6. verify epistemic continuity paths via phase4c drills and shadow airlock scripts when native or utility policy transitions are involved.

The important point is not only that functionality exists, but that the operator can now tie each transition to verifiable artifacts.

## R.15 Final Cross-Layer Contract Mapping

The last-day changes effectively reinforce an end-to-end contract:

- Genesis contracts now define additional frontier and utility behavior in `Genesis/schema/v19_0/*` and update v18 event/receipt schemas.
- Verifiers in `CDEL-v2/cdel` and `CDEL-v2/Genesis/schema` now consume and emit those contracts with stronger checks.
- Orchestrators in `orchestrator/*` now drive run behavior using that contract and persist receipts.
- Campaign packs in `campaigns/*` now encode concrete policy and capability selection intent for each phase and lane.
- meta-core artifacts now stage explicit proof packages to move the system across generations only after acceptance gates.
- Genesis engine tooling and test scripts now generate and validate the evidence needed for deterministic replay and post-hoc review.

This is the source-of-truth alignment for 2026-02-22. Future changes should keep this sequence intact and avoid bypassing any one boundary.

## R.16 Evidence Chain Deep-Dive

To keep this update operationally useful for closeout review, the following is a concrete artifact-by-artifact map for the last-day path from raw event to activation.

### R.16.1 Canonical Evidence Spine

At the beginning of a run, the observable system state is still anchored by canonicalized state artifacts and content-addressed references. In practice, this means:

1. campaign pack and mission request files are resolved from registries and profile inputs.
2. mission and long-run policy inputs are validated as schema-bound objects.
3. tick lifecycle code executes and emits raw intermediate state updates.
4. verifier contracts validate outcomes and produce CCAP/tick/receipt artifacts.
5. mutation and promotion layers generate one or more binding artifacts that now include stronger required fields.
6. preflight and disciplined-loop scripts read both live and historical artifacts, generating summary outputs.
7. meta-core staging/verification stages only consume fully materialized and bound artifacts.

The new files in this sequence (`dependency_debt_state_v1`, `dependency_routing_receipt_v1`, `utility_proof_receipt_v1`, and utility policy additions) are now not peripheral. They are the points where ambiguity is removed.

### R.16.2 Frontier Debt Memory as the Deterministic Anti-Stall Switch

The debt memory object update is now persistent and visible every tick through `dependency_debt_state_v1`. This object is not simply accounting; it is the mechanism that keeps frontier pressure explicit and replayable.

The new state flow expresses four distinct facts per tick:

1. frontier pressure accumulation via debt counters.
2. timing of missed or delayed frontier attempts via `ticks_without_frontier_attempt_by_key`.
3. forced frontier activation status via hard-lock fields and debt keys.
4. evidence-level reasoning via dependency routing reason codes and per-tick deltas.

Hard-lock semantics matter for operator interpretation. `hard_lock_active_b` plus debt keys gives a one-line diagnosis of whether a front-loading constraint is a policy choice or a forcing result. That distinction is now machine-detectable and is part of the evidence loop.

### R.16.3 CCAP and Patch Governance Signal Tightening

The CCAP path now has stronger gate points around touched paths, registry state, and non-bundle failure reasons. Changes in:

- `CDEL-v2/cdel/v18_0/verify_ccap_v1.py`
- `CDEL-v2/cdel/v18_0/ccap_runtime_v1.py`
- `CDEL-v2/cdel/v18_0/omega_promoter_v1.py`
- `CDEL-v2/cdel/v18_0/tests_omega_daemon/test_campaign_ge_sh1_patch_registry_detection_v1.py`
- `CDEL-v2/cdel/v18_0/tests_omega_daemon/test_ccap_rollout_registry_v1.py`
- `CDEL-v2/cdel/v18_0/tests_omega_daemon/test_promotion_no_bundle_reason_v1.py`

all point to a stricter interpretation of proposal legitimacy. The practical implication is that a proposal is less likely to pass with missing patch context.

That does not necessarily reduce throughput when the toolchain is clean; it reduces silent ambiguity. If this introduces extra reject signals, the corrective action should be improved patch metadata, not permissive verification.

### R.16.4 Native and Utility Path Tightening

Native routing and utility policy additions are a path where capability enablement is now coupled to proof readiness and receipt completeness. Relevant files include:

- `campaigns/rsi_omega_daemon_v19_0_phase4b_native_transpiler_v1/omega_capability_registry_v2.json`
- `campaigns/rsi_omega_daemon_v19_0_long_run_v1/utility/omega_utility_policy_v1.json`
- `orchestrator/native/native_router_v1.py`
- `orchestrator/native/runtime_stats_v1.py`
- `orchestrator/omega_bid_market_v1.py`
- `scripts/run_epistemic_airlock_closure_v1.py`
- `scripts/preflight_long_run_v1.py`

The new requirement profile is:

1. capability registration must align with policy.
2. utility policy must define required stress/probe signals.
3. runtime stats and telemetry must be present.
4. preflight checks must certify reproducibility and deterministic mode before transition.

If any step is missing, lane promotion should stop at verification and remain in fail-closed posture.

### R.16.5 Epistemic Shadow Chain

The epistemic additions and shadow campaign scaffolds now form a durable chain across generation, verification, and activation boundaries:

- epistemic campaign verifiers and utilities in `CDEL-v2/cdel/v19_0/epistemic`
- shadow airlock and shadow corpus modules in both verifier and campaign layers
- shadow tiers and readiness tests in continuity suites
- phase4d campaign manifests for airlock readiness and invariance.

This chain means epistemic runs have stronger operational expectations: if receipts or invariance checks are absent, the chain should not be interpreted as policy-compliant.

### R.16.6 Meta-Core Bundle Evidence Normalization

The newly staged and stored bundle data under the fixed hash path:

- `meta-core/stage/bundles/518179d5a11f5b727461a568510905e6df878d3f788dd462f13aecb7144b2a87/...`
- `meta-core/store/bundles/518179d5a11f5b727461a568510905e6df878d3f788dd462f13aecb7144b2a87/...`

is not only a runtime convenience path. It is the concrete representation of constitutional evolution:

- explicit constitution manifest,
- kernel proof receipt,
- dominance witness,
- ruleset files for verification behavior.

This confirms that constitutional updates are no longer abstract; they are now first-class artifacts with explicit hash-addressed provenance.

### R.16.7 Preflight as Always-On Safety Layer

Because preflight artifacts and CI summaries are now tightly coupled to script execution, preflight should be treated as a permanent gate:

- `scripts/preflight_long_run_v1.py` should complete with machine-readable artifacts.
- `scripts/run_long_disciplined_loop_v1.py` should fail closed when preflight assumptions are not met.
- `CI_FULL_GREEN_SUMMARY_v1.json` now acts as a compact acceptance marker for this flow.

The operational sequence for long-run work now is:

1. preflight input validation,
2. deterministic dispatch,
3. evidence artifact generation,
4. verifier/receipt validation,
5. staged transition,
6. rollback rehearsal.

Any run missing that sequence should be interpreted as incomplete, even if individual tasks return nominal completion.

## R.17 Extended File Surface Map by Runtime Layer

This list groups recently touched files into the layer they impact for faster incident-level triage.

### R.17.1 RE2 Verification Layer

- `CDEL-v2/Genesis/schema/v18_0/omega_goal_queue_v1.jsonschema`
- `CDEL-v2/Genesis/schema/v18_0/omega_ledger_event_v1.jsonschema`
- `CDEL-v2/Genesis/schema/v18_0/omega_native_runtime_stats_v1.jsonschema`
- `CDEL-v2/Genesis/schema/v18_0/omega_promotion_receipt_v1.jsonschema`
- `CDEL-v2/Genesis/schema/v18_0/omega_subverifier_receipt_v1.jsonschema`
- `CDEL-v2/Genesis/schema/v18_0/omega_tick_outcome_v1.jsonschema`
- `CDEL-v2/Genesis/schema/v18_0/omega_tick_snapshot_v1.jsonschema`
- `CDEL-v2/cdel/v18_0/campaign_ge_symbiotic_optimizer_sh1_v0_1.py`
- `CDEL-v2/cdel/v18_0/ccap_runtime_v1.py`
- `CDEL-v2/cdel/v18_0/omega_bid_market_v1.py`
- `CDEL-v2/cdel/v18_0/omega_promoter_v1.py`
- `CDEL-v2/cdel/v18_0/omega_tick_outcome_v1.py`
- `CDEL-v2/cdel/v18_0/verify_rsi_omega_daemon_v1.py`
- `CDEL-v2/cdel/v18_0/verify_ccap_v1.py`
- `CDEL-v2/cdel/v19_0/omega_promoter_v1.py`
- `CDEL-v2/cdel/v19_0/tests_omega_daemon/test_long_run_discipline_v1.py`
- `CDEL-v2/cdel/v19_0/verify_rsi_omega_daemon_v1.py`.

### R.17.2 RE4 Specification Layer

- `Genesis/schema/v18_0/omega_goal_queue_v1.jsonschema`
- `Genesis/schema/v18_0/omega_ledger_event_v1.jsonschema`
- `Genesis/schema/v18_0/omega_native_runtime_stats_v1.jsonschema`
- `Genesis/schema/v18_0/omega_promotion_receipt_v1.jsonschema`
- `Genesis/schema/v18_0/omega_subverifier_receipt_v1.jsonschema`
- `Genesis/schema/v18_0/omega_tick_outcome_v1.jsonschema`
- `Genesis/schema/v18_0/omega_tick_snapshot_v1.jsonschema`
- `Genesis/schema/v19_0/anti_monopoly_state_v1.jsonschema`
- `Genesis/schema/v19_0/dependency_debt_state_v1.jsonschema`
- `Genesis/schema/v19_0/dependency_routing_receipt_v1.jsonschema`
- `Genesis/schema/v19_0/eval_report_v1.jsonschema`
- `Genesis/schema/v19_0/long_run_profile_v1.jsonschema`
- `Genesis/schema/v19_0/long_run_stop_receipt_v1.jsonschema`
- `Genesis/schema/v19_0/mission_goal_ingest_receipt_v1.jsonschema`
- `Genesis/schema/v19_0/mission_request_v1.jsonschema`
- `Genesis/schema/v19_0/utility_policy_v1.jsonschema`
- `Genesis/schema/v19_0/utility_proof_receipt_v1.jsonschema`.

### R.17.3 RE3 Campaign and Operational Layer

- `campaigns/rsi_omega_daemon_v18_0/omega_capability_registry_v2.json`
- `campaigns/rsi_omega_daemon_v18_0_prod/omega_capability_registry_v2.json`
- `campaigns/rsi_omega_daemon_v19_0/omega_capability_registry_v2.json`
- `campaigns/rsi_omega_daemon_v19_0_llm_enabled/omega_capability_registry_v2.json`
- `campaigns/rsi_omega_daemon_v19_0_long_run_v1/omega_capability_registry_v2.json`
- `campaigns/rsi_omega_daemon_v19_0_long_run_v1/goals/omega_goal_queue_v1.json`
- `campaigns/rsi_omega_daemon_v19_0_long_run_v1/long_run_profile_v1.json`
- `campaigns/rsi_omega_daemon_v19_0_long_run_v1/rsi_omega_daemon_pack_v1.json`
- `campaigns/rsi_omega_daemon_v19_0_long_run_v1/utility/omega_utility_policy_v1.json`
- `campaigns/rsi_omega_daemon_phase0_kernel_autonomy_v1/omega_capability_registry_v2.json`
- `campaigns/rsi_omega_daemon_survival_drill_v1/omega_capability_registry_v2.json`
- `campaigns/rsi_omega_daemon_v19_0_phase4b_native_transpiler_v1/omega_capability_registry_v2.json`
- `campaigns/rsi_omega_daemon_v19_0_phase3_bench/omega_capability_registry_v2.json`
- `campaigns/rsi_omega_daemon_v19_0_phase3_market_toy/omega_capability_registry_v2.json`
- `campaigns/rsi_omega_daemon_v19_0_super_unified/omega_capability_registry_v2.json`
- `campaigns/rsi_omega_daemon_v19_0_unified/omega_capability_registry_v2.json`
- `campaigns/rsi_omega_daemon_v19_0_phase4d_epistemic_airlock/*`.

### R.17.4 Runtime and Orchestration Layer

- `orchestrator/common/run_invoker_v1.py`
- `orchestrator/native/native_router_v1.py`
- `orchestrator/native/runtime_stats_v1.py`
- `orchestrator/omega_bid_market_v1.py`
- `orchestrator/omega_v18_0/coordinator_v1.py`
- `orchestrator/omega_v18_0/goal_synthesizer_v1.py`
- `orchestrator/omega_v18_0/io_v1.py`
- `orchestrator/omega_v19_0/coordinator_v1.py`
- `orchestrator/omega_v19_0/goal_synthesizer_v1.py`
- `orchestrator/omega_v19_0/eval_cadence_v1.py`
- `orchestrator/omega_v19_0/io_v1.py`
- `orchestrator/omega_v19_0/microkernel_v1.py`
- `orchestrator/omega_v19_0/mission_goal_ingest_v1.py`
- `orchestrator/rsi_coordinator_mutator_v1.py`
- `orchestrator/rsi_market_rules_mutator_v1.py`.

### R.17.5 Evidence and Tooling Layer

- `scripts/preflight_long_run_v1.py`
- `scripts/run_long_disciplined_loop_v1.py`
- `scripts/run_epistemic_airlock_closure_v1.py`
- `scripts/run_phase4c_real_swap_drill_v1.py`
- `scripts/generate_ceiling_report_v1.py`
- `scripts/generate_epistemic_canary_bundle_v1.py`
- `scripts/generate_phase3b_phase4_evidence_v1.py`
- `tools/genesis_engine/ge_symbiotic_optimizer_v0_3.py`
- `tools/genesis_engine/tests/test_ge_llm_selector_replay_path_v1.py`
- `tools/omega/epistemics/*`
- `.github/workflows/ci.yml`
- `CI_FULL_GREEN_SUMMARY_v1.json`.

### R.17.6 Constitutional Layer

- `meta-core/active/ACTIVE_BUNDLE`
- `meta-core/active/ACTIVE_NEXT_BUNDLE`
- `meta-core/active/PREV_ACTIVE_BUNDLE`
- `meta-core/active/work/canary_receipt.json`
- `meta-core/active/work/receipt.json`
- `meta-core/active/work/stage.json`
- `meta-core/stage/bundles/518179d5a11f5b727461a568510905e6df878d3f788dd462f13aecb7144b2a87/*`
- `meta-core/store/bundles/518179d5a11f5b727461a568510905e6df878d3f788dd462f13aecb7144b2a87/*`.

## R.18 Guidance for the Next Day's Update

The next source-of-truth increment should include three mandatory diffs:

- a dedicated section on any `v19_0` schema backward-compatibility migration decisions;
- a full list of new reason codes introduced in verifiers and routing receipts;
- any changes to `ACTIVE_*` and `meta-core` bundle id transitions.

Without these, continuity across governance decisions becomes ambiguous because hardening updates can change what “ready,” “forced,” or “rejected” mean in practice.

For consistency, include in each update:

1. every changed schema file, not only new campaign files.
2. the producing and consuming module mapping for each schema.
3. all new reason-code strings and the modules that emit them.

This keeps source-of-truth and operational decisioning synchronized.

## R.19 Closing Governance Model Update

To make the last-day changes durable in governance practice, this release should be interpreted as a transition from “feature-specific correctness” to “transition-specific correctness.” Earlier hardening often focused on making one checker stronger. This update made transitions themselves observable and constrained.

There are four explicit governance checks now visible in practice:

1. structural schema congruence across v18/v19 verifier boundaries,
2. behavioral forcing state in long-run debt and frontier routing,
3. proof-chain completeness in preflight and disciplined-loop scripts,
4. bundle-level constitutional consistency in meta-core.

When all four checks succeed together, the system can progress from exploratory lanes into production lanes with lower rollback risk. Missing any one check should be treated as a hard stop, even if immediate runtime telemetry appears healthy.

The update also narrows the interpretation of “policy intent.” Capability intent now lives in at least three places:

- registries indicate which capabilities are legally selectable in a pack,
- profiles declare when and why those capabilities are admissible,
- receipts prove whether the run respected those constraints under observed state.

This creates a robust three-way contract. If a capability appears enabled in a registry but is not represented in profile lanes, the outcome may still appear plausible at the runtime layer until a routing receipt or debt state shows a contradiction. If policy intent and profile intent align but receipts fail, the issue is execution governance and not capability definition.

From a closeout perspective, this implies that every incident or anomaly report should include:

- the pack selection snapshot,
- the profile and profile version used,
- the dependency state row for the affected tick,
- the subverifier, utility proof, and promotion receipts,
- and the meta-core stage receipt if a transition was attempted.

That evidence set reduces ambiguity and speeds failure attribution.

One practical benefit of this release is that it gives operators a deterministic escalation path for frontier-heavy behavior:

1. allow the frontier to stall and collect debt,
2. inspect debt and lock state,
3. inspect route reason codes and utility proof receipts,
4. force frontier attempt only if deterministic predicates say so,
5. if forced attempt fails, reject transition and re-run preflight.

This replaces trial-and-error runbook habits with deterministic, auditable steps.

The residual governance debt after this update is mostly integration hygiene:

- remove any accidental divergence between old and new schema expectations across run products,
- normalize log naming for the newly added frontier and utility proof receipts,
- ensure CI and preflight scripts fail with explicit code-level reasons instead of generic shell errors,
- and make the RE1 bundle path part of normal operational checklists.

The target state for the next 24-hour cycle is therefore not more gates. It is cleaner gate interpretation and fewer hidden assumptions.

## R.20 What the Current Diff Actually Changes in Runtime Behavior

This section translates the worktree diff into operational behavior. The change set is no longer "new feature" centered; it is mostly **policy-control hardening**.

### Frontier Control Becomes State-Machine Driven

`orchestrator/omega_v19_0/microkernel_v1.py` and the new `dependency_*` schema set now do three concrete things:

1. **Track frontier pressure explicitly** in state artifacts (`dependency_debt_state_v1`):
   - debt counters by key,
   - hard-lock indicators,
   - pending frontier goals,
   - last frontier attempts,
   - failed-patch and failed-shape ban maps.

2. **Drive deterministic routing decisions** for every tick:
   - `routing_selector_id` is now persisted in decision receipts,
   - forced-heavy dispatch can be explicitly signaled and checked later,
   - frontier attempts and counts are replay-coupled to policy rationale.

3. **Preserve failure memory** to prevent repeated blind retries:
   - failed patches and failed nontriviality shapes are propagated into dispatch-time skip filters,
   - repeated candidate families can be blocked from re-entry automatically.

In practical terms, this converts many “soft” heuristics into materialized state transitions.

### CCAP Path Now Requires Stronger Evidence of Substantial Changes

`tools/genesis_engine/ge_symbiotic_optimizer_v0_3.py`, `CDEL-v2/cdel/v19_0/omega_promoter_v1.py`, and `CDEL-v2/cdel/v19_0/verify_rsi_omega_daemon_v1.py` now treat candidate proposal quality as an auditable artifact, not a best-effort signal.

- SH-1 now emits a **candidate precheck receipt** per dispatch (`candidate_precheck_receipt_v1`) with:
  - selected-for-ccap decision,
  - drop reason (policy/shape/parse/threshold/repeat),
  - candidate ordering/hash details.
- SH-1 computes and attaches a **nontriviality certificate** (`nontriviality_cert_v1`) for selected candidates.
- `omega_promoter_v1.py` rewrites subverifier receipts to include that certificate and rejects frontier-heavy selections that do not provide required nontrivial deltas.
- v19 verifier now checks the candidate precheck receipt before accepting promotion input, so an omitted/invalid precheck is a hard verifier failure.

Net effect: accepted frontier proposals must now carry both routing context and structural evidence.

### Long-Run Discipline Gets Hard Preconditions and Telemetry

`scripts/preflight_long_run_v1.py` and `scripts/run_long_disciplined_loop_v1.py` now enforce and record concrete governance gates:

- preflight now reports repo cleanliness, activation mode safety, frontier registry integrity, and frontier-lane wiring preconditions;
- replay validation now reports failure classes explicitly instead of only aggregate pass/fail;
- frontier rows are scored with attempt-quality classes (heavy OK / valid but no utility / invalid);
- hard-lock and forced-frontier events are serialized into tick summaries for post-run audit;
- strict “must-have” signals were added for frontier promotion pipeline presence and counted frontier attempts.

This creates deterministic preconditions for auto-run campaigns and a fixed signal schema for postmortems.

### CCAP/Tx Verification Tolerance + Fail-Fast Paths

`CDEL-v2/cdel/v18_0/ccap_runtime_v1.py`, `CDEL-v2/cdel/v18_0/verify_ccap_v1.py`, and `orchestrator/common/run_invoker_v1.py` now support `OMEGA_CCAP_ALLOW_DIRTY_TREE` as a controlled behavior switch.

- In tolerant mode, snapshotting uses tracked workspace files instead of index-only state.
- CCAP verifier computes base-tree with tolerant logic when explicitly enabled.
- If base-tree hashing fails, CCAP returns an explicit `BASE_TREE_UNAVAILABLE` refutation instead of continuing.
- Invocation plumbing now carries this env var through subrun environments.

That is an operator control, not a default bypass: it relaxes snapshot strictness only when intentionally set.

### SH-1 / Mutator Reliability Improvements

`orchestrator/rsi_coordinator_mutator_v1.py` and `orchestrator/rsi_market_rules_mutator_v1.py` now move failure modes from silent exits to recoverable outputs.

- mutators can fallback to deterministic template patch generation on backend failures,
- base-tree identity is computed with tolerant mode,
- parse/apply mismatches are written into failure artifacts instead of returning partial/noisy state,
- patch touched-path mismatches can be repaired with a template fallback.

This reduces stochastic failure behavior in frontier-heavy mutation runs and makes post-run diagnosis deterministic.

### RE1 Bundle Activity Became a Real-Time Governance Signal

`meta-core/active/*` and the newly present staged/store bundle IDs indicate a live constitutional transition path with proof material:

- new dominance witnesses,
- rule sets and proof manifests,
- new active/next pointers and work receipts.

In this update, activation is no longer only an operator abstraction; it is represented as concrete hash-bound proof artifacts and audit points.

### Practical Effect on Decision-Making

The operator-facing behavior changed from:

- "Run produced status X"

to:

- "Run produced status X, along with explicit frontier debt, routing selector, quality class, precheck reasons, and verifier receipts that are replay-comparable."

That is the main effect: every frontier-heavy action now has a deterministic paper trail from decision to activation.

*End Appendix R.*

---

# Appendix Z: Repository Coverage Addendum (2026-02-22)

This addendum captures repository surfaces that were present in the codebase but not explicitly represented in prior Source of Truth sections. It prioritizes operationally relevant assets and excludes cache-only noise (`__pycache__`, `.pytest_cache`, transient workdirs).

## Z.1 Governance and Authority Surfaces Added

- `authority/boundary_event_sets/boundary_event_set_omega_v1.json`
- `authority/build_recipes/build_recipes_v1.json`
- `authority/dsbx_profiles/dsbx_profile_core_v1.json`
- `authority/gir_integrators/gir_active_set_v1.json`

These are part of executable governance semantics (boundary events, build realization, sandbox profile identity, GIR active set selection) and should be treated as trust-adjacent configuration.

## Z.2 Runtime Config Surfaces Added

- `configs/mission_request_v1.json`
- `configs/mission_request_v1.jsonschema`
- `configs/omega_axis_gate_exemptions_v1.json`
- `configs/sealed_thermo_fixture_v1.toml`
- `configs/sealed_thermo_grand_challenge_heldout.toml`
- `configs/sealed_thermo_live_capture_v1.toml`

These files materially influence mission admission, gate behavior, and thermo fixture modes.

## Z.3 Genesis API/Extensions Surfaces Added

- `Genesis/api/evaluate_v1.openapi.yaml`
- `Genesis/extensions/caoe_v1_1/`
- `Genesis/extensions/code_patch_v1/`
- `Genesis/scripts/run_ccai_conformance_all.sh`
- `Genesis/receipt_examples/pass_receipt.json`

These expand the RE4 layer beyond schemas/docs/conformance vectors by adding API contracts and extension specs used by adjacent tooling.

## Z.4 CDEL-v2 Support Assets Added

- `CDEL-v2/spec/schemas/constraint_spec.v1.schema.json`
- `CDEL-v2/suitepacks/` (including `grand_challenge_heldout_v1.suitepack`, `omega_dev_v1.suitepack`)
- `CDEL-v2/sealed_suites/`
- `CDEL-v2/analysis/`
- `CDEL-v2/bench/`

These are not primary verifier entrypoints, but they are important verifier-adjacent assets for analysis, benchmark workflows, and sealed evaluation bundles.

## Z.5 Legacy/Parallel Orchestrator and Daemon Lines Added

- `orchestrator/metasearch_v16_1/`
- `orchestrator/sas_code_v12_0/`
- `orchestrator/sas_science_v13_0/`
- `orchestrator/val_v17_0/`
- `orchestrator/tools/`
- `daemon/rsi_sas_kernel_v15_0/`
- `daemon/rsi_sas_kernel_v15_1/`
- `daemon/rsi_sas_metasearch_v16_0/`

These directories preserve operational lineage and are relevant for replay and historical campaign compatibility.

## Z.6 Additional Tooling Surfaces Added

- `tools/math_checker_v1/checker.py`
- `tools/v19_hypothesis/run_ladder.py`
- `tools/v19_hypothesis/scan_axis_bundle_coverage.py`

These are utility surfaces used in diagnostics/hypothesis workflows and should be considered part of the practical operator toolbox.

## Z.7 Evidence, Baseline, and Legacy Forensics Packs Added

- `baselines/pi0_grand_challenge_v1/baseline_report_v1.json`
- `smoking_gun_v11_0_2026-02-04/README.md`
- `smoking_gun_v11_0_2026-02-04/arch_synthesis_toolchain_manifest_v1.json`
- `smoking_gun_v11_0_2026-02-04/state/`
- `docs/ENDGAME_EVIDENCE_PACK_v1.md`
- `docs/eudrs_u/EUDRS_U_v1_0_SCIENTIST_HANDOFF.md`
- `docs/eudrs_u/EUDRS_U_v1_0_SPEC_OUTLINE.md`
- `docs/llm_backends.md`
- `docs/phase1_native_module_pipeline_v0_1_proof.md`
- `docs/phase3_nuisance_v1_2_results.md`
- `docs/phase_u2_4_swarm_scaling_plan.md`

These artifacts are not transient notes; they encode reproducibility, handoff, and hardening evidence with operational relevance.

## Z.8 Test Harness and Root Test Coverage Added

Core test wiring:

- `conftest.py`
- `pytest.ini`

Unlisted root tests now explicitly tracked:

- `test_native_module_pipeline_v0_1.py`
- `test_orchestrator_bid_market_parity_v1.py`
- `test_v19_axis_gate_ccap_effective_touched_paths.py`
- `test_v19_axis_gate_propagation.py`
- `test_v19_gate_matrix_e2e.py`
- `test_v19_ladder_evidence_pipeline_v1.py`
- `test_v19_ladder_harness.py`
- `test_v19_phase1_native_modules_pack_e2e.py`
- `test_v19_predation_market_e2e_determinism.py`
- `test_v19_promotion_cwd_subrun_required.py`
- `test_v19_real_run_uses_subrun_cwd.py`
- `test_v19_tick_gate_matrix_e2e.py`
- `test_v19_tier2_determinism.py`
- `test_v19_wiring_smoke.py`
- `test_vision_stage0_e2e.py`
- `test_vision_stage1_e2e.py`
- `test_vision_stage2_e2e.py`

## Z.9 Campaign Inventory Delta (Legacy + Specialized Packs)

The campaign surface extends significantly beyond the previously summarized set. Additional directories with operational/history value include:

- `campaigns/grand_challenges`
- `campaigns/rsi_agi_orchestrator_llm_v1`
- `campaigns/rsi_alignment_v7_0`
- `campaigns/rsi_alignment_v8_0`
- `campaigns/rsi_alignment_v9_0`
- `campaigns/rsi_arch_synthesis_v11_0`
- `campaigns/rsi_boundless_math_v8_0`
- `campaigns/rsi_boundless_science_v9_0`
- `campaigns/rsi_coordinator_mutator_v1`
- `campaigns/rsi_daemon_v6_0`
- `campaigns/rsi_daemon_v7_0`
- `campaigns/rsi_daemon_v8_0_math`
- `campaigns/rsi_eudrs_u_dmpl_plan_v1`
- `campaigns/rsi_eudrs_u_eval_cac_v1`
- `campaigns/rsi_eudrs_u_index_rebuild_v1`
- `campaigns/rsi_eudrs_u_ontology_update_v1`
- `campaigns/rsi_eudrs_u_qxrl_train_v1`
- `campaigns/rsi_eudrs_u_train_v1`
- `campaigns/rsi_eudrs_u_vision_index_build_v1`
- `campaigns/rsi_eudrs_u_vision_perception_v1`
- `campaigns/rsi_ge_symbiotic_optimizer_sh1_v0_1`
- `campaigns/rsi_market_rules_mutator_v1`
- `campaigns/rsi_model_genesis_v10_0`
- `campaigns/rsi_omega_apply_shadow_proposal_v1`
- `campaigns/rsi_omega_daemon_v18_0_phase1_native_modules_v1`
- `campaigns/rsi_omega_daemon_v19_0_phase1_native_modules_v1`
- `campaigns/rsi_omega_daemon_v19_0_phase3_death_test`
- `campaigns/rsi_omega_daemon_v19_0_phase3_market_mutator`
- `campaigns/rsi_omega_daemon_v19_0_phase3_mutator`
- `campaigns/rsi_omega_native_module_v0_1`
- `campaigns/rsi_omega_phase0_immune_repair_ccap_v0_1`
- `campaigns/rsi_omega_phase0_victim_ccap_v0_1`
- `campaigns/rsi_omega_self_optimize_core_v1`
- `campaigns/rsi_omega_skill_alignment_v1`
- `campaigns/rsi_omega_skill_boundless_math_v1`
- `campaigns/rsi_omega_skill_boundless_science_v1`
- `campaigns/rsi_omega_skill_eff_flywheel_v1`
- `campaigns/rsi_omega_skill_model_genesis_v1`
- `campaigns/rsi_omega_skill_ontology_v1`
- `campaigns/rsi_omega_skill_persistence_v1`
- `campaigns/rsi_omega_skill_swarm_v1`
- `campaigns/rsi_omega_skill_thermo_v1`
- `campaigns/rsi_omega_skill_transfer_v1`
- `campaigns/rsi_polymath_conquer_domain_v1`
- `campaigns/rsi_polymath_sip_ingestion_l0_v1`
- `campaigns/rsi_real_csi_v2_2`
- `campaigns/rsi_real_demon_v3`
- `campaigns/rsi_real_demon_v4`
- `campaigns/rsi_real_demon_v5_autonomy`
- `campaigns/rsi_real_demon_v6_efficiency`
- `campaigns/rsi_real_demon_v8_csi`
- `campaigns/rsi_real_demon_v9_hardening`
- `campaigns/rsi_real_flywheel_v2_0`
- `campaigns/rsi_real_hardening_v2_3`
- `campaigns/rsi_real_ignite_v1`
- `campaigns/rsi_real_integrity_v1`
- `campaigns/rsi_real_omega_v4_0`
- `campaigns/rsi_real_onto_v2`
- `campaigns/rsi_real_portfolio_v1`
- `campaigns/rsi_real_recursive_ontology_v2_1`
- `campaigns/rsi_real_recursive_ontology_v2_1_source`
- `campaigns/rsi_real_recursive_ontology_v2_1_target`
- `campaigns/rsi_real_science_v1`
- `campaigns/rsi_real_swarm_v3_0`
- `campaigns/rsi_real_swarm_v3_1`
- `campaigns/rsi_real_swarm_v3_2`
- `campaigns/rsi_real_swarm_v3_3`
- `campaigns/rsi_real_thermo_v5_0`
- `campaigns/rsi_real_transfer_v1`
- `campaigns/rsi_sas_code_v12_0`
- `campaigns/rsi_sas_kernel_v15_0`
- `campaigns/rsi_sas_kernel_v15_1`
- `campaigns/rsi_sas_math_v11_0`
- `campaigns/rsi_sas_math_v11_1`
- `campaigns/rsi_sas_math_v11_2`
- `campaigns/rsi_sas_math_v11_3`
- `campaigns/rsi_sas_metasearch_v16_0`
- `campaigns/rsi_sas_metasearch_v16_1`
- `campaigns/rsi_sas_science_v13_0`
- `campaigns/rsi_sas_system_demon_v14_0`
- `campaigns/rsi_sas_system_v14_0`
- `campaigns/rsi_sas_val_v17_0`

## Z.10 Explicitly Excluded As Non-Canonical/Transient

To keep Source of Truth focused, the following remain intentionally excluded from primary architectural mapping unless needed for incident analysis:

- cache/transient directories: `__pycache__`, `.pytest_cache`, `.omega_v18_exec_workspace`, `tmp_ek_meta`
- local/debug scratch docs not part of protocol/state contracts: `debugging_1.md`, `debug_2.md`, `master_debug.md`

This exclusion is documentation scope control, not a claim that those files never matter operationally.

## Z.11 Worktree Delta (Current Local Changes)

As-of `2026-02-22`, the working tree contains changes that materially alter how frontier-heavy long-run behavior is decided, proved, and rejected. This is now more than refactoring: it is a control-surface upgrade.

### What the changed modules do

- `orchestrator/omega_v19_0/microkernel_v1.py`: turns long-run frontier decisions into first-class state. It records debt and hard-lock state (`dependency_debt_state_v1`), tracks frontier attempts, and can force heavy SH-1 dispatch deterministically with explicit reasons when frontier progress stalls.

- `tools/genesis_engine/ge_symbiotic_optimizer_v0_3.py`: expands SH-1 from “generate patch” to “generate verifiable evidence for a patch.” It now writes per-candidate precheck receipts (`candidate_precheck_receipt_v1`) and nontriviality certificates for frontier candidates, so failed or low-signal patch shapes are filtered before they reach promotion as much as possible.

- `CDEL-v2/cdel/v19_0/omega_promoter_v1.py` and `CDEL-v2/cdel/v18_0/omega_promoter_v1.py`: tighten promotion rejection semantics for mutator dispatches. They infer explicit `NO_BUNDLE_*` reason codes instead of collapsing failures into generic no-promotion outcomes, and include nontriviality evidence in subverifier receipts.

- `CDEL-v2/cdel/v18_0/verify_ccap_v1.py` + `CDEL-v2/cdel/v18_0/ccap_runtime_v1.py`: add controlled tolerance for dirty working trees (`OMEGA_CCAP_ALLOW_DIRTY_TREE`). When enabled, CCAP can hash/validate from repository working contents instead of strict git-index-only tree IDs. If that cannot be computed, it now emits `BASE_TREE_UNAVAILABLE` as a typed refutation.

- `orchestrator/common/run_invoker_v1.py`: ensures that CCAP-specific env controls (for example `OMEGA_CCAP_ALLOW_DIRTY_TREE`) are carried to invocations, so verifier and execution agree on how the snapshot is interpreted.

- `CDEL-v2/cdel/v18_0/verify_rsi_omega_daemon_v1.py` + `CDEL-v2/cdel/v19_0/verify_rsi_omega_daemon_v1.py`: harden replay checks by allowing a bounded set of extra environment keys and by validating frontier/utility control artifacts explicitly (forced frontier overrides, utility policy IDs, and runtime stat source linkage).

- `scripts/preflight_long_run_v1.py`: adds stronger startup and replay-time hard stops for long-run mode (activation mode, dirty-tree acceptance, frontier wiring integrity, required frontier signal rows, and stronger ledger/reason checks).

- `scripts/run_long_disciplined_loop_v1.py`: turns frontier long-run behavior into measurable telemetry: hard-lock transitions, frontier attempt quality classes, and explicit stop reasons for failed frontier progression.

- `CDEL-v2/Genesis/schema/v18_0/*` and `Genesis/schema/v19_0/*`: add/extend contracts to match the runtime logic above, including `candidate_precheck_receipt_v1`, `nontriviality_cert_v1`, `dependency_debt_state_v1`, `utility_policy_v1`, `dependency_routing_receipt_v1`, and expanded reason-code enums.

- Campaign and profile updates in `campaigns/rsi_omega_daemon_v19_0_long_run_v1/*`, plus `omega_capability_registry_v2.json` edits across daemon packs: they wire the new long-run control policy (frontier lanes, utility classing, and hard-lock routing) into executable runtime configuration.

- `meta-core/active` and bundle artifacts under `meta-core/stage|store/bundles/*`: reflect an attempted deterministic constitutional transition path with newly generated proof material and dominance/witness artifacts.

### Why this section exists

This section intentionally diverges from the architectural “static” appendices by tracking **operational state**: what is currently staged or changed in this workspace, including transitional activation artifacts and policy updates that are still under active iteration. Use `git status` for exact path-level truth; this section is the human-readable index.

*End Appendix Z.*
