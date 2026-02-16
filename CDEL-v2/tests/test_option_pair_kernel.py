from cdel.kernel.eval import BoolVal, Evaluator, IntVal, ListVal, OptionVal, PairVal
from cdel.kernel.parse import parse_definition
from cdel.kernel.spec import check_specs
from cdel.kernel.typecheck import typecheck_definition


def test_option_typecheck_eval():
    defn_json = {
        "name": "head_opt",
        "params": [{"name": "xs", "type": {"tag": "list", "of": {"tag": "int"}}}],
        "ret_type": {"tag": "option", "of": {"tag": "int"}},
        "body": {
            "tag": "match_list",
            "scrutinee": {"tag": "var", "name": "xs"},
            "nil_case": {"tag": "none"},
            "cons_case": {
                "head_var": "h",
                "tail_var": "t",
                "body": {"tag": "some", "value": {"tag": "var", "name": "h"}},
            },
        },
        "termination": {"kind": "structural", "decreases_param": None},
    }
    defn = parse_definition(defn_json)
    typecheck_definition(defn, {})
    evaluator = Evaluator(100)
    defs = {defn.name: defn}
    nil_val = ListVal(tuple())
    result_nil = evaluator.eval_term(defn.body, [nil_val], defs)
    assert result_nil == OptionVal(False, None)
    list_val = ListVal((IntVal(5),))
    result_some = evaluator.eval_term(defn.body, [list_val], defs)
    assert result_some == OptionVal(True, IntVal(5))


def test_pair_typecheck_eval():
    defn_json = {
        "name": "swap_pair",
        "params": [
            {
                "name": "p",
                "type": {"tag": "pair", "left": {"tag": "int"}, "right": {"tag": "bool"}},
            }
        ],
        "ret_type": {"tag": "pair", "left": {"tag": "bool"}, "right": {"tag": "int"}},
        "body": {
            "tag": "pair",
            "left": {"tag": "snd", "pair": {"tag": "var", "name": "p"}},
            "right": {"tag": "fst", "pair": {"tag": "var", "name": "p"}},
        },
        "termination": {"kind": "structural", "decreases_param": None},
    }
    defn = parse_definition(defn_json)
    typecheck_definition(defn, {})
    evaluator = Evaluator(100)
    defs = {defn.name: defn}
    pair_val = PairVal(IntVal(3), BoolVal(True))
    result = evaluator.eval_term(defn.body, [pair_val], defs)
    assert result == PairVal(BoolVal(True), IntVal(3))


def test_spec_domain_option_pair():
    specs = [
        {
            "kind": "forall",
            "vars": [
                {"name": "o", "type": {"tag": "option", "of": {"tag": "int"}}},
                {"name": "p", "type": {"tag": "pair", "left": {"tag": "int"}, "right": {"tag": "bool"}}},
            ],
            "domain": {"int_min": 0, "int_max": 1, "list_max_len": 0, "fun_symbols": []},
            "assert": {"tag": "bool", "value": True},
        }
    ]
    stats = check_specs(specs, {}, {}, step_limit=100)
    assert stats.spec_work == 12
