"""Stand-alone analyses that are handy for sanity-checking the engine."""

from __future__ import annotations

import random

from ..engine import Hand, Rules, Shoe

DEALER_COLUMNS = ("17", "18", "19", "20", "21", "blackjack", "bust")


def dealer_outcomes(rules: Rules, trials: int = 100_000, seed: int = 0) -> dict[int, dict[str, float]]:
    """Probability of each dealer final result by upcard (1 = Ace .. 10).

    The dealer draws from a real shoe (reshuffled at the cut card) with the
    upcard removed, following the ``dealer_hits_soft_17`` rule. Blackjacks are
    reported separately, i.e. these are *unconditional* probabilities (not
    conditioned on the dealer having peeked).
    """
    rng = random.Random(seed)
    table: dict[int, dict[str, float]] = {}
    h17 = rules.dealer_hits_soft_17
    for up in range(1, 11):
        counts = dict.fromkeys(DEALER_COLUMNS, 0)
        shoe = Shoe(rules.num_decks, rules.penetration, rng, rules.burn_cards)
        for _ in range(trials):
            if shoe.needs_shuffle:
                shoe.shuffle()
            hand = Hand()
            hand.add(up)
            hand.add(shoe.draw())
            if hand.total == 21:
                counts["blackjack"] += 1
                continue
            while hand.total < 17 or (h17 and hand.total == 17 and hand.is_soft):
                hand.add(shoe.draw())
            counts["bust" if hand.is_bust else str(hand.total)] += 1
        table[up] = {k: v / trials for k, v in counts.items()}
    return table
