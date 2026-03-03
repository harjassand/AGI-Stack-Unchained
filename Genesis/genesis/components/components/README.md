# components

> Path: `Genesis/genesis/components/components`

## Mission

Schema, protocol, and artifact-contract definitions for stack-wide interoperability.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `0e5b03eef48f94902df706cc0d9bf76541cadba05bf6a5742887db88ac4c742b.json`: JSON contract, config, or artifact.
- `37228364ce39e3d5344c4c5d30fe767689a8b7f75dc59552951b1eea68839c44.json`: JSON contract, config, or artifact.
- `6273c79feb7df403008aed6ea94de3e628140e9bd5d26b13dae4b729466d901e.json`: JSON contract, config, or artifact.
- `7d772c85ee0357e52627a17f60972026ef53c132783b4cc917e19e90817fb46f.json`: JSON contract, config, or artifact.
- `8bd3ac88eb59b49239a76436f3ca1cfc699d8d94198ddab5ae1bc4f0507e718c.json`: JSON contract, config, or artifact.
- `b4b1d4c36ac059049ccb8780fbc290af26a3499edc743f53fb70c1f83dadead8.json`: JSON contract, config, or artifact.
- `bb473bb3fe223072557c314ff3596fe7c1623cb43b1ec1dd01ebabe2e28fa436.json`: JSON contract, config, or artifact.
- `cca5796b4a188dcdf2dd098f69c8dc46477309ac3600e69db512400aa863d4c4.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 8 files

## Operational Checks

```bash
ls -la Genesis/genesis/components/components
find Genesis/genesis/components/components -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Genesis/genesis/components/components | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
