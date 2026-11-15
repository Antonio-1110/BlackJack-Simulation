"""The round engine.

A round is written as a generator: it *yields* a :class:`Decision` whenever a
player has to choose something and receives the chosen :class:`Action` back
via ``send()``. When the round is over the generator returns a
:class:`RoundResult`.

This keeps the rules readable as plain top-to-bottom code while still letting
an outside driver step through a round one decision at a time -- which is
exactly what a Gymnasium environment needs later. For normal simulations use
:func:`play_round`, which drives the generator with strategy objects.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Callable, Generator, Sequence

from .cards import Shoe
from .hand import Action, Hand, Outcome
from .rules import Rules

_EPS = 1e-9


class IllegalAction(ValueError):
    pass


@dataclass(slots=True)
class Decision:
    """Everything a strategy may look at when it has to act."""

    kind: str  # "play" or "insurance"
    seat: int
    hand_index: int
    hand: Hand
    num_hands: int
    dealer_up: int  # rank of the dealer's upcard (1 = Ace)
    legal: tuple[Action, ...]
    table: "Table"

    @property
    def rules(self) -> Rules:
        return self.table.rules

    @property
    def shoe(self) -> Shoe:
        return self.table.shoe

    @property
    def dealer_value(self) -> int:
        """Upcard value 1..10 (1 = Ace)."""
        return 10 if self.dealer_up >= 10 else self.dealer_up


@dataclass(slots=True)
class SeatResult:
    seat: int
    initial_bet: float
    hands: list[Hand]
    insurance_bet: float = 0.0
    insurance_net: float = 0.0
    net: float = 0.0
    wagered: float = 0.0  # all money put at risk: hand bets incl. doubles/splits + insurance

    @property
    def won(self) -> bool:
        return self.net > _EPS

    @property
    def lost(self) -> bool:
        return self.net < -_EPS


@dataclass(slots=True)
class RoundResult:
    seats: list[SeatResult | None]
    dealer_cards: list[int]
    dealer_total: int
    dealer_blackjack: bool
    shuffled: bool = False
    extra: dict = field(default_factory=dict)

    @property
    def dealer_bust(self) -> bool:
        return self.dealer_total > 21


RoundGenerator = Generator[Decision, Action, RoundResult]

_STAND_ONLY = (Action.STAND,)
_STAND_SPLIT = (Action.STAND, Action.SPLIT)
_STAND_HIT = (Action.STAND, Action.HIT)


class Table:
    """A blackjack table with ``num_seats`` player spots sharing one shoe."""

    def __init__(
        self,
        rules: Rules | None = None,
        num_seats: int = 1,
        rng: random.Random | None = None,
    ) -> None:
        if num_seats < 1:
            raise ValueError("num_seats must be >= 1")
        self.rules = rules or Rules()
        self.num_seats = num_seats
        self.rng = rng or random.Random()
        self.shoe = Shoe(
            self.rules.num_decks, self.rules.penetration, self.rng, self.rules.burn_cards
        )
        self.rounds_played = 0
        self._prepared = False
        self._shuffled = False

    def prepare_round(self) -> bool:
        """Shuffle if the cut card was reached (or on every round with a
        continuous shuffler). Returns True if a shuffle happened.

        Call this *before* asking a betting strategy for its wager so that it
        sees the post-shuffle count. It is idempotent until the next round is
        played, and :meth:`play_round` calls it itself if you did not.
        """
        if not self._prepared:
            self._shuffled = self.rules.continuous_shuffle or self.shoe.needs_shuffle
            if self._shuffled:
                self.shoe.shuffle()
            self._prepared = True
        return self._shuffled

    # ------------------------------------------------------------------ rules
    def legal_actions(self, hand: Hand, num_hands: int, available: float) -> tuple[Action, ...]:
        """Actions allowed for ``hand`` given the seat's uncommitted funds."""
        # Called before every decision, so Hand properties are read directly
        # from their fields (is_pair, is_split, total, is_soft).
        r = self.rules
        cards = hand.cards
        two_cards = len(cards) == 2
        can_afford = available + _EPS >= hand.bet
        split_depth = hand.split_depth
        can_split = False
        if two_cards and can_afford and num_hands < r.max_split_hands:
            a, b = cards
            pair_value = 10 if a >= 10 else a
            if pair_value == (10 if b >= 10 else b):
                can_split = not (pair_value == 1 and split_depth and not r.resplit_aces)
        if hand.from_split_aces and not r.hit_split_aces:
            return _STAND_SPLIT if can_split else _STAND_ONLY

        if not two_cards:
            return _STAND_HIT
        actions = [Action.STAND, Action.HIT]
        hard = hand.hard
        soft = hand.has_ace and hard <= 11
        if (
            can_afford
            and r.can_double_total(hard + 10 if soft else hard, soft)
            and (not split_depth or r.double_after_split)
        ):
            actions.append(Action.DOUBLE)
        if can_split:
            actions.append(Action.SPLIT)
        if r.surrender != "none" and not split_depth:
            actions.append(Action.SURRENDER)
        return tuple(actions)

    def _hand_finished(self, hand: Hand) -> bool:
        hard = hand.hard
        if hard > 21 or hard == 21 or (hard == 11 and hand.has_ace):
            return True
        charlie = self.rules.charlie_cards
        return bool(charlie) and len(hand.cards) >= charlie

    # ------------------------------------------------------------------ round
    def play_round(
        self,
        bets: Sequence[float],
        bankrolls: Sequence[float] | None = None,
    ) -> RoundGenerator:
        """Play one round. ``bets[i] == 0`` means seat ``i`` sits out.

        ``bankrolls`` caps how much each seat can commit (for doubles, splits
        and insurance); ``None`` means unlimited.
        """
        rules, shoe = self.rules, self.shoe
        draw_seen = shoe.draw_seen
        hand_finished, legal_actions = self._hand_finished, self.legal_actions
        n = self.num_seats
        if len(bets) != n:
            raise ValueError(f"expected {n} bets, got {len(bets)}")
        funds = [math.inf] * n if bankrolls is None else list(bankrolls)

        shuffled = self.prepare_round()
        self._prepared = False
        shoe.start_round()

        active = [i for i in range(n) if bets[i] > 0]
        committed = [0.0] * n
        hands: dict[int, list[Hand]] = {}
        for i in active:
            if bets[i] > funds[i] + _EPS:
                raise ValueError(f"seat {i} bet {bets[i]} exceeds bankroll {funds[i]}")
            hands[i] = [Hand(bets[i])]
            committed[i] = bets[i]

        # ---- deal: one card each, dealer up, second card each, dealer hole
        dealer = Hand()
        for i in active:
            hands[i][0].add(draw_seen())
        up = draw_seen()
        dealer.add(up)
        for i in active:
            hands[i][0].add(draw_seen())
        if rules.dealer_peeks:
            dealer.add(shoe.draw())  # face down: not observed yet

        # ---- insurance / even money
        insurance = [0.0] * n
        if rules.insurance and up == 1:
            for i in active:
                hand = hands[i][0]
                cost = hand.bet / 2
                if funds[i] - committed[i] + _EPS < cost:
                    continue
                legal = (Action.INSURANCE, Action.NO_INSURANCE)
                action = yield Decision("insurance", i, 0, hand, 1, up, legal, self)
                if action not in legal:
                    raise IllegalAction(f"{action!r} not in {legal}")
                if action is Action.INSURANCE:
                    insurance[i] = cost
                    committed[i] += cost

        # ---- dealer peek (hole-card games only)
        if rules.dealer_peeks and dealer.total == 21:
            shoe.observe(dealer.cards[1])
            return self._settle(bets, hands, insurance, dealer, True, shuffled)

        # ---- players act
        for i in active:
            seat_hands = hands[i]
            h = 0
            while h < len(seat_hands):
                hand = seat_hands[h]
                while True:
                    if len(hand.cards) == 1:  # split hand waiting for its 2nd card
                        hand.add(draw_seen())
                    if hand_finished(hand):
                        break
                    legal = legal_actions(hand, len(seat_hands), funds[i] - committed[i])
                    if len(legal) == 1:
                        break
                    action = yield Decision(
                        "play", i, h, hand, len(seat_hands), up, legal, self
                    )
                    if action not in legal:
                        raise IllegalAction(f"{action!r} not in {legal} for {hand!r}")
                    if action is Action.STAND:
                        break
                    if action is Action.HIT:
                        hand.add(draw_seen())
                    elif action is Action.DOUBLE:
                        committed[i] += hand.bet
                        hand.bet *= 2
                        hand.doubled = True
                        hand.add(draw_seen())
                        break
                    elif action is Action.SURRENDER:
                        hand.surrendered = True
                        break
                    elif action is Action.SPLIT:
                        committed[i] += hand.bet
                        aces = hand.pair_value == 1
                        first = Hand(hand.bet, hand.split_depth + 1)
                        second = Hand(hand.bet, hand.split_depth + 1)
                        first.add(hand.cards[0])
                        second.add(hand.cards[1])
                        first.from_split_aces = second.from_split_aces = aces
                        seat_hands[h] = first
                        seat_hands.insert(h + 1, second)
                        hand = first
                hand.done = True
                h += 1

        # ---- dealer acts
        if not rules.dealer_peeks:
            dealer.add(shoe.draw())
        shoe.observe(dealer.cards[1])
        dealer_bj = dealer.is_blackjack
        charlie = rules.charlie_cards
        live = False
        for seat_hands in hands.values():
            for hd in seat_hands:
                if not (
                    hd.hard > 21
                    or hd.surrendered
                    or hd.is_blackjack
                    or (charlie and len(hd.cards) >= charlie)
                ):
                    live = True
                    break
            if live:
                break
        if live and not dealer_bj:
            h17 = rules.dealer_hits_soft_17
            while dealer.total < 17 or (h17 and dealer.total == 17 and dealer.is_soft):
                dealer.add(draw_seen())

        return self._settle(bets, hands, insurance, dealer, dealer_bj, shuffled)

    # ------------------------------------------------------------- settlement
    def _settle(
        self,
        bets: Sequence[float],
        hands: dict[int, list[Hand]],
        insurance: list[float],
        dealer: Hand,
        dealer_bj: bool,
        shuffled: bool,
    ) -> RoundResult:
        rules = self.rules
        dealer_total = dealer.total
        dealer_bust = dealer_total > 21
        obo = dealer_bj and not rules.dealer_peeks and rules.no_peek_original_bets_only
        results: list[SeatResult | None] = [None] * self.num_seats

        for i, seat_hands in hands.items():
            original_lost = False
            for hand in seat_hands:
                b = hand.bet
                if obo and not hand.is_blackjack:
                    # Original bets only: against a dealer blackjack the seat
                    # loses its original bet once, however many hands it split
                    # into, doubled or busted; the extra money is returned.
                    if original_lost:
                        hand.outcome, hand.net = Outcome.PUSH, 0.0
                    else:
                        hand.outcome = (
                            Outcome.SURRENDER if hand.surrendered
                            else Outcome.BUST if hand.is_bust
                            else Outcome.LOSE
                        )
                        hand.net = -bets[i]
                        original_lost = True
                elif hand.surrendered:
                    hand.outcome = Outcome.SURRENDER
                    hand.net = -b if dealer_bj else -b / 2
                elif hand.is_bust:
                    hand.outcome, hand.net = Outcome.BUST, -b
                elif dealer_bj:
                    if hand.is_blackjack:
                        hand.outcome, hand.net = Outcome.PUSH, 0.0
                    else:
                        hand.outcome, hand.net = Outcome.LOSE, -b
                elif hand.is_blackjack:
                    hand.outcome, hand.net = Outcome.BLACKJACK, b * rules.blackjack_payout
                elif rules.charlie_cards and len(hand.cards) >= rules.charlie_cards:
                    hand.outcome, hand.net = Outcome.WIN, b
                elif dealer_bust or hand.total > dealer_total:
                    hand.outcome, hand.net = Outcome.WIN, b
                elif hand.total == dealer_total:
                    hand.outcome, hand.net = Outcome.PUSH, 0.0
                else:
                    hand.outcome, hand.net = Outcome.LOSE, -b

            ins = insurance[i]
            ins_net = (2 * ins if dealer_bj else -ins) if ins else 0.0
            # Plain loops instead of sum(<genexpr>): same order of additions,
            # so identical floats, but noticeably cheaper per round.
            net = wagered = 0
            for hd in seat_hands:
                net += hd.net
                wagered += hd.bet
            results[i] = SeatResult(
                seat=i,
                initial_bet=bets[i],
                hands=seat_hands,
                insurance_bet=ins,
                insurance_net=ins_net,
                net=net + ins_net,
                wagered=wagered + ins,
            )

        self.rounds_played += 1
        return RoundResult(results, list(dealer.cards), dealer_total, dealer_bj, shuffled)


Policy = Callable[[Decision], Action]


def play_round(
    table: Table,
    bets: Sequence[float],
    policies: Sequence[Policy],
    bankrolls: Sequence[float] | None = None,
) -> RoundResult:
    """Run one full round, asking ``policies[seat](decision)`` for every choice."""
    gen = table.play_round(bets, bankrolls)
    try:
        decision = next(gen)
        while True:
            decision = gen.send(policies[decision.seat](decision))
    except StopIteration as stop:
        return stop.value
