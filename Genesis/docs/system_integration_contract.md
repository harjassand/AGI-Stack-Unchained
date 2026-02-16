# System Integration Contract (Normative)

## Scope
This document defines the contract semantics for SYSTEM composition, component integrity rules, dependency graph requirements, and failure-probability accounting at the system level.

## System Capsule Semantics
A SYSTEM capsule represents a composition of component capsules. The composition is defined by an explicit graph specifying call relationships and dependencies.

Normative requirements:
- The SYSTEM capsule MUST bind to component capsule hashes in a deterministic composition block.
- The SYSTEM capsule MUST declare its component dependency graph and shared data/randomness assumptions.
- The SYSTEM capsule MUST provide system-level functional, safety, resource, statistical, and robustness clauses.

## Component Integrity Model
- Every referenced component hash MUST resolve to a canonical capsule in the component store.
- The SYSTEM capsule MUST FAIL validation if any component hash is missing or mismatched.
- Component hashes MUST be computed using the canonicalization scheme specified by the specpack.

## Dependency Graph Requirements
- The composition graph MUST be acyclic.
- Each edge MUST identify the caller and callee components.
- Shared randomness or shared data MUST be declared in the dependency tags.

## Composition Admissibility Rules
A SYSTEM evaluation is admissible only if:
- All components are schema-valid and effect-compatible with the system effects.
- The system effects are no broader than the union of component effects.
- Resource caps for the system are >= the maximum required for any component path.
- The system-level contract is well-formed and contains adjudicable clauses.

## Failure-Probability Accounting
- If components share data or randomness, system-level statistical guarantees MUST use conservative composition (union bound) unless independence is certified.
- System-level failure probability MUST include component-level uncertainties and any additional evaluation uncertainty introduced by composition.
- The system transcript MUST record dependency tags and the accounting rule applied.

## Determinism and Auditing
- System evaluation MUST be deterministic under harness-controlled seeds.
- System transcript hashing MUST include the component hashes and dependency graph.
- Receipts MUST bind the measurement transcript hash and audit reference.
