# PubChem Weight300

- Domain ID: `pubchem_weight300`
- Task: binary classification from SMILES (`target=1` iff molecular weight >= 300).
- Metric: `accuracy`.
- Corpus ladder:
- `domain_pack_l0_v1.json` (tiny)
- `domain_pack_l1_v1.json` (small)
- `domain_pack_l2_v1.json` (overnight)
- All dataset blobs are sealed into the canonical polymath store (`OMEGA_POLYMATH_STORE_ROOT` or `.omega_cache/polymath/store`) by `tools/polymath/polymath_build_flagship_pubchem_weight300_v1.py`.
