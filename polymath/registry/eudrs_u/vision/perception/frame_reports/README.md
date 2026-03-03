# frame_reports

> Path: `polymath/registry/eudrs_u/vision/perception/frame_reports`

## Mission

Polymath registry/store logic for scouting, bootstrap, and domain conquest flows.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `sha256_07478b04bde3893cbffcaadd6a0cea50f3ea4948f4c8fb906c15eec1d81fd1d2.vision_mask_rle_v1.bin`: project artifact.
- `sha256_0bced6e910816339ece5629a38accf215be66ac9eda96a44514f64be2aa59c3f.vision_perception_frame_report_v1.json`: JSON contract, config, or artifact.
- `sha256_1d3b7ce4bbc2ec19bafefd5ad26392c3ad855736104c396918a0f152aba08a26.vision_mask_rle_v1.bin`: project artifact.
- `sha256_21ea40f2e372e52b5c359de5f6f0d7ac842dd538db57bcdd66e1fedf0c33a05f.vision_mask_rle_v1.bin`: project artifact.
- `sha256_24acd8fec0d6a37fae47a00e88cd512c656d02ea2d69e67634482154cf165f34.vision_mask_rle_v1.bin`: project artifact.
- `sha256_515f4700e04b99c0b14781661781c546ca6e18009907b5f00decd3132f15c261.vision_perception_frame_report_v1.json`: JSON contract, config, or artifact.
- `sha256_567e5d00ef8fe76b9042f969f8da71a9be258dfaf99d6ced58425013c7e8cd08.vision_perception_frame_report_v1.json`: JSON contract, config, or artifact.
- `sha256_68774b691a6ae4abb6cf1e3e91d3ae7db669b68c9b2cb9527c1cb9a97de7dd16.vision_perception_frame_report_v1.json`: JSON contract, config, or artifact.
- `sha256_82e52cb57cd342f4a804bfd893100e2c5255a586f8abb26a74742109edb18697.vision_mask_rle_v1.bin`: project artifact.
- `sha256_8bbef73694d67dc46641a02fc6c27ec2b0667c5d0d49a17dc5fde0ffbe16ca7d.vision_mask_rle_v1.bin`: project artifact.
- `sha256_960cc4460f31f55fead1ebe613ba1d905893418684d0d3ba27e7d6a709315153.vision_perception_frame_report_v1.json`: JSON contract, config, or artifact.
- `sha256_a8a73cc6ea52601b51ba733478886e702838087e15a1ac5bcda1514afaf1ddb9.vision_perception_frame_report_v1.json`: JSON contract, config, or artifact.
- `sha256_ab2da96f4c0660e91709d49575cd5002ebad7fe0577a2e5e92b5a733b8fb8507.vision_perception_frame_report_v1.json`: JSON contract, config, or artifact.
- `sha256_c3e836c1eacb5ea1b5ab9b8c46ed1846dd115cf079ee4b30b310573f18a61c7d.vision_mask_rle_v1.bin`: project artifact.
- `sha256_ccb31eb90089ccf2cf20931adfd1b1ed0c3d576cbeb10e64eb45e4812618c4f1.vision_mask_rle_v1.bin`: project artifact.
- `sha256_fc4d7f0cd1fcff8158d1bcfb5f0de028e1891bc067771eb0f40bd299f2d3f0f8.vision_perception_frame_report_v1.json`: JSON contract, config, or artifact.
- `sha256_fce5637058cf842de80bb4d989b0be92b124ee3bc590082ec44eca80d916dadf.vision_perception_frame_report_v1.json`: JSON contract, config, or artifact.
- `sha256_ff3a3fb720f3dfe40c18cd6e2aad7283e665fbe99515d20b97fe30fa5bc93453.vision_mask_rle_v1.bin`: project artifact.

## File-Type Surface

- `json`: 9 files
- `bin`: 9 files

## Operational Checks

```bash
ls -la polymath/registry/eudrs_u/vision/perception/frame_reports
find polymath/registry/eudrs_u/vision/perception/frame_reports -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files polymath/registry/eudrs_u/vision/perception/frame_reports | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
