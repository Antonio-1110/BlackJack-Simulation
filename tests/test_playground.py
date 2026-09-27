"""The browser playground's runner (blackjack_sim.playground) and its build."""

import re
import sys
import zipfile
from pathlib import Path

import pytest

from blackjack_sim import playground as pg
from blackjack_sim.simulation import Candidate, SessionSettings, summarize
from blackjack_sim.engine import Rules
from blackjack_sim.simulation.session import run_session
from blackjack_sim.strategies import PLAY_STRATEGIES

ROOT = Path(__file__).resolve().parent.parent
SMALL = {"session": {"rounds": 40, "sessions": 6, "seed": 3}}

PLAY = """
from blackjack_sim.engine import Action
from blackjack_sim.strategies import PlayStrategy

class HitTo17(PlayStrategy):
    def play(self, d):
        return Action.HIT if d.hand.total < 17 else Action.STAND
"""

BET = """
from blackjack_sim.strategies import BetStrategy

class Double(BetStrategy):
    def bet(self, ctx):
        return 2 * ctx.rules.table_min
"""


def examples() -> list[str]:
    text = (ROOT / "web" / "examples.js").read_text()
    return re.findall(r"code: `(.*?)`,", text, re.S)


def test_runs_user_play_and_bet():
    out = pg.run(PLAY + BET, SMALL)
    assert (out["play"], out["bet"]) == ("HitTo17", "Double")
    yours, base = out["candidates"]
    assert yours["name"] == pg.YOURS and base["name"] == pg.BASELINE
    assert yours["summary"]["avg_bet"] == pytest.approx(20)
    assert base["summary"]["avg_bet"] == pytest.approx(10)
    assert len(yours["nets"]) == 6
    assert yours["bands"]["round"][-1] == 40
    assert out["log"] and out["log"][0]["round"] == 1


def test_missing_half_falls_back_to_basic_and_flat():
    out = pg.run(BET, {**SMALL, "compare": False})
    assert out["play"] is None and out["bet"] == "Double"
    assert len(out["candidates"]) == 1


def test_matches_the_numpy_summary():
    rules = Rules()
    settings = SessionSettings(rounds=60, sessions=12, seed=9)
    sessions = [run_session(rules, settings, Candidate("x"), i) for i in range(12)]
    mine, ref = pg.summary(sessions), summarize(sessions)
    for key in ref.keys() & mine.keys():
        assert mine[key] == pytest.approx(ref[key]), key


def test_rules_and_players_are_applied():
    settings = {
        "rules": {"num_decks": 1, "penetration": 0.5, "dealer_hits_soft_17": True, "insurance": False},
        "session": {"rounds": 50, "sessions": 2, "other_players": 3},
    }
    out = pg.run(BET, settings)
    assert sum(r["shuffled"] for r in out["log"]) > 5  # one deck, four seats, half dealt


@pytest.mark.parametrize(
    "code, message",
    [
        ("x = 1\n", "doesn't define a strategy"),
        ("def f(:\n    pass\n", "SyntaxError"),
        (PLAY + PLAY.replace("HitTo17", "Other"), "PLAY = Other"),
        (BET.replace("2 * ctx.rules.table_min", "1 / 0"), "line 6, in bet"),
    ],
)
def test_errors_point_at_user_code(code, message):
    with pytest.raises(pg.StrategyError, match=re.escape(message)):
        pg.run(code, SMALL)


def test_pick_one_of_several():
    out = pg.run(PLAY + PLAY.replace("HitTo17", "Other") + "PLAY = HitTo17\n", SMALL)
    assert out["play"] == "HitTo17"


def test_registry_is_reset_between_runs():
    code = PLAY.replace("class HitTo17", "@register_play\nclass HitTo17").replace(
        "import PlayStrategy", "import PlayStrategy, register_play"
    ).replace("(PlayStrategy):", "(PlayStrategy):\n    key = 'mine'")
    pg.run(code, SMALL)
    pg.run(code, SMALL)  # a duplicate key would raise here
    pg.load_strategies(BET)
    assert "mine" not in PLAY_STRATEGIES


@pytest.mark.parametrize("code", examples())
def test_examples_run(code):
    out = pg.run(code, SMALL)
    assert out["candidates"][0]["summary"]["sessions"] == 6


def test_build_zips_the_package(tmp_path):
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import build_web
    finally:
        sys.path.pop(0)
    out = build_web.build(tmp_path / "site")
    names = zipfile.ZipFile(out / "blackjack_sim.zip").namelist()
    assert "blackjack_sim/playground.py" in names
    assert not any("/rl/" in n or "__pycache__" in n for n in names)
    assert (out / "index.html").exists() and (out / "worker.js").exists()
