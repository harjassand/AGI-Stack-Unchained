# Domains

Domain packs, schemas, and solvers used by Polymath and domain-targeted campaign flows.

## Current Domain Pack

- `pubchem_weight300/`: Fully scaffolded example domain with packs, schemas, and baseline solver.

## Domain Pack Contract

A production-ready domain directory should include:

1. Level packs (`domain_pack_l0_v1.json`, `domain_pack_l1_v1.json`, ...).
2. Input/target schemas under `schemas/`.
3. Reference or baseline solver implementation under `solver/`.
4. Local README documenting domain-specific assumptions.

## Notes

- Keep domain packs deterministic and schema-tagged.
- Prefer additive versioning when changing domain contracts.
