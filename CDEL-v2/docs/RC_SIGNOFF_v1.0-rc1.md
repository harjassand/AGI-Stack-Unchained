# RC Sign-off v1.0-rc1

Tag: v1.0-rc1
Tag link: https://github.com/harjassand/CDEL-v2/releases/tag/v1.0-rc1
Commit (git rev-parse HEAD at tag): ee698075b8cd92aa91166ab403cc58147b9ba879

CI build link references:
- https://github.com/harjassand/CDEL-v2/actions?query=workflow%3Aci+v1.0-rc1
- https://github.com/harjassand/CDEL-v2/releases/tag/v1.0-rc1

RC Sign-off Command Log (record exactly)
0) Environment
python --version
pip --version

1) Fresh checkout at the RC tag
git clone <REPO_URL>
cd <REPO_DIR>
git checkout v1.0-rc1
git rev-parse HEAD


Record the commit hash printed by git rev-parse HEAD.

2) Clean virtual environment + installs
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip


Core install

python -m pip install -e ".[core]"


Dev install (tests + smokes)

python -m pip install -e ".[dev]"

3) Compile sanity check
python -m compileall -q cdel

4) Test suite (must be clean)
pytest -q
pytest -q -rs


Acceptance to record:

pytest -q passes

pytest -q -rs shows no skips for:

tests/test_sealed*

tests/test_stat_cert*

invariants bundle

output schema tests

(Any remaining unrelated skip must be explicitly named.)

5) Smoke tests (exact set)

Run each in a fresh temp directory:

./smoke_statcert_adopt.sh "$(mktemp -d)"

./smoke_generalization_experiment.sh "$(mktemp -d)"

./smoke_evidence_suite.sh "$(mktemp -d)"

./smoke_scaling_experiment.sh "$(mktemp -d)"

./smoke_solve_one_task.sh "$(mktemp -d)"

./smoke_solve_suite_small.sh "$(mktemp -d)"

./smoke_solve_stress_small.sh "$(mktemp -d)"

./smoke_solve_suite_ablations_small.sh "$(mktemp -d)"

./smoke_solve_suite_ablations_golden.sh "$(mktemp -d)"


Acceptance to record:

All exit with status 0

Any expected explicit rejection (e.g., harness mismatch) occurs for the correct reason

6) Evidence manifest verification (hash check)

For the Phase 14 manifest:

sha256sum summary.md results.json


(or the exact files named in EVIDENCE_MANIFEST_phase14_657e550.txt)

Record:

the printed hashes

confirmation they match the manifest exactly

7) CI artifact verification (manual but recorded)

Record links / identifiers for:

CI run for tag v1.0-rc1

Uploaded artifacts:

summary.md

results.json

suite / ablation / stress outputs (as listed in the manifest)

What must be written into RC_SIGNOFF_v1.0-rc1.md

The full command list above (unchanged)

The commit hash from step 1

Confirmation bullets:

Tests passed

No core skips

Smokes passed

Hashes matched manifest

CI artifacts uploaded for the tag

Recorded outcomes

- Tests passed
- No core skips
- Smokes passed
- Hashes matched manifest
- CI artifacts uploaded for tag v1.0-rc1
- Unrelated skips: tests/test_cache_equivalence_from_run.py
