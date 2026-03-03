# families

> Path: `campaigns/rsi_real_integrity_v1/families`

## Mission

Campaign configuration and execution packaging for reproducible orchestrator runs.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `02344afc75c18049eb10af5448b846f06e8b6b256258af51dda600ed06bd2e9d.json`: JSON contract, config, or artifact.
- `032dfa16fe2a8e85d70921e21b4d741f866a91bc102324725db2bec05fd5f440.json`: JSON contract, config, or artifact.
- `120bca0d6fc89db7771c49b4d7a50c6168478bd3719f9d81282e37f05e27d104.json`: JSON contract, config, or artifact.
- `1a9ca3a2bde55f3faaf13f29f252cb7fefabdf993dbde482c57f6d4f9c3bd72f.json`: JSON contract, config, or artifact.
- `2e775f0c1875874593219e89c4b16a38337296e1bbafdca59433bb2416645bf9.json`: JSON contract, config, or artifact.
- `44fd22486344b169e7f57b368c90b3b9641cf6fc4f28c64e348c4499d633caaf.json`: JSON contract, config, or artifact.
- `50e33496456a6e89742b9f621c8fcb72c1d69ecce4dafd323b5aa3dfabe326d5.json`: JSON contract, config, or artifact.
- `523b9896b8d4ae0d89e468ea987c310ff7ec2befd22ec2c2908a0645d23e06d3.json`: JSON contract, config, or artifact.
- `6443002f17771d37cd06d4a6b78a9d620bc570e6dcf3b1b40c83dc564af471dd.json`: JSON contract, config, or artifact.
- `7f6a646fc6d71c6a872f0ef37a8eeaffcd0237bf807683dacc0c231a7de9dd5f.json`: JSON contract, config, or artifact.
- `88d2442a2a76b28f04f39b5b156e7a3cf4d02cefa7ef9d42b03ee205d8541828.json`: JSON contract, config, or artifact.
- `9cb4ba2043da30180d94efcad1f5fe552e18b4a95b1bfd327d5e89ad069549ae.json`: JSON contract, config, or artifact.
- `9f0eff2cb2e8ab700f6fecba8da6f45c2291ad6fc90c65089b00f2d9b4cdf002.json`: JSON contract, config, or artifact.
- `a6d46d4ffa6e5615baa722314ef5d80ff17976b67ac674e836f7f4250c2c16e8.json`: JSON contract, config, or artifact.
- `c732351af77a12045249feb3ba83cceaed533539c30b49ab31ac84c8da1e4a06.json`: JSON contract, config, or artifact.
- `d6628c05267b453738a94b1a226ec443e93d137441083aae42f6950dc385160f.json`: JSON contract, config, or artifact.
- `db86a64154f8f110b21658a9f0f6fd3c4f512b4bb4b175771d08a265c1d2a326.json`: JSON contract, config, or artifact.
- `e0c2ced4f8f8242cf2492052ef5da194c9801a64c7a54194fd781ca95eae2144.json`: JSON contract, config, or artifact.
- `eaba4d07bde280212f2ec5de57eca3a6ac98a821f616d73bf8dc3cecc9ee6575.json`: JSON contract, config, or artifact.
- `ead5d3fe9e617606263c8931a4fd2e12b485d04adc739202b635d16030105c87.json`: JSON contract, config, or artifact.
- `f66125b2862b6b08f832dbb2f5bd52b7e64a0e4aaf2009099505fc23a894d0f4.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 21 files

## Operational Checks

```bash
ls -la campaigns/rsi_real_integrity_v1/families
find campaigns/rsi_real_integrity_v1/families -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files campaigns/rsi_real_integrity_v1/families | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
