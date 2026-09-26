"""Betting systems that depend only on past results (and optionally randomness).

Important: in blackjack without card counting, rounds are (almost) independent,
so none of these can change the expected loss per unit wagered. They reshape
the *distribution* of results -- e.g. Martingale trades many small wins for rare
large losses. The simulation suite exists to measure exactly that trade-off.
"""

from __future__ import annotations

import math

from ...engine import SeatResult
from ..base import BetContext, BetStrategy, Param
from ..registry import register_bet

UNIT = Param("unit", float, 10.0, "Money value of one betting unit.", 0.01, None, 1.0)


def _outcome(result: SeatResult) -> int:
    return 1 if result.won else -1 if result.lost else 0


@register_bet
class FlatBet(BetStrategy):
    key = "flat"
    label = "Flat"
    description = "Bet the same amount every round. The baseline for everything else."
    params = (UNIT, Param("units", float, 1.0, "Units per round.", 0.01, None, 1.0))

    def bet(self, ctx: BetContext) -> float:
        return self.unit * self.units


@register_bet
class Martingale(BetStrategy):
    key = "martingale"
    label = "Martingale"
    description = "Multiply the bet after each loss, return to one unit after a win."
    params = (
        UNIT,
        Param("multiplier", float, 2.0, "Bet multiplier after a loss.", 1.0, 10.0, 0.1),
        Param("max_steps", int, 0, "Reset after this many consecutive increases (0 = never).", 0, 50),
    )

    def reset(self) -> None:
        self.level = 0

    def bet(self, ctx: BetContext) -> float:
        return self.unit * self.multiplier**self.level

    def update(self, result: SeatResult) -> None:
        o = _outcome(result)
        if o > 0:
            self.level = 0
        elif o < 0:
            self.level += 1
            if self.max_steps and self.level > self.max_steps:
                self.level = 0


@register_bet
class Paroli(BetStrategy):
    key = "paroli"
    label = "Paroli (reverse Martingale)"
    description = "Multiply the bet after each win, return to one unit after a loss or after a target streak."
    params = (
        UNIT,
        Param("multiplier", float, 2.0, "Bet multiplier after a win.", 1.0, 10.0, 0.1),
        Param("streak_target", int, 3, "Wins in a row before banking the profit and resetting.", 1, 20),
    )

    def reset(self) -> None:
        self.level = 0

    def bet(self, ctx: BetContext) -> float:
        return self.unit * self.multiplier**self.level

    def update(self, result: SeatResult) -> None:
        o = _outcome(result)
        if o > 0:
            self.level += 1
            if self.level >= self.streak_target:
                self.level = 0
        elif o < 0:
            self.level = 0


@register_bet
class DAlembert(BetStrategy):
    key = "dalembert"
    label = "D'Alembert"
    description = "Add a step after a loss, remove a step after a win (never below one step)."
    params = (UNIT, Param("step_units", float, 1.0, "Units added / removed per round.", 0.01, None, 1.0))

    def reset(self) -> None:
        self.units = self.step_units

    def bet(self, ctx: BetContext) -> float:
        return self.unit * self.units

    def update(self, result: SeatResult) -> None:
        o = _outcome(result)
        if o < 0:
            self.units += self.step_units
        elif o > 0:
            self.units = max(self.step_units, self.units - self.step_units)


@register_bet
class Fibonacci(BetStrategy):
    key = "fibonacci"
    label = "Fibonacci"
    description = "Move one step up the Fibonacci sequence after a loss, two steps down after a win."
    params = (UNIT, Param("max_index", int, 20, "Highest Fibonacci step (caps the bet).", 1, 60))

    def reset(self) -> None:
        self.index = 0
        self.fib = [1, 1]
        while len(self.fib) <= self.max_index:
            self.fib.append(self.fib[-1] + self.fib[-2])

    def bet(self, ctx: BetContext) -> float:
        return self.unit * self.fib[self.index]

    def update(self, result: SeatResult) -> None:
        o = _outcome(result)
        if o < 0:
            self.index = min(self.index + 1, self.max_index)
        elif o > 0:
            self.index = max(0, self.index - 2)


@register_bet
class OscarsGrind(BetStrategy):
    key = "oscars_grind"
    label = "Oscar's Grind"
    description = (
        "Aim to win one unit per cycle: raise the bet by a unit after a win, keep it after a loss, "
        "never bet more than needed to finish the cycle."
    )
    params = (UNIT,)

    def reset(self) -> None:
        self.cycle = 0.0  # cycle profit in units
        self.units = 1.0

    def bet(self, ctx: BetContext) -> float:
        needed = 1.0 - self.cycle
        return self.unit * max(1.0, min(self.units, needed))

    def update(self, result: SeatResult) -> None:
        self.cycle += result.net / self.unit
        if self.cycle >= 1.0 - 1e-9:
            self.reset()
        elif result.won:
            self.units += 1.0


@register_bet
class SequenceBet(BetStrategy):
    key = "sequence"
    label = "Sequence (e.g. 1-3-2-6)"
    description = "Walk through a unit sequence while winning; restart after a loss or at the end."
    params = (
        UNIT,
        Param("sequence", str, "1-3-2-6", "Units separated by '-'."),
        Param("advance_on", str, "win", "Advance on a win (positive) or loss (negative progression).",
              choices=("win", "loss")),
    )

    def validate(self) -> None:
        try:
            self.steps = [float(x) for x in self.sequence.split("-") if x.strip()]
        except ValueError:
            raise ValueError(f"sequence: cannot parse {self.sequence!r}") from None
        if not self.steps or min(self.steps) <= 0:
            raise ValueError("sequence: need at least one positive number")

    def reset(self) -> None:
        self.pos = 0

    def bet(self, ctx: BetContext) -> float:
        return self.unit * self.steps[self.pos]

    def update(self, result: SeatResult) -> None:
        o = _outcome(result)
        if o == 0:
            return
        advance = (o > 0) == (self.advance_on == "win")
        self.pos = (self.pos + 1) % len(self.steps) if advance else 0


@register_bet
class RandomBet(BetStrategy):
    key = "random"
    label = "Random volatility"
    description = (
        "Bet a random multiple of the unit, drawn from a mean-preserving log-normal distribution. "
        "Isolates the effect of bet-size volatility on its own (no information used)."
    )
    params = (
        UNIT,
        Param("mean_units", float, 1.0, "Average units per round.", 0.01, None, 0.5),
        Param("volatility", float, 0.5, "Log-normal sigma: 0 = flat betting.", 0.0, 3.0, 0.05),
    )

    def bet(self, ctx: BetContext) -> float:
        s = self.volatility
        return self.unit * self.mean_units * math.exp(s * self.rng.gauss(0.0, 1.0) - s * s / 2)


@register_bet
class ProportionalBet(BetStrategy):
    key = "proportional"
    label = "Proportional (fixed fraction)"
    description = "Bet a fixed fraction of the current bankroll (Kelly-style sizing)."
    params = (Param("fraction", float, 0.01, "Fraction of bankroll per round.", 0.0001, 1.0, 0.005),)

    def bet(self, ctx: BetContext) -> float:
        return ctx.bankroll * self.fraction
