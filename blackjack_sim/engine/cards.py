"""Cards and the shoe.

Cards are plain ``int`` ranks (1 = Ace, 11/12/13 = J/Q/K). Suits never matter
for standard blackjack rules, so they are not modelled. Using ints keeps the
hot simulation loop fast.
"""

from __future__ import annotations

import random
from typing import Iterable

ACE = 1
RANK_NAMES = {1: "A", 11: "J", 12: "Q", 13: "K"}


def card_value(rank: int) -> int:
    """Blackjack value of a rank, with the Ace counted as 1 and faces as 10."""
    return 10 if rank >= 10 else rank


def card_name(rank: int) -> str:
    return RANK_NAMES.get(rank, str(rank))


def format_cards(cards: Iterable[int]) -> str:
    return " ".join(card_name(c) for c in cards)


class Shoe:
    """A shuffled multi-deck shoe with a cut card.

    The shoe also tracks which cards have been *seen* (exposed face up) since
    the last shuffle, which is exactly the information a card counter has.
    ``seen[v]`` is the number of seen cards with value ``v`` (1..10).
    """

    def __init__(
        self,
        num_decks: int,
        penetration: float,
        rng: random.Random,
        burn_cards: int = 1,
    ) -> None:
        if num_decks < 1:
            raise ValueError("num_decks must be >= 1")
        if not 0.0 < penetration <= 1.0:
            raise ValueError("penetration must be in (0, 1]")
        self.num_decks = num_decks
        self.penetration = penetration
        self.burn_cards = burn_cards
        self.rng = rng
        self.total_cards = 52 * num_decks
        self._cut_index = int(round(self.total_cards * penetration))
        self._cards: list[int] = []
        self.dealt = 0
        self.seen = [0] * 11  # index by card value 1..10; index 0 unused
        self.seen_total = 0
        self.shuffles = 0
        self.shuffle()

    # ------------------------------------------------------------------ state
    def shuffle(self) -> None:
        cards = list(range(1, 14)) * (4 * self.num_decks)
        self.rng.shuffle(cards)
        self._cards = cards
        self.dealt = 0
        self.seen = [0] * 11
        self.seen_total = 0
        self.shuffles += 1
        for _ in range(self.burn_cards):
            self.draw()

    @property
    def needs_shuffle(self) -> bool:
        """True once the cut card has been reached."""
        return self.dealt >= self._cut_index

    @property
    def cards_remaining(self) -> int:
        return len(self._cards)

    @property
    def unseen_cards(self) -> int:
        """Cards whose identity a counter does not know (includes the burn card)."""
        return self.total_cards - self.seen_total

    @property
    def decks_remaining(self) -> float:
        return max(self.unseen_cards, 1) / 52.0

    # --------------------------------------------------------------- dealing
    def draw(self) -> int:
        if not self._cards:
            # Only reachable with extreme penetration / many seats. Real tables
            # would reshuffle the discards; a fresh shoe is a close stand-in.
            self.shuffle()
        self.dealt += 1
        return self._cards.pop()

    def observe(self, rank: int) -> None:
        """Mark a card as seen by everyone at the table."""
        self.seen[10 if rank >= 10 else rank] += 1
        self.seen_total += 1

    def draw_seen(self) -> int:
        card = self.draw()
        self.observe(card)
        return card

    def stack(self, cards: Iterable[int]) -> None:
        """Force the next cards to be ``cards`` (first element dealt first).

        Only meant for tests and hand-by-hand debugging.
        """
        self._cards.extend(reversed(list(cards)))
