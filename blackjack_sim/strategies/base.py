"""Strategy interfaces and the parameter schema used by configs and the UI.

There are two independent kinds of strategy:

* :class:`PlayStrategy` -- decides hit / stand / double / split / surrender /
  insurance for a hand.
* :class:`BetStrategy` -- decides how much to bet before each round.

Each concrete class declares its tunable knobs in ``params``. The registry uses
that schema to validate JSON configs, and the frontend uses it to build input
widgets, so a new strategy shows up in the UI without any UI code changes.
"""

from __future__ import annotations

import random
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, ClassVar

from ..engine import Action, Decision, Rules, SeatResult, Shoe


@dataclass(frozen=True)
class Param:
    name: str
    kind: type  # int, float, bool or str
    default: Any
    help: str = ""
    min: float | None = None
    max: float | None = None
    step: float | None = None
    choices: tuple[str, ...] | None = None

    def coerce(self, value: Any) -> Any:
        if self.kind is bool:
            if isinstance(value, str):
                value = value.strip().lower() in ("1", "true", "yes", "on")
            value = bool(value)
        elif self.kind is int:
            value = int(value)
        elif self.kind is float:
            value = float(value)
        else:
            value = str(value)
        if self.choices is not None and value not in self.choices:
            raise ValueError(f"{self.name}: {value!r} not in {self.choices}")
        if self.min is not None and value < self.min:
            raise ValueError(f"{self.name}: {value} < minimum {self.min}")
        if self.max is not None and value > self.max:
            raise ValueError(f"{self.name}: {value} > maximum {self.max}")
        return value


class Configurable:
    key: ClassVar[str] = ""
    label: ClassVar[str] = ""
    description: ClassVar[str] = ""
    params: ClassVar[tuple[Param, ...]] = ()

    def __init__(self, rng: random.Random | None = None, **values: Any) -> None:
        self.rng = rng or random.Random()
        known = {p.name: p for p in self.params}
        unknown = set(values) - set(known)
        if unknown:
            raise ValueError(f"{self.key}: unknown parameter(s) {sorted(unknown)}")
        for p in self.params:
            setattr(self, p.name, p.coerce(values.get(p.name, p.default)))
        self.validate()
        self.reset()

    def validate(self) -> None:
        """Override for cross-parameter checks; raise ValueError on bad input."""

    def config(self) -> dict[str, Any]:
        return {p.name: getattr(self, p.name) for p in self.params}

    def reset(self) -> None:
        """Called at the start of every session."""


class PlayStrategy(Configurable, ABC):
    def __call__(self, decision: Decision) -> Action:
        if decision.kind == "insurance":
            return Action.INSURANCE if self.take_insurance(decision) else Action.NO_INSURANCE
        action = self.play(decision)
        if action not in decision.legal:
            raise ValueError(f"{self.key} chose illegal {action} (legal: {decision.legal})")
        return action

    @abstractmethod
    def play(self, decision: Decision) -> Action:
        """Return one of ``decision.legal``."""

    def take_insurance(self, decision: Decision) -> bool:
        return False


@dataclass(slots=True)
class BetContext:
    """What a betting strategy knows before the cards are dealt."""

    round_index: int
    bankroll: float
    starting_bankroll: float
    rules: Rules
    shoe: Shoe

    @property
    def profit(self) -> float:
        return self.bankroll - self.starting_bankroll


class BetStrategy(Configurable, ABC):
    @abstractmethod
    def bet(self, ctx: BetContext) -> float:
        """Desired wager for the next round (the runner clamps it to table
        limits and the available bankroll)."""

    def update(self, result: SeatResult) -> None:
        """Observe the result of the round that was just played."""
