from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from genesis.capsules.canonicalize import capsule_hash
from genesis.core.archive import Archive
from genesis.core.counterexamples import CounterexampleDB
from genesis.core import distill
from genesis.core.failure_patterns import FailurePatternStore, operator_signature
from genesis.core import library as lib
from genesis.core import operators as ops
from genesis.shadow_cdel.calibration import ShadowCalibrator
from genesis.shadow_cdel.shadow_eval import ShadowResult, evaluate_shadow


def _load_capsule(path: Path) -> Dict:
    with path.open("r", encoding="utf-8") as fp:
        return json.load(fp)


@dataclass
class SearchEvent:
    capsule: Dict
    operator: str
    repair_depth: int
    parent_hash: str | None
    shadow: ShadowResult
    counterexample_id: str | None
    failure_pattern_id: str | None
    failure_patterns_top: List[Dict[str, Any]] | None


def _add_parent(capsule: Dict, parent_hash: str | None) -> None:
    if not parent_hash:
        return
    parents = list(capsule.get("parents", []))
    if parent_hash not in parents:
        parents.append(parent_hash)
    capsule["parents"] = parents


def _record_counterexample(db: CounterexampleDB, capsule: Dict, shadow: ShadowResult) -> str | None:
    if shadow.trace is None:
        input_value = {
            "metric": shadow.metric_name,
            "value": shadow.metric_value,
            "bound": shadow.bound,
            "threshold": shadow.threshold,
        }
        test_name = "metric_threshold"
        failure_class = shadow.status
    else:
        input_value = shadow.trace.counterexample
        test_name = shadow.trace.failing_test or "unknown_test"
        failure_class = shadow.trace.status
    entry = db.add(
        test_name=test_name,
        input_value=input_value,
        failure_class=failure_class,
        capsule_hash=capsule_hash(capsule),
    )
    return entry.counterexample_id


def _snapshot_patterns(
    store: FailurePatternStore,
    every: int,
    top_k: int,
    event_idx: int,
) -> List[Dict[str, Any]]:
    if every <= 0:
        return []
    if event_idx % every != 0:
        return []
    return store.top_k(top_k)


def _choose_operator(
    rng: random.Random,
    choices: List[str],
    op_label_map: Dict[str, str],
    failure_patterns: FailurePatternStore,
) -> str:
    if not choices:
        return "mutate"
    penalties = {}
    for choice in choices:
        label = op_label_map.get(choice, choice)
        sig = operator_signature([label])
        penalties[choice] = failure_patterns.penalty_for_signature(sig)
    min_penalty = min(penalties.values())
    candidates = sorted([choice for choice, score in penalties.items() if score == min_penalty])
    if len(candidates) == 1:
        return candidates[0]
    return rng.choice(candidates)


def run_search(config: Dict, calibrator: ShadowCalibrator | None = None) -> Dict[str, List[SearchEvent]]:
    rng = random.Random(int(config.get("seed", 0)))
    archive_path = Path(config.get("archive_path", "genesis_archive.jsonl"))
    archive = Archive(archive_path)
    counterexamples = CounterexampleDB()
    failure_patterns = FailurePatternStore()

    dataset_config = Path(config.get("dataset_config", "genesis/configs/datasets.json"))
    dataset_id = config.get("dataset_id", "shadow_eval")
    forager_max_tests = int(config.get("forager_max_tests", 0))
    pattern_snapshot_every = int(config.get("failure_pattern_snapshot_every", 5))
    pattern_top_k = int(config.get("failure_pattern_top_k", 3))

    library_path = Path(config.get("library_path", "genesis/library.json"))
    library = lib.Library.load(library_path)
    distill_every = int(config.get("distill_every", 1))
    distill_min_count = int(config.get("distill_min_count", 2))
    force_reuse_next = False

    seed_capsule_path = Path(config["seed_capsule"]).resolve()
    seed_capsule = _load_capsule(seed_capsule_path)

    candidates = [seed_capsule]
    events: List[SearchEvent] = []
    epoch_id = config.get("epoch_id", "epoch-1")

    margin = calibrator.margin_for_epoch(epoch_id) if calibrator else 0.0
    seed_result = evaluate_shadow(
        seed_capsule,
        seed=str(config.get("seed", "0")),
        margin=margin,
        counterexamples=counterexamples.entries(),
        dataset_config_path=dataset_config,
        dataset_id=dataset_id,
        forager_max_tests=forager_max_tests,
    )
    seed_status = "shadow_pass" if seed_result.decision == "PASS" else "shadow_fail"
    seed_metric = seed_result.metric_value if seed_result.metric_value is not None else None
    archive.append(seed_capsule, status=seed_status, shadow_metric=seed_metric, shadow=seed_result, repair_depth=0)
    events.append(
        SearchEvent(
            capsule=seed_capsule,
            operator="seed",
            repair_depth=0,
            parent_hash=None,
            shadow=seed_result,
            counterexample_id=None,
            failure_pattern_id=None,
            failure_patterns_top=_snapshot_patterns(failure_patterns, pattern_snapshot_every, pattern_top_k, len(events) + 1),
        )
    )

    iterations = int(config.get("iterations", 5))
    repair_attempts = int(config.get("repair_attempts", 2))
    operator_sequence = config.get("operator_sequence") or []
    force_first = config.get("force_first_operator")
    reuse_when_available = bool(config.get("force_reuse_if_available", True))

    for idx in range(iterations):
        base = rng.choice(candidates)
        if force_reuse_next and library.primitives:
            choice = "reuse"
            force_reuse_next = False
        elif idx < len(operator_sequence):
            choice = operator_sequence[idx]
        elif idx == 0 and force_first in {"mutate", "swap", "compose"}:
            choice = force_first
        elif library.primitives and reuse_when_available and idx == 0:
            choice = "reuse"
        else:
            choices = ["mutate", "swap", "compose"]
            if library.primitives:
                choices.append("reuse")
            op_label_map = {
                "mutate": "x-mutate_constant",
                "swap": "x-swap_primitive",
                "compose": "x-compose_two_candidates",
                "reuse": "x-reuse_primitive",
            }
            choice = _choose_operator(rng, choices, op_label_map, failure_patterns)

        parent_hash = capsule_hash(base)
        if choice == "mutate":
            candidate = ops.mutate_constant(base, rng)
            operator = "x-mutate_constant"
        elif choice == "swap":
            candidate = ops.swap_primitive(base, rng)
            operator = "x-swap_primitive"
        elif choice == "reuse" and library.primitives:
            primitive = library.select(rng)
            candidate = ops.reuse_primitive(base, primitive)
            operator = "x-reuse_primitive"
        else:
            partner = rng.choice(candidates)
            candidate = ops.compose_two_candidates(base, partner)
            operator = "x-compose_two_candidates"

        _add_parent(candidate, parent_hash)
        candidate["x-repair_depth"] = 0

        margin = calibrator.margin_for_epoch(epoch_id) if calibrator else 0.0
        result = evaluate_shadow(
            candidate,
            seed=str(config.get("seed", "0")),
            margin=margin,
            counterexamples=counterexamples.entries(),
            dataset_config_path=dataset_config,
            dataset_id=dataset_id,
            forager_max_tests=forager_max_tests,
        )
        status = "shadow_pass" if result.decision == "PASS" else "shadow_fail"
        metric = result.metric_value if result.metric_value is not None else None
        counterexample_id = None
        pattern_id = None
        if result.decision != "PASS":
            counterexample_id = _record_counterexample(counterexamples, candidate, result)
            last_counterexample = counterexamples.latest()
            if last_counterexample is not None:
                op_sig = operator_signature(candidate.get("operators_used", []))
                pattern_id = failure_patterns.add(
                    failure_class=last_counterexample.failure_class,
                    env_id=str(dataset_id),
                    operator_sig=op_sig,
                    trace_hash=last_counterexample.input_hash,
                )
        archive.append(
            candidate,
            status=status,
            shadow_metric=metric,
            shadow=result,
            repair_depth=0,
            failure_pattern_ids=[pattern_id] if pattern_id else [],
        )
        events.append(
            SearchEvent(
                capsule=candidate,
                operator=operator,
                repair_depth=0,
                parent_hash=parent_hash,
                shadow=result,
                counterexample_id=counterexample_id,
                failure_pattern_id=pattern_id,
                failure_patterns_top=_snapshot_patterns(failure_patterns, pattern_snapshot_every, pattern_top_k, len(events) + 1),
            )
        )

        candidates.append(candidate)
        if result.decision == "PASS":
            if distill_every > 0 and (idx + 1) % distill_every == 0:
                updated = distill.update_library(archive_path, library, distill_min_count)
                if updated:
                    library.save(library_path)
                    force_reuse_next = True
            continue

        last_counterexample = counterexamples.latest()

        for attempt in range(repair_attempts):
            repair = None
            repair_op = ""
            if attempt == 0 and parent_hash:
                repair = ops.revert_last_mutation(base)
                repair_op = "x-revert_last_mutation"
            elif attempt == 1:
                repair = ops.patch_parameter(candidate, last_counterexample.input_value if last_counterexample else None)
                repair_op = "x-patch_parameter"
            elif attempt == 2:
                repair = ops.repair_by_guard(candidate, last_counterexample.input_value if last_counterexample else None)
                repair_op = "x-repair_by_guard"
            else:
                repair = ops.shrink_on_fail(candidate, last_counterexample.input_value if last_counterexample else None)
                repair_op = "x-shrink_on_fail"

            if repair is None:
                continue

            _add_parent(repair, parent_hash)
            repair_depth = int(candidate.get("x-repair_depth", 0)) + 1
            repair["x-repair_depth"] = repair_depth
            margin = calibrator.margin_for_epoch(epoch_id) if calibrator else 0.0
            repair_result = evaluate_shadow(
                repair,
                seed=str(config.get("seed", "0")),
                margin=margin,
                counterexamples=counterexamples.entries(),
                dataset_config_path=dataset_config,
                dataset_id=dataset_id,
                forager_max_tests=forager_max_tests,
            )
            repair_status = "shadow_pass" if repair_result.decision == "PASS" else "shadow_fail"
            repair_metric = repair_result.metric_value if repair_result.metric_value is not None else None
            repair_counterexample_id = None
            repair_pattern_id = None
            if repair_result.decision != "PASS":
                repair_counterexample_id = _record_counterexample(counterexamples, repair, repair_result)
                last_counterexample = counterexamples.latest()
                if last_counterexample is not None:
                    op_sig = operator_signature(repair.get("operators_used", []))
                    repair_pattern_id = failure_patterns.add(
                        failure_class=last_counterexample.failure_class,
                        env_id=str(dataset_id),
                        operator_sig=op_sig,
                        trace_hash=last_counterexample.input_hash,
                    )
            archive.append(
                repair,
                status=repair_status,
                shadow_metric=repair_metric,
                shadow=repair_result,
                repair_depth=repair_depth,
                failure_pattern_ids=[repair_pattern_id] if repair_pattern_id else [],
            )
            events.append(
                SearchEvent(
                    capsule=repair,
                    operator=repair_op,
                    repair_depth=repair_depth,
                    parent_hash=parent_hash,
                    shadow=repair_result,
                    counterexample_id=repair_counterexample_id or counterexample_id,
                    failure_pattern_id=repair_pattern_id,
                    failure_patterns_top=_snapshot_patterns(failure_patterns, pattern_snapshot_every, pattern_top_k, len(events) + 1),
                )
            )
            if repair_result.decision == "PASS":
                candidates.append(repair)
                break

        if distill_every > 0 and (idx + 1) % distill_every == 0:
            updated = distill.update_library(archive_path, library, distill_min_count)
            if updated:
                library.save(library_path)
                force_reuse_next = True

    if library.primitives:
        library.save(library_path)

    return {"events": events, "archive_path": str(archive_path)}
