# frames

> Path: `polymath/registry/eudrs_u/vision/frames`

## Mission

Polymath registry/store logic for scouting, bootstrap, and domain conquest flows.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `sha256_01cb7298b5042ab66be1bc0ced31783d4338d1ce2bb366870aad947ca7dd55d1.vision_frame_manifest_v1.json`: JSON contract, config, or artifact.
- `sha256_22272ae204caf6f61b46a868bf397cd11ba97ff7004c847aad3ec1e3cd8e6e99.vision_frame_manifest_v1.json`: JSON contract, config, or artifact.
- `sha256_266d5f5ff11d19d9a13f4f7c179d4c24a1e2d23474bc68cfa54bf7d70987f752.vision_frame_v1.bin`: project artifact.
- `sha256_27ce8f93e99a59309647a0141331c119018a2e757abbad213cc819dcc053d668.vision_frame_v1.bin`: project artifact.
- `sha256_2bd55d8c3240dacf59f55357f39e79119347d2b30f67879d24689c51c7fa4c94.vision_frame_v1.bin`: project artifact.
- `sha256_3d05940c17537533a20c09c580f50b72f22dcddab12e810482ea7cad9784b268.vision_frame_manifest_v1.json`: JSON contract, config, or artifact.
- `sha256_55a551274552b119f92b89a48bf79c83efa3daa8da1e9a4135d2fda817d6bf67.vision_frame_manifest_v1.json`: JSON contract, config, or artifact.
- `sha256_5b3192c701ae65f61dcdc63373c8bbbc2570ed194bed1a1cff3be343f2c3c021.vision_frame_manifest_v1.json`: JSON contract, config, or artifact.
- `sha256_5d6d2eef2a6fa499db6455aca724b1ca56c995c4a8b47f3903da2c3e31126358.vision_frame_manifest_v1.json`: JSON contract, config, or artifact.
- `sha256_62c8702bb63679a91e9a5b511098be806f10fc9245dfeea51a116d146e2a9daa.vision_frame_v1.bin`: project artifact.
- `sha256_67e6941c89c662a93d6309dcaebfb2e0e004f32284ea707f07a6f5a2759e303f.vision_frame_v1.bin`: project artifact.
- `sha256_6e0b97a139d2c06dc934d18c4156997aac95eaa1e5fb4f0e11e615f3408a8180.vision_frame_manifest_v1.json`: JSON contract, config, or artifact.
- `sha256_d2efa857d591f6b1e5f86090af86accc6cb9da161e812787e31f94e8b6ed4746.vision_frame_manifest_v1.json`: JSON contract, config, or artifact.
- `sha256_f8efa583c1ccecf11159560b8e5dc2b3f1daaa8e47597c36f942bbad2b01a37b.vision_frame_v1.bin`: project artifact.
- `sha256_f8f72e44be1b422de3d7bf05b280ba6b4c4c99d80423895575ee752e494df091.vision_frame_v1.bin`: project artifact.
- `sha256_febd25399c5242b8a842140fe0267a81ba45eeba0e9cda173c544a5374eeb96b.vision_frame_v1.bin`: project artifact.

## File-Type Surface

- `json`: 8 files
- `bin`: 8 files

## Operational Checks

```bash
ls -la polymath/registry/eudrs_u/vision/frames
find polymath/registry/eudrs_u/vision/frames -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files polymath/registry/eudrs_u/vision/frames | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
