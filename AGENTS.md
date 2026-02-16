Repo root: AGI-Stack-Clean/
As-of: 2026-02-13
Baseline commit: b59c1fd37d9f9e888c266e539cb69c5c5c260d81 (branch fix/unified-4h-ready)
Trust boundary: RE1–RE4 unchanged (per handoff pack).
Determinism substrate: GCJ-1 canonical JSON (floats rejected), Q32 ops in RE2, replay verifiers fail-closed.

This spec is normative. “MUST/SHALL” are mandatory for correctness and replay-verification. Anything not specified is forbidden.

0.2 Non-goals

No changes to RE1/RE2/RE3/RE4 trust layering.

No new “approval” or “council” mechanisms.

No reliance on JSON floats.

No network access beyond existing dsbx profiles.

No unverifiable sampling. (A deterministic sampling mode may be defined later, but v1 requires full deterministic replay.)

Appendix A — eudrs_u_promotion_summary_v1.json (required producer output)

Campaigns MUST emit exactly one summary file under eudrs_u/evidence/ that points to all other evidence.

{
  "schema_id":"eudrs_u_promotion_summary_v1",

  "proposed_root_tuple_ref": { "artifact_id":"sha256:<...>", "artifact_relpath":"eudrs_u/staged_registry_tree/polymath/registry/eudrs_u/roots/sha256_<...>.eudrs_u_root_tuple_v1.json" },

  "staged_registry_tree_relpath":"eudrs_u/staged_registry_tree",

  "evidence": {
    "weights_manifest_ref": { "artifact_id":"sha256:<...>", "artifact_relpath":"eudrs_u/evidence/sha256_<...>.weights_manifest_v1.json" },
    "ml_index_manifest_ref": { "artifact_id":"sha256:<...>", "artifact_relpath":"eudrs_u/evidence/sha256_<...>.ml_index_manifest_v1.json" },

    "cac_ref": { "artifact_id":"sha256:<...>", "artifact_relpath":"eudrs_u/evidence/sha256_<...>.cac_v1.json" },
    "ufc_ref": { "artifact_id":"sha256:<...>", "artifact_relpath":"eudrs_u/evidence/sha256_<...>.ufc_v1.json" },

    "cooldown_ledger_ref": { "artifact_id":"sha256:<...>", "artifact_relpath":"eudrs_u/evidence/sha256_<...>.cooldown_ledger_v1.json" },
    "stability_metrics_ref": { "artifact_id":"sha256:<...>", "artifact_relpath":"eudrs_u/evidence/sha256_<...>.stability_metrics_v1.json" },

    "determinism_cert_ref": { "artifact_id":"sha256:<...>", "artifact_relpath":"eudrs_u/evidence/sha256_<...>.determinism_cert_v1.json" },
    "universality_cert_ref": { "artifact_id":"sha256:<...>", "artifact_relpath":"eudrs_u/evidence/sha256_<...>.universality_cert_v1.json" }
  }
}


RE2 verifier uses this as the entrypoint.

Appendix B — Required “no ambiguity” conventions

These are mandatory coding rules for EUDRS-U modules and campaigns.

No reliance on dict iteration order unless canonical JSON sorting is applied before hashing.

All lists are ordered; if a list is conceptually a set, you MUST specify its sort key.

All binary encodings are little-endian, and padding bytes MUST be zero.

All paths in artifacts are repo-relative POSIX paths.

All comparisons are bytewise, and tie-break rules are always explicit.

All caps are enforced in both producer and verifier, and verifier is authoritative.
