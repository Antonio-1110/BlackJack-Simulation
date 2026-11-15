"""Cards and the shoe.

Cards are plain ``int`` ranks (1 = Ace, 11/12/13 = J/Q/K). Suits never matter
for standard blackjack rules, so they are not modelled. Using ints keeps the
hot simulation loop fast.
"""

from __future__ import annotations

import random
from collections import Counter
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
        self._in_play: list[int] = []  # cards drawn this round (still on the table)
        self._in_play_seen = [0] * 11
        self._reshuffle_due = False
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
        self._reshuffle_due = False
        self._in_play = []
        self._in_play_seen = [0] * 11
        self._burn()

    def _burn(self) -> None:
        for _ in range(min(self.burn_cards, len(self._cards) - 1)):
            self._cards.pop()
            self.dealt += 1

    def start_round(self) -> None:
        """Forget which cards are on the table: the previous round's cards are
        now in the discard tray. The table calls this at the start of a round."""
        self._in_play = []
        self._in_play_seen = [0] * 11

    def _reshuffle_discards(self) -> None:
        """The shoe ran out mid-round: shuffle the discards back in.

        Cards still on the table stay out of the new stack, so a round can
        never contain more copies of a rank than the shoe holds. The count
        restarts from the cards on the table that everyone has already seen,
        and a full shuffle is forced before the next round.
        """
        in_play = Counter(self._in_play)
        cards = [
            rank
            for rank in range(1, 14)
            for _ in range(4 * self.num_decks - in_play[rank])
        ]
        if not cards:  # every card is on the table; nothing left to reshuffle
            cards = list(range(1, 14)) * (4 * self.num_decks)
        self.rng.shuffle(cards)
        self._cards = cards
        self.seen = list(self._in_play_seen)
        self.seen_total = sum(self.seen)
        self.shuffles += 1
        self._reshuffle_due = True
        self._burn()

    @property
    def needs_shuffle(self) -> bool:
        """True once the cut card has been reached (or the discards had to be
        reshuffled mid-round)."""
        return self._reshuffle_due or self.dealt >= self._cut_index

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
            # Reachable with deep penetration and several seats.
            self._reshuffle_discards()
        self.dealt += 1
        card = self._cards.pop()
        self._in_play.append(card)
        return card

    def observe(self, rank: int) -> None:
        """Mark a card as seen by everyone at the table."""
        v = 10 if rank >= 10 else rank
        self.seen[v] += 1
        self.seen_total += 1
        self._in_play_seen[v] += 1

    def draw_seen(self) -> int:
        card = self.draw()
        self.observe(card)
        return card

    def stack(self, cards: Iterable[int]) -> None:
        """Force the next cards to be ``cards`` (first element dealt first).

        Only meant for tests and hand-by-hand debugging.
        """
        self._cards.extend(reversed(list(cards)))
