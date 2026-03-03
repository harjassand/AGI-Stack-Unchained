# components

> Path: `Genesis/genesis/components_v1_2/components`

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
- `17560c6b52b4f72f801941710c9b08f5be0cf8bf675f3d54f7e874698d9d66e0.json`: JSON contract, config, or artifact.
- `1b71fcf275379056cfb4ef070d729a2547d1edb1bc4460705bde3e5710211862.json`: JSON contract, config, or artifact.
- `20ce80702c84af7b64be52627181047638bc80b79c4c7fb086ca27b4fd3bdc98.json`: JSON contract, config, or artifact.
- `2103361300f9568b627e1f418628d9b05da0d05b341b5bdef06f7d9455e0e5b7.json`: JSON contract, config, or artifact.
- `2747020cdd19f0ac341dc80e9d7b61d73947fefb1a9930052bfe49acd19cd1dd.json`: JSON contract, config, or artifact.
- `2c1d7d7ba4a45e528e101e0442cad1d521aff0d3561427a95935a3110e3d24d3.json`: JSON contract, config, or artifact.
- `3527170ac30cb58369b2262aca1880e1a6c9d1214eae68d4df03fe05f450622f.json`: JSON contract, config, or artifact.
- `417c72bdb973b2bde380666bc62c908f835f0985c0ea450e0a15d00f39f1898d.json`: JSON contract, config, or artifact.
- `418842028f19e3315098120c1be01ade4c0900438d1e685d08967bb0405298e4.json`: JSON contract, config, or artifact.
- `45402bab85115ad23754157a1de4469d789752f7183dd1714a36b1b29ed11578.json`: JSON contract, config, or artifact.
- `52b81515b5d0ed15c0f3eda25f26d5bb82b88e4988e6bc8ce8948b9f308c4f18.json`: JSON contract, config, or artifact.
- `52e959ed4a30e7b0bb69e6baabd72bd17b4c0fe669b780ee64626b6d5a24804f.json`: JSON contract, config, or artifact.
- `536a52be9c5ae2346a72e367d8ed90eb6666717540619b9fb615e7a32dd2896e.json`: JSON contract, config, or artifact.
- `555029e4d478cd47ef2ba39229e0d464c40c748d9e43c6b75d53bd8960ec8115.json`: JSON contract, config, or artifact.
- `5dc13d2bf5cbddf74d93304d5dda5e5f58736eef24cd31d7038de448675e41e0.json`: JSON contract, config, or artifact.
- `5f3b96453066bacf5a6009630334c0684b930abf003d7cee6f13363afbbdf029.json`: JSON contract, config, or artifact.
- `603dada831913b1177473b42105efbcca40751ffde1c4825dbddb010068a5641.json`: JSON contract, config, or artifact.
- `6b33de92b23d4c2cc7113bc80586220f3dc834c86c3ecf3a00dfde8d89c6709c.json`: JSON contract, config, or artifact.
- `707f3574ad0663f86f25886e571d2d6f2f77328c98077e74e0e6a983c2eef0a8.json`: JSON contract, config, or artifact.
- `748888956201967ba3622e8f633bf2b4914afa5153d1e38c427e49f266b4f202.json`: JSON contract, config, or artifact.
- `89ba53bfb0e234460ddc42bee3ad29644cd7a509d1cc4897543f1f739e7831ca.json`: JSON contract, config, or artifact.
- `89bd7413eec02fec96acd369be1accfb189a973fce00e20f476a9312e2053094.json`: JSON contract, config, or artifact.
- `8aed38eaf7a2a03f73eef47bc0b79d03128fc8128a44350230ed4357aab0e844.json`: JSON contract, config, or artifact.
- `9c9834b52f42d431df9cf8b18e685035377b4f7c48fd0a473fb8c4d8385bf66c.json`: JSON contract, config, or artifact.
- ... and 13 more files.

## File-Type Surface

- `json`: 38 files

## Operational Checks

```bash
ls -la Genesis/genesis/components_v1_2/components
find Genesis/genesis/components_v1_2/components -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Genesis/genesis/components_v1_2/components | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
