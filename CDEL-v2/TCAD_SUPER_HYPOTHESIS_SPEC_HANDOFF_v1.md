# TCAD Super Hypothesis (L0-L11) - Spec Handoff for External Research Scientist

Date: 2026-02-11
Repository snapshot: `/Users/harjas/AGI-Stack-Clean`
Audience: Senior research scientist creating a formal specification for integration
Purpose: Provide a complete, implementation-grounded brief so the hypothesis can be specified and integrated cleanly, with no redundant architecture.

Companion repository docs:
- `CDEL-v2/CURRENT_IMPLEMENTATION_AUDIT_LEVEL1_LEVEL2.md` (current capability audit)
- `CDEL-v2/CDEL_VERSION_MAP_v1_5r_to_v18_0.md` (lineage and integration map)

## 1. Executive Summary

The workspace already has a strong fail-closed, deterministic, receipt-driven governance stack (especially RE1 meta-core + RE2 Omega v18). This is enough to support a serious specification effort for your L0-L11 continuity hypothesis.

What exists now:
- Deterministic, content-addressed replay and fail-closed verification are first-class.
- Promotion is already constrained by subverifier validity, allowlists, CCAP checks, and meta-core verification.
- Cross-domain scaffolding exists (math/science/code/system + polymath lifecycle), but deep cross-domain abstraction quality evaluators are still shallow.

What is not yet native:
- A single explicit continuity theorem object enforced across all upgrade types.
- First-class overlap semantics + total translator proofs + backward-refutation lane as universal required artifacts.
- World snapshot ingestion (L10) and federated treaty semantics (L11).
- A unified, pinned global objective `J` with all axis debts (KDL/EDL/CDL/CoDL/IDL) in one acceptance predicate.

Bottom line for the scientist:
- Treat this stack as a robust deterministic substrate that already enforces authority and replay.
- Specify your hypothesis as an extension layer over existing promotion/verification flows, not as a replacement runtime.

## 2. Current Architecture (What Is Actually Running)

### 2.1 Trust and Control Layers

- RE1 (trusted core): `meta-core/`
- RE2 (trusted execution/verifiers): `CDEL-v2/cdel/`
- Untrusted proposal/orchestration surfaces: campaign executors, external feeds, optional LLM proposer paths

Practical trust boundary already implemented:
- Untrusted campaign outputs do not directly alter authority.
- Promotion depends on verifier receipts + meta-core promotion verification + activation gates.

Key references:
- `orchestrator/omega_v18_0/coordinator_v1.py`
- `CDEL-v2/cdel/v18_0/omega_promoter_v1.py`
- `CDEL-v2/cdel/v18_0/verify_rsi_omega_daemon_v1.py`
- `meta-core/kernel/verify_promotion_bundle.py`

### 2.2 Omega Tick Lifecycle (Current)

Entrypoint:
- `orchestrator/rsi_omega_daemon_v18_0.py`

Tick pipeline (implemented in `run_tick`):
1. Freeze config pack into daemon config.
2. Load policy, registry, objectives, runaway config, budgets, allowlists.
3. Observe -> Diagnose -> Decide.
4. If actionable: Dispatch campaign -> Run subverifier -> Run promotion -> Run activation.
5. Write state, optional runaway state, ledger events, trace hash chain, snapshot, outcome/perf artifacts.
6. SAFE_HALT when hard safety conditions hit (for example invalid subverifier, forbidden path).

Core implementation:
- `orchestrator/omega_v18_0/coordinator_v1.py`

### 2.3 Determinism and Canonical Identity

Identity and hashing behavior:
- Canonical JSON + SHA-256 identifiers used everywhere.
- Helper methods enforce deterministic serialization and hash-anchored filenames.

Key implementation:
- `CDEL-v2/cdel/v18_0/omega_common_v1.py`
- `CDEL-v2/cdel/v1_7r/canon.py`

Important behavior:
- `fail(reason)` normalizes to `INVALID:<reason>` and aborts fail-closed.
- Schema validation is strict (`Genesis/schema/v18_0/*.jsonschema`).

## 3. Current Acceptance / Governance Surfaces

### 3.1 Configuration Regime Equivalents

The closest current equivalent to your regime tuple `(C,K,E,W,T)` is:
- Constitution/kernel authority roots: RE1 meta-core + authority pins
- K-like layer: verifier modules in registry + meta-core kernel
- E-like layer: campaign packs, benchmark/test plan receipts, hidden-ish source artifacts
- W: not implemented as formal sealed world snapshots
- T: not implemented (no treaty layer)

Primary regime config files:
- `campaigns/rsi_omega_daemon_v18_0/rsi_omega_daemon_pack_v1.json`
- `campaigns/rsi_omega_daemon_v18_0/omega_policy_ir_v1.json`
- `campaigns/rsi_omega_daemon_v18_0/omega_capability_registry_v2.json`
- `campaigns/rsi_omega_daemon_v18_0/omega_objectives_v1.json`
- `campaigns/rsi_omega_daemon_v18_0/omega_budgets_v1.json`
- `campaigns/rsi_omega_daemon_v18_0/omega_allowlists_v1.json`
- `campaigns/rsi_omega_daemon_v18_0/omega_runaway_config_v1.json`

### 3.2 Promotion Gate Reality (Current)

Promotion requires all of:
- Valid subverifier receipt.
- Valid promotion bundle (or explicit skip).
- Path checks against allowlists (or CCAP-specific path constraints).
- Test-plan receipt when required.
- CCAP receipt + replay consistency when using CCAP bundle.
- Meta-core promotion verify pass before activation binding.

Implementation:
- `CDEL-v2/cdel/v18_0/omega_promoter_v1.py`

Promotion result schema and reason codes:
- `Genesis/schema/v18_0/omega_promotion_receipt_v1.jsonschema`

### 3.3 Replay Verifier Guarantees

Omega verifier recomputes and checks:
- Hash-bound loading of snapshot-linked artifacts.
- Policy/registry/objective/budget hash consistency.
- Observation recomputation from declared sources.
- Diagnosis recomputation.
- Decision recomputation proof and plan hash binding.
- Runaway state advancement determinism (if enabled).
- Trace hash chain integrity.
- Promotion/activation consistency rules and binding checks.

Implementation:
- `CDEL-v2/cdel/v18_0/verify_rsi_omega_daemon_v1.py`

## 4. Canonical Data Contracts (Critical for Spec Integration)

You should model the spec directly against these contracts.

State and planning:
- `omega_state_v1`: `Genesis/schema/v18_0/omega_state_v1.jsonschema`
- `omega_decision_plan_v1`: `Genesis/schema/v18_0/omega_decision_plan_v1.jsonschema`
- `omega_policy_ir_v1`: `Genesis/schema/v18_0/omega_policy_ir_v1.jsonschema`
- `omega_objectives_v1`: `Genesis/schema/v18_0/omega_objectives_v1.jsonschema`
- `omega_capability_registry_v2`: `Genesis/schema/v18_0/omega_capability_registry_v2.jsonschema`

Receipts and evidence chain:
- `omega_dispatch_receipt_v1`
- `omega_subverifier_receipt_v1`
- `omega_promotion_receipt_v1`
- `omega_activation_receipt_v1`
- `omega_tick_snapshot_v1`
- `omega_observation_report_v1`
- `omega_trace_hash_chain_v1`

All in `Genesis/schema/v18_0/`.

CCAP and authority:
- `ccap_v1`, `ccap_receipt_v1`, `ccap_refutation_cert_v1`
- `meta_core_promo_verify_receipt_v1`
- Authority pins and allowlists:
  - `authority/authority_pins_v1.json`
  - `authority/ccap_patch_allowlists_v1.json`
- Hash/pin logic:
  - `CDEL-v2/cdel/v18_0/authority/authority_hash_v1.py`
  - `CDEL-v2/cdel/v18_0/verify_ccap_v1.py`

Polymath domain stack:
- `polymath_domain_registry_v1`
- `polymath_portfolio_v1`
- `polymath_domain_pack_v1`
- `polymath_equivalence_report_v1`

Schemas in `Genesis/schema/v18_0/` and implementations in `CDEL-v2/cdel/v18_0/`.

## 5. Current Workspace State Snapshot (Important for Honest Spec Baseline)

As of this snapshot:

Polymath registry and portfolio:
- `polymath/registry/polymath_domain_registry_v1.json` has 1 active domain (`pubchem_weight300`), unconquered.
- `polymath/registry/polymath_portfolio_v1.json` has 0 domain entries, score 0.

Authority pins (active root hashes pinned):
- `authority/authority_pins_v1.json`

CCAP patch scope constraints:
- `authority/ccap_patch_allowlists_v1.json`
- Current policy forbids direct patching of `CDEL-v2/`, `Genesis/`, `meta-core/`, `authority/`, etc. for CCAP.

Observed Omega sample run (tick 20):
- Goals done in first ticks, then mostly NOOP due queue/cooldown conditions.
- High metasearch cost ratio issue still detected in issue bundle.

Artifacts inspected:
- `runs/rsi_omega_daemon_v18_0_tick_0020/daemon/rsi_omega_daemon_v18_0/state/state/sha256_8e4fd07c25599d90777707c61f447c1183f72ff5b258358122771d708c831e95.omega_state_v1.json`
- `runs/rsi_omega_daemon_v18_0_tick_0020/daemon/rsi_omega_daemon_v18_0/state/observations/sha256_634c3664dac357f878c7bbf18082d4c09aab552d1a1cba84d4534bdc792343fe.omega_observation_report_v1.json`
- `runs/rsi_omega_daemon_v18_0_tick_0020/daemon/rsi_omega_daemon_v18_0/state/issues/sha256_eeb331ec3716ffa93652818d3d6c68b3ef1f72efef22c1e4959f08c1e812612c.omega_issue_bundle_v1.json`

Interpretation:
- Governance/replay machinery is present.
- Cross-domain compounding evidence is still sparse in live state.

## 6. L0-L11 Mapping to Existing Capability

This is the key mapping your scientist needs for scoping.

L0 (fail-closed deterministic baseline):
- Strongly implemented.
- Deterministic IDs, schema-validated receipts, replay verifier, fail-closed reason codes.

L1 (certified accounting/invariants):
- Implemented in bounded form.
- Objectives/policy/issue bundles/run scorecards/runaway provide measurable control loops.

L2 (cross-domain abstraction with charged reconstruction):
- Partial.
- Polymath domain infrastructure exists; abstraction quality and reconstruction charging are shallow.

L3 (verifier-visible discovery speedups):
- Partial.
- Runaway objective tightening/escalation exists, but not a formally pinned universal UDC law.

L4 (model-class conservative extension):
- Weak-to-partial.
- Campaign families and CCAP allow new patches, but no universal overlap conservativity proof object.

L5 (autocatalytic meta-yield):
- Partial.
- Scorecards and flywheel-style adapters exist; strong causal compounding criteria are not yet formalized globally.

L6 (trusted kernel evolution):
- Partial.
- Meta-core kernel and promotion verification exist, but explicit kernel polarity/equivalence proofs are not first-class axis objects.

L7 (environment co-evolution with reductions):
- Partial.
- Test plans, benchmark/evaluation kernels, and campaign environments exist; formal dominance reduction witnesses are not universalized.

L8 (tri-coupled K+E+M with pinned continuity constitution):
- Not fully implemented.
- Pieces exist (meta-core + Omega governance), but no explicit C-CONT artifact enforcing the continuity law across upgrades.

L9 (self-amending constitution via CK):
- Very partial.
- Meta-constitution machinery exists, but no explicit constitution morphism contract with overlap continuity proof obligations as your hypothesis defines.

L10 (sealed world snapshots):
- Not implemented as hypothesis-grade SIP.
- External ingestion exists in polymath scouting/fetch, but no system-level sealed world snapshot contract tied into universal acceptance.

L11 (multi-sovereign treaties and safe split):
- Not implemented.
- No treaty object, overlap kernel profile, path-commutativity checks, or SAFE_SPLIT portability protocol.

## 7. Non-Redundant Integration Rules (Must Be Followed)

Your spec should enforce these integration constraints to avoid architecture duplication:

1. Do not create a second promotion path.
- All acceptance remains through existing dispatch -> subverifier -> promotion -> activation.

2. Do not create a second authority root.
- Keep RE1 meta-core and existing authority pins as the only trust anchor.

3. Do not bypass existing receipts/snapshots.
- New proof objects must be additional required artifacts, not alternate artifacts.

4. Do not duplicate hash/canonicalization stacks.
- Reuse GCJ-1/canon + SHA-256 patterns already in `v1_7r.canon` and `omega_common_v1`.

5. Do not make continuity optional on affected upgrades.
- If an upgrade declares overlap, continuity proof or backward refutation must be mandatory (else reject/SAFE_HALT).

6. Do not let world/federation lanes bypass local fail-closed semantics.
- World ingestion/treaties must produce deterministic receipts and fail into `SAFE_HALT` or `SAFE_SPLIT`, never silent acceptance.

## 8. Proposed Integration Blueprint (Cleanest Path)

### 8.1 Where to Plug the Hypothesis In

Primary insertion point:
- Extend promotion bundle semantics and promotion verifier checks.

Concretely:
- Add continuity proof artifacts as required sidecars to promotion bundles for relevant axes.
- Validate them in `run_promotion` and revalidate in `verify_rsi_omega_daemon_v1`.
- Mirror critical checks in meta-core promotion verification flow (RE1) for trust-closed behavior.

Why this is clean:
- Uses existing acceptance bottleneck.
- Reuses existing receipts and activation bindings.
- Avoids redundant orchestration/verifier trees.

### 8.2 New Artifact Families to Specify (Recommended)

The scientist should define formal schemas for at least:
- `continuity_morphism_v1`
- `overlap_profile_v1` (language/signature + semantics profile ID)
- `translator_totality_cert_v1` (`Phi`, optional `Pi`)
- `backrefute_cert_v1` (old-semantics-checkable refutation witness)
- `continuity_receipt_v1` (result of continuity check for a candidate upgrade)
- `axis_upgrade_bundle_v1` (typed axis declaration: Sigma/Pi/D/H/A/K/E/M/C/W/S)

For L10:
- `world_snapshot_v1` (sealed root, provenance grades, non-interference gate result)

For L11:
- `treaty_v1`
- `treaty_coherence_receipt_v1`
- `refutation_interop_receipt_v1`

Note: place under a new version namespace (recommended `v19_0`) to avoid destabilizing `v18_0` contracts.

### 8.3 Acceptance Predicate Refactor (Spec-Level)

Define one explicit RE2-computable scalar objective `J` with enabled terms by axis, but implement as extension over existing objective/policy machinery:
- Keep current `omega_objectives_v1` as baseline terms.
- Add axis-debt terms through new metric IDs and deterministic evaluators.
- Require rent-paid dominance before promotion.

Do not replace existing policy IR; layer new mandatory checks into promotion gating and decision evaluation.

## 9. Level-by-Level Implementation Guidance (for Spec Author)

L0-L1:
- Reuse existing deterministic replay + receipt chain.
- Only formalize theorem language and reason-code taxonomy alignment.

L2-L3:
- Strengthen polymath/domain evaluators with semantic transfer and compression metrics.
- Add certified discovery-cost measurement artifact, not just heuristic throughput.

L4:
- Require overlap translation/conservativity proofs per model-class upgrade bundle.

L5:
- Add explicit meta-yield certificates with pinned horizons and anti-drift controls.

L6:
- Introduce kernel-upgrade proof object with polarity/equivalence constraints.

L7:
- Add environment reduction witness + hardness stationarity checks as required artifacts.

L8:
- Introduce pinned continuity constitution (C-CONT) as mandatory upgrade law for K/E/M joint changes.

L9:
- Add constitution kernel obligations for constitution morphisms (`M_C`) and constitutional back-refutation lanes.

L10:
- Implement sealed ingestion protocol and tie world tasks to dominance-reducible subsets.

L11:
- Add treaty overlap kernel, total translators, refutation interoperability, and path-independence checks.
- Define `SAFE_SPLIT` as explicit non-acceptance terminal for unresolved portability disputes.

## 10. Testing and Verification Requirements

Existing test base is strong for Omega mechanics:
- `CDEL-v2/cdel/v18_0/tests_omega_daemon/` has 119 tests.

Spec should require new tests in the same style:

1. Determinism and replay tests:
- Same inputs -> identical decision/promotion/continuity receipts.

2. Fail-closed tests:
- Missing translator proofs, missing overlap declarations, or timeout in totality checks must reject.

3. No new acceptance path tests:
- Candidate cannot promote via any route that omits continuity obligations.

4. Backward refutation tests:
- Revocations require old-semantics-checkable refutation witness.

5. Treaty coherence tests (L11):
- Non-commuting translation paths must fail portability and produce SAFE_SPLIT.

6. World sealing tests (L10):
- External state dependency not captured in snapshot root must reject.

## 11. Critical Open Decisions the Scientist Must Pin Early

These must be explicit in the specification before implementation starts:

1. Overlap semantics format.
- Exact representation of `L_cap`, signature, and semantic profile IDs.

2. Continuity class lattice.
- Allowed classes (`EQUIV`, `REFINE`, `EXTEND`, `RESTRICT`) and forbidden classes by default.

3. Back-refutation witness grammar.
- Syntax and RE2/RE1 check procedure under old intended semantics.

4. Translator totality budget model.
- Budget/time semantics and deterministic timeout behavior.

5. Global objective `J` term definitions.
- Exact measurement kernels for each debt term and amortization policy.

6. SAFE_HALT vs SAFE_SPLIT boundaries.
- Local/federated resolution policy and non-acceptance semantics.

## 12. What Not to Re-Specify (Already Provided by Workspace)

To avoid redundancy, do not re-design:
- Canonical hashing / content addressing primitives.
- Existing Omega orchestration lifecycle.
- Existing receipt storage and snapshot linkage patterns.
- Existing authority pins root model.
- Existing meta-core promotion verification architecture.

Instead, specify additional proof obligations and typed artifacts that fit into those existing mechanisms.

## 13. Minimal File Touch Strategy for Clean Integration

When implementation begins, prefer this sequence:

1. Add new schemas (new version namespace).
- `Genesis/schema/<new_version>/...`

2. Add new validators/loaders in RE2.
- `CDEL-v2/cdel/<new_version>/...`

3. Wire mandatory checks into promotion flow.
- Extend `omega_promoter_v1` behavior through versioned adapter or successor module.

4. Wire replay checks into verifier.
- Extend `verify_rsi_omega_daemon_v1` equivalent in new version.

5. Add RE1 mirror checks for high-trust continuity obligations.
- `meta-core/kernel/...` plus wrapper integration.

6. Add tests before enabling capabilities in registry.
- Keep new capability entries disabled until proofs/tests pass.

## 14. Final Practical Brief You Can Hand Off Verbally

"Our stack already has deterministic, fail-closed promotion and replay governance. We need your spec to add one universal continuity theorem across all upgrade axes without introducing new trust paths. Please define typed morphism artifacts, overlap semantics, translator totality proofs, and backward-refutation witnesses so they can be enforced in the existing promotion and replay verifiers. Keep RE1 meta-core and current receipt chains as-is, and treat world/treaty layers as new certified artifacts that still fail closed (SAFE_HALT/SAFE_SPLIT)."
