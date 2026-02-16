# Recursive Ontology Contract v1

This contract specifies the v2.1 recursive ontology requirements:

- Concept invention: new optimization concepts must be generated during the run and accepted via deterministic verification.
- Recursive composition: at least one accepted concept must compose a prior accepted concept via an explicit `call` node in the concept DSL.
- Cross-domain transfer: each accepted concept must pass efficiency gates in both source and target domains under deterministic replay.
- Fail-closed semantics: schema violations, hash mismatches, or nondeterminism are fatal.

This document is normative for META_HASH computation in v2.1.
