"""Run strategy code typed into the browser playground (``web/``).

The playground page runs this module inside Pyodide (Python compiled to
WebAssembly), so the user's code runs in their own browser and never on a
server. It only uses the engine, the strategies and single sessions, all pure
Python, so the page doesn't have to download numpy.

The user's code is an ordinary Python module: it defines a ``PlayStrategy``
subclass, a ``BetStrategy`` subclass, or both. Whatever it leaves out falls
back to basic strategy and a flat bet of the table minimum.
"""

from __future__ import annotations

import inspect
import linecache
import math
import sys
import traceback
import types
from typing import Any, Callable

from .engine import Rules
from .simulation.config import Candidate, SessionSettings
from .simulation.session import SessionResult, run_session
from .strategies import BET_STRATEGIES, PLAY_STRATEGIES, BetStrategy, PlayStrategy

USER_MODULE = "user_strategy"
USER_FILE = "<your code>"
USER_PLAY_KEY = "__user_play__"
USER_BET_KEY = "__user_bet__"
YOURS = "Your strategy"
BASELINE = "Basic strategy, flat bet"
MAX_POINTS = 400  # bankroll chart resolution
SAMPLE_PATHS = 10
LOG_ROWS = 300

ProgressFn = Callable[[int, int], None]

# The registries as they are with only the built-in strategies, so each run
# starts clean even if earlier code used @register_play / @register_bet.
_BUILTIN_PLAY = dict(PLAY_STRATEGIES)
_BUILTIN_BET = dict(BET_STRATEGIES)


class StrategyError(Exception):
    """A problem in the user's code, with a traceback trimmed to their lines."""


def run(code: str, settings: dict[str, Any], progress: ProgressFn | None = None) -> dict[str, Any]:
    """Load ``code``, play the sessions and return JSON-ready results.

    ``settings`` has ``rules`` (``Rules`` fields), ``session``
    (``SessionSettings`` fields) and ``compare`` (also run the baseline).
    """
    rules = Rules.from_dict(settings.get("rules"))
    session = SessionSettings(**(settings.get("session") or {}))
    session.validate()

    play_cls, bet_cls = load_strategies(code)
    yours = Candidate(
        YOURS,
        play={"type": USER_PLAY_KEY} if play_cls else {"type": "basic"},
        bet={"type": USER_BET_KEY} if bet_cls else _flat(rules),
    )
    candidates = [yours]
    if settings.get("compare", True):
        candidates.append(Candidate(BASELINE, play={"type": "basic"}, bet=_flat(rules)))
    for c in candidates:
        _user_errors(c.validate)

    total = session.sessions * len(candidates)
    done = 0
    out = []
    for ci, cand in enumerate(candidates):
        sessions = []
        for i in range(session.sessions):
            sessions.append(
                _user_errors(run_session, rules, session, cand, i, record_log=ci == 0 and i == 0)
            )
            done += 1
            if progress and (done % 5 == 0 or done == total):
                progress(done, total)
        out.append(_candidate_result(cand, sessions, session.rounds))

    return {
        "candidates": out,
        "play": play_cls.__name__ if play_cls else None,
        "bet": bet_cls.__name__ if bet_cls else None,
        "log": out[0].pop("log"),
    }


# ---------------------------------------------------------------- user code
def load_strategies(code: str) -> tuple[type[PlayStrategy] | None, type[BetStrategy] | None]:
    """Execute the user's code and register the strategies it defines."""
    PLAY_STRATEGIES.clear()
    PLAY_STRATEGIES.update(_BUILTIN_PLAY)
    BET_STRATEGIES.clear()
    BET_STRATEGIES.update(_BUILTIN_BET)

    module = types.ModuleType(USER_MODULE)
    module.__file__ = USER_FILE
    sys.modules[USER_MODULE] = module
    # Lets tracebacks quote the user's lines.
    linecache.cache[USER_FILE] = (len(code), None, code.splitlines(True), USER_FILE)
    try:
        compiled = compile(code, USER_FILE, "exec")
    except SyntaxError as e:
        raise StrategyError(_format_syntax_error(e)) from None
    _user_errors(exec, compiled, module.__dict__)

    play_cls = _pick(module, PlayStrategy, "PLAY", "play")
    bet_cls = _pick(module, BetStrategy, "BET", "bet")
    if play_cls is None and bet_cls is None:
        raise StrategyError(
            "Your code doesn't define a strategy. Write a class that extends "
            "PlayStrategy (or BasicStrategy) and/or BetStrategy."
        )
    for cls in (play_cls, bet_cls):
        if cls is not None and "key" not in cls.__dict__:
            cls.key = cls.__name__  # names it in error messages
    if play_cls:
        PLAY_STRATEGIES[USER_PLAY_KEY] = play_cls
    if bet_cls:
        BET_STRATEGIES[USER_BET_KEY] = bet_cls
    return play_cls, bet_cls


def _pick(module: types.ModuleType, base: type, override: str, kind: str):
    chosen = module.__dict__.get(override)
    if chosen is not None:
        if not (inspect.isclass(chosen) and issubclass(chosen, base)):
            raise StrategyError(f"{override} must be a {base.__name__} subclass")
        return chosen
    found = [
        obj
        for obj in module.__dict__.values()
        if inspect.isclass(obj)
        and issubclass(obj, base)
        and obj.__module__ == USER_MODULE
        and not inspect.isabstract(obj)
    ]
    if len(found) > 1:
        names = ", ".join(c.__name__ for c in found)
        raise StrategyError(
            f"Your code defines several {kind} strategies ({names}). "
            f"Pick one by adding a line like: {override} = {found[-1].__name__}"
        )
    return found[0] if found else None


def _user_errors(fn, *args, **kwargs):
    """Call ``fn`` and turn any exception into a StrategyError showing only the
    frames from the user's code (the engine's internals are noise to them)."""
    try:
        return fn(*args, **kwargs)
    except StrategyError:
        raise
    except Exception as e:
        frames = [f for f in traceback.extract_tb(e.__traceback__) if f.filename == USER_FILE]
        lines = []
        if frames:
            lines.append("Traceback (your code only):\n")
            lines += traceback.format_list(frames)
        lines += traceback.format_exception_only(type(e), e)
        raise StrategyError("".join(lines).rstrip()) from None


def _format_syntax_error(e: SyntaxError) -> str:
    return "".join(traceback.format_exception_only(type(e), e)).rstrip()


def _flat(rules: Rules) -> dict[str, Any]:
    return {"type": "flat", "params": {"unit": rules.table_min, "units": 1}}


# ------------------------------------------------------------------ results
def _candidate_result(cand: Candidate, sessions: list[SessionResult], rounds: int) -> dict[str, Any]:
    return {
        "name": cand.name,
        "summary": summary(sessions),
        "bands": bankroll_bands(sessions, rounds),
        "samples": [_downsample(s.path, rounds) for s in sessions[:SAMPLE_PATHS]],
        "nets": [s.net for s in sessions],
        "log": (sessions[0].log or [])[:LOG_ROWS],
    }


def summary(sessions: list[SessionResult]) -> dict[str, float | None]:
    """The headline numbers. Same definitions as ``simulation.summarize``
    (which needs numpy); a test keeps the two in step."""
    n = len(sessions)
    net = [s.net for s in sessions]
    bets = [s.initial_bet_total for s in sessions]
    hands = sum(s.hands for s in sessions)
    total_bet = sum(bets)
    edge = sum(net) / total_bet if total_bet else 0.0
    if n > 1 and total_bet:
        resid = [x - edge * b for x, b in zip(net, bets)]
        edge_se = _std(resid) / ((total_bet / n) * math.sqrt(n))
    else:
        edge_se = None  # undefined with a single session
    ordered = sorted(net)
    return {
        "sessions": n,
        "mean_net": sum(net) / n,
        "median_net": _percentile(ordered, 50),
        "p05_net": _percentile(ordered, 5),
        "p95_net": _percentile(ordered, 95),
        "prob_profit": sum(x > 1e-9 for x in net) / n,
        "prob_ruin": sum(s.ruined for s in sessions) / n,
        "prob_target": sum(s.hit_target for s in sessions) / n,
        "prob_stop_loss": sum(s.hit_stop_loss for s in sessions) / n,
        "avg_hands": hands / n,
        "avg_bet": total_bet / hands if hands else 0.0,
        "edge_pct": 100 * edge,
        "edge_se_pct": None if edge_se is None else 100 * edge_se,
        "ev_per_hand": sum(net) / hands if hands else 0.0,
        "avg_max_drawdown": sum(s.max_drawdown for s in sessions) / n,
        "start": sessions[0].start,
        "mean_final": sum(s.final for s in sessions) / n,
    }


def bankroll_bands(sessions: list[SessionResult], rounds: int) -> dict[str, list[float]]:
    """Per-round bankroll percentiles across sessions, at up to MAX_POINTS
    rounds. A session that stopped early keeps its final bankroll."""
    idx = _indices(rounds)
    bands: dict[str, list[float]] = {"round": idx, "p05": [], "p25": [], "p50": [], "p75": [], "p95": [], "mean": []}
    for r in idx:
        col = sorted(s.path[min(r, len(s.path) - 1)] for s in sessions)
        for p in (5, 25, 50, 75, 95):
            bands[f"p{p:02d}"].append(_percentile(col, p))
        bands["mean"].append(sum(col) / len(col))
    return bands


def _indices(rounds: int) -> list[int]:
    if rounds <= MAX_POINTS:
        return list(range(rounds + 1))
    step = rounds / MAX_POINTS
    return sorted({round(i * step) for i in range(MAX_POINTS)} | {rounds})


def _downsample(path: list[float], rounds: int) -> list[float]:
    return [path[min(r, len(path) - 1)] for r in _indices(rounds)]


def _percentile(ordered: list[float], p: float) -> float:
    """Linear interpolation, like numpy's default."""
    k = (len(ordered) - 1) * p / 100
    lo = math.floor(k)
    hi = min(lo + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


def _std(xs: list[float]) -> float:
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))
