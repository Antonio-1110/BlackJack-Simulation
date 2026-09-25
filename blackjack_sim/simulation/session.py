"""Run one session: a single player with a bankroll sitting at a table."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any

from ..engine import HI_LO, Rules, Table, format_cards, play_round
from ..strategies import BetContext, create_bet, create_play
from ..strategies.play.basic import BasicStrategy
from .config import Candidate, SessionSettings

_EPS = 1e-9


@dataclass
class SessionResult:
    path: list[float]  # bankroll before round 1, then after every round
    hands: int = 0  # rounds the player actually had a bet in
    initial_bet_total: float = 0.0
    wagered_total: float = 0.0  # incl. doubles, splits and insurance
    net_sq_total: float = 0.0  # sum of squared per-round results (for volatility)
    max_bet: float = 0.0
    ruined: bool = False
    hit_target: bool = False
    hit_stop_loss: bool = False
    shuffles: int = 0
    log: list[dict[str, Any]] | None = field(default=None, repr=False)

    @property
    def start(self) -> float:
        return self.path[0]

    @property
    def final(self) -> float:
        return self.path[-1]

    @property
    def net(self) -> float:
        return self.path[-1] - self.path[0]

    @property
    def rounds(self) -> int:
        return len(self.path) - 1

    @property
    def max_drawdown(self) -> float:
        peak, worst = -math.inf, 0.0
        for v in self.path:
            peak = max(peak, v)
            worst = max(worst, peak - v)
        return worst


def session_rngs(seed: int, session_index: int) -> tuple[random.Random, random.Random]:
    """Independent RNG streams for the shoe and for the player's strategies.

    Every candidate gets the same shoe stream for the same session index, so
    candidates are compared on identical cards (common random numbers) as long
    as they draw the same number of cards.
    """
    return (
        random.Random(f"{seed}:{session_index}:shoe"),
        random.Random(f"{seed}:{session_index}:player"),
    )


def run_session(
    rules: Rules,
    settings: SessionSettings,
    candidate: Candidate,
    session_index: int = 0,
    record_log: bool = False,
) -> SessionResult:
    shoe_rng, player_rng = session_rngs(settings.seed, session_index)
    others = settings.other_players
    table = Table(rules, 1 + others, shoe_rng)
    play = create_play(candidate.play, player_rng)
    bet_strategy = create_bet(candidate.bet, player_rng)
    filler = BasicStrategy()
    policies = [play] + [filler] * others
    other_bets = [rules.table_min] * others
    other_funds = [math.inf] * others

    start = bankroll = float(settings.bankroll)
    res = SessionResult(path=[start], log=[] if record_log else None)

    for r in range(settings.rounds):
        if bankroll < rules.table_min - _EPS:
            res.ruined = True
            break
        shuffled = table.prepare_round()
        ctx = BetContext(r, bankroll, start, rules, table.shoe)
        wanted = bet_strategy.bet(ctx)
        if wanted > 0:
            stake = min(max(wanted, rules.table_min), rules.table_max, bankroll)
        else:
            stake = 0.0
        tc = HI_LO.true_count(table.shoe) if record_log else 0.0

        result = play_round(table, [stake] + other_bets, policies, [bankroll] + other_funds)
        res.shuffles += shuffled
        seat = result.seats[0]
        if seat is not None:
            bankroll += seat.net
            res.hands += 1
            res.initial_bet_total += seat.initial_bet
            res.wagered_total += seat.wagered
            res.net_sq_total += seat.net * seat.net
            res.max_bet = max(res.max_bet, seat.initial_bet)
            bet_strategy.update(seat)
        res.path.append(bankroll)

        if record_log:
            res.log.append(_log_row(r + 1, shuffled, tc, stake, seat, result, bankroll))

        profit = bankroll - start
        if settings.win_target and profit >= settings.win_target - _EPS:
            res.hit_target = True
            break
        if settings.stop_loss and -profit >= settings.stop_loss - _EPS:
            res.hit_stop_loss = True
            break
    else:
        if bankroll < rules.table_min - _EPS:
            res.ruined = True

    return res


def _log_row(rnd, shuffled, tc, stake, seat, result, bankroll) -> dict[str, Any]:
    if seat is None:
        hands, outcomes, net = "(sat out)", "", 0.0
    else:
        hands = " | ".join(
            format_cards(h.cards) + (" (D)" if h.doubled else "") for h in seat.hands
        )
        outcomes = " | ".join(h.outcome.value for h in seat.hands)
        if seat.insurance_bet:
            outcomes += f" + insurance {seat.insurance_net:+g}"
        net = seat.net
    return {
        "round": rnd,
        "shuffled": shuffled,
        "true_count": round(tc, 2),
        "bet": stake,
        "player": hands,
        "dealer": format_cards(result.dealer_cards),
        "dealer_total": result.dealer_total,
        "outcome": outcomes,
        "net": net,
        "bankroll": bankroll,
    }
