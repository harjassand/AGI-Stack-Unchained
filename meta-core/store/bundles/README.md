# bundles

> Path: `meta-core/store/bundles`

## Mission

Promotion, staging, verification, and rollback control-plane foundations.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- `0118b8e6dcfc3280e12ccae84064667f9983c8edbe1785393b8d0af4f0f8e3c2/`: component subtree.
- `086d8d89def2901df97b4c88ee98909438ab0804afabb389aa74319b031f8abf/`: component subtree.
- `0af1510f5cb8854a0abb6e21d841abdf00a22be904ae71ab2111a5ddb2c818d4/`: component subtree.
- `0dc6c0b82f5742c8cafa9ae52d0647f170cd92839bc512eb4511475964b56396/`: component subtree.
- `0e4b5c81cd32f2b4bb89927e69d45ee2cfa1ee7ac32efc3cf3c77c94d05a4e6a/`: component subtree.
- `0e56fa55a4fe451fe79bf02579be3031d1bd6b5cc5fef0a03ad0cde4f22ff505/`: component subtree.
- `1454c1210b334795e0eb5cb328a3f23bc0d165e59b0b2673fe99879e65f75fc7/`: component subtree.
- `14f559bf871bafc0a80c66a2e096302d30f3e40c287c03ea1842c92a354ba7d7/`: component subtree.
- `15d6667888102d3294407d2b2919893d267b42b18e91bc97496d5319e31081fc/`: component subtree.
- `17f2b6cdbf706695d0f65109e6d7b7fbb7d0617760aaa08533a53b5a5fd06297/`: component subtree.
- `1860c395e9fafd94442d7aa2bf9c6a1b880f19699f06e086bfb594344440ebf7/`: component subtree.
- `18ed54d933d144458c8d2f203355d6cdac85376b7265438f7a26922db35e7923/`: component subtree.
- `1d278f92aebb77b9f56158504a27bda88e118392aa74bbe4bc7e45d4f716ce14/`: component subtree.
- `1f81ad32134c8235b584dbec91cf5d34521e4df152419d91418c94031781d336/`: component subtree.
- `23b236960bddbe1a50578251d6f9118f0044ac14f745d2a5bbfcda8c46dc9d35/`: component subtree.
- `23b3a9b55fdd04f150127c1b0cb64844970e130a83c6ba71af523147c023802c/`: component subtree.
- `23ef7941583482513bf21a104cb02b24c4a53a0580bc216682383cd2d005ece6/`: component subtree.
- `24c1204427fcc57d455b0a5ea3b2f57df41ff7edd19fb3762d267f25f9834582/`: component subtree.
- `273a35c9afe23a63ae7e75ab911eb1245c92aabeb2ee175cc4bb179d3640c72c/`: component subtree.
- `2b1bb39f635dab45a752eabcca84688f4b2cafeb1770c0c76eb6047798a22456/`: component subtree.
- ... and 59 more child directories.

## Key Files

- No direct files at this level (directory primarily organizes subtrees).

## File-Type Surface

- No direct files to classify at this level.

## Operational Checks

```bash
ls -la meta-core/store/bundles
find meta-core/store/bundles -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files meta-core/store/bundles | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
