"""Bet sizing driven by a card count -- the only kind of bet variation that can
actually change the player's expected return, because it correlates bet size
with the player's advantage."""

from __future__ import annotations

import math

from ...engine import SYSTEMS, get_system
from ..base import BetContext, BetStrategy, Param
from ..registry import register_bet
from .progressions import UNIT


@register_bet
class CountSpread(BetStrategy):
    key = "count_spread"
    label = "Card-count bet spread"
    description = (
        "Bet min_units at low counts; from tc_start upward bet ramp units per true-count point, "
        "capped at max_units. Optionally sit out ('Wong out') below a count."
    )
    params = (
        UNIT,
        Param("system", str, "hi_lo", "Counting system.", choices=tuple(SYSTEMS)),
        Param("min_units", float, 1.0, "Bet at or below tc_start - 1.", 0.01, None, 1.0),
        Param("max_units", float, 8.0, "Largest bet.", 0.01, None, 1.0),
        Param("tc_start", float, 1.0, "True count where the ramp starts.", -10.0, 20.0, 0.5),
        Param("ramp", float, 2.0, "Extra units per true-count point above tc_start - 1.", 0.0, None, 0.5),
        Param("floor_tc", bool, True, "Round the true count down before using it."),
        Param("wong_out_below", float, -99.0, "Sit out rounds while TC is below this (-99 = never).",
              -99.0, 20.0, 0.5),
    )

    def validate(self) -> None:
        if self.max_units < self.min_units:
            raise ValueError("max_units must be >= min_units")
        self._system = get_system(self.system)

    def true_count(self, ctx: BetContext) -> float:
        sys = self._system
        if sys.balanced:
            tc = sys.true_count(ctx.shoe)
        else:  # unbalanced (KO): use the running count directly
            tc = sys.running_count(ctx.shoe)
        return math.floor(tc) if self.floor_tc else tc

    def bet(self, ctx: BetContext) -> float:
        tc = self.true_count(ctx)
        if tc < self.wong_out_below:
            return 0.0
        units = self.min_units + self.ramp * (tc - self.tc_start + 1)
        return self.unit * min(self.max_units, max(self.min_units, units))
