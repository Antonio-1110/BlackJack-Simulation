"""Monte Carlo experiments: many sessions per candidate, then summary stats."""

from __future__ import annotations

import math
import os
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from .config import Candidate, ExperimentConfig
from .session import SessionResult, run_session

ProgressFn = Callable[[int, int], None]


@dataclass
class CandidateResult:
    candidate: Candidate
    sessions: list[SessionResult]
    summary: dict[str, float] = field(default_factory=dict)

    @property
    def name(self) -> str:
        return self.candidate.name

    def paths(self, rounds: int | None = None) -> np.ndarray:
        """Bankroll paths as a (sessions, rounds + 1) array. Sessions that
        stopped early are padded with their final bankroll."""
        n = rounds if rounds is not None else max(s.rounds for s in self.sessions)
        out = np.empty((len(self.sessions), n + 1))
        for i, s in enumerate(self.sessions):
            p = s.path[: n + 1]
            out[i, : len(p)] = p
            out[i, len(p):] = p[-1]
        return out

    def column(self, attr: str) -> np.ndarray:
        return np.array([getattr(s, attr) for s in self.sessions], dtype=float)


@dataclass
class ExperimentResult:
    config: ExperimentConfig
    candidates: list[CandidateResult]
    elapsed: float

    def summary_rows(self) -> list[dict[str, Any]]:
        return [{"candidate": c.name, **c.summary} for c in self.candidates]

    def summary_frame(self):
        import pandas as pd

        return pd.DataFrame(self.summary_rows()).set_index("candidate")

    def __getitem__(self, name: str) -> CandidateResult:
        for c in self.candidates:
            if c.name == name:
                return c
        raise KeyError(name)


# ---------------------------------------------------------------- summarising
SUMMARY_COLUMNS: dict[str, str] = {
    "mean_net": "Mean profit per session",
    "median_net": "Median profit per session",
    "std_net": "Std dev of session profit",
    "p05_net": "5th percentile profit",
    "p95_net": "95th percentile profit",
    "prob_profit": "P(session ends in profit)",
    "prob_ruin": "P(ruin: bankroll < table min)",
    "prob_target": "P(win target hit)",
    "prob_stop_loss": "P(stop loss hit)",
    "avg_hands": "Avg hands played",
    "avg_bet": "Avg initial bet",
    "max_bet": "Largest bet seen",
    "edge_pct": "Return per unit bet, % (player edge)",
    "edge_se_pct": "Std error of edge, %",
    "ev_per_hand": "Expected profit per hand",
    "sd_per_hand": "Std dev per hand",
    "avg_max_drawdown": "Avg max drawdown",
    "worst_max_drawdown": "Worst max drawdown",
}


def summarize(sessions: list[SessionResult]) -> dict[str, float]:
    net = np.array([s.net for s in sessions])
    bets = np.array([s.initial_bet_total for s in sessions])
    hands = np.array([s.hands for s in sessions], dtype=float)
    dd = np.array([s.max_drawdown for s in sessions])
    n = len(sessions)
    total_bet = bets.sum()
    total_hands = hands.sum()
    edge = net.sum() / total_bet if total_bet else 0.0
    # Ratio-estimator standard error of (sum net / sum bet), using sessions as samples.
    if n > 1 and total_bet:
        resid = net - edge * bets
        edge_se = resid.std(ddof=1) / (bets.mean() * math.sqrt(n))
    else:
        edge_se = float("nan")
    ev_hand = net.sum() / total_hands if total_hands else 0.0
    sq = sum(s.net_sq_total for s in sessions)
    var_hand = sq / total_hands - ev_hand**2 if total_hands else 0.0
    return {
        "mean_net": float(net.mean()),
        "median_net": float(np.median(net)),
        "std_net": float(net.std(ddof=1)) if n > 1 else 0.0,
        "p05_net": float(np.percentile(net, 5)),
        "p95_net": float(np.percentile(net, 95)),
        "prob_profit": float((net > 1e-9).mean()),
        "prob_ruin": float(np.mean([s.ruined for s in sessions])),
        "prob_target": float(np.mean([s.hit_target for s in sessions])),
        "prob_stop_loss": float(np.mean([s.hit_stop_loss for s in sessions])),
        "avg_hands": float(hands.mean()),
        "avg_bet": float(total_bet / total_hands) if total_hands else 0.0,
        "max_bet": float(max(s.max_bet for s in sessions)),
        "edge_pct": 100 * float(edge),
        "edge_se_pct": 100 * float(edge_se),
        "ev_per_hand": float(ev_hand),
        "sd_per_hand": float(math.sqrt(max(var_hand, 0.0))),
        "avg_max_drawdown": float(dd.mean()),
        "worst_max_drawdown": float(dd.max()),
    }


# ------------------------------------------------------------------- running
def _run_chunk(
    config_data: dict[str, Any], cand_index: int, start: int, stop: int, log_first: bool
) -> tuple[int, int, list[SessionResult]]:
    cfg = ExperimentConfig.from_dict(config_data)
    cand = cfg.candidates[cand_index]
    out = [
        run_session(cfg.rules, cfg.session, cand, i, record_log=log_first and i == 0)
        for i in range(start, stop)
    ]
    return cand_index, start, out


def run_experiment(
    config: ExperimentConfig,
    workers: int | None = 1,
    progress: ProgressFn | None = None,
    log_first_session: bool = True,
    chunk_size: int | None = None,
) -> ExperimentResult:
    """Run every candidate for ``config.session.sessions`` sessions.

    ``workers``: number of processes (``None`` = all CPUs, 1 = in-process).
    ``progress(done, total)`` is called as sessions complete.
    Session ``i`` of every candidate uses the same shoe seed.
    """
    config.validate()
    t0 = time.perf_counter()
    n_sessions = config.session.sessions
    n_cand = len(config.candidates)
    total = n_sessions * n_cand
    workers = (os.cpu_count() or 1) if workers is None else max(1, workers)
    if chunk_size is None:
        chunk_size = max(1, min(50, math.ceil(total / (workers * 8))))

    jobs = [
        (ci, s, min(s + chunk_size, n_sessions))
        for ci in range(n_cand)
        for s in range(0, n_sessions, chunk_size)
    ]
    collected: dict[int, dict[int, list[SessionResult]]] = {ci: {} for ci in range(n_cand)}
    done = 0
    data = config.to_dict()

    if workers == 1:
        for ci, a, b in jobs:
            _, _, res = _run_chunk(data, ci, a, b, log_first_session)
            collected[ci][a] = res
            done += len(res)
            if progress:
                progress(done, total)
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_run_chunk, data, ci, a, b, log_first_session) for ci, a, b in jobs]
            for fut in futures:
                ci, a, res = fut.result()
                collected[ci][a] = res
                done += len(res)
                if progress:
                    progress(done, total)

    results = []
    for ci, cand in enumerate(config.candidates):
        sessions = [s for a in sorted(collected[ci]) for s in collected[ci][a]]
        results.append(CandidateResult(cand, sessions, summarize(sessions)))
    return ExperimentResult(config, results, time.perf_counter() - t0)
