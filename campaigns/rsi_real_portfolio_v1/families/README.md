# families

> Path: `campaigns/rsi_real_portfolio_v1/families`

## Mission

Campaign configuration and execution packaging for reproducible orchestrator runs.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `04070c97f844171f26bac4d9ea4f7e2a6d89eb6765e2dbb70e86bf1e05d752fa.json`: JSON contract, config, or artifact.
- `06afe9c88705ef4d1995b3ffa36943f656268f059beb17de408868fb381789ed.json`: JSON contract, config, or artifact.
- `09190dd3872e50fee2f705020e21ebd62b17e9567bd56270682cdca42964e20e.json`: JSON contract, config, or artifact.
- `09a7472ba84627b12c6e158573918cad0ee571572b7fe1c549fed4b76f564e6f.json`: JSON contract, config, or artifact.
- `0c120bb8c7d4029921969c1de2545bbceacdce77c0950bac856e445ccc37dc6d.json`: JSON contract, config, or artifact.
- `11578890daf159cb97fb5c513b533ea6e74141ef2322dbc5e216e2e6c2a9e4d6.json`: JSON contract, config, or artifact.
- `11755f16abcefc624bdef1826283164e35c6d841c5e1050bf64248f4b2acd265.json`: JSON contract, config, or artifact.
- `13c596fa47648c0ad5a7b0778f279499b0cde0e50119da0bb1277171136315a4.json`: JSON contract, config, or artifact.
- `162183b5f6ea9dab4fdf80cd8fb8de40e17a28ca16e474dc8aa4c4c0014483bc.json`: JSON contract, config, or artifact.
- `18ec4c458873a398664b6a9744a9c85cc7964acbadc18a1ad9688c745087da74.json`: JSON contract, config, or artifact.
- `2425a4752316069c513f459ecfb9cddbd93712aa77fb0a97d24d6e73f8278ed5.json`: JSON contract, config, or artifact.
- `2439c63cd000b6a2da110f098d9dbec2624dee7c278d9ce5bb782f054f71b721.json`: JSON contract, config, or artifact.
- `28c0fb31c6958efba4a6c3cd6e0252a2b94e058a0c83a0716b74bb3cf5eb0b56.json`: JSON contract, config, or artifact.
- `2ac611b70cde8183508417c8f15575973081a10d11e3ccdb5e2eafcc67bae4e8.json`: JSON contract, config, or artifact.
- `2fdb164e85c71dc58c8112ae56a4f68e4f61493adccce24dcfaf2a155639efb8.json`: JSON contract, config, or artifact.
- `356e5d63f795e4a9890548ab6fb5eda22603653f58c2e085e5aaa9cdc9b85bd2.json`: JSON contract, config, or artifact.
- `390e8f025ebd74be621510d7caf10feeca5294c290e2f6cf5ad11b9ad8e02a7c.json`: JSON contract, config, or artifact.
- `3c4509d1437fc888ef642f159d665a21002330cd74b50c05402eda8eb81dd87b.json`: JSON contract, config, or artifact.
- `3d12402f072249c6e7b00cda55f3b41b7a1f1cb257a288b2f2b8a3fa54adc671.json`: JSON contract, config, or artifact.
- `3ed1d236e0527016650633f276b0f71de856b292672d5b63f6d00252db6908f7.json`: JSON contract, config, or artifact.
- `4598697ed86bb4677e1b759396531a9bb1bc7e28b297dbed156a016b357cd4fe.json`: JSON contract, config, or artifact.
- `46550a911a2d0617ab19653051d77f6408c2b6e52eea13ca8252bf0c050a3ca3.json`: JSON contract, config, or artifact.
- `4728f67cc6f6601be86b9d02447fc2da3b4dec7b5eae2238701154f782176021.json`: JSON contract, config, or artifact.
- `4b68e9bbbcff6f9158578d7ed9994b657a4a500d354edcfd848f733dc934787a.json`: JSON contract, config, or artifact.
- `4cca10a2aaf266bfedb9e11dfa2957a6b0e7f8fca2104eea5f1284b909d7128b.json`: JSON contract, config, or artifact.
- ... and 72 more files.

## File-Type Surface

- `json`: 97 files

## Operational Checks

```bash
ls -la campaigns/rsi_real_portfolio_v1/families
find campaigns/rsi_real_portfolio_v1/families -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files campaigns/rsi_real_portfolio_v1/families | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
