"""Confidence intervals, paired comparisons and an engine regression guard."""

import math

import pytest

from blackjack_sim import playground as pg
from blackjack_sim.engine import Rules
from blackjack_sim.simulation import Candidate, ExperimentConfig, SessionSettings, run_experiment, run_session
from blackjack_sim.simulation.stats import (
    Z95,
    interval_stats,
    paired_edge_difference,
    ratio_se,
    sessions_needed,
    wilson,
)


def _sessions(cand, n=30, rounds=200, seed=5):
    settings = SessionSettings(rounds=rounds, sessions=n, seed=seed, bankroll=1e6)
    return [run_session(Rules(), settings, cand, i) for i in range(n)]


def test_wilson_interval():
    lo, hi = wilson(0, 10)
    assert lo == 0.0 and hi == pytest.approx(0.2775, abs=1e-4)
    lo, hi = wilson(5, 10)
    assert lo == pytest.approx(0.2366, abs=1e-4) and hi == pytest.approx(0.7634, abs=1e-4)
    assert wilson(0, 0) == (0.0, 1.0)


def test_ratio_se_and_sessions_needed():
    assert ratio_se([1.0], [1.0]) is None
    assert ratio_se([1.0, 2.0], [1.0, 2.0]) == pytest.approx(0.0)
    assert sessions_needed(100, 0.4, 0.1) == 1600
    assert sessions_needed(100, 0.05, 0.1) == 100  # already precise enough
    assert sessions_needed(100, None, 0.1) is None


def test_intervals_bracket_the_estimates():
    sessions = _sessions(Candidate("flat"))
    ref = run_experiment(
        ExperimentConfig(Rules(), SessionSettings(rounds=200, sessions=30, seed=5, bankroll=1e6),
                         [Candidate("flat")]),
        log_first_session=False,
    ).candidates[0].summary
    st = interval_stats(sessions)
    half = Z95 * ref["edge_se_pct"]
    assert st["edge_ci_low_pct"] == pytest.approx(ref["edge_pct"] - half)
    assert st["edge_ci_high_pct"] == pytest.approx(ref["edge_pct"] + half)
    assert st["ev_per_hand_ci_low"] < ref["ev_per_hand"] < st["ev_per_hand_ci_high"]
    assert st["mean_net_ci_low"] < ref["mean_net"] < st["mean_net_ci_high"]
    assert st["prob_profit_ci_low"] <= ref["prob_profit"] <= st["prob_profit_ci_high"]
    assert st["prob_ruin_ci_low"] == 0.0 and 0 < st["prob_ruin_ci_high"] < 0.2
    assert st["sessions_for_0_1pct"] >= 30
    # The numpy summary carries the same numbers.
    for key, value in st.items():
        assert ref[key] == pytest.approx(value), key


def test_single_session_intervals_are_undefined():
    st = interval_stats(_sessions(Candidate("flat"), n=1))
    assert st["edge_ci_low_pct"] is None and st["mean_net_se"] is None
    assert st["sessions_for_0_1pct"] is None


def test_paired_difference_uses_common_random_numbers():
    flat = _sessions(Candidate("flat"))
    same = paired_edge_difference(flat, flat)
    assert same["diff_pct"] == 0 and same["diff_se_pct"] == pytest.approx(0.0)
    assert same["correlation"] == pytest.approx(1.0)

    counter = _sessions(Candidate("dev", play={"type": "basic", "params": {"deviations": True}}))
    paired = paired_edge_difference(counter, flat)
    unpaired = math.hypot(
        ratio_se([s.net for s in counter], [s.initial_bet_total for s in counter]),
        ratio_se([s.net for s in flat], [s.initial_bet_total for s in flat]),
    )
    assert paired["correlation"] > 0.5
    assert paired["diff_se_pct"] < 0.5 * 100 * unpaired
    assert paired["diff_ci_low_pct"] < paired["diff_pct"] < paired["diff_ci_high_pct"]
    with pytest.raises(ValueError):
        paired_edge_difference(flat, flat[:-1])


def test_experiment_compare():
    cfg = ExperimentConfig(
        Rules(), SessionSettings(rounds=100, sessions=10, seed=3),
        [Candidate("flat10", bet={"type": "flat", "params": {"unit": 10}}),
         Candidate("flat20", bet={"type": "flat", "params": {"unit": 20}})],
    )
    cmp = run_experiment(cfg, log_first_session=False).compare("flat20", "flat10")
    assert cmp["diff_pct"] == pytest.approx(0.0, abs=1e-9)  # same cards, scaled bets


def test_playground_reports_intervals_and_comparison():
    code = "from blackjack_sim.strategies.play.basic import BasicStrategy\n\n\nclass Mine(BasicStrategy):\n    pass\n"
    out = pg.run(code, {"session": {"rounds": 50, "sessions": 4}})
    s = out["candidates"][0]["summary"]
    assert s["edge_ci_low_pct"] <= s["edge_pct"] <= s["edge_ci_high_pct"]
    assert out["comparison"]["diff_pct"] == pytest.approx(0.0)  # same play, same cards
    assert pg.run(code, {"session": {"rounds": 20, "sessions": 2}, "compare": False})["comparison"] is None


# Golden values recorded before the hot-loop optimisations of #17. Speedups
# must keep every result bit-identical for a given seed; if a deliberate
# rule or RNG change moves these, update them in the same commit.
GOLDEN = {
    "a": [(920.0, 5620.0), (730.0, 5740.0), (1205.0, 5760.0)],
    "b": [(1535.0, 12010.0), (620.0, 10675.0), (2030.0, 13020.0)],
}


@pytest.mark.parametrize("name", sorted(GOLDEN))
def test_engine_results_are_unchanged(name):
    cand = {
        "a": Candidate("a"),
        "b": Candidate("b", play={"type": "basic", "params": {"deviations": True}},
                       bet={"type": "count_spread"}),
    }[name]
    settings = SessionSettings(rounds=500, sessions=3, seed=2024, other_players=2)
    got = [(s.final, s.wagered_total) for s in (run_session(Rules(), settings, cand, i) for i in range(3))]
    assert got == GOLDEN[name]
