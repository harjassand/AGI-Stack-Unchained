# Pi0 Baselines v1 (Pinned)

This file defines the frozen Pi0 baseline programs for v1.5r.

## Constraints

- Max instructions: 128
- Max horizon: 32
- Memoryless
- Reads only phi_core features

## Programs

### Program 1

program_id: `sha256:8a2cdeade1c4d024d284c0b19a91bd3f731b3db813e64ba4a352bb728f6f8a73`

```json
{
  "predicate": {
    "feature": "xor_obs_mod_16",
    "op": "FEATURE_EQ",
    "value": 0
  },
  "program_id": "sha256:8a2cdeade1c4d024d284c0b19a91bd3f731b3db813e64ba4a352bb728f6f8a73",
  "program_version": 1,
  "schema": "pi0_program_v1",
  "schema_version": 1
}
```

### Program 2

program_id: `sha256:fbfa97155da1fae79768b921c15b27d245008e6e47761f83cbea0665778b4ecc`

```json
{
  "predicate": {
    "feature": "first_obs_mod_16",
    "op": "FEATURE_EQ",
    "value": 0
  },
  "program_id": "sha256:fbfa97155da1fae79768b921c15b27d245008e6e47761f83cbea0665778b4ecc",
  "program_version": 1,
  "schema": "pi0_program_v1",
  "schema_version": 1
}
```

### Program 3

program_id: `sha256:0f32760686de5f150caaa704be9ca7c7d72d319bbdf5eadf4db909324556c4ef`

```json
{
  "predicate": {
    "feature": "last_obs_mod_16",
    "op": "FEATURE_EQ",
    "value": 0
  },
  "program_id": "sha256:0f32760686de5f150caaa704be9ca7c7d72d319bbdf5eadf4db909324556c4ef",
  "program_version": 1,
  "schema": "pi0_program_v1",
  "schema_version": 1
}
```

