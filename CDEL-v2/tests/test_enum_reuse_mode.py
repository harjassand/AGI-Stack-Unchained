import json
from pathlib import Path

from cdel.gen.enum import EnumGenerator, TaskSpec
from cdel.kernel.parse import parse_definition
from cdel.bench.run import parse_type_str


def test_enum_reuse_mode_prioritizes_apps():
    module = json.loads(Path("tests/fixtures/module1.json").read_text(encoding="utf-8"))
    inc_def = parse_definition(module["payload"]["definitions"][0])
    env_defs = {"inc": inc_def}
    env_symbols = {"inc": parse_type_str("Int -> Int")}

    task_spec = TaskSpec(
        new_symbol="inc2",
        typ=parse_type_str("Int -> Int"),
        specs=[],
        allowed_deps=["inc"],
    )

    baseline = EnumGenerator(max_candidates=1, mode="baseline")
    reuse = EnumGenerator(max_candidates=1, mode="reuse")

    base_cands = baseline.generate(task_spec, env_symbols, env_defs=env_defs)
    reuse_cands = reuse.generate(task_spec, env_symbols, env_defs=env_defs)

    assert base_cands
    assert reuse_cands
    assert base_cands[0].definition["body"]["tag"] != "app"
    assert reuse_cands[0].definition["body"]["tag"] == "app"
