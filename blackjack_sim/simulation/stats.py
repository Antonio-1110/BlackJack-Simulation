"""Confidence intervals and precision estimates for Monte Carlo results.

Pure Python (no numpy), so the browser Strategy Lab can use it inside Pyodide
as well as the numpy-based experiment suite.

All intervals are two-sided at ``Z95`` (95%). Sessions are the independent
samples: rounds within a session share a shoe and a bankroll, so treating
rounds as independent would understate the uncertainty for counting and
progression strategies.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Sequence

if TYPE_CHECKING:
    from .session import SessionResult

Z95 = 1.959963984540054


def _var(xs: Sequence[float]) -> float:
    """Sample variance (n - 1 denominator)."""
    n = len(xs)
    m = sum(xs) / n
    return sum((x - m) ** 2 for x in xs) / (n - 1)


def ratio_se(num: Sequence[float], den: Sequence[float]) -> float | None:
    """Standard error of ``sum(num) / sum(den)`` with per-session pairs as
    samples (the delta-method ratio estimator). ``None`` if undefined."""
    n = len(num)
    total = sum(den)
    if n < 2 or not total:
        return None
    r = sum(num) / total
    resid = [x - r * d for x, d in zip(num, den)]
    return math.sqrt(_var(resid)) / ((total / n) * math.sqrt(n))


def wilson(successes: int, n: int, z: float = Z95) -> tuple[float, float]:
    """Wilson score interval for a proportion. Unlike the textbook
    ``p ± z·sqrt(p(1-p)/n)`` it stays inside [0, 1] and is sensible when
    ``p`` is 0 or 1 (e.g. no session was ruined)."""
    if n <= 0:
        return (0.0, 1.0)
    p = successes / n
    z2 = z * z
    denom = 1 + z2 / n
    centre = (p + z2 / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def sessions_needed(n: int, se: float | None, target_se: float) -> int | None:
    """Sessions needed for the standard error to shrink to ``target_se``,
    given ``se`` measured from ``n`` sessions (SE scales as 1/sqrt(n))."""
    if se is None or target_se <= 0 or n < 1:
        return None
    return max(n, math.ceil(n * (se / target_se) ** 2))


def interval_stats(sessions: Sequence[SessionResult]) -> dict[str, float | None]:
    """Standard errors and 95% intervals for the headline numbers.

    Keys (``None`` when undefined, i.e. fewer than two sessions):

    * ``edge_ci_low_pct`` / ``edge_ci_high_pct``: player edge (return per unit
      initially bet).
    * ``ev_per_hand_se``, ``ev_per_hand_ci_low`` / ``_high``: profit per hand.
    * ``mean_net_se``, ``mean_net_ci_low`` / ``_high``: profit per session.
    * ``prob_profit_ci_low`` / ``_high``, ``prob_ruin_ci_low`` / ``_high``:
      Wilson intervals.
    * ``sessions_for_0_1pct``: sessions needed to pin the edge down to a
      standard error of 0.1 percentage points.
    """
    n = len(sessions)
    net = [s.net for s in sessions]
    bets = [s.initial_bet_total for s in sessions]
    hands = [float(s.hands) for s in sessions]
    out: dict[str, float | None] = {}

    def interval(key: str, estimate: float | None, se: float | None, scale: float = 1.0,
                 suffix: str = "") -> None:
        ok = se is not None and estimate is not None
        out[f"{key}_ci_low{suffix}"] = scale * (estimate - Z95 * se) if ok else None
        out[f"{key}_ci_high{suffix}"] = scale * (estimate + Z95 * se) if ok else None

    total_bet = sum(bets)
    edge = sum(net) / total_bet if total_bet else None
    edge_se = ratio_se(net, bets)
    interval("edge", edge, edge_se, 100.0, "_pct")

    total_hands = sum(hands)
    ev = sum(net) / total_hands if total_hands else None
    ev_se = ratio_se(net, hands)
    out["ev_per_hand_se"] = ev_se
    interval("ev_per_hand", ev, ev_se)

    mean_net = sum(net) / n if n else None
    mean_se = math.sqrt(_var(net) / n) if n > 1 else None
    out["mean_net_se"] = mean_se
    interval("mean_net", mean_net, mean_se)

    for key, hits in (
        ("prob_profit", sum(x > 1e-9 for x in net)),
        ("prob_ruin", sum(s.ruined for s in sessions)),
    ):
        lo, hi = wilson(hits, n)
        out[f"{key}_ci_low"], out[f"{key}_ci_high"] = lo, hi

    out["sessions_for_0_1pct"] = sessions_needed(
        n, None if edge_se is None else 100 * edge_se, 0.1
    )
    return out


def paired_edge_difference(
    a: Sequence[SessionResult], b: Sequence[SessionResult]
) -> dict[str, float | None]:
    """Edge of ``a`` minus edge of ``b``, in percentage points, with a 95%
    interval that uses the pairing of session ``i`` in ``a`` with session
    ``i`` in ``b``.

    Candidates in an experiment (and "your strategy" vs the baseline in the
    Strategy Lab) play session ``i`` on the same shoe seed, so their results
    are positively correlated and most of the card luck cancels in the
    difference. The paired interval is therefore usually much narrower than
    comparing the two separate edge intervals, so a real difference shows up
    with far fewer sessions.
    """
    if len(a) != len(b):
        raise ValueError("paired comparison needs the same number of sessions")
    n = len(a)
    bets_a = [s.initial_bet_total for s in a]
    bets_b = [s.initial_bet_total for s in b]
    tot_a, tot_b = sum(bets_a), sum(bets_b)
    if not n or not tot_a or not tot_b:
        return {"diff_pct": None, "diff_se_pct": None, "diff_ci_low_pct": None,
                "diff_ci_high_pct": None, "correlation": None}
    ra = sum(s.net for s in a) / tot_a
    rb = sum(s.net for s in b) / tot_b
    mean_a, mean_b = tot_a / n, tot_b / n
    # Linearised per-session contributions of each ratio estimator.
    ua = [(s.net - ra * x) / mean_a for s, x in zip(a, bets_a)]
    ub = [(s.net - rb * x) / mean_b for s, x in zip(b, bets_b)]
    diff = ra - rb
    if n < 2:
        se = corr = None
    else:
        se = math.sqrt(_var([x - y for x, y in zip(ua, ub)]) / n)
        va, vb = _var(ua), _var(ub)
        ma, mb = sum(ua) / n, sum(ub) / n
        cov = sum((x - ma) * (y - mb) for x, y in zip(ua, ub)) / (n - 1)
        corr = cov / math.sqrt(va * vb) if va > 0 and vb > 0 else None
    return {
        "diff_pct": 100 * diff,
        "diff_se_pct": None if se is None else 100 * se,
        "diff_ci_low_pct": None if se is None else 100 * (diff - Z95 * se),
        "diff_ci_high_pct": None if se is None else 100 * (diff + Z95 * se),
        "correlation": corr,
    }
