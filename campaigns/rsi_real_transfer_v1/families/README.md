# families

> Path: `campaigns/rsi_real_transfer_v1/families`

## Mission

Campaign configuration and execution packaging for reproducible orchestrator runs.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `2401f004628522230d01405b41ac0ffe774d196fd47c9b6f7a0362737c8c5667.json`: JSON contract, config, or artifact.
- `27ca61ecad3c072d754d835131cad8c673e7f99f8ff0711f1b6e8694a5ebbe9f.json`: JSON contract, config, or artifact.
- `312969ac1dfb073bca2bcb245310075e1aefe16b72e4bc3afd8c36c9d70b2dcb.json`: JSON contract, config, or artifact.
- `3331f7f6166527c3566373d72d73219640309f75dc62ebb3aaf2a880a0a62b36.json`: JSON contract, config, or artifact.
- `38a6057db01333f1ca7fb100589a0c0ec09ff2e67c8791af8a5ae57a1428c51d.json`: JSON contract, config, or artifact.
- `421f0c7d7a0f7676ce90e55a724715df1ec234fbaf26877b5aa3487e7eb0fbc4.json`: JSON contract, config, or artifact.
- `5ab40bfa3785efa8f159d71a6e0e582d0e295e1cb2171e5014ef53e15b4b56ea.json`: JSON contract, config, or artifact.
- `5e9d10be131958aef8bd440621b474236c0ed5fb9a268b18b6834395b127fd1d.json`: JSON contract, config, or artifact.
- `6ff3c3246a41738cc0261f245cfb1fea297d0a87d87594114df1648bbb0ee4e1.json`: JSON contract, config, or artifact.
- `719281ac18203ce83adeada7358a8558ec1ba5075be1be459c9e7d44167cb12f.json`: JSON contract, config, or artifact.
- `735d1548ef4a0773eb3bb35b36cf766a5736dc96c110b4a312f63d29ae94d79e.json`: JSON contract, config, or artifact.
- `7c1ce9f6265924770d367c1e5f50475396b92187fd3a51df3b293656c49afd9c.json`: JSON contract, config, or artifact.
- `7e32c4a3f5cb4061c08f2f9a3f0919002d3c64315a8dcd429d6d7c35e72a2622.json`: JSON contract, config, or artifact.
- `85a390bcec11a5864419daa05a7b7c3e1de66f8b9c23fbf745c590cdd701c65d.json`: JSON contract, config, or artifact.
- `89b94ca3504bf37f021200430bb1352648f16c8ff2ed227c34b8190401d88a4f.json`: JSON contract, config, or artifact.
- `9e2a7c12b33c7be10c717b346af6e17efb29eab9f1277ce6882a4cb22c710750.json`: JSON contract, config, or artifact.
- `a0cc5c259355e25712d568a8446f0b26038bc6399fc31af5082ab30a0630ec5a.json`: JSON contract, config, or artifact.
- `a2603ab54ad21a936d2defbaa046cb662e064dbc52420b5bdd6d94f402322819.json`: JSON contract, config, or artifact.
- `a91fe8a44176cd696881c3a35eb27e5efcc2ec0a02e368c81afda3e627239182.json`: JSON contract, config, or artifact.
- `afdb9bb90ad721845a3ae6dc6a298d122bc9a0633aa225b7bad93accacad4acb.json`: JSON contract, config, or artifact.
- `b27dbe62056ec4e9d3138a8b2b8f9ae6805ccf38d4e6e242c21f7903a4404322.json`: JSON contract, config, or artifact.
- `b401f9cd65240633a7218d468e37e2cc40e7d28a5b43f12730971a8853534e91.json`: JSON contract, config, or artifact.
- `b6dd14c1b879badbfcf8324bc19a245939380cd471695d214812c569379ff999.json`: JSON contract, config, or artifact.
- `witness_seed_editworld_fail.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 24 files

## Operational Checks

```bash
ls -la campaigns/rsi_real_transfer_v1/families
find campaigns/rsi_real_transfer_v1/families -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files campaigns/rsi_real_transfer_v1/families | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
