"""Proposer interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from orchestrator.types import Candidate, ContextBundle


class Proposer(ABC):
    @abstractmethod
    def propose(self, *, context: ContextBundle, budget: int, rng_seed: int) -> list[Candidate]:
        raise NotImplementedError
