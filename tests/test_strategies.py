import math
import random

import pytest

from blackjack_sim.engine import Action, Decision, Hand, Rules, SeatResult, Table
from blackjack_sim.strategies import (
    BET_STRATEGIES,
    PLAY_STRATEGIES,
    BetContext,
    create_bet,
    create_play,
)

A, K = 1, 13
H, S, D, P, R = Action.HIT, Action.STAND, Action.DOUBLE, Action.SPLIT, Action.SURRENDER


def decide(cards, up, rules=None, deviations=False, running_count=0):
    table = Table(rules or Rules(), 1, random.Random(0))
    if running_count:
        # Fake a running count by marking low cards as seen.
        table.shoe.seen[5] += running_count
        table.shoe.seen_total += running_count
    hand = Hand(10)
    for c in cards:
        hand.add(c)
    legal = table.legal_actions(hand, 1, math.inf)
    d = Decision("play", 0, 0, hand, 1, up, legal, table)
    return create_play({"type": "basic", "params": {"deviations": deviations}})(d)


@pytest.mark.parametrize(
    "cards,up,expected",
    [
        ((10, 6), 10, H),
        ((10, 6), 6, S),
        ((10, 2), 3, H),
        ((10, 2), 4, S),
        ((6, 5), 10, D),
        ((6, 5), A, H),  # S17
        ((5, 4), 3, D),
        ((5, 4), 2, H),
        ((A, 7), 2, S),  # S17
        ((A, 7), 6, D),
        ((A, 7), 9, H),
        ((A, 6), 2, H),
        ((A, 8), 6, S),  # S17
        ((8, 8), 10, P),
        ((A, A), A, P),
        ((10, K), 6, S),
        ((9, 9), 7, S),
        ((9, 9), 8, P),
        ((5, 5), 9, D),  # never split fives
        ((4, 4), 5, P),  # DAS
        ((2, 2), 3, P),  # DAS
        ((10, 7), A, S),
        ((A, 2, 5), 3, S),  # soft 18, can't double -> stand (Ds fallback)
        ((2, 3, 6), 10, H),  # 3-card 11 cannot double -> hit
    ],
)
def test_basic_strategy_s17(cards, up, expected):
    assert decide(cards, up) is expected


@pytest.mark.parametrize(
    "cards,up,expected",
    [((6, 5), A, D), ((A, 7), 2, D), ((A, 8), 6, D), ((10, 7), A, S)],
)
def test_basic_strategy_h17(cards, up, expected):
    assert decide(cards, up, Rules(dealer_hits_soft_17=True)) is expected


def test_basic_strategy_rule_dependent():
    assert decide((4, 4), 5, Rules(double_after_split=False)) is H
    assert decide((10, 6), 10, Rules(surrender="late")) is R
    assert decide((10, 5), 10, Rules(surrender="late")) is R
    assert decide((10, 7), A, Rules(surrender="late", dealer_hits_soft_17=True)) is R
    assert decide((10, 8), A, Rules(surrender="late", dealer_hits_soft_17=True)) is S
    assert decide((8, 8), A, Rules(surrender="late", dealer_hits_soft_17=True)) is R
    assert decide((5, 4), 3, Rules(double_on="10-11")) is H


def test_index_plays():
    assert decide((10, 6), 10, deviations=True, running_count=-5) is H
    assert decide((10, 6), 10, deviations=True, running_count=1) is S
    assert decide((10, 2), 3, deviations=True, running_count=20) is S
    assert decide((10, 10), 6, deviations=True, running_count=40) is P
    assert decide((10, 10), 6, deviations=False, running_count=40) is S


def test_insurance_only_with_deviations_and_high_count():
    table = Table(Rules(), 1, random.Random(0))
    hand = Hand(10)
    hand.add(10)
    hand.add(9)
    d = Decision("insurance", 0, 0, hand, 1, A, (Action.INSURANCE, Action.NO_INSURANCE), table)
    assert create_play("basic")(d) is Action.NO_INSURANCE
    assert create_play({"type": "basic", "params": {"deviations": True}})(d) is Action.NO_INSURANCE
    table.shoe.seen[5] += 30
    table.shoe.seen_total += 30
    assert create_play({"type": "basic", "params": {"deviations": True}})(d) is Action.INSURANCE


# -------------------------------------------------------------------- betting
def ctx(bankroll=1000.0, table=None):
    table = table or Table(Rules(), 1, random.Random(0))
    return BetContext(0, bankroll, 1000.0, table.rules, table.shoe)


def seat(net, bet=10.0):
    return SeatResult(0, bet, [], net=net)


def run_bets(strategy, nets):
    """Return the bet before each result, plus the bet after the last one."""
    bets = []
    for n in nets:
        b = strategy.bet(ctx())
        bets.append(b)
        strategy.update(seat(n * b, b))
    bets.append(strategy.bet(ctx()))
    return bets


def test_martingale():
    m = create_bet({"type": "martingale", "params": {"unit": 10}})
    assert run_bets(m, [-1, -1, -1, 1, 0, -1]) == [10, 20, 40, 80, 10, 10, 20]


def test_martingale_max_steps():
    m = create_bet({"type": "martingale", "params": {"unit": 10, "max_steps": 2}})
    assert run_bets(m, [-1, -1, -1]) == [10, 20, 40, 10]


def test_paroli():
    p = create_bet({"type": "paroli", "params": {"unit": 10, "streak_target": 3}})
    assert run_bets(p, [1, 1, 1, 1, -1]) == [10, 20, 40, 10, 20, 10]


def test_dalembert():
    d = create_bet({"type": "dalembert", "params": {"unit": 10}})
    assert run_bets(d, [-1, -1, 1, 1, 1]) == [10, 20, 30, 20, 10, 10]


def test_fibonacci():
    f = create_bet({"type": "fibonacci", "params": {"unit": 10}})
    assert run_bets(f, [-1, -1, -1, -1, 1]) == [10, 10, 20, 30, 50, 20]


def test_sequence_1326():
    s = create_bet({"type": "sequence", "params": {"unit": 10}})
    assert run_bets(s, [1, 1, 1, 1, 1, -1]) == [10, 30, 20, 60, 10, 30, 10]


def test_oscars_grind_stops_at_one_unit_profit():
    o = create_bet({"type": "oscars_grind", "params": {"unit": 10}})
    # lose 1, lose 1, win 1 (+1 unit next), win 2 -> cycle profit +1 -> reset
    assert run_bets(o, [-1, -1, 1, 1]) == [10, 10, 10, 20, 10]


def test_random_bet_is_mean_preserving():
    r = create_bet({"type": "random", "params": {"unit": 10, "volatility": 1.0}}, rng=random.Random(1))
    bets = [r.bet(ctx()) for _ in range(200_000)]
    assert sum(bets) / len(bets) == pytest.approx(10, rel=0.03)
    assert min(bets) < 5 < 20 < max(bets)


def test_proportional():
    p = create_bet({"type": "proportional", "params": {"fraction": 0.02}})
    assert p.bet(ctx(bankroll=500)) == 10


def test_count_spread():
    table = Table(Rules(num_decks=1), 1, random.Random(0))
    c = create_bet({"type": "count_spread", "params": {"unit": 10, "min_units": 1, "max_units": 8,
                                                        "tc_start": 1, "ramp": 2}})
    assert c.bet(ctx(table=table)) == 10
    table.shoe.seen = [0] * 11
    table.shoe.seen[5] = 2  # RC +2, ~1 deck left -> TC 2 -> 1 + 2*2 = 5 units
    table.shoe.seen_total = 2
    assert c.bet(ctx(table=table)) == 50
    table.shoe.seen[5] = 20
    table.shoe.seen_total = 20
    assert c.bet(ctx(table=table)) == 80


def test_count_spread_wong_out():
    table = Table(Rules(num_decks=1), 1, random.Random(0))
    table.shoe.seen[10] = 10
    table.shoe.seen_total = 10
    c = create_bet({"type": "count_spread", "params": {"wong_out_below": -1}})
    assert c.bet(ctx(table=table)) == 0


# ------------------------------------------------------------------- registry
def test_registry_validation():
    with pytest.raises(ValueError, match="unknown parameter"):
        create_bet({"type": "flat", "params": {"units": 1, "colour": "red"}})
    with pytest.raises(ValueError, match="Unknown bet strategy"):
        create_bet("nope")
    with pytest.raises(ValueError):
        create_bet({"type": "martingale", "params": {"multiplier": 0.5}})
    with pytest.raises(ValueError):
        create_bet({"type": "sequence", "params": {"sequence": "1-x"}})


@pytest.mark.parametrize("key", sorted(PLAY_STRATEGIES))
def test_every_play_strategy_plays_legal_moves(key):
    rules = Rules(surrender="late", charlie_cards=0)
    table = Table(rules, 1, random.Random(5))
    strat = create_play(key, rng=random.Random(1))
    from blackjack_sim.engine import play_round

    for _ in range(300):
        play_round(table, [10], [strat])


@pytest.mark.parametrize("key", sorted(BET_STRATEGIES))
def test_every_bet_strategy_returns_non_negative_bets(key):
    strat = create_bet(key, rng=random.Random(1))
    for n in (-1, -1, 1, 0, 1, -1):
        b = strat.bet(ctx())
        assert b >= 0
        strat.update(seat(n * max(b, 1), max(b, 1)))
