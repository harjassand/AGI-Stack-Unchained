# families

> Path: `campaigns/rsi_real_ignite_v1/families`

## Mission

Campaign configuration and execution packaging for reproducible orchestrator runs.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `0253b22e5fe088ce24e120d616ca774d9cd1c00ce2153082372c8c6fb1d8e46c.json`: JSON contract, config, or artifact.
- `0d20a6d6ba1e49e53ea4a92865d1bb8b03fb9b8eaca9209d2d0e1ea39ed46376.json`: JSON contract, config, or artifact.
- `14852683d32af04bee274b2be8ea39106f77ea285e70442be888b5c0fa6a9e69.json`: JSON contract, config, or artifact.
- `183a8217c58c01f13a046ae61e26bb438fab3861d64f120499f6ebe4871d0a95.json`: JSON contract, config, or artifact.
- `1ce19a7a60cee5e83a627c4c9e9b70af80325af60f5a1e6111ab261d79a7e652.json`: JSON contract, config, or artifact.
- `3ab5be12946c0ac363c18733da6e55bd9584c9faace2979398c31959c3898b16.json`: JSON contract, config, or artifact.
- `3efd1c77b0a57845bb7cb1d06cd4e18fd75b23692f72c9ad061302eb569c66f2.json`: JSON contract, config, or artifact.
- `4410055a0009daf11d7b06464aad26d0b4d9be907404a1adbb28b08ee4cc8e36.json`: JSON contract, config, or artifact.
- `49a2dac9dc6ef97d94726a1a1601af101aeefc6c2cb4bb41d6985943a342fd5e.json`: JSON contract, config, or artifact.
- `54dec3c602eee7a6821284f22e707b89005ff3181536a356665d2eac55371a6e.json`: JSON contract, config, or artifact.
- `57d1aff1be3d3a8262913d9590330c62554ab282b64bdb160aba4c8d23259cdf.json`: JSON contract, config, or artifact.
- `5fdfa5cd476c245a3665e6fba01100195bb04edf4dd93c263a67ade54f0fcee0.json`: JSON contract, config, or artifact.
- `6182f7475d3f784bcd142016343e20905d4b0afb52b0cc7f3e794966943933ed.json`: JSON contract, config, or artifact.
- `6902eba06cbd8e1be8967f575a51cc03ba7d554a6819ff0f2750c5d4a451a846.json`: JSON contract, config, or artifact.
- `6b06b99ab975e8dad16e24e4b80d2a481bc01fa78a30131fce7a2151cebb8cf3.json`: JSON contract, config, or artifact.
- `6f17ae5356553b1488223e2c9820bc66e558be50383507a56693dcb982a10504.json`: JSON contract, config, or artifact.
- `748db53ca4a35f546128a57fa5b3d860e21d0f5f82be7783be651782b6f84dfc.json`: JSON contract, config, or artifact.
- `7b5c6adc07d2b313bc097b3095dc83329ee9856b35156fe83d0ca7ec8bb878d2.json`: JSON contract, config, or artifact.
- `7ba44d9030032c919c459d10258df4451b088c42d9f3c6f74ca191e2da20a19a.json`: JSON contract, config, or artifact.
- `82ff7788e347c7257bff12b632ae6c11ded2852e51a520afdaed31296b8436fc.json`: JSON contract, config, or artifact.
- `8b9ec3f3503a8535ec6ebecd937deedf0e78a89f012b512d8d64d47fda259969.json`: JSON contract, config, or artifact.
- `991767e5e0e081e3a0be7cba52515d81e87fc7220db34f13cc22ef7501fd0d88.json`: JSON contract, config, or artifact.
- `9aed59e5c4df9040d4e78153c4d7abf80c996f804f3b486f4aedbea18711fdc0.json`: JSON contract, config, or artifact.
- `ad31f0ebed060bbe0df8191294d2c052930dfc597e565592f59e68971e28758b.json`: JSON contract, config, or artifact.
- `af3339af8650526666713e1b94f29655ac19cd954be83b090f70b53e9394e512.json`: JSON contract, config, or artifact.
- ... and 12 more files.

## File-Type Surface

- `json`: 37 files

## Operational Checks

```bash
ls -la campaigns/rsi_real_ignite_v1/families
find campaigns/rsi_real_ignite_v1/families -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files campaigns/rsi_real_ignite_v1/families | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
