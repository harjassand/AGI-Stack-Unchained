# components

> Path: `Genesis/genesis/components_v0_7/components`

## Mission

Schema, protocol, and artifact-contract definitions for stack-wide interoperability.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `0276d9623b8713d8bb50efc841eec50f5b754d561c48b4a2729d4efffadc5a34.json`: JSON contract, config, or artifact.
- `06f90f834a75ccf808da57bf776e9182825f60216c1002e70cd8778534eddb35.json`: JSON contract, config, or artifact.
- `137792f0469b1690cda82dc8caa2b4f6496e16a5d635e7b35a8f5705bf8f9374.json`: JSON contract, config, or artifact.
- `17560c6b52b4f72f801941710c9b08f5be0cf8bf675f3d54f7e874698d9d66e0.json`: JSON contract, config, or artifact.
- `26dc26a20f70a7bdc5993e0d360526344a004d66c329bae96d1047120ab39271.json`: JSON contract, config, or artifact.
- `2a24e6d4f2220c1afb8d2bf89c2b404d695cde6af2ed80b4e5ceaed843ebed61.json`: JSON contract, config, or artifact.
- `3527170ac30cb58369b2262aca1880e1a6c9d1214eae68d4df03fe05f450622f.json`: JSON contract, config, or artifact.
- `45402bab85115ad23754157a1de4469d789752f7183dd1714a36b1b29ed11578.json`: JSON contract, config, or artifact.
- `5f3b96453066bacf5a6009630334c0684b930abf003d7cee6f13363afbbdf029.json`: JSON contract, config, or artifact.
- `748888956201967ba3622e8f633bf2b4914afa5153d1e38c427e49f266b4f202.json`: JSON contract, config, or artifact.
- `88bdb775bc28cd2921a2bfe847773f85389ee5a95bb19ad03f8141ebc1873045.json`: JSON contract, config, or artifact.
- `89bd7413eec02fec96acd369be1accfb189a973fce00e20f476a9312e2053094.json`: JSON contract, config, or artifact.
- `9870f4245f3bfbd5375412384a4e2d1eaccc84414e23c6fb3740de681aa73f97.json`: JSON contract, config, or artifact.
- `9c9834b52f42d431df9cf8b18e685035377b4f7c48fd0a473fb8c4d8385bf66c.json`: JSON contract, config, or artifact.
- `a1d81ebf7e173cc24ce82d1ade346b3f45b3b66db62cc0797a54d8b38ba60b81.json`: JSON contract, config, or artifact.
- `b1638d3ec6b9ade51e56d615f72c3a5fd346ee82df84a87c009bf1adbf963cf4.json`: JSON contract, config, or artifact.
- `cdec419f2c1ab098b4c6e97938a5cb96538e2e4c6a298cc849a0f01232c470ee.json`: JSON contract, config, or artifact.
- `d0029649745410728eaa4926080a06fa9e289a5c09e01f2eccd3f22fd29df883.json`: JSON contract, config, or artifact.
- `d5dd8faca081a118c8473096bde361c788f3932517c85dbd9861ca68520d9911.json`: JSON contract, config, or artifact.
- `e5da7643b3cd032e8adf78431c63e4bcdb9240a0fbb908f23cb297e057cad5f9.json`: JSON contract, config, or artifact.
- `e7409e12696e668047d91e48ec531a2e7f4f3250f0c60f5c6582bbeb014c5795.json`: JSON contract, config, or artifact.
- `f93fd21e3843b05944295dccc299fac4be6f457ee66794231bc3b6f11d6a864e.json`: JSON contract, config, or artifact.
- `fb565f0ffefe0f3a7a521999be3ef71fa901d1cb568c50a074b2eb74ce2026ce.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 23 files

## Operational Checks

```bash
ls -la Genesis/genesis/components_v0_7/components
find Genesis/genesis/components_v0_7/components -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Genesis/genesis/components_v0_7/components | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
