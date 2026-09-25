from pathlib import Path

import pytest

from blackjack_sim import Candidate, ExperimentConfig, Rules, SessionSettings, run_experiment, run_session
from blackjack_sim.__main__ import main
from blackjack_sim.simulation.export import write_results

ROOT = Path(__file__).resolve().parents[1]


def small_config(**session):
    settings = dict(rounds=200, sessions=6, bankroll=1000, seed=1)
    settings.update(session)
    return ExperimentConfig(
        rules=Rules(),
        session=SessionSettings(**settings),
        candidates=[
            Candidate("flat10", bet={"type": "flat", "params": {"unit": 10}}),
            Candidate("flat20", bet={"type": "flat", "params": {"unit": 20}}),
            Candidate("mart", bet={"type": "martingale", "params": {"unit": 10}}),
        ],
    )


def test_session_is_reproducible():
    cfg = small_config()
    a = run_session(cfg.rules, cfg.session, cfg.candidates[2], 3)
    b = run_session(cfg.rules, cfg.session, cfg.candidates[2], 3)
    assert a.path == b.path


def test_common_random_numbers_across_bet_sizes():
    # Same play strategy + same seed = same cards, so flat 20 is exactly 2x flat 10.
    cfg = small_config()
    a = run_session(cfg.rules, cfg.session, cfg.candidates[0], 0)
    b = run_session(cfg.rules, cfg.session, cfg.candidates[1], 0)
    assert b.net == pytest.approx(2 * a.net)
    assert b.hands == a.hands


def test_bankroll_accounting_matches_path():
    cfg = small_config()
    s = run_session(cfg.rules, cfg.session, cfg.candidates[2], 0, record_log=True)
    assert len(s.log) == s.rounds
    assert sum(r["net"] for r in s.log) == pytest.approx(s.net)
    assert s.log[-1]["bankroll"] == pytest.approx(s.final)


def test_ruin_ends_session():
    cfg = small_config(bankroll=50, rounds=5000)
    s = run_session(cfg.rules, cfg.session, cfg.candidates[2], 0)
    assert s.ruined
    assert s.final < cfg.rules.table_min
    assert s.rounds < 5000


def test_win_target_and_stop_loss():
    cfg = small_config(win_target=30, stop_loss=30, rounds=10_000)
    for i in range(5):
        s = run_session(cfg.rules, cfg.session, cfg.candidates[0], i)
        assert s.hit_target or s.hit_stop_loss
        assert s.net >= 30 or s.net <= -30


def test_bet_is_clamped_to_table_limits_and_bankroll():
    cfg = small_config(bankroll=1000)
    cfg.rules = Rules(table_min=10, table_max=50)
    s = run_session(cfg.rules, cfg.session, Candidate("big", bet={"type": "flat", "params": {"unit": 500}}), 0)
    assert s.max_bet == 50


def test_experiment_summary_and_parallel_equivalence():
    cfg = small_config()
    serial = run_experiment(cfg, workers=1)
    parallel = run_experiment(cfg, workers=2, chunk_size=2)
    for a, b in zip(serial.candidates, parallel.candidates):
        assert [s.path for s in a.sessions] == [s.path for s in b.sessions]
    summary = serial.summary_frame()
    assert list(summary.index) == ["flat10", "flat20", "mart"]
    assert summary.loc["flat20", "edge_pct"] == pytest.approx(summary.loc["flat10", "edge_pct"])
    assert serial["flat10"].paths().shape == (6, 201)


def test_config_roundtrip(tmp_path):
    cfg = small_config()
    path = tmp_path / "cfg.json"
    cfg.save(path)
    loaded = ExperimentConfig.load(path)
    assert loaded.to_dict() == cfg.to_dict()


@pytest.mark.parametrize("path", sorted((ROOT / "configs").glob("*.json")))
def test_example_configs_load(path):
    ExperimentConfig.load(path)


def test_bad_config_rejected():
    with pytest.raises(ValueError, match="unique"):
        ExperimentConfig(candidates=[Candidate("a"), Candidate("a")]).validate()
    with pytest.raises(ValueError, match="Unknown session"):
        ExperimentConfig.from_dict({"session": {"hands": 5}})


def test_export_and_cli(tmp_path, capsys):
    result = run_experiment(small_config(sessions=2, rounds=50))
    out = write_results(result, tmp_path / "res")
    assert {p.name for p in out.iterdir()} >= {"config.json", "summary.csv", "sessions.csv",
                                               "bankroll_percentiles.csv", "hand_log_flat10.csv"}
    cfg_path = tmp_path / "cfg.json"
    small_config(sessions=2, rounds=50).save(cfg_path)
    assert main(["run", str(cfg_path), "--out", str(tmp_path / "cli"), "--workers", "1"]) == 0
    assert (tmp_path / "cli" / "summary.csv").exists()
    assert main(["strategies"]) == 0


def test_house_edge_is_in_the_right_ballpark():
    """6D S17 DAS 3:2 basic strategy is about -0.4%. 300k hands -> SE ~0.2%."""
    cfg = ExperimentConfig(
        rules=Rules(table_max=1e9),
        session=SessionSettings(rounds=10_000, sessions=30, bankroll=1e12, seed=99),
        candidates=[Candidate("basic")],
    )
    edge = run_experiment(cfg, workers=None, log_first_session=False).candidates[0].summary["edge_pct"]
    assert -1.2 < edge < 0.4
