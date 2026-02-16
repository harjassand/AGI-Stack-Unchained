# CSI Contract v1

This contract specifies the v2.2 Code Self-Improvement (CSI) requirements:

- Autonomous patching: the system must generate and apply a code patch to its own Proposer sources within the allowlisted CSI roots.
- Functional preservation: benchmark outputs must match baseline bit-for-bit and all required tests must pass.
- Efficiency gate: the patch must reduce CSI work cost by at least the pinned rho threshold.
- Recursive binding: the patch must be parameterized by a recursive ontology concept and obey the deterministic concept selection rule.
- Fail-closed semantics: any schema violation, hash mismatch, forbidden path, forbidden syntax/import, or nondeterminism is fatal.

This document is normative for META_HASH computation in v2.2.
