# cases

> Path: `campaigns/rsi_sas_kernel_v15_1/brain_corpus/cases`

## Mission

Campaign configuration and execution packaging for reproducible orchestrator runs.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- `sha256:006e7e9f57eef218f247976a5b165f5410ca2adc2f2c3b766b599694ffdacd0f/`: component subtree.
- `sha256:039c896027a7608f865ca12ac5876f4b2833c23f0442abe014eed993c673d417/`: component subtree.
- `sha256:0499e24259d129661a5d32f50babea518440a08abe1a64f634e0f2eb94ae3d9a/`: component subtree.
- `sha256:07b781b93f5e06594dd3702aa975cae13d3cf5ec5b0d9ed4a8a1003f98448cff/`: component subtree.
- `sha256:08e4a5f52ed6d432dd0a2ecefb0c3daca9aead58035ab0f9653dee89cf328a17/`: component subtree.
- `sha256:0a3850d65e07292a7c32459b098bc022931b53301c4c93176abf615681a2202e/`: component subtree.
- `sha256:0b09943db6134f7ed8b4942871157228ba77d395a6b8f33bd7a0150902598e7e/`: component subtree.
- `sha256:0e9a20c7321ab4380afa4283233b75af84b2c4d1c7c27c03ef1a304bb4bea2c9/`: component subtree.
- `sha256:0faba53d8e62a3f5708e6e6f05c3666ec67ede3f0815b70b809a70e325e4b04c/`: component subtree.
- `sha256:1015005a81164a5635558b505ff5ebf9042da25467065be9f63d3ce4d0cb6673/`: component subtree.
- `sha256:10618283861e1c3a70913bd5f8b6cb6763a53b1c0e4844522c6f6331ddacb94b/`: component subtree.
- `sha256:1ad3ac240c26d264b44e0e2566eec2dabb82adfbaedf7a6175406f50bb0c0052/`: component subtree.
- `sha256:20174f5cb5675997d4580c2f707a630cb3b0960779f81486f025875f0cac4229/`: component subtree.
- `sha256:20d8ad5ec21dbfa07a8b626b78e2dbcfafc5ced9a9d84d62b7e09e68fe03491e/`: component subtree.
- `sha256:215fe2fce3b1a32b23bdb82f716d91a75d2956f2fb7c766ac1b40af5528680dd/`: component subtree.
- `sha256:25785b197c7f6339acf52b6321a25db73b6bab542da0cabb23e5a0d3c7bcb25d/`: component subtree.
- `sha256:25e028c983225fd11c43ee8d015376fb31c6fc4b294854cc2cc5815a2d70a903/`: component subtree.
- `sha256:2d25e57be1be0668186c0fd13b581ae06aa6f47e394a839c8d6dacc50c663952/`: component subtree.
- `sha256:30c65b752c9cfd0d29f3711a017d9b952145b8b4c6ecb5de15875b3d1951a3e0/`: component subtree.
- `sha256:3241ea84ecc359b69a67da94c81088e8736b11e704eae5b47de0de3bb8da35c5/`: component subtree.
- ... and 80 more child directories.

## Key Files

- No direct files at this level (directory primarily organizes subtrees).

## File-Type Surface

- No direct files to classify at this level.

## Operational Checks

```bash
ls -la campaigns/rsi_sas_kernel_v15_1/brain_corpus/cases
find campaigns/rsi_sas_kernel_v15_1/brain_corpus/cases -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files campaigns/rsi_sas_kernel_v15_1/brain_corpus/cases | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
