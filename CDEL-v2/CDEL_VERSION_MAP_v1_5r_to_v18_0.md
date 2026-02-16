# CDEL Version Map (v1.5r -> v18.0)

This document is a thorough walkthrough of what each CDEL version lineage does, what changed over time, and how integrated the stack is today. The focus is practical: what each version is responsible for, what artifacts/verifiers it introduced, and how those pieces fit into a broader system.

## Executive Summary

CDEL evolved as a **versioned verification stack**, not as a single rewrite-each-release codebase. That means each version generally preserves its own contracts and verifiers while later versions add new capability domains. The result is a layered architecture where old versions are still meaningful as replay verifiers and compatibility anchors.

On your architecture question directly: the versions are **neither fully orthogonal nor fully disjoint**. They are partially modular (different domains per version), but there is cross-version reuse (notably canonical hashing/schema utilities) and explicit top-layer wiring in modern versions (especially `v18_0`) that can call subverifiers for older campaign families. So the system is best viewed as an evolutionary tree with a unifying control layer emerging on top, not a clean greenfield microkernel where every module plugs in through one universal ABI.

If your goal is one continuous autonomous loop, you still need unification wiring: campaign registry, dispatch policy, subverifier routing, promotion/activation policy, and shared state contracts. Much of that exists in newer omega/orchestrator paths, but legacy versions remain version-specific capabilities rather than one flattened runtime.

---

## v1.5r (Foundation Runtime)

`v1_5r` is the first strongly structured RSI foundation in this tree. It establishes a broad runtime skeleton that later lines keep reusing conceptually: campaign execution, proposal generation, portfolio handling, diagnostics, and explicit replay verifiers for core artifact families. From the directory shape, this version is less about one narrow algorithm and more about establishing governance rails around iterative self-improvement runs. You can see this in its mix of `campaign`, `proposals`, `proposers`, `portfolio`, `suite_eval`, and integrity/trackers.

The verification model in this version is already explicit and split by concern (`ignition`, `integrity`, `portfolio`), which signals an early design decision: don’t trust runtime behavior unless artifacts can be replay-checked and hash-consistent. That fail-closed pattern becomes a recurring CDEL identity. Another key foundation is the internal DSL and SR-CEGAR-style structure (`family_dsl`, `sr_cegar`) suggesting family-level or strategy-space exploration under constrained semantics instead of unconstrained code mutation.

Practically, `v1.5r` should be read as “the control-plane seed.” It may not yet have the later specialized domains (math, science, code, system kernels), but it defines the governance vocabulary those domains inherit: campaign epochs, bundles, promotions, integrity boundaries, and replay-first assurance. Even when later versions replace most implementation details, this version’s decomposition of runtime vs verifier concerns remains architecturally important.

## v1.6r (Transfer + Ontology v2)

`v1_6r` takes the v1.5r substrate and expands it with stronger semantic and transfer machinery. The notable additions include ontology versioning (`ontology_v2`), transfer tracking (`rsi_transfer_tracker.py`), and corresponding replay verifiers (`verify_rsi_ontology_v2.py`, `verify_rsi_transfer.py`). This indicates a pivot from merely running campaigns and tracking portfolios toward encoding what kinds of conceptual movement between capabilities are allowed and how to certify that movement.

Compared with v1.5r, v1.6r keeps the broad operational skeleton (campaign, proposals/proposers, suite eval, diagnostics) but adds more representational discipline. The “witness/generalizer” artifacts imply that transfer isn’t treated as ad-hoc success metrics; it is represented by explicit artifacts that can be validated. This helps shift the stack toward compositional learning claims: not just “did it improve?” but “what structure was transferred, under what ontology constraints, and can replay confirm it?”

From an integration perspective, v1.6r is still foundational rather than isolated. It sits in a direct lineage from v1.5r and introduces concepts that later versions repackage in domain-specific forms (e.g., math/science/system variants of policy, selection, promotion, and ledgering). The core contribution is semantic hardening: moving from campaign bookkeeping toward certified meaning-preserving transitions.

If you were modernizing this era today, v1.6r is where you would mine invariant definitions for transfer correctness, because it turns transfer into a first-class verifiable object rather than runtime side effects.

## v1.7r (Canon Core + Demon v3/Science Track)

`v1_7r` is a major structural anchor because it introduces or stabilizes utilities that many later versions depend on, especially canonical JSON/hashing (`canon.py`). In practical terms, this becomes a shared cryptographic normalization layer across the repository. When later verifiers import from `v1_7r.canon`, they are effectively inheriting deterministic encoding/hash semantics established in this period. That alone makes v1.7r non-optional in understanding cross-version coupling.

Functionally, v1.7r also advances the demon/science framing (`verify_rsi_demon_v3.py`, `verify_rsi_science.py`) and includes ontology/macros ecosystems (`ontology_v3`, `macros_v2`, science modules). The stack starts to separate “semantic substrate” from “campaign execution” more clearly: ontology/macro ledgers can evolve while campaign logic consumes those artifacts. That decomposition later appears again in SAS-era pipelines where IR generation, selection, evaluation, and verification are distinct stages.

v1.7r is also where you can see the emergence of reusable determinism contracts as infrastructure, not campaign-specific code. Instead of every version rolling its own hash/serialization rules, the system centralizes them. This is a key reason the overall architecture is not disjoint: even very new modules in v18 often still rely on canonicalization patterns rooted here.

In short, v1.7r plays two roles simultaneously: it is a capability step in the demon/science lineage, and it is a long-lived infrastructure dependency for deterministic artifact identity across many future versions.

## v1.8r (Demon v4 + Metabolism)

`v1_8r` tightens the demon line with metabolism-related runtime behavior while retaining replay-verification discipline via `verify_rsi_demon_v4.py`. Relative to v1.7r, this looks like a targeted specialization: less about broad foundation building and more about improving how the demon loop internally manages context, work vectors, and throughput-like properties under deterministic constraints.

The presence of `metabolism_v1` and its test coverage indicates a design move toward runtime efficiency/flow mechanics within the verifiable campaign lifecycle. Rather than treating each campaign epoch as a static evaluation, v1.8r appears to model dynamic processing quality: cache behavior, context hashing paths, and translation/work-vector quality improvements are represented and testable. That matters because later “efficiency/flywheel/optimization” phases in v2.x can then build on a better behaved demon substrate.

Architecturally, v1.8r still depends on earlier infrastructure (especially canonicalization and ontology/macro interactions), so it is neither orthogonal nor standalone. It is better seen as a demon-runtime refinement layer in the same family tree. The verifier’s job remains replay safety, but the runtime’s job becomes more nuanced: deterministic handling of richer internal state dynamics.

If you want the shortest characterization: v1.8r is where demon execution stops being just campaign orchestration and starts looking like a controlled state machine with measurable internal metabolism, without giving up fail-closed verification semantics.

## v1.9r (Autonomy Emphasis)

`v1_9r` continues the demon trajectory and introduces explicit autonomy framing (`autonomy.py`) while advancing verification to `verify_rsi_demon_v5.py`. This phase appears focused on decision-loop independence under constraints: what the system can choose to do next, how those choices are encoded, and how replay checks ensure those choices stayed within contract.

Compared with v1.8r’s metabolism orientation, v1.9r pushes more into control logic and policy shape. The module inventory suggests demon + metabolism are still present, but autonomy is now first-class. That usually implies higher coupling to policy and capability registry concerns: an autonomy mechanism is only meaningful if the allowed action surface is constrained and auditable. In CDEL terms, this normally manifests as tighter artifact contracts and explicit verifier checks for state transitions.

v1.9r is important because it bridges the earliest demon-era runtime into the v2.x phase where efficiency, recursive ontology, and code self-improvement become formalized tracks. You can think of v1.9r as the last pre-v2 checkpoint where autonomy is established before aggressive capability expansion begins.

From a system-integration perspective, this version is not an endpoint. It provides a behavior contract that later versions reinterpret with stronger hardening and richer domains. The value today is historical compatibility and semantic continuity: if you need to reason about why v2+ verifiers expect certain autonomy/attempt structures, v1.9r gives that context.

## v2.0 (Efficiency + Flywheel)

`v2_0` introduces an explicit efficiency/flywheel phase, with both demon verification (`verify_rsi_demon_v6.py`) and a flywheel verifier (`verify_rsi_flywheel_v1.py`). This is a meaningful shift from “can the loop run?” to “can the loop sustain and compound improvement under deterministic accounting?” The module `efficiency.py` suggests runtime economics became codified rather than implicit.

What changes architecturally is that progress is now expected to be measurable in structured terms, not only pass/fail outcomes. Flywheel framing typically implies repeated attempts where gains must be retained and regressions detected. In a fail-closed verifier stack, that usually means stronger chain checks and stricter artifact dependencies across iterations. So v2.0 can be viewed as the first mature attempt to turn iterative self-improvement into a certifiable process dynamic.

This version still inherits earlier demon/autonomy semantics and canonicalization utilities, reinforcing that versions are layered. It is not a cleanly separate subsystem; it is a new lens applied to the same broader run-verification discipline.

If you are mapping system intent, v2.0 is where the project starts caring about sustained curve shape rather than single-epoch correctness. That perspective echoes much later in scorecards/temperature/runaway-style mechanisms in v18, even though implementation details are entirely different.

It also makes iteration quality itself a governed artifact, not only an emergent outcome.

## v2.1 (Recursive Ontology)

`v2_1` deepens the v2 line with recursive ontology and auto-concept expansion (`autoconcept.py`, `opt_ontology.py`) plus paired verifiers (`verify_rsi_demon_v7.py`, `verify_rsi_recursive_ontology_v1.py`). This indicates an attempt to formalize not only performance loops but conceptual self-organization: how definitions, abstractions, or ontology fragments can evolve while preserving constraints.

The key distinction from v2.0 is representational recursion. Efficiency/flywheel asks “are we improving?”; recursive ontology asks “what conceptual scaffolding are we building, and does it remain coherent under replay?” In deterministic verification terms, that introduces new failure modes: ontology drift, incompatible recursive updates, and non-replayable concept evolution. The dedicated recursive ontology verifier suggests these are checked explicitly rather than hand-waved.

v2.1 also sets up conceptual precedent for later SAS IR families (math/code/science/system) where candidate generation and selection depend heavily on formal representations. Even if the concrete data structures differ, the pattern of constrained representational evolution originates here.

Integration-wise, v2.1 remains tightly connected to earlier layers. It still sits on shared canonical/hash assumptions and demon run structures. So this is not a disjoint branch; it is a deepening of the same branch toward formal concept recursion.

In short: v2.1 is the version where CDEL starts treating ontology evolution itself as a certified object of computation.

## v2.2 (CSI: Code Self-Improvement)

`v2_2` is the first explicit CSI (Code Self-Improvement) milestone. The module set (`autocodepatch.py`, `code_patch.py`, `csi_bench.py`, `csi_meter.py`) shows a deliberate move to patch-level improvement attempts with measurable evaluation. Two verifiers reflect this split: `verify_rsi_csi_v1.py` for CSI runs and `verify_rsi_demon_v8.py` for demon attempts in this regime.

This phase is significant because the object under verification becomes source-level transformation, not just policy/portfolio evolution. That requires additional safety gates: patch legality, forbidden imports/paths, deterministic tree hashing, and benchmark output consistency. The tests in this area strongly suggest fail-closed handling of code-modification attempts when constraints are violated.

From a systems perspective, v2.2 introduces the core shape that later appears in modern CCAP flows: propose a patch-like artifact, evaluate it under controlled conditions, and verify all receipts deterministically. The modern implementation is more elaborate, but the conceptual pipeline starts here.

v2.2 is therefore a bridge between early autonomy/demon lines and later universal patch governance. It’s still embedded in the layered architecture (shared canon, inherited run semantics), but it opens a major new axis: controlled self-editing with certifiable evaluation.

If you need one takeaway: v2.2 turns self-improvement from abstract strategy changes into concrete code mutation attempts with hard replay constraints.

A practical implication is that this era defines many of the compliance-style checks later generalized by modern patch governance layers.

## v2.3 (Constitutional Hardening)

`v2_3` adds hardening around an immutable core (`immutable_core.py`) and verifies both demon attempts and hardening conditions (`verify_rsi_demon_v9.py`, `verify_rsi_hardening_v1.py`). This is where the stack explicitly says: some regions must remain protected even during self-improvement.

Compared with v2.2 CSI, which opens controlled patching, v2.3 introduces constitutional boundaries. The architecture now has two simultaneous goals: allow improvement attempts and prevent unauthorized mutation of critical trust anchors. The hardening verifier likely enforces lock integrity, protected path constraints, and consistency of core receipts. In effect, this creates a governance membrane around self-modification.

This design decision is foundational for later versions that rely on policy pins, authority controls, and allowlists. You can see the philosophical continuity: what v2.3 calls immutable-core hardening evolves into richer authority/evaluation-kernel controls by v18.

v2.3 should not be treated as a dead branch; it’s an early implementation of safety boundaries that later layers refine and generalize. It remains part of the same lineage and uses shared deterministic infrastructure, reinforcing that versions are stacked, not isolated.

Operationally, if someone asks “when did CDEL begin serious self-protection against unsafe edits?”, v2.3 is the clearest inflection point in this repo.

It also introduces a governance mindset where negative permissions are explicit, versioned, and independently replay-auditable.

## v3.0 (Swarm v1)

`v3_0` shifts emphasis from single-line demon attempts to swarm-style protocol verification. Core modules include `swarm_ledger.py`, `barrier_ledger.py`, and `immutable_core.py`, with `verify_rsi_swarm_v1.py` enforcing protocol correctness. The architecture becomes multi-agent or multi-node in flavor, where consistency across participants and ledgers matters as much as local correctness.

The barrier/swarm dual-ledger pattern suggests explicit synchronization rules: swarm events record distributed attempts, while barrier entries encode committed state boundaries or cross-checkpoints. In such systems, replay verifiers must detect cross-ledger mismatch, stale barrier updates, invalid edge relations, and unauthorized writes to protected channels.

v3.0’s contribution is introducing distributed coordination semantics into CDEL’s fail-closed framework. Instead of verifying one process’s artifact chain, it verifies interdependent chains and their coherence constraints.

Importantly, this doesn’t replace previous lines (demon/CSI/hardening); it adds a coordination mode. That makes it partially orthogonal by responsibility but still integrated by infrastructure and safety principles. Later swarm versions (v3.1-v3.3) extend this protocol, and later omega layers can still conceptually benefit from swarm-style ledger discipline.

In short, v3.0 marks the transition from “single-loop certifiable RSI” toward “coordinated multi-actor certifiable RSI.”

That transition matters because later top-layer coordinators depend on exactly this kind of chain-level, cross-actor accountability.

## v3.1 (Swarm v2: Recursive Subswarms)

`v3_1` extends swarm verification with recursive subswarm semantics (`verify_rsi_swarm_v2.py`). This means the protocol now supports nested coordination structures rather than a flat swarm graph. The testing shape in this version indicates concern for depth limits, cycle detection, join conditions, and progress guarantees under recursion.

Architecturally, recursion introduces new correctness risks: duplicate joins, stale parent/child linkage, excessive depth, and deadlock-like stalling. A fail-closed verifier for this mode must validate not only per-event hashes and references but also structural properties of the subswarm tree over time. This is substantially harder than v3.0 flat synchronization.

v3.1 is therefore a protocol sophistication step. It keeps the same ledger-centric worldview but introduces hierarchical orchestration semantics. That pattern foreshadows later hierarchical control ideas (e.g., layered campaign registries and promotion pipelines), even if direct code reuse is limited.

In system terms, v3.1 increases expressive power of coordination while trying to preserve deterministic replay and safety invariants. It demonstrates that CDEL’s approach scales from local checks to structural topology checks.

If your goal is understanding where recursive coordination enters the lineage, this is the key version. It is still clearly part of the same architectural family as v3.0 and v3.2/3.3, not a detached experiment.

## v3.2 (Swarm v3: Lateral Bridge)

`v3_2` introduces lateral bridge semantics in the swarm protocol and is verified by `verify_rsi_swarm_v3.py`. “Bridge” features generally represent controlled cross-context exchange between swarm segments or domains. This adds another class of invariants beyond recursion: exchange legitimacy, publisher identity, context freshness, and anti-duplication constraints.

The module/test footprint suggests detailed checks around bridge offers/accepts, graph reporting consistency, stale context rejection, and mismatch handling with immutable-core constraints. In practice, this means the verifier must ensure that cross-link events are both cryptographically consistent and semantically legal under protocol rules.

Relative to v3.1, v3.2 emphasizes inter-subsystem communication integrity. If v3.1 focused on nested structure, v3.2 focuses on controlled lateral permeability. That balance is common in distributed protocol evolution: once hierarchy works, safe lateral coordination becomes the next bottleneck.

This version remains tightly aligned with CDEL’s core principles: deterministic hashing, replay-first validation, and fail-closed behavior on ambiguity. It also reinforces that “orthogonality” in this repo is domain-level, not implementation-isolation-level; these swarm variants share primitives and conceptual policy with adjacent versions.

As a lineage checkpoint, v3.2 is where swarm protocol starts resembling a general distributed control fabric rather than a simple synchronized queue.

In implementation terms, this is where protocol legality and cross-context provenance become inseparable verification concerns.

## v3.3 (Swarm v4: Meta/Holographic Consensus)

`v3_3` adds meta-ledger capabilities to the swarm line and is verified via `verify_rsi_swarm_v4.py`. This phase is best interpreted as consensus hardening and meta-coordination: not just tracking swarm events and barriers, but capturing higher-order commitments about swarm state. The addition of `meta_ledger.py` supports that interpretation.

In practical verification terms, meta-ledgers introduce “ledger-of-ledgers” invariants. A verifier must confirm that meta-level references accurately summarize lower-level chains and that no divergence occurs between what the swarm did and what the meta layer claims. This can reduce ambiguity in distributed replay because meta artifacts encode canonical checkpoints or consensus views.

Compared with v3.2, v3.3 is less about adding new communication channels and more about strengthening global agreement and observability. It likely improves diagnosability and confidence in large-scale swarm behavior, where direct inspection of all low-level events becomes expensive.

This version remains in continuity with v3.x and earlier safety themes. It doesn’t create a separate runtime universe; it extends the same distributed-verification model with stronger consensus metadata.

Strategically, v3.3 is an important precursor to later versions that rely on higher-level scorecards/registries/activation states. It demonstrates CDEL’s recurring pattern: add capability, then add meta-control structures to keep capability auditable.

## v4.0 (Omega Protocol v1)

`v4_0` marks an early Omega protocol phase (`omega_ledger.py`, `omega_metrics.py`, `sealed_worker_v1.py`) with verifier `verify_rsi_omega_v1.py`. This is not yet the full modern omega daemon architecture of v18, but it represents the first clear Omega-branded protocolization.

The module split implies three main concerns: ledgering Omega events, computing metrics, and running sealed worker execution. That suggests an intent to standardize control-loop reporting and replay under stricter envelopes. In prior versions, similar ideas are distributed across demon/swarm modules; here they begin to consolidate under Omega semantics.

From an architectural perspective, v4.0 is a naming and structuring inflection point. It likely establishes terminology and artifact forms that much later versions reinterpret in a richer way (observer/decider/promoter/etc.). The key continuity is deterministic, hash-addressed, fail-closed verification.

v4.0 by itself is not the final unifying layer, but it signals a move toward one. It frames a protocol-centric view of system operation: produce measurable Omega artifacts, then prove those artifacts are internally consistent and replayable.

If you compare this with v18, think of v4.0 as the conceptual ancestor: same governance instinct, far less orchestration breadth.

It effectively prototypes Omega vocabulary that later grows into a much broader observer-decider-promoter architecture.

## v5.0 (Thermodynamic Integration)

`v5_0` introduces thermodynamic integration concepts (`thermo_ledger.py`, `thermo_metrics.py`, `thermo_verify_utils.py`) with verifier `verify_rsi_thermo_v1.py`. The theme here is explicit modeling of computational/economic dynamics as first-class verification objects.

Why this matters: once systems optimize themselves, raw capability metrics are insufficient. You need cost-aware invariants and stability indicators. Thermodynamic framing typically captures notions like dissipative cost, throughput-quality tradeoffs, or bounded resource transformations. Even if the exact formulas are version-specific, CDEL’s inclusion of dedicated thermo ledgers and metrics indicates that resource discipline became protocolized.

v5.0 extends v4 Omega-style governance rather than replacing it. It adds another dimension to what gets certified: not only “did the run obey rules?” but also “did it obey resource/entropy-like constraints encoded by this protocol?” This aligns with later budgeted mechanisms in modern campaigns.

Integration-wise, v5.0 remains part of the same layered system: shared canon/hashing assumptions, versioned verifiers, and deterministic artifact contracts. It is domain-specialized but not disjoint.

As a historical checkpoint, v5.0 is where “performance under governance” broadens toward “performance under governance plus formalized cost dynamics.” That perspective resurfaces repeatedly in later budget/temperature/runaway control mechanisms.

This is also where resource semantics begin shifting from reporting-only to policy-relevant control inputs.

## v6.0 (Sovereign Persistence)

`v6_0` formalizes persistence as a protocol concern through `daemon_state.py`, `daemon_ledger.py`, and `daemon_checkpoint.py`, verified by `verify_rsi_persistence_v1.py`. This is a critical reliability milestone: once runs become long-lived and iterative, correctness depends on robust state continuity, not just per-run outputs.

This version appears to encode checkpoint structure and replay expectations for daemon-style operation. In fail-closed systems, persistence verification typically includes state hash continuity, ledger/checkpoint alignment, missing snapshot detection, and deterministic reconstruction guarantees. Without this, all higher-level claims are fragile because resumption behavior could drift.

Relative to v5.0, v6.0 is less about policy sophistication and more about operational survivability. It makes daemon continuity auditable, turning crash/restart/replay behavior into certifiable artifacts. That is a prerequisite for later complex loops (alignment, boundless domains, SAS families, omega daemon) where campaign outcomes depend on many sequential ticks.

In architecture terms, v6.0 is infrastructure-heavy and broadly reusable. It is not orthogonal in the “no dependencies” sense; it is a shared systems reliability layer. Many future components conceptually assume this kind of persistent run-state discipline, even when they implement it in newer schemas.

If you need one sentence: v6.0 makes continuity itself verifiable.

That baseline is essential for every subsequent campaign family that depends on multi-tick deterministic replay.

## v7.0 (Alignment / Superego)

`v7_0` introduces an explicit alignment layer with `superego_policy.py`, `superego_ledger.py`, and `alignment_eval.py`, verified by both `verify_rsi_alignment_v1.py` and `verify_rsi_run_with_superego_v1.py`. This phase formalizes policy oversight as a primary runtime gate.

The two-verifier structure suggests split responsibilities: one checks alignment artifact correctness, another checks enforcement within actual run traces. That distinction is important. Many systems define policies but fail to prove runtime adherence; v7.0 appears designed to close that gap.

Compared with v6.0 persistence, v7.0 adds normative constraints: not just “state continues correctly,” but “state evolution respects superego policy.” This is a governance inflection that echoes strongly in later allowlist/authority designs. It demonstrates CDEL’s recurring strategy: encode control logic into artifacts, then force replay verifiers to recompute and reject drift.

v7.0 remains embedded in the layered stack; it doesn’t isolate alignment from runtime. Instead, alignment becomes another mandatory dimension of the same deterministic verification pipeline.

Historically, this is where policy-constrained self-improvement becomes explicit and testable. If you are tracing safety lineage from early hardening (v2.3) to modern authority mechanisms (v18), v7.0 is a central middle link.

In other words, v7.0 connects technical execution receipts to normative policy receipts in one verification envelope.

## v8.0 (Boundless Math)

`v8_0` introduces a dedicated boundless-math pipeline: toolchain manifests, problem specs, attempt receipts, math ledger chain validation, and sealed proof-check interactions. The verifier `verify_rsi_boundless_math_v1.py` ties these artifacts together. This is one of the first fully specialized domain stacks where generation/evaluation machinery is clearly separated and strongly typed.

The package exports key primitives (`compute_toolchain_id`, `load_toolchain_manifest`, `compute_problem_id`, `compute_attempt_id`, ledger validators), indicating this version was designed not only as one verifier script but as reusable domain infrastructure. It emphasizes deterministic identity for each stage artifact, from toolchain to attempt receipt.

Relative to earlier generic campaign lines, v8.0 is more workflow-explicit: define math problem, run attempt through constrained checker, record receipt, append to ledger, verify chain. That staged pattern later becomes standard across SAS-code/science/system pipelines.

Integration-wise, v8.0 is both specialized and connected. Later versions (for example parts of v11.x math conjecture pipelines) reuse v8 components, proving non-disjointness. Shared canonicalization and deterministic receipt semantics also tie it to broader CDEL infrastructure.

In short, v8.0 is where domain-specific proving pipelines become first-class citizens inside CDEL, with strong replay and artifact identity guarantees.

Its modular exports also make it a reusable substrate for later formal-math-adjacent workflows.

That reuse value helps explain why v8-era assumptions still surface in later formal verification paths.

## v9.0 (Boundless Science)

`v9_0` is the science counterpart to v8’s math stack, introducing `science_dataset.py`, `science_toolchain.py`, `science_attempts.py`, `science_ledger.py`, and sealed science worker support. Verification is handled by `verify_rsi_boundless_science_v1.py`.

The core contribution is turning scientific hypothesis/evaluation flows into deterministic artifact pipelines. Instead of ad-hoc experiment scripts, v9.0 appears to encode dataset provenance, toolchain identity, attempt receipts, and ledger chaining with fail-closed replay checks. This preserves scientific process integrity under autonomous iteration.

Compared with v8, the conceptual template is similar but domain semantics differ: science attempts often involve data-model fit or theory-selection style artifacts rather than theorem-style proof attempts. The existence of dedicated modules indicates the stack respects this difference while maintaining common verification discipline.

v9.0 also serves as a precursor to SAS-Science v13.0, where science reasoning gets more formal IR/selection/eval structure. So v9 is not an abandoned branch; it is an earlier generation of the same capability class.

Architecturally, this version strengthens the argument that CDEL versions are layered domain adapters atop shared deterministic infrastructure. Domain logic changes, but replay-oriented governance remains constant.

That consistency is why newer controllers can still reason about older science lineage artifacts with confidence.

It also improves long-horizon auditability when science results must be compared across campaign generations.

## v10.0 (Model Genesis)

`v10_0` introduces sovereign model genesis, with components for corpus construction (`corpus_builder.py`, `corpus_manifest.py`), training toolchain, sealed training/eval workers, model bundling, and model genesis ledgering. Verification is provided by `verify_rsi_model_genesis_v1.py`.

This is a major shift from “attempt-level artifacts” to “training lifecycle artifacts.” The system now needs to certify dataset assembly, split policy, source run receipts, model outputs, and deterministic replay of training/evaluation pathways under bounded assumptions. The corpus manifest structure is central: if data lineage is wrong, model claims are invalid regardless of metrics.

v10.0 likely enforces stronger provenance and bundle integrity than earlier domain stacks because training pipelines have more hidden state risk. Sealed worker components indicate execution envelopes were narrowed to reduce nondeterminism and leakage.

In the broader timeline, v10 acts as a bridge between boundless domain attempts and architecture synthesis lines in v11+. It brings model-centric concerns (data curation, training receipts, evaluation receipts) into the same verification worldview.

From an integration angle, v10 is specialized but not isolated. Its receipt/manifest patterns align with later campaign promotion and subverification logic. If modern controllers need to reason about historical model-generation artifacts, v10 provides the contract shape.

This makes v10 particularly important whenever training provenance must be elevated into system-level trust decisions.

## v11.x (Architecture Synthesis + SAS-MATH Evolution)

The v11 family is internally diverse and should be understood as a mini-era:
- `v11_0` establishes architecture synthesis plus SAS-MATH v1 verification.
- `v11_1` refines the same tracks.
- `v11_2` introduces conjecture generation v2 stack.
- `v11_3` adds conjecture generation v3 while preserving v2 compatibility paths.

Core modules include architecture builders/bundles/ledgers, fixed-point arithmetic, novelty/path canon helpers, math policy IR, conjecture seed/selection/triviality modules, and sealed workers. Verifiers span `verify_rsi_arch_synthesis_v1.py`, `verify_rsi_sas_math_v1.py`, `verify_rsi_sas_math_v2.py`, and `verify_rsi_sas_math_v3.py`.

What this era contributes is separation of concerns inside formal reasoning workflows: candidate generation, validity/triviality filtering, policy scoring, and deterministic evaluation receipts. It also demonstrates controlled version migration. Rather than deleting old verifiers, newer point releases keep compatibility layers so historical runs remain replayable.

Integration-wise, v11.x reuses earlier building blocks (canonicalization, math toolchain primitives from v8 in some paths), proving the stack is layered. Conceptually, v11 is where formal architecture search and formal math conjecture mechanics become deeply engineered rather than experimental.

If you are evaluating maturity progression, v11.x is a major quality jump in formal synthesis discipline.

It is also one of the clearest examples of CDEL keeping backward replay compatibility while evolving generation logic.

## v12.0 (SAS-CODE)

`v12_0` formalizes a code-centric synthesis and verification pipeline with modules for code IR, candidate generation, selection, evaluation, workmetering, and proof-task execution (`sas_code_proof_task_v1.py`). Verification is via `verify_rsi_sas_code_v1.py`.

This version takes lessons from CSI (v2.2/v2.3) and formalizes them into a stronger campaign contract. Instead of arbitrary patch attempts alone, v12 introduces structured IR-level generation and proof-aware validation. The toolchain invocation controls and checker entrypoint constraints suggest strong anti-wrapper/anti-cheat posture in execution contracts.

A key distinction is that SAS-CODE integrates formal proof tooling concerns directly into the campaign artifacts. That gives it more semantic rigor than pure benchmark-driven patch loops. Candidate code is not only scored but tied to policy/evaluation structures intended to be replayable and auditable.

In the long arc, v12 is a direct ancestor of later promotion/subverifier ecosystems. It defines what a “code capability campaign” looks like under strict replay governance. Modern omega promotion flows can reference such campaigns because their contracts are deterministic and versioned.

Architecturally, v12 is domain-specific yet tightly connected: shared canon/hashing, deterministic receipts, and compatibility with broader campaign orchestration assumptions.

This interoperability is what allows v12 outputs to participate in later promotion and activation decision chains.

That design choice keeps code-synthesis artifacts useful beyond their original campaign context.

## v13.0 (SAS-Science)

`v13_0` upgrades science workflows into the SAS pattern: science IR, generator, selection, fit/eval logic, workmeter, dataset/canon handling, and sealed evaluation workers/clients. Verification is handled by `verify_rsi_sas_science_v1.py`.

Compared to v9’s boundless science baseline, v13 adds stronger formalization and campaign structure. The module layout indicates theory-level artifacts with explicit IDs, deterministic scoring, and controlled evaluator invocation. This is less “run experiments” and more “generate/select/verify scientific candidate structures under auditable contracts.”

The presence of dedicated tests around forbidden shortcuts (e.g., cheat-like constants or schema violations) implies aggressive fail-closed design. That aligns with CDEL’s broader anti-shortcut philosophy: campaigns must improve through legal mechanism, not artifact spoofing.

v13 also integrates with orchestrator-level test utilities in this repo, showing it participates in higher-level campaign wiring rather than being standalone. It therefore contributes to the “partial unification” picture: domain-specific internals plus shared orchestration interfaces.

In capability terms, v13 is the mature science-discovery branch before later system/kernel/metasearch/val expansions. It provides a high-assurance template for scientific reasoning campaigns that modern control layers can promote or reject through deterministic evidence.

That design also improves cross-run comparability, since theory artifacts are normalized and replay-checkable.

It further reduces evaluator ambiguity by making theory selection paths explicitly inspectable.

## v14.0 (SAS-System)

`v14_0` extends CDEL into system-level synthesis and verification. Modules include system IR, extraction, optimization, Rust codegen/build, proof checking, equivalence checking, immutability constraints, and performance reporting. Verifier: `verify_rsi_sas_system_v1.py`.

This is a major engineering step because system artifacts have broader attack surface than isolated math/code tasks. v14 addresses this by combining formal checks (proof/equivalence), build determinism (sealed Rust build receipts, offline constraints), and policy constraints (forbidden token scanning, immutability rules). The inclusion of Lean and Rust integration reflects ambition: certify end-to-end system derivations, not just intermediate abstractions.

v14 also becomes a campaign family referenced in later omega/subverifier logic, which is evidence of real integration into modern top-layer orchestration. So even though v14 has its own contracts, it remains active in broader wiring.

From an architectural lens, v14 is where CDEL starts treating full system construction as a certifiable process with both formal and practical checks. This broadens replay verification beyond synthetic tasks into build/runtime realities.

If you are assessing unification readiness, v14 is one of the key middle layers because it produces rich artifacts that later controllers can consume for promotion decisions.

As a result, v14 often serves as a bridge between formal proofs and operational deployment constraints.

## v15.x (SAS-Kernel)

The v15 family introduces kernel-level execution contracts and then extends them.
- `v15_0` includes kernel activation/equivalence/hash-tree/trace/snapshot/perf/pinning/run-spec mechanics plus Rust kernel runtime and verifier `verify_rsi_sas_kernel_v1.py`.
- `v15_1` adds a `brain/` subsystem and stronger source-bundle/replay checks via `verify_rsi_sas_kernel_v15_1.py`.

v15’s core idea is to make kernel execution itself a verifiable artifact boundary, not merely the environment in which other campaigns run. Run specs, pinned binaries, trace receipts, and snapshot determinism indicate heavy emphasis on reproducibility and tamper resistance.

The v15.1 additions suggest governance around decision context and provenance of orchestrator sources. Requiring source bundles/manifests in verification pipelines reduces ambiguity about what exact controller code influenced kernel behavior.

Integration significance is high: kernel artifacts naturally sit beneath higher campaigns, so v15’s contracts influence trust in upper layers. Later versions (including omega-era logic) can treat kernel receipts/perf traces as authoritative signals only because v15 formalized them.

In short, v15 turns execution substrate integrity into a first-class certified capability, then v15.1 hardens the control-context side of that substrate.

This dual focus makes kernel trust both operationally measurable and cryptographically auditable.

It is a core prerequisite for safely delegating higher-level decisions to kernel-backed execution flows.

## v16.x (SAS-Metasearch)

The v16 family addresses metasearch workflows.
- `v16_0` provides corpus/prior/policy/run/trace modules with Rust codegen/build and verifier `verify_rsi_sas_metasearch_v1.py`.
- `v16_1` adds promotion bundle handling, selection logic, state snapshots, and trace v2, with verifier `verify_rsi_sas_metasearch_v16_1.py` plus a compatibility alias.

This phase is about searching over strategy/capability spaces with deterministic accountability. Metasearch systems are prone to hidden heuristics and nondeterministic drift, so v16’s artifactization (plans, traces, snapshots, promotion bundles) is crucial. It creates replayable evidence of why a particular candidate/path was selected.

v16.1’s additions indicate maturation from raw search execution to lifecycle governance: not only run search, but capture promotion-ready bundles and state transitions that can be consumed by higher-level controllers.

In modern integration terms, metasearch outputs are explicitly used in observer/decision contexts in newer omega stacks, which means v16 is a live dependency in the layered architecture. It is not a dead-end version.

If you summarize v16 in one line: it certifies the search process that decides what to try next, with v16.1 adding the promotion/state machinery needed for system-wide coordination.

That is why metasearch outputs can function as policy-relevant signals rather than opaque heuristics.

In practical operations, this enables reproducible strategy-selection postmortems rather than guesswork.

## v17.0 (SAS-VAL)

`v17_0` introduces SAS-VAL with `val/`, `runtime/`, and `hotloop/` components plus verifier `verify_rsi_sas_val_v1.py`. The module set (ISA/decode/equivalence/safety/lift constructs) suggests this version formalizes validation loops around low-level or patch-level execution semantics under strict determinism.

VAL appears to combine runtime execution control with verification-focused transforms and safety constraints. This can function as a “tight loop” campaign family: quickly evaluate candidate changes while preserving replay guarantees and robust safety checks. The presence of hotloop mechanics reinforces this interpretation.

Compared with v16 metasearch (choose what to attempt), v17 looks oriented toward executing and validating those attempts in a controlled loop. That makes it naturally complementary to metasearch and kernel/system layers, and modern observers can draw metrics from this family.

Architecturally, v17 continues the CDEL pattern of domain specialization plus shared governance primitives. It is specialized enough to have its own runtime and verifier contracts, but integrated enough to appear in later top-level campaign registries and observer metrics.

In capability progression, v17 closes the pre-v18 SAS arc by providing a high-assurance validation loop that newer omega control logic can orchestrate and reason about.

This gives upper layers a faster but still certifiable mechanism for iterative candidate triage.

That balance is critical when decision cadence must increase without sacrificing replay confidence.

## v18.0 (Omega Daemon + CCAP + Authority Integration)

`v18_0` is the current top-layer consolidation point. It introduces a richer omega daemon architecture: observer, decider, executor, promoter, activator, diagnoser, runaway control, scorecards, tick perf/stats/outcomes, trace hash chains, and verifier worker support. It also introduces CCAP runtime/verification and polymath campaign families, plus authority pins and evaluation-kernel controls.

Key verifiers include `verify_rsi_omega_daemon_v1.py`, `verify_ccap_v1.py`, `verify_rsi_omega_self_optimize_core_v1.py`, `verify_rsi_polymath_domain_v1.py`, and `verify_rsi_polymath_scout_v1.py`. Importantly, v18’s promotion/subverifier paths can invoke verifier modules from earlier capability families, which is the strongest code-level evidence of partial unification across historical versions.

CCAP in v18 generalizes controlled patch proposal/evaluation/promote flows with strict allowlists, authority hashes, and budget/cost accounting. This can be seen as an evolved form of ideas first appearing in CSI/hardening eras, now wrapped in a broader orchestrated control loop.

So v18 is not “everything replaced by new code.” It is a coordinating superlayer over accumulated capability domains, with deterministic replay still central. This is why the stack is neither disjoint nor fully orthogonal: v18 stitches many versioned contracts together while preserving historical verifier boundaries.

Practically, v18 is where governance, dispatch, verification, and promotion become one integrated control surface.

It is the clearest expression of CDEL’s transition from many verifiers to a coordinated verifier ecosystem.

---

## LLM Usage Audit (v1.5r -> v18.0 + Full Stack)

This section answers the direct question: where do LLMs actually appear in this repository, and are any CDEL versioned runtime/verifier modules dependent on live LLM calls?

For the CDEL version line itself (`CDEL-v2/cdel/v1_5r` through `CDEL-v2/cdel/v18_0`), the answer is: **no direct live LLM provider integration appears in the versioned CDEL modules**. The core mechanics across versions remain deterministic artifact generation, sealed worker execution, replay verification, canonical hashing, and fail-closed validation. You see heavy cryptographic and schema logic, but not `OpenAI/Anthropic/Gemini` SDK-style provider calls inside these version folders.

The main LLM surface appears in **`agi-orchestrator`**, not in CDEL verifiers:
- `agi-orchestrator/orchestrator/proposer/llm.py` defines `LLMProposer`.
- `agi-orchestrator/orchestrator/llm_backend.py` exposes backends.
- In this codebase snapshot, the implemented backends are `mock` and `replay`, with environment controls like `ORCH_LLM_BACKEND`, `ORCH_LLM_REPLAY_PATH`, and `ORCH_LLM_MOCK_RESPONSE`.
- I did not find a built-in live provider backend (for example direct OpenAI/Anthropic API clients) in these modules.

So, for v1.5r-v18 campaign families as represented here, **LLM usage is optional orchestration-time proposal generation** rather than an intrinsic requirement of the CDEL verifier pipeline. If you run standard deterministic campaign paths and replay verifiers, they do not require live external model inference.

Genesis has a related but different pattern: `Genesis/schema/v18_0/ge_config_v1.jsonschema` includes an optional `llm_trace` field, and `tools/genesis_engine/ge_symbiotic_optimizer_v0_2.py` / `ge_symbiotic_optimizer_v0_3.py` hash prompt/response traces. That behavior records or fingerprints traces; it is not itself a live model-provider client.

Meta-core paths likewise show no LLM dependency. `meta-core` and `CDEL-v2/cdel_meta_core_gate` focus on signed bundle verification, activation/rollback protocols, and kernel/ruleset integrity.

## Full-Stack Coverage Addendum (What Was Missing)

The original map captured CDEL internals well but underrepresented where orchestration, schema, and activation control live across repositories. This addendum closes that gap.

Across this workspace, the full picture is split across these layers:
- `CDEL-v2/cdel/v*`: versioned deterministic runtime/verifier logic (RE2 verification layer).
- `orchestrator/`: current wrapper/orchestration entrypoints for modern campaign families, especially `v12+` and omega v18.
- `Extension-1/agi-orchestrator/orchestrator/`: broader legacy/transition orchestrator coverage for many early and mid versions.
- `Genesis/schema/v*`: schema contracts for versioned campaign packs/artifacts from `v1_5r` through `v18_0`.
- `meta-core/`: activation constitution, bundle verification, commit/rollback protocol, and immutable trust-root management.
- `CDEL-v2/cdel_meta_core_gate`: fail-closed bridge that injects audited meta-core provenance into receipt flows.

Practically, version coverage by layer looks like this:
- `v1.5r` through `v11.3`: CDEL + Genesis schema + meta-core constitution folders are present; orchestration is primarily represented in `Extension-1/agi-orchestrator/orchestrator`.
- `v12.0` through `v14.0`: represented in CDEL and Genesis; orchestrator support exists in both `Extension-1/...` and top-level `orchestrator/` (with top-level wrappers used by newer omega dispatch paths).
- `v15.x`: CDEL has `v15_0` and `v15_1`; top-level orchestrator has `rsi_sas_kernel_v15_0.py`; `v15_1` appears as partial/auxiliary support in extension tooling rather than the same level of top-level wrapper symmetry.
- `v16.x`: `v16_0` orchestration appears in extension paths; `v16_1` has active top-level orchestrator wrapper and coordinator.
- `v17.0`: top-level orchestrator wrapper + CDEL runtime/verifier + Genesis schema.
- `v18.0`: top-level omega orchestrator + CDEL omega/CCAP/verifier stack + Genesis v18 schemas/configs + meta-core activation protocol integration.

Meta-core deserves a special note: `meta-core/meta_constitution` has explicit version folders through earlier/mid generations (through `v11_3` in this snapshot), while newer omega-era integration is handled via generic activation/bundle protocol artifacts and runtime binding checks (for example CDEL v18 activator paths and meta-core CLI apply/rollback).

## v18 Integration Note: Orchestrator, Genesis, Meta-Core

For modern operation, v18 is a multi-repo composition:
- Orchestrator side (`orchestrator/omega_v18_0/coordinator_v1.py`) runs tick control flow and delegates to CDEL modules for observe/decide/dispatch/promote/activate plumbing.
- CDEL side (`CDEL-v2/cdel/v18_0/omega_executor_v1.py`, `omega_promoter_v1.py`, `verify_rsi_omega_daemon_v1.py`) enforces deterministic receipts, subverifier replay, and promotion legality.
- Genesis side contributes schema/config contracts, including GE config and polymath-related pack schemas.
- Meta-core side (`meta-core/cli/meta_core_apply.py`, `meta_core_rollback.py`, audited via CDEL activator logic) controls active bundle pointer swaps with rollback and audit evidence.

This is the clearest proof that the system is not disjoint: it is intentionally layered across repos, with CDEL verifying artifacts, orchestrator coordinating runtime flow, Genesis defining contracts, and meta-core governing activation trust.

## Orthogonality, Disjointness, and Unification (Direct Answer)

The versions are not orthogonal in the strict sense because implementation dependencies and shared primitives span generations, and modern orchestration can explicitly route through older verifier modules. They are also not disjoint, because there is active top-layer coupling (especially in v18), shared canonicalization infrastructure, and reuse of campaign artifact conventions.

At the same time, the repository is not one completely uniform runtime API where all versions become interchangeable plugins. Most versions still encode their own campaign-specific contracts and verifier assumptions. That is intentional: it preserves replayability for historical runs and keeps each capability family auditable under the rules it was designed with.

So today’s reality is a **layered evolutionary system with partial unification**:
- Lower/mid layers provide versioned capability contracts.
- Upper layers (mainly modern omega/orchestrator flows) provide coordination, dispatch, subverification, and promotion governance.
- Shared deterministic primitives connect everything.

If your objective is one continuous unified autonomous system, wiring is still required and is concentrated in those upper layers. The necessary pieces are campaign registry, verifier routing, activation/promotion policy, authority controls, and a consistent state/reporting contract. The repo has substantial pieces of this already, but full universal coverage across every historical version remains an integration exercise rather than a solved one-line abstraction.
