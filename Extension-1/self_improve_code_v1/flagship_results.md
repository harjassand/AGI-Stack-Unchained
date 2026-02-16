# Flagship RSI v1 Run Analysis

## Runs Executed

- **Dev demo (5 epochs, stub devscreen + sealed dev):** `/var/folders/7d/zc9qs93x1mdcyvwmjvgwz0tm0000gn/T/tmp.2SpLUpwFUe/runs/2c8b050bd82e1623330e0113c1dc94ba77a23b098f518ef9f452c57cb12e40fc`
- **Real dev eval (1 epoch, code_agentic devscreen + sealed dev):** `/var/folders/7d/zc9qs93x1mdcyvwmjvgwz0tm0000gn/T/tmph_yqrg8s/runs/9a3c013f49b50f0f4e04ba0dbdd0178b43feb408b51108f3f27f882849af00a5`

## Demo Run Configuration (applied overrides)

- candidates_per_epoch: 4
- topk_to_sealed_dev: 1
- devscreen.suite_id: stub (fast deterministic devscreen)
- sealed_dev.eval_plan_id: code_agentic_v1_dev_ladder
- sealed_heldout: disabled

## Demo Run Summary

- run_id: `2c8b050bd82e1623330e0113c1dc94ba77a23b098f518ef9f452c57cb12e40fc`
- baseline_commit: `a0251d778a14c616e951592cf74de9a4f91a9647`
- config_hash: `d7b3f16afa344982d38b837b4885e407c70dbd546e31903e2e0248c90e6a1087`
- total_epochs: 5
- sealed_dev_passes_total: 5
- scoreboard_epochs: 5

### Per-epoch results (demo)

| epoch | topk_submitted | sealed_passes | best_candidate_id | top_template_ids |
| --- | --- | --- | --- | --- |
| 0 | 1 | 1 | 82363b84ea8fec22f0bd22336036fdddb8a70a46373011c425a1170d4b203ade | insert_header_comment_v1, guard_nonetype_attr_v1, tabs_to_spaces_v1 |
| 1 | 1 | 1 | 4f27d4b8d2f0dcae8e488209013522607db7a556796363ce2b46c1b79951afdf | insert_header_comment_v1, guard_nonetype_attr_v1, tabs_to_spaces_v1 |
| 2 | 1 | 1 | 38ccc375da8f3ee6644b33673df1442cd451fcac98d39d441119433500d52ad0 | insert_header_comment_v1, guard_nonetype_attr_v1, tabs_to_spaces_v1 |
| 3 | 1 | 1 | 3cbab0deb239d102cfdbca270e1585c550d01f54091107b48ce54372e2194639 | insert_header_comment_v1, guard_nonetype_attr_v1, tabs_to_spaces_v1 |
| 4 | 1 | 1 | 4e2a82f72898d74cc84d1181233a60167402ce057ba5a5e22f7042f7aef7f1eb | insert_header_comment_v1, guard_nonetype_attr_v1, tabs_to_spaces_v1 |

### Demo sealed-dev receipt (epoch_0000)

- candidate_id: `82363b84ea8fec22f0bd22336036fdddb8a70a46373011c425a1170d4b203ade`
- receipt_path: `/var/folders/7d/zc9qs93x1mdcyvwmjvgwz0tm0000gn/T/tmp.2SpLUpwFUe/runs/2c8b050bd82e1623330e0113c1dc94ba77a23b098f518ef9f452c57cb12e40fc/epochs/epoch_0000/sealed_dev/candidate_82363b84ea8fec22f0bd22336036fdddb8a70a46373011c425a1170d4b203ade/receipt.json`

## Real Dev Eval Summary

- run_id: `9a3c013f49b50f0f4e04ba0dbdd0178b43feb408b51108f3f27f882849af00a5`
- baseline_commit: `a0251d778a14c616e951592cf74de9a4f91a9647`
- config_hash: `e35192ac77238c3901ce5eb4372148fc998807a0dee6fca96ab1a7eef01c1061`
- total_epochs: 1
- sealed_dev_passes_total: 1

### Real dev sealed-dev receipt (epoch_0000)

- candidate_id: `c051cc60aab1eacb2b357041416f06f4bef512e7ed9c7a2c4efc9bd227196d52`
- receipt_path: `/var/folders/7d/zc9qs93x1mdcyvwmjvgwz0tm0000gn/T/tmph_yqrg8s/runs/9a3c013f49b50f0f4e04ba0dbdd0178b43feb408b51108f3f27f882849af00a5/epochs/epoch_0000/sealed_dev/candidate_c051cc60aab1eacb2b357041416f06f4bef512e7ed9c7a2c4efc9bd227196d52/receipt.json`

## Notes / Observations

- Sealed dev evaluations now correctly resolve against the **target repo** (`agi-system`) rather than CDEL-v2; PASS receipts are captured when available.
- Demo run used stub devscreen for speed; the **real dev eval** used the code_agentic_v1 devscreen runner with a 120s timeout and still completed within ~40s for 1 candidate.
- All sealed dev evaluations in the demo run returned PASS under the allowlisted plan `code_agentic_v1_dev_ladder`.
