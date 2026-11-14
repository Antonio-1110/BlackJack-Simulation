"""Rule edge cases and invariants for the round engine.

Complements ``test_engine.py``: these tests pin down the less common rule
interactions (no-hole-card games, even money, split edge cases, the shoe
running out mid-round) and fuzz the engine with random legal play to check
bookkeeping invariants across many rule sets.
"""

import collections
import random

import pytest

from blackjack_sim.engine import Action, Outcome, Rules, Table, play_round
from blackjack_sim.strategies.play.basic import BasicStrategy

from test_engine import deal

A, J, Q, K = 1, 11, 12, 13
ENHC = Rules(dealer_peeks=False)
OBO = Rules(dealer_peeks=False, no_peek_original_bets_only=True)


# ------------------------------------------------------------ even money
def test_even_money_wins_one_to_one_when_dealer_has_no_blackjack():
    res, _ = deal([A, A, K, 7], [Action.INSURANCE])
    seat = res.seats[0]
    assert seat.hands[0].outcome is Outcome.BLACKJACK
    assert seat.net == 15 - 5


def test_even_money_wins_one_to_one_when_dealer_has_blackjack():
    res, _ = deal([A, A, K, K], [Action.INSURANCE])
    assert res.seats[0].net == 0 + 10


def test_no_insurance_offered_when_rule_is_off():
    _, seen = deal([10, A, 9, 7], [Action.STAND], rules=Rules(insurance=False))
    assert [d.kind for d in seen] == ["play"]


# ---------------------------------------------------------- no hole card
def test_no_peek_player_blackjack_pays_after_dealer_checks():
    # dealer: A up, then hole 7 is drawn after players act -> soft 18, no BJ
    res, seen = deal([A, A, K, 7], [Action.NO_INSURANCE], rules=ENHC)
    assert not res.dealer_blackjack
    assert res.seats[0].net == 15
    assert res.dealer_cards == [A, 7]  # dealer does not draw past the hole card


def test_no_peek_blackjack_against_blackjack_pushes():
    res, _ = deal([A, A, K, K], [Action.NO_INSURANCE], rules=ENHC)
    assert res.dealer_blackjack and res.seats[0].net == 0


def test_no_peek_surrender_against_dealer_blackjack_loses_whole_bet():
    rules = Rules(dealer_peeks=False, surrender="late")
    res, _ = deal([10, A, 6, K], [Action.NO_INSURANCE, Action.SURRENDER], rules=rules)
    assert res.dealer_blackjack
    assert res.seats[0].hands[0].outcome is Outcome.SURRENDER
    assert res.seats[0].net == -10


def test_no_peek_splits_lose_every_hand_to_dealer_blackjack():
    # 8,8 v 10: split, 8+10 stand, 8+9 stand; hole card A -> blackjack.
    cards = [8, 10, 8, 10, 9, A]
    res, _ = deal(cards, [Action.SPLIT, Action.STAND, Action.STAND], rules=ENHC)
    assert res.dealer_blackjack
    assert res.seats[0].net == -20


def test_obo_splits_lose_only_the_original_bet():
    cards = [8, 10, 8, 10, 9, A]
    res, _ = deal(cards, [Action.SPLIT, Action.STAND, Action.STAND], rules=OBO)
    seat = res.seats[0]
    assert seat.net == -10
    assert [h.outcome for h in seat.hands] == [Outcome.LOSE, Outcome.PUSH]


def test_obo_busted_split_hand_still_loses_only_the_original_bet():
    # 8,8 v 10: first hand 8+10 hits a K and busts, second 8+9 stands; hole A.
    cards = [8, 10, 8, 10, K, 9, A]
    res, _ = deal(cards, [Action.SPLIT, Action.HIT, Action.STAND], rules=OBO)
    seat = res.seats[0]
    assert res.dealer_blackjack
    assert seat.hands[0].outcome is Outcome.BUST
    assert seat.net == -10
    # Without OBO both hands are lost.
    res, _ = deal(cards, [Action.SPLIT, Action.HIT, Action.STAND], rules=ENHC)
    assert res.seats[0].net == -20


def test_obo_busted_double_loses_only_the_original_bet():
    # 6,6 v 10 doubled into a bust (6+6+K); hole A.
    res, _ = deal([6, 10, 6, K, A], [Action.DOUBLE], rules=OBO)
    assert res.seats[0].hands[0].outcome is Outcome.BUST
    assert res.seats[0].net == -10


def test_obo_does_not_change_play_against_a_dealer_without_blackjack():
    cards = [8, 10, 8, 10, K, 9, 7]
    res, _ = deal(cards, [Action.SPLIT, Action.HIT, Action.STAND], rules=OBO)
    assert not res.dealer_blackjack
    # first hand busts (-10), second hand 17 v dealer 17 pushes
    assert res.seats[0].net == -10
    assert [h.outcome for h in res.seats[0].hands] == [Outcome.BUST, Outcome.PUSH]


# ----------------------------------------------------------------- splits
def test_split_tens_drawing_an_ace_pay_even_money_not_blackjack():
    # K,K v 6: split; K+A = 21 (not a natural), K+9 stands; dealer 6+10+10 busts.
    res, seen = deal([K, 6, K, 10, A, 9, 10], [Action.SPLIT, Action.STAND])
    seat = res.seats[0]
    assert [h.outcome for h in seat.hands] == [Outcome.WIN, Outcome.WIN]
    assert seat.net == 20
    assert len(seen) == 2  # the 21 hand needs no decision


def test_mixed_ten_value_cards_can_be_split_and_resplit():
    cards = [J, 6, Q, 10, K, 9, 8, 10]
    _, seen = deal(cards, [Action.SPLIT, Action.SPLIT, Action.STAND, Action.STAND, Action.STAND])
    assert Action.SPLIT in seen[0].legal
    assert Action.SPLIT in seen[1].legal  # J + K is still a pair
    assert seen[-1].num_hands == 3


def test_hit_split_aces_when_allowed():
    rules = Rules(hit_split_aces=True)
    cards = [A, 7, A, 10, 5, 3, 9, 10]
    res, seen = deal(cards, [Action.SPLIT, Action.HIT, Action.STAND, Action.STAND], rules=rules)
    assert Action.HIT in seen[1].legal
    assert res.seats[0].hands[0].cards == [A, 5, 3]


def test_split_aces_stand_on_one_card_even_with_a_small_total():
    res, seen = deal([A, 9, A, 10, 2, 3], [Action.SPLIT])
    assert len(seen) == 1
    assert [h.cards for h in res.seats[0].hands] == [[A, 2], [A, 3]]


def test_no_split_without_money_for_the_second_bet():
    _, seen = deal([8, 6, 8, 10, 10, 10], [Action.STAND], bankrolls=[15])
    assert Action.SPLIT not in seen[0].legal
    assert Action.DOUBLE not in seen[0].legal  # no doubling for less either


def test_splitting_is_off_when_max_split_hands_is_one():
    _, seen = deal([8, 6, 8, 10, 10], [Action.STAND], rules=Rules(max_split_hands=1))
    assert Action.SPLIT not in seen[0].legal


def test_surrender_not_offered_on_split_hands():
    rules = Rules(surrender="late")
    cards = [8, 10, 8, 7, 6, 10, 10]
    _, seen = deal(cards, [Action.SPLIT, Action.STAND, Action.STAND], rules=rules)
    assert Action.SURRENDER in seen[0].legal
    assert all(Action.SURRENDER not in d.legal for d in seen[1:])


# --------------------------------------------------------- double / charlie
def test_double_draws_exactly_one_card():
    res, seen = deal([2, 10, 3, 10, 2], [Action.DOUBLE])
    hand = res.seats[0].hands[0]
    assert hand.cards == [2, 3, 2] and hand.doubled
    assert len(seen) == 1
    assert res.seats[0].net == -20


def test_soft_double_restricted_by_double_on_rule():
    _, seen = deal([A, 6, 9, 10, 10], [Action.STAND], rules=Rules(double_on="9-11"))
    assert Action.DOUBLE not in seen[0].legal  # soft 20
    _, seen = deal([A, 6, 9, 10, 10], [Action.STAND], rules=Rules(double_on="any"))
    assert Action.DOUBLE in seen[0].legal


def test_dealer_does_not_draw_when_only_charlie_hands_remain():
    rules = Rules(charlie_cards=5)
    res, _ = deal([2, 10, 2, 6, 2, 2, 3, 5], [Action.HIT] * 3, rules=rules)
    assert res.seats[0].net == 10
    assert res.dealer_cards == [10, 6]


def test_charlie_loses_to_dealer_blackjack():
    rules = Rules(charlie_cards=5, dealer_peeks=False)
    res, _ = deal([2, 10, 2, 2, 2, 3, A], [Action.HIT] * 3, rules=rules)
    assert res.dealer_blackjack
    assert res.seats[0].net == -10


# ----------------------------------------------------------------- shoe
def test_shoe_running_out_mid_round_never_repeats_cards_on_the_table():
    rules = Rules(num_decks=1, penetration=1.0, burn_cards=0)
    table = Table(rules, num_seats=7, rng=random.Random(11))
    policy = BasicStrategy()
    mid_round_reshuffles = 0
    for _ in range(300):
        shuffles_before = table.shoe.shuffles
        res = play_round(table, [10] * 7, [policy] * 7)
        cards = list(res.dealer_cards) + [
            c for seat in res.seats for h in seat.hands for c in h.cards
        ]
        assert max(collections.Counter(cards).values()) <= 4
        if table.shoe.shuffles - shuffles_before > res.shuffled:
            mid_round_reshuffles += 1
            assert table.shoe.needs_shuffle  # full shuffle before next round
    assert mid_round_reshuffles > 10


def test_count_after_mid_round_reshuffle_only_includes_cards_on_the_table():
    rules = Rules(num_decks=1, penetration=1.0, burn_cards=0)
    table = Table(rules, num_seats=1, rng=random.Random(0))
    table.prepare_round()
    shoe = table.shoe
    while shoe.cards_remaining > 2:
        shoe.draw()
    shoe.start_round()
    shoe._cards[-2:] = [5, 10]  # next draws: 10 (seat), 5 (dealer up)
    res = play_round(table, [10], [lambda d: Action.STAND])
    on_table = list(res.dealer_cards) + res.seats[0].hands[0].cards
    expected = [0] * 11
    for c in on_table:
        expected[min(c, 10)] += 1
    assert shoe.seen == expected
    assert shoe.unseen_cards == 52 - len(on_table)


def test_burn_cards_validated():
    with pytest.raises(ValueError):
        Rules(burn_cards=-1)
    with pytest.raises(ValueError):
        Rules(num_decks=1, burn_cards=40)
    assert Rules(burn_cards=0).burn_cards == 0


# ------------------------------------------------------------- invariants
def _random_rules(rng):
    return Rules(
        num_decks=rng.choice([1, 2, 6, 8]),
        penetration=rng.choice([0.5, 0.75, 1.0]),
        dealer_hits_soft_17=rng.random() < 0.5,
        dealer_peeks=rng.random() < 0.7,
        no_peek_original_bets_only=rng.random() < 0.5,
        blackjack_payout=rng.choice([1.5, 1.2, 1.0]),
        insurance=rng.random() < 0.8,
        double_on=rng.choice(["any", "9-11", "10-11"]),
        double_after_split=rng.random() < 0.5,
        max_split_hands=rng.choice([1, 2, 3, 4]),
        resplit_aces=rng.random() < 0.5,
        hit_split_aces=rng.random() < 0.5,
        surrender=rng.choice(["none", "late"]),
        charlie_cards=rng.choice([0, 0, 5, 6]),
    )


@pytest.mark.parametrize("seed", range(8))
def test_random_legal_play_keeps_the_books_straight(seed):
    rng = random.Random(seed)
    for _ in range(25):
        rules = _random_rules(rng)
        seats = rng.choice([1, 2, 5, 7])
        table = Table(rules, seats, random.Random(rng.random()))
        bankrolls = [rng.choice([10, 25, 1000]) for _ in range(seats)]

        def policy(d):
            assert d.legal, "a decision must offer at least one action"
            return rng.choice(d.legal)

        for _ in range(30):
            res = play_round(table, [10] * seats, [policy] * seats, bankrolls)
            cards = list(res.dealer_cards)
            for i, seat in enumerate(res.seats):
                cards += [c for h in seat.hands for c in h.cards]
                hand_sum = sum(h.net for h in seat.hands)
                assert seat.net == pytest.approx(hand_sum + seat.insurance_net)
                assert seat.wagered <= bankrolls[i] + 1e-9
                assert seat.wagered == pytest.approx(
                    sum(h.bet for h in seat.hands) + seat.insurance_bet
                )
                assert len(seat.hands) <= rules.max_split_hands
                max_win = sum(h.bet for h in seat.hands) * max(1.0, rules.blackjack_payout)
                assert -seat.wagered - 1e-9 <= seat.net <= max_win + seat.insurance_bet * 2
                for h in seat.hands:
                    assert h.outcome is not None
                    assert h.bet in (10, 20)
                    if h.outcome is Outcome.BLACKJACK:
                        assert h.is_blackjack and not res.dealer_blackjack
                    if h.is_bust and not h.surrendered:
                        assert h.net <= 0
            assert max(collections.Counter(cards).values()) <= 4 * rules.num_decks
            shoe = table.shoe
            assert sum(shoe.seen[1:]) == shoe.seen_total <= shoe.total_cards
            if res.dealer_total < 17 and not res.dealer_blackjack:
                # the dealer only stops short of 17 when no live hand is left
                live = [
                    h for seat in res.seats for h in seat.hands
                    if not (h.is_bust or h.surrendered or h.is_blackjack)
                    and not (rules.charlie_cards and len(h.cards) >= rules.charlie_cards)
                ]
                assert not live


# ------------------------------------------------------------ house edge
def test_basic_strategy_house_edge_is_in_the_textbook_range():
    """6 decks, S17, DAS, no surrender: basic strategy loses about 0.4-0.5%.

    A payout or settlement bug usually moves this by a whole percent or more,
    so a seeded 60k-round run with a wide band catches it without flaking.
    """
    table = Table(Rules(), 1, random.Random(2024))
    policy = BasicStrategy()
    rounds = 60_000
    net = sum(play_round(table, [1], [policy]).seats[0].net for _ in range(rounds))
    edge = net / rounds
    assert -0.017 < edge < 0.008
