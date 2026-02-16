# Solve Loop (Track B)

The solve loop is an untrusted orchestrator. It proposes candidates and requests sealed evaluation, but it cannot bypass the CDEL/CAL verifiers. A solve only succeeds if the candidate module is accepted by the CDEL verifier and the adoption record is accepted by CAL.

Pipeline

1) Retrieve candidates via concept/type indices.
2) Propose candidate definition(s) (templates or enumerative search).
3) Request a sealed stat_cert (signed, alpha-spent).
4) Commit the module to CDEL (hard gate).
5) Adopt into CAL (hard gate).
6) Report audit metadata (module hash, alpha round, evalue).

CLI usage

```bash
cdel solve \
  --task pred.lt_k.7 \
  --max-candidates 2 \
  --episodes 128 \
  --seed-key sealed-seed \
  --private-key "$CDEL_SEALED_PRIVKEY"
```

Outputs

`cdel solve` prints a JSON report including:

- `attempts[].accepted` / `attempts[].rejection`
- `attempts[].module_hash` / `attempts[].adoption_hash`
- `attempts[].alpha` (round_before/round_after, alpha_i, threshold, evalue, decision)

Scoreboard

Run a fixed-budget scoreboard across a task subset:

```bash
cdel run-solve-scoreboard \
  --out /tmp/cdel_trackB_scoreboard \
  --tasks 12 \
  --max-candidates 2 \
  --episodes 32 \
  --budget 1000000
```

Outputs:

- `/tmp/cdel_trackB_scoreboard/trackB_scoreboard.json`
- `/tmp/cdel_trackB_scoreboard/trackB_scoreboard.md`
