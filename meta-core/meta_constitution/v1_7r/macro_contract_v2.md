# Macro Contract v2

This contract defines v2 macros with context guards for CDEL v1_7r.

- Macros are GCJ-1 canonical JSON and self-hashed.
- Guards list allowed context hashes (sorted, unique, bounded length).
- Encoder uses greedy longest-match with deterministic tie-break.
- Admission requires ctx-MDL gain and family support thresholds.
- Rolling window eviction is mandatory when MDL gain is non-positive.
