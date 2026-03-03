# packs

> Path: `authority/holdouts/packs`

## Mission

Governance, authority pins, holdouts, and policy envelopes that gate promotion.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `sha256_00c48e1a48e603e8c49a5995f8eefcbd8a993e477fef173b18878df6ba69fe94.json`: JSON contract, config, or artifact.
- `sha256_01560da4b538bdae3892a0ce1f9f35c82b7180a07add6440b6a5cdc4ccc61243.json`: JSON contract, config, or artifact.
- `sha256_0191b94649b0be763293dbf79e9de453891ae8533626600ef05bab8bc26a3de2.json`: JSON contract, config, or artifact.
- `sha256_0334af79b07c1d6dd804a2577a9fde0d70553f6f6354ad90b9a0286a3673c1c9.json`: JSON contract, config, or artifact.
- `sha256_03f472a740dc833d4b51251daf41ea4dcecd9cfad2c75086070b9e1b61cbb29c.json`: JSON contract, config, or artifact.
- `sha256_0431cb1c567e4b063c1ae4c001775966624d8ce6ad2049a17335db003e51b17c.json`: JSON contract, config, or artifact.
- `sha256_04edc5d8499752e6a8216dffd86e871a9f960fcfa9f23d701441bc1d3d759405.json`: JSON contract, config, or artifact.
- `sha256_05dc7a40dc026d30348aa9b39d300a66d77bae677c4081377dd3deec5c7218d7.json`: JSON contract, config, or artifact.
- `sha256_0652fca43c671c380e71a48c337efba9e396a2064d46728ff68d0a0ffe8cc127.json`: JSON contract, config, or artifact.
- `sha256_06929b776ea436f74b98e2aaea95422ad451296a79d1883e4c0b641558b750fa.json`: JSON contract, config, or artifact.
- `sha256_06e7c0f1adb5d1b2595fd96cce08755c105a5af338b09384da1a3386e6d5aaea.json`: JSON contract, config, or artifact.
- `sha256_07cb35144fd0b835b42ab18f2846330539248fd0e495e326fe773515aa265ea6.json`: JSON contract, config, or artifact.
- `sha256_0870ebf6e42f8f0ea104725ad5d6cc8d8afe7c05ec9e1aaf669ed65e08c0bb36.json`: JSON contract, config, or artifact.
- `sha256_08c93dee3a81e94fc87f83168795d19130d3dfb0f36806768b6fb324f0b159b1.json`: JSON contract, config, or artifact.
- `sha256_094a8746140bd848ec9b15c5a08ef2be4c42c613dad438c58aabeaaef7be73ad.json`: JSON contract, config, or artifact.
- `sha256_094e058d77064199750d5aa0a970f5e8b54e9ca0a941b6beda25a564936a1943.oracle_hidden_tests_pack_v1.json`: JSON contract, config, or artifact.
- `sha256_0a5a8a3bc077ac0b8c4024a66d3a0454cea6800f30b78d84b4c78bfb69c492d7.json`: JSON contract, config, or artifact.
- `sha256_0a7ef7856636f7656b8a375099afcc9e5a2ca6cb41775d7ee4cb0dd9ac298072.oracle_task_inputs_pack_v1.json`: JSON contract, config, or artifact.
- `sha256_0de45b5df19b3890bca04e80e34b0d64df9ac07b79bc76fdb7da76da6def43ce.json`: JSON contract, config, or artifact.
- `sha256_0df34d36dc35f39f01d0cfd5da3bc12b8219d77299461a030d88f4d607fb4c07.json`: JSON contract, config, or artifact.
- `sha256_106fd0a2bc975b7922a832b25d6b5d5b73098e09a05b892d0ab9f71d24489fd4.json`: JSON contract, config, or artifact.
- `sha256_10793d048be47f4b68922e8b4f3d3fdbdda372778c6baf83c3ef2a38f7a611e4.json`: JSON contract, config, or artifact.
- `sha256_11f6d153c1b429f60d615a8b677c6b7af87d7710d363ffe81a2b21c36efdd0f6.json`: JSON contract, config, or artifact.
- `sha256_1276ee039a1a275b87caf0f1272ef2264016a62894aec8522bbacd25f4666ff9.oracle_hidden_tests_pack_v1.json`: JSON contract, config, or artifact.
- `sha256_1298f8e3a12e8b2dcfb0a38d659a5bd1208d23b05800659929acb649cd11d276.json`: JSON contract, config, or artifact.
- ... and 257 more files.

## File-Type Surface

- `json`: 282 files

## Operational Checks

```bash
ls -la authority/holdouts/packs
find authority/holdouts/packs -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files authority/holdouts/packs | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
