# tracks

> Path: `polymath/registry/eudrs_u/vision/perception/tracks`

## Mission

Polymath registry/store logic for scouting, bootstrap, and domain conquest flows.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `sha256_10aac4f9c7771154d7db0cbe12c500cc30fef9b87f0edf73e990b0ace828feed.vision_track_manifest_v1.json`: JSON contract, config, or artifact.
- `sha256_991a8b5af8c9a4134eb851d37e811890dc7027fbac7cea198339039a5d0716bf.vision_track_manifest_v1.json`: JSON contract, config, or artifact.
- `sha256_a12e2bdb97a348cfd81cfe18273cbc36fd4808c66f812c2eab61188348466c1b.vision_track_manifest_v1.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 3 files

## Operational Checks

```bash
ls -la polymath/registry/eudrs_u/vision/perception/tracks
find polymath/registry/eudrs_u/vision/perception/tracks -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files polymath/registry/eudrs_u/vision/perception/tracks | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
