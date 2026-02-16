"""Configuration loading for CDEL."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib

DEFAULT_CONFIG = {
    "ledger": {
        "budget": 1_000_000,
    },
    "runs": {
        "base_dir": "runs",
    },
    "evaluator": {
        "step_limit": 100_000,
    },
    "spec": {
        "int_min": -3,
        "int_max": 3,
        "list_max_len": 4,
    },
    "cost": {
        "alpha": 1,
        "beta": 1,
        "gamma": 1,
    },
    "sealed": {
        "public_key": "",
        "key_id": "",
        "public_keys": [],
        "prev_public_keys": [],
        "alpha_total": "1e-4",
        "alpha_schedule": {
            "name": "p_series",
            "exponent": 2,
            "coefficient": "0.60792710185402662866",
        },
        "eval_harness_id": "",
        "eval_harness_hash": "",
        "eval_suite_hash": "",
    },
    "sealed_safety": {
        "public_key": "",
        "key_id": "",
        "public_keys": [],
        "prev_public_keys": [],
        "alpha_total": "1e-4",
        "alpha_schedule": {
            "name": "p_series",
            "exponent": 2,
            "coefficient": "0.60792710185402662866",
        },
        "eval_harness_id": "",
        "eval_harness_hash": "",
        "eval_suite_hash": "",
    },
    "constraints": {
        "required_concepts": [],
        "spec_hash": "",
    },
}


def _merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result


@dataclass(frozen=True)
class Config:
    root: Path
    data: dict

    @property
    def ledger_dir(self) -> Path:
        return self.root / "ledger"

    @property
    def adoption_dir(self) -> Path:
        return self.root / "adoption"

    @property
    def adoption_objects_dir(self) -> Path:
        return self.adoption_dir / "objects"

    @property
    def adoption_meta_dir(self) -> Path:
        return self.adoption_dir / "meta"

    @property
    def adoption_order_log(self) -> Path:
        return self.adoption_dir / "order.log"

    @property
    def adoption_head_file(self) -> Path:
        return self.adoption_dir / "head"

    @property
    def index_dir(self) -> Path:
        return self.root / "index"

    @property
    def cache_dir(self) -> Path:
        return self.root / "cache"

    @property
    def logs_dir(self) -> Path:
        return self.root / "logs"

    @property
    def tasks_dir(self) -> Path:
        return self.root / "tasks"

    @property
    def objects_dir(self) -> Path:
        return self.ledger_dir / "objects"

    @property
    def meta_dir(self) -> Path:
        return self.ledger_dir / "meta"

    @property
    def runs_dir(self) -> Path:
        base = (self.data.get("runs") or {}).get("base_dir", "runs")
        return self.root / base

    @property
    def order_log(self) -> Path:
        return self.ledger_dir / "order.log"

    @property
    def head_file(self) -> Path:
        return self.ledger_dir / "head"

    @property
    def budget_file(self) -> Path:
        return self.ledger_dir / "budget.json"

    @property
    def sqlite_path(self) -> Path:
        return self.index_dir / "index.sqlite"



def load_config(root: Path) -> Config:
    cfg_path = root / "config.toml"
    data = DEFAULT_CONFIG
    if cfg_path.exists():
        with cfg_path.open("rb") as fh:
            raw = tomllib.load(fh)
        data = _merge(DEFAULT_CONFIG, raw)
    return Config(root=root, data=data)


def load_config_from_path(root: Path, cfg_path: Path) -> Config:
    with cfg_path.open("rb") as fh:
        raw = tomllib.load(fh)
    data = _merge(DEFAULT_CONFIG, raw)
    return Config(root=root, data=data)


def write_default_config(root: Path, budget: int) -> None:
    cfg_path = root / "config.toml"
    if cfg_path.exists():
        return
    contents = (
        "[ledger]\n"
        f"budget = {budget}\n\n"
        "[runs]\n"
        f"base_dir = \"{DEFAULT_CONFIG['runs']['base_dir']}\"\n\n"
        "[evaluator]\n"
        f"step_limit = {DEFAULT_CONFIG['evaluator']['step_limit']}\n\n"
        "[spec]\n"
        f"int_min = {DEFAULT_CONFIG['spec']['int_min']}\n"
        f"int_max = {DEFAULT_CONFIG['spec']['int_max']}\n"
        f"list_max_len = {DEFAULT_CONFIG['spec']['list_max_len']}\n\n"
        "[cost]\n"
        f"alpha = {DEFAULT_CONFIG['cost']['alpha']}\n"
        f"beta = {DEFAULT_CONFIG['cost']['beta']}\n"
        f"gamma = {DEFAULT_CONFIG['cost']['gamma']}\n"
        "\n"
        "[sealed]\n"
        f"public_key = \"{DEFAULT_CONFIG['sealed']['public_key']}\"\n"
        f"key_id = \"{DEFAULT_CONFIG['sealed']['key_id']}\"\n"
        f"public_keys = []\n"
        f"prev_public_keys = []\n"
        f"alpha_total = \"{DEFAULT_CONFIG['sealed']['alpha_total']}\"\n"
        f"eval_harness_id = \"{DEFAULT_CONFIG['sealed']['eval_harness_id']}\"\n"
        f"eval_harness_hash = \"{DEFAULT_CONFIG['sealed']['eval_harness_hash']}\"\n"
        f"eval_suite_hash = \"{DEFAULT_CONFIG['sealed']['eval_suite_hash']}\"\n\n"
        "[sealed.alpha_schedule]\n"
        f"name = \"{DEFAULT_CONFIG['sealed']['alpha_schedule']['name']}\"\n"
        f"exponent = {DEFAULT_CONFIG['sealed']['alpha_schedule']['exponent']}\n"
        f"coefficient = \"{DEFAULT_CONFIG['sealed']['alpha_schedule']['coefficient']}\"\n"
        "\n"
        "[sealed_safety]\n"
        f"public_key = \"{DEFAULT_CONFIG['sealed_safety']['public_key']}\"\n"
        f"key_id = \"{DEFAULT_CONFIG['sealed_safety']['key_id']}\"\n"
        f"public_keys = []\n"
        f"prev_public_keys = []\n"
        f"alpha_total = \"{DEFAULT_CONFIG['sealed_safety']['alpha_total']}\"\n"
        f"eval_harness_id = \"{DEFAULT_CONFIG['sealed_safety']['eval_harness_id']}\"\n"
        f"eval_harness_hash = \"{DEFAULT_CONFIG['sealed_safety']['eval_harness_hash']}\"\n"
        f"eval_suite_hash = \"{DEFAULT_CONFIG['sealed_safety']['eval_suite_hash']}\"\n\n"
        "[sealed_safety.alpha_schedule]\n"
        f"name = \"{DEFAULT_CONFIG['sealed_safety']['alpha_schedule']['name']}\"\n"
        f"exponent = {DEFAULT_CONFIG['sealed_safety']['alpha_schedule']['exponent']}\n"
        f"coefficient = \"{DEFAULT_CONFIG['sealed_safety']['alpha_schedule']['coefficient']}\"\n"
        "\n"
        "[constraints]\n"
        "required_concepts = []\n"
        f"spec_hash = \"{DEFAULT_CONFIG['constraints']['spec_hash']}\"\n"
    )
    cfg_path.write_text(contents, encoding="utf-8")


def write_config_path(cfg_path: Path, data: dict) -> None:
    ledger = data.get("ledger") or {}
    evaluator = data.get("evaluator") or {}
    spec = data.get("spec") or {}
    cost = data.get("cost") or {}
    sealed = data.get("sealed") or {}
    sealed_safety = data.get("sealed_safety") or {}
    alpha_schedule = sealed.get("alpha_schedule") or {}
    safety_schedule = sealed_safety.get("alpha_schedule") or {}
    constraints = data.get("constraints") or {}
    lines = [
        "[ledger]",
        f"budget = {int(ledger.get('budget', DEFAULT_CONFIG['ledger']['budget']))}",
        "",
        "[runs]",
        f"base_dir = \"{(data.get('runs') or {}).get('base_dir', DEFAULT_CONFIG['runs']['base_dir'])}\"",
        "",
        "[evaluator]",
        f"step_limit = {int(evaluator.get('step_limit', DEFAULT_CONFIG['evaluator']['step_limit']))}",
        "",
        "[spec]",
        f"int_min = {int(spec.get('int_min', DEFAULT_CONFIG['spec']['int_min']))}",
        f"int_max = {int(spec.get('int_max', DEFAULT_CONFIG['spec']['int_max']))}",
        f"list_max_len = {int(spec.get('list_max_len', DEFAULT_CONFIG['spec']['list_max_len']))}",
        "",
        "[cost]",
        f"alpha = {int(cost.get('alpha', DEFAULT_CONFIG['cost']['alpha']))}",
        f"beta = {int(cost.get('beta', DEFAULT_CONFIG['cost']['beta']))}",
        f"gamma = {int(cost.get('gamma', DEFAULT_CONFIG['cost']['gamma']))}",
        "",
        "[sealed]",
        f"public_key = \"{sealed.get('public_key', DEFAULT_CONFIG['sealed']['public_key'])}\"",
        f"key_id = \"{sealed.get('key_id', DEFAULT_CONFIG['sealed']['key_id'])}\"",
        f"alpha_total = \"{sealed.get('alpha_total', DEFAULT_CONFIG['sealed']['alpha_total'])}\"",
        f"eval_harness_id = \"{sealed.get('eval_harness_id', DEFAULT_CONFIG['sealed']['eval_harness_id'])}\"",
        f"eval_harness_hash = \"{sealed.get('eval_harness_hash', DEFAULT_CONFIG['sealed']['eval_harness_hash'])}\"",
        f"eval_suite_hash = \"{sealed.get('eval_suite_hash', DEFAULT_CONFIG['sealed']['eval_suite_hash'])}\"",
        "",
        "[sealed.alpha_schedule]",
        f"name = \"{alpha_schedule.get('name', DEFAULT_CONFIG['sealed']['alpha_schedule']['name'])}\"",
        f"exponent = {int(alpha_schedule.get('exponent', DEFAULT_CONFIG['sealed']['alpha_schedule']['exponent']))}",
        f"coefficient = \"{alpha_schedule.get('coefficient', DEFAULT_CONFIG['sealed']['alpha_schedule']['coefficient'])}\"",
        "",
    ]
    lines.extend(_format_key_list("sealed.public_keys", sealed.get("public_keys")))
    lines.append("")
    lines.extend(_format_key_list("sealed.prev_public_keys", sealed.get("prev_public_keys")))
    lines.append("")
    lines.extend(
        [
            "[sealed_safety]",
            f"public_key = \"{sealed_safety.get('public_key', DEFAULT_CONFIG['sealed_safety']['public_key'])}\"",
            f"key_id = \"{sealed_safety.get('key_id', DEFAULT_CONFIG['sealed_safety']['key_id'])}\"",
            f"alpha_total = \"{sealed_safety.get('alpha_total', DEFAULT_CONFIG['sealed_safety']['alpha_total'])}\"",
            f"eval_harness_id = \"{sealed_safety.get('eval_harness_id', DEFAULT_CONFIG['sealed_safety']['eval_harness_id'])}\"",
            f"eval_harness_hash = \"{sealed_safety.get('eval_harness_hash', DEFAULT_CONFIG['sealed_safety']['eval_harness_hash'])}\"",
            f"eval_suite_hash = \"{sealed_safety.get('eval_suite_hash', DEFAULT_CONFIG['sealed_safety']['eval_suite_hash'])}\"",
            "",
            "[sealed_safety.alpha_schedule]",
            f"name = \"{safety_schedule.get('name', DEFAULT_CONFIG['sealed_safety']['alpha_schedule']['name'])}\"",
            f"exponent = {int(safety_schedule.get('exponent', DEFAULT_CONFIG['sealed_safety']['alpha_schedule']['exponent']))}",
            f"coefficient = \"{safety_schedule.get('coefficient', DEFAULT_CONFIG['sealed_safety']['alpha_schedule']['coefficient'])}\"",
            "",
        ]
    )
    lines.extend(_format_key_list("sealed_safety.public_keys", sealed_safety.get("public_keys")))
    lines.append("")
    lines.extend(_format_key_list("sealed_safety.prev_public_keys", sealed_safety.get("prev_public_keys")))
    lines.append("")
    lines.extend(
        [
            "[constraints]",
            f"spec_hash = \"{constraints.get('spec_hash', DEFAULT_CONFIG['constraints']['spec_hash'])}\"",
        ]
    )
    lines.extend(_format_str_list("constraints.required_concepts", constraints.get("required_concepts")))
    lines.append("")
    cfg_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def write_config(root: Path, data: dict) -> None:
    write_config_path(root / "config.toml", data)


def _format_key_list(table_name: str, items: object) -> list[str]:
    if items is None:
        return [f"{table_name} = []"]
    if not isinstance(items, list) or not items:
        return [f"{table_name} = []"]
    lines: list[str] = []
    for entry in items:
        if not isinstance(entry, dict):
            continue
        key_id = entry.get("key_id")
        public_key = entry.get("public_key")
        if not isinstance(key_id, str) or not isinstance(public_key, str):
            continue
        lines.append(f"[[{table_name}]]")
        lines.append(f"key_id = \"{key_id}\"")
        lines.append(f"public_key = \"{public_key}\"")
    return lines


def _format_str_list(key_name: str, items: object) -> list[str]:
    if items is None:
        return [f"{key_name} = []"]
    if not isinstance(items, list):
        return [f"{key_name} = []"]
    if any(not isinstance(item, str) for item in items):
        return [f"{key_name} = []"]
    rendered = ", ".join(f"\"{item}\"" for item in items)
    return [f"{key_name} = [{rendered}]"]
