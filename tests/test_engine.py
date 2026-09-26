import random

import pytest

from blackjack_sim.engine import (
    HI_LO,
    Action,
    Hand,
    IllegalAction,
    Outcome,
    Rules,
    Shoe,
    Table,
    play_round,
)

A, J, Q, K = 1, 11, 12, 13


def deal(cards, actions=(), rules=None, bets=(10,), bankrolls=None):
    """Play one round on a stacked shoe.

    Deal order: seat cards, dealer upcard, seat cards, dealer hole card (only
    in peek games), then hits / dealer draws in order.
    """
    table = Table(rules or Rules(), len(bets), random.Random(0))
    table.prepare_round()
    table.shoe.stack(cards)
    todo = list(actions)
    seen = []

    def policy(decision):
        seen.append(decision)
        if not todo:
            raise AssertionError(f"unexpected decision: {decision.kind} {decision.hand}")
        return todo.pop(0)

    result = play_round(table, list(bets), [policy] * len(bets), bankrolls)
    assert not todo, f"unused actions: {todo}"
    return result, seen


def make_hand(*cards):
    h = Hand()
    for c in cards:
        h.add(c)
    return h


# --------------------------------------------------------------------- hands
@pytest.mark.parametrize(
    "cards,total,soft",
    [
        ((A, 6), 17, True),
        ((A, 6, 10), 17, False),
        ((A, A), 12, True),
        ((A, A, 9), 21, True),
        ((K, Q), 20, False),
        ((K, Q, 5), 25, False),
        ((A, A, A, A, 7), 21, True),
        ((5, 5, A), 21, True),
    ],
)
def test_hand_totals(cards, total, soft):
    h = make_hand(*cards)
    assert h.total == total
    assert h.is_soft == soft


def test_blackjack_and_pairs():
    assert make_hand(A, K).is_blackjack
    assert not make_hand(A, 5, 5).is_blackjack
    assert make_hand(J, Q).is_pair  # any two ten-value cards
    assert not make_hand(9, 10).is_pair


# ------------------------------------------------------------------ payouts
def test_player_blackjack_pays_3_to_2():
    res, seen = deal([A, 9, K, 7])
    seat = res.seats[0]
    assert seen == []
    assert seat.hands[0].outcome is Outcome.BLACKJACK
    assert seat.net == 15


def test_six_to_five_payout():
    res, _ = deal([A, 9, K, 7], rules=Rules(blackjack_payout=1.2))
    assert res.seats[0].net == pytest.approx(12)


def test_dealer_blackjack_with_peek_ends_round():
    res, seen = deal([10, A, 9, K], [Action.NO_INSURANCE])
    assert [d.kind for d in seen] == ["insurance"]
    assert res.dealer_blackjack
    assert res.seats[0].net == -10


def test_insurance_pays_2_to_1():
    res, _ = deal([10, A, 9, K], [Action.INSURANCE])
    seat = res.seats[0]
    assert seat.insurance_bet == 5
    assert seat.insurance_net == 10
    assert seat.net == 0


def test_insurance_lost_when_no_dealer_blackjack():
    res, _ = deal([10, A, 9, 7], [Action.INSURANCE, Action.STAND])
    seat = res.seats[0]
    assert seat.net == 10 - 5  # hand wins 19 v 18, insurance lost


def test_blackjack_vs_blackjack_pushes():
    res, _ = deal([A, A, K, K], [Action.NO_INSURANCE])
    assert res.seats[0].hands[0].outcome is Outcome.PUSH
    assert res.seats[0].net == 0


def test_ten_upcard_peek_no_insurance_offered():
    res, seen = deal([10, K, 7, A])
    assert seen == []
    assert res.dealer_blackjack and res.seats[0].net == -10


# ------------------------------------------------------------------- dealer
def test_dealer_stands_on_soft_17_s17():
    res, _ = deal([10, 6, 10, A], [Action.STAND], rules=Rules(dealer_hits_soft_17=False))
    assert res.dealer_total == 17
    assert res.seats[0].net == 10


def test_dealer_hits_soft_17_h17():
    res, _ = deal([10, 6, 10, A, 3], [Action.STAND], rules=Rules(dealer_hits_soft_17=True))
    assert res.dealer_total == 20
    assert res.seats[0].net == 0


def test_dealer_hits_soft_17_reached_after_drawing():
    # 2 + 4 + A = soft 17 reached on a draw (the legacy engine missed this).
    cards = [10, 2, 10, 4, A, 2]
    res, _ = deal(cards, [Action.STAND], rules=Rules(dealer_hits_soft_17=True))
    assert res.dealer_total == 19
    res, _ = deal(cards, [Action.STAND], rules=Rules(dealer_hits_soft_17=False))
    assert res.dealer_total == 17


def test_dealer_does_not_draw_when_all_players_bust():
    res, _ = deal([10, 6, 6, 5, K], [Action.HIT])
    assert res.seats[0].hands[0].outcome is Outcome.BUST
    assert res.dealer_cards == [6, 5]


# ---------------------------------------------------------- player options
def test_double_down():
    res, _ = deal([5, 6, 6, 10, 10, 10], [Action.DOUBLE])
    seat = res.seats[0]
    assert seat.hands[0].doubled and seat.hands[0].bet == 20
    assert seat.net == 20 and seat.wagered == 20


def test_split_and_double_after_split():
    # 8,8 v 6: split; first hand 8+3 -> double -> 21; second 8+10 stand; dealer 16 busts.
    cards = [8, 6, 8, 10, 3, 10, 10, 10]
    res, seen = deal(cards, [Action.SPLIT, Action.DOUBLE, Action.STAND])
    seat = res.seats[0]
    assert [h.cards for h in seat.hands] == [[8, 3, 10], [8, 10]]
    assert Action.DOUBLE in seen[1].legal
    assert seat.net == 30 and seat.wagered == 30


def test_no_double_after_split_rule():
    cards = [8, 6, 8, 10, 3, 10, 10, 10]
    _, seen = deal(cards, [Action.SPLIT, Action.HIT, Action.STAND], rules=Rules(double_after_split=False))
    assert Action.DOUBLE not in seen[1].legal


def test_split_aces_get_one_card_and_21_is_not_blackjack():
    res, seen = deal([A, 7, A, 10, K, 5], [Action.SPLIT])
    seat = res.seats[0]
    assert len(seen) == 1  # no decisions after splitting aces
    assert [h.outcome for h in seat.hands] == [Outcome.WIN, Outcome.LOSE]
    assert seat.net == 0


def test_resplit_aces_when_allowed():
    rules = Rules(resplit_aces=True)
    _, seen = deal([A, 7, A, 10, A, K, 5, 9], [Action.SPLIT, Action.SPLIT], rules=rules)
    assert Action.SPLIT in seen[1].legal
    _, seen = deal([A, 7, A, 10, A, K, 5], [Action.SPLIT], rules=Rules(resplit_aces=False))
    assert len(seen) == 1


def test_max_split_hands():
    rules = Rules(max_split_hands=2)
    cards = [8, 6, 8, 10, 8, 10, 10, 10]
    _, seen = deal(cards, [Action.SPLIT, Action.STAND, Action.STAND], rules=rules)
    assert Action.SPLIT not in seen[1].legal


def test_late_surrender():
    res, _ = deal([10, 10, 6, 7], [Action.SURRENDER], rules=Rules(surrender="late"))
    assert res.seats[0].hands[0].outcome is Outcome.SURRENDER
    assert res.seats[0].net == -5


def test_surrender_not_offered_by_default_or_after_hit():
    _, seen = deal([10, 10, 3, 7, 3], [Action.HIT, Action.STAND], rules=Rules(surrender="late"))
    assert Action.SURRENDER in seen[0].legal
    assert Action.SURRENDER not in seen[1].legal
    _, seen = deal([10, 10, 6, 7], [Action.STAND])
    assert Action.SURRENDER not in seen[0].legal


def test_double_restriction():
    _, seen = deal([4, 6, 5, 10, 10, 10], [Action.HIT, Action.STAND], rules=Rules(double_on="10-11"))
    assert Action.DOUBLE not in seen[0].legal  # hard 9


def test_bankroll_limits_doubles_splits_and_insurance():
    res, seen = deal([8, A, 8, 7, 10], [Action.STAND], bankrolls=[10])
    assert [d.kind for d in seen] == ["play"]  # no insurance offered
    assert seen[0].legal == (Action.STAND, Action.HIT)


def test_five_card_charlie():
    res, _ = deal([2, 10, 2, K, 2, 2, 3], [Action.HIT] * 3, rules=Rules(charlie_cards=5))
    assert res.seats[0].net == 10


def test_illegal_action_raises():
    with pytest.raises(IllegalAction):
        deal([10, 6, 9, 10], [Action.SPLIT])


def test_multiple_seats_and_sitting_out():
    # seat0 sits out (bet 0): deal order skips it.
    res, _ = deal([10, 6, 9, 10, 10], [Action.STAND], bets=(0, 10))
    assert res.seats[0] is None
    assert res.seats[1].hands[0].cards == [10, 9]
    assert res.seats[1].net == 10


# ---------------------------------------------------------- no-hole-card
def test_no_peek_dealer_blackjack_takes_doubles():
    rules = Rules(dealer_peeks=False)
    res, _ = deal([5, 10, 6, 9, A], [Action.DOUBLE], rules=rules)
    assert res.dealer_blackjack
    assert res.seats[0].net == -20


def test_no_peek_original_bets_only():
    rules = Rules(dealer_peeks=False, no_peek_original_bets_only=True)
    res, _ = deal([5, 10, 6, 9, A], [Action.DOUBLE], rules=rules)
    assert res.seats[0].net == -10


# --------------------------------------------------------------------- shoe
def test_shoe_penetration_and_reshuffle():
    shoe = Shoe(1, 0.5, random.Random(1), burn_cards=0)
    assert shoe.cards_remaining == 52
    for _ in range(25):
        shoe.draw()
    assert not shoe.needs_shuffle
    shoe.draw()
    assert shoe.needs_shuffle


def test_table_reshuffles_at_cut_card():
    table = Table(Rules(num_decks=1, penetration=0.5), 1, random.Random(3))
    shuffles = 0
    for _ in range(200):
        res = play_round(table, [10], [lambda d: Action.STAND if d.kind == "play" else Action.NO_INSURANCE])
        shuffles += res.shuffled
        assert table.shoe.dealt <= 52
    assert shuffles > 10


def test_composition_is_six_decks():
    shoe = Shoe(6, 1.0, random.Random(0), burn_cards=0)
    cards = [shoe.draw() for _ in range(312)]
    assert all(cards.count(r) == 24 for r in range(1, 14))


def test_hi_lo_counts_only_seen_cards():
    shoe = Shoe(1, 1.0, random.Random(0), burn_cards=0)
    for c in (2, 3, 4, 10, A, 7):
        shoe.observe(c)
    assert HI_LO.running_count(shoe) == 1
    assert HI_LO.true_count(shoe) == pytest.approx(1 / (46 / 52))


def test_bad_rules_rejected():
    with pytest.raises(ValueError):
        Rules(double_on="whenever")
    with pytest.raises(ValueError):
        Rules.from_dict({"decks": 6})
