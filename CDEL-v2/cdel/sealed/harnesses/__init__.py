"""Sealed evaluation harness registry."""

from __future__ import annotations

from cdel.sealed.harnesses.base import EvalHarness
from cdel.sealed.harnesses.env_v1 import HARNESS_ID as ENV_HARNESS_ID
from cdel.sealed.harnesses.env_v1 import EnvHarness
from cdel.sealed.harnesses.io_v1 import HARNESS_ID as IO_HARNESS_ID
from cdel.sealed.harnesses.io_v1 import IOHarness
from cdel.sealed.harnesses.pyut_v1 import HARNESS_ID as PYUT_HARNESS_ID
from cdel.sealed.harnesses.pyut_v1 import PyUTHarness
from cdel.sealed.harnesses.suite_v1 import HARNESS_ID as SUITE_HARNESS_ID
from cdel.sealed.harnesses.suite_v1 import SuiteHarness
from cdel.sealed.harnesses.tooluse_v1 import HARNESS_ID as TOOLUSE_HARNESS_ID
from cdel.sealed.harnesses.tooluse_v1 import ToolUseHarness
from cdel.sealed.harnesses.toy_v1 import HARNESS_ID as TOY_HARNESS_ID
from cdel.sealed.harnesses.toy_v1 import ToyHarness

_HARNESS_REGISTRY: dict[str, EvalHarness] = {
    TOY_HARNESS_ID: ToyHarness(),
    SUITE_HARNESS_ID: SuiteHarness(),
    ENV_HARNESS_ID: EnvHarness(),
    IO_HARNESS_ID: IOHarness(),
    PYUT_HARNESS_ID: PyUTHarness(),
    TOOLUSE_HARNESS_ID: ToolUseHarness(),
}


def get_harness(harness_id: str) -> EvalHarness:
    harness = _HARNESS_REGISTRY.get(harness_id)
    if harness is None:
        raise ValueError(f"unknown eval harness: {harness_id}")
    return harness
