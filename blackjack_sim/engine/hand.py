"""Hands and player actions."""

from __future__ import annotations

from enum import Enum

from .cards import format_cards


class Action(str, Enum):
    HIT = "hit"
    STAND = "stand"
    DOUBLE = "double"
    SPLIT = "split"
    SURRENDER = "surrender"
    INSURANCE = "insurance"
    NO_INSURANCE = "no_insurance"


class Outcome(str, Enum):
    BLACKJACK = "blackjack"
    WIN = "win"
    PUSH = "push"
    LOSE = "lose"
    BUST = "bust"
    SURRENDER = "surrender"


class Hand:
    """A blackjack hand.

    ``hard`` is the total counting every Ace as 1; ``total`` promotes one Ace
    to 11 when that does not bust (a *soft* hand).
    """

    __slots__ = (
        "cards",
        "bet",
        "hard",
        "has_ace",
        "doubled",
        "split_depth",
        "from_split_aces",
        "surrendered",
        "done",
        "outcome",
        "net",
    )

    def __init__(self, bet: float = 0.0, split_depth: int = 0) -> None:
        self.cards: list[int] = []
        self.bet = bet
        self.hard = 0
        self.has_ace = False
        self.doubled = False
        self.split_depth = split_depth
        self.from_split_aces = False
        self.surrendered = False
        self.done = False
        self.outcome: Outcome | None = None
        self.net = 0.0

    def add(self, rank: int) -> None:
        self.cards.append(rank)
        if rank == 1:
            self.has_ace = True
            self.hard += 1
        else:
            self.hard += 10 if rank >= 10 else rank

    @property
    def total(self) -> int:
        if self.has_ace and self.hard <= 11:
            return self.hard + 10
        return self.hard

    @property
    def is_soft(self) -> bool:
        return self.has_ace and self.hard <= 11

    @property
    def is_bust(self) -> bool:
        return self.hard > 21

    @property
    def is_split(self) -> bool:
        return self.split_depth > 0

    @property
    def is_blackjack(self) -> bool:
        """A natural: two-card 21 that did not come from a split."""
        return len(self.cards) == 2 and not self.is_split and self.total == 21

    @property
    def is_pair(self) -> bool:
        """Two cards of equal value (any two ten-value cards count)."""
        if len(self.cards) != 2:
            return False
        a, b = self.cards
        return min(a, 10) == min(b, 10)

    @property
    def pair_value(self) -> int:
        """Value of the paired card (1 for Aces); only meaningful if is_pair."""
        return min(self.cards[0], 10)

    def __repr__(self) -> str:
        soft = "soft " if self.is_soft else ""
        return f"Hand([{format_cards(self.cards)}] {soft}{self.total}, bet={self.bet})"
