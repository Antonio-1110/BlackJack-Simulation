"""Simple and experimental play strategies.

``threshold``, ``linear`` and ``sigmoid`` are cleaned-up versions of the
strategies from the original prototype (Discrete / Linear / Sigmoid). They only
ever hit or stand, which makes them useful baselines against basic strategy.
"""

from __future__ import annotations

import math

from ...engine import Action, Decision
from ..base import Param, PlayStrategy
from ..registry import register_play


@register_play
class ThresholdStrategy(PlayStrategy):
    key = "threshold"
    label = "Stand on threshold"
    description = "Hit until the hand total reaches a threshold, then stand. Never doubles or splits."
    params = (
        Param("stand_on", int, 17, "Stand once the total is at least this.", 12, 21),
        Param("hit_soft", bool, True, "Keep hitting soft totals below 18 even above the threshold."),
    )

    def play(self, d: Decision) -> Action:
        total = d.hand.total
        if d.hand.is_soft and self.hit_soft and total < 18:
            return Action.HIT
        return Action.HIT if total < self.stand_on else Action.STAND


@register_play
class MimicDealerStrategy(PlayStrategy):
    key = "mimic_dealer"
    label = "Mimic the dealer"
    description = "Play exactly like the dealer: hit below 17 (optionally hit soft 17)."
    params = (Param("hit_soft_17", bool, False, "Hit soft 17 like an H17 dealer."),)

    def play(self, d: Decision) -> Action:
        total = d.hand.total
        if total < 17 or (self.hit_soft_17 and total == 17 and d.hand.is_soft):
            return Action.HIT
        return Action.STAND


@register_play
class LinearStrategy(PlayStrategy):
    key = "linear"
    label = "Linear probability (legacy)"
    description = (
        "Always hit below 12. From 12 up, hit with probability (21 - total) / 13, "
        "i.e. the chance the next card does not bust you under an infinite deck approximation."
    )
    params = (
        Param("stand_above", int, 16, "Always stand when the total is above this.", 12, 21),
        Param("hard_stop", bool, True, "Enforce 'stand_above'."),
        Param("hit_soft", bool, True, "Always hit soft totals up to 'stand_above'."),
    )

    def play(self, d: Decision) -> Action:
        total = d.hand.total
        if total < 12:
            return Action.HIT
        if self.hard_stop and total > self.stand_above:
            return Action.STAND
        if d.hand.is_soft and self.hit_soft and total <= self.stand_above:
            return Action.HIT
        return Action.HIT if self.rng.random() < (21 - total) / 13 else Action.STAND


@register_play
class SigmoidStrategy(PlayStrategy):
    key = "sigmoid"
    label = "Sigmoid probability (legacy)"
    description = (
        "Hit with probability 1 / (1 + exp(-w_self * (center - total + w_dealer * (upcard - dealer_center)))). "
        "The Ace upcard counts as 11."
    )
    params = (
        Param("w_self", float, 1.0, "Steepness in the player's total.", 0.0, 20.0, 0.1),
        Param("w_dealer", float, 1.0, "Weight of the dealer upcard.", -5.0, 5.0, 0.1),
        Param("center", float, 14.5, "Player total with a 50% hit chance (vs. a neutral upcard).", 10.0, 21.0, 0.5),
        Param("dealer_center", float, 7.0, "Upcard treated as neutral.", 2.0, 11.0, 0.5),
        Param("stand_above", int, 21, "Always stand when the total is above this.", 12, 21),
    )

    def play(self, d: Decision) -> Action:
        total = d.hand.total
        if total < 12:
            return Action.HIT
        if total > self.stand_above:
            return Action.STAND
        up = 11 if d.dealer_value == 1 else d.dealer_value
        z = self.w_self * (self.center - total + self.w_dealer * (up - self.dealer_center))
        z = max(min(z, 60.0), -60.0)
        p = 1.0 / (1.0 + math.exp(-z))
        return Action.HIT if self.rng.random() < p else Action.STAND


@register_play
class RandomStrategy(PlayStrategy):
    key = "random"
    label = "Random legal action"
    description = "Pick uniformly among legal actions. A worst-case baseline."
    params = ()

    def play(self, d: Decision) -> Action:
        return self.rng.choice(d.legal)
