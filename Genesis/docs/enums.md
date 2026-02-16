# Enumerations (Level-1)

This document lists normative enumerations used across schema and docs.

## Machine-Readable Enums

```json
{
  "artifact_types": [
    "ALGORITHM",
    "WORLD_MODEL",
    "CAUSAL_MODEL",
    "POLICY",
    "EXPERIMENT"
  ],
  "grades": ["ResearchGrade", "DeploymentGrade"],
  "effect_permissions": [
    "pure",
    "read_only",
    "filesystem_read",
    "filesystem_write",
    "network",
    "process_spawn",
    "gpu",
    "clock",
    "nondeterminism"
  ],
  "clause_types": [
    "functional",
    "safety",
    "resource",
    "statistical",
    "robustness"
  ],
  "canonicalization_id": "gcj-1"
}
```
