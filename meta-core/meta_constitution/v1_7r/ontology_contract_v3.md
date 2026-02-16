# Ontology Contract v3

This contract defines the v3 ontology admission rules for CDEL v1_7r.

- Ontology definitions follow `ontology_def_v3` with GCJ-1 canonical JSON.
- Snapshot selection uses deterministic greedy forward selection with bounded arity.
- DL metric uses context hashes derived from snapshot-selected, bucketed concept outputs.
- Admission requires minimum DL gain and family support thresholds.
- All promotable artifacts are self-hashed and content-addressed.
