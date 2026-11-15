"""Measure simulation throughput (rounds per second) for a few typical setups.

    python scripts/benchmark.py            # quick run
    python scripts/benchmark.py --rounds 200000 --json out.json

Each case runs single sessions in-process (one core), which is also how the
browser Strategy Lab runs them. A checksum of every session's final bankroll is
printed so you can confirm an optimisation did not change any results.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from blackjack_sim.engine import Rules  # noqa: E402
from blackjack_sim.simulation import Candidate, SessionSettings, run_session  # noqa: E402

CASES = {
    "basic_flat": Candidate("basic", play={"type": "basic"}, bet={"type": "flat"}),
    "basic_deviations_hilo": Candidate(
        "counter",
        play={"type": "basic", "params": {"deviations": True}},
        bet={"type": "count_spread"},
    ),
    "basic_flat_3_others": Candidate("crowded", play={"type": "basic"}, bet={"type": "flat"}),
}


def run_case(name: str, cand: Candidate, rounds: int, sessions: int, repeat: int = 1) -> dict:
    """Best of ``repeat`` timings (the least disturbed by other processes)."""
    runs = [_run_case(name, cand, rounds, sessions) for _ in range(repeat)]
    return min(runs, key=lambda r: r["seconds"])


def _run_case(name: str, cand: Candidate, rounds: int, sessions: int) -> dict:
    rules = Rules(table_max=10_000)
    others = 3 if name.endswith("others") else 0
    settings = SessionSettings(
        rounds=rounds // sessions, sessions=sessions, bankroll=1e9, other_players=others, seed=7
    )
    digest = hashlib.sha256()
    played = 0
    t0 = time.perf_counter()
    for i in range(sessions):
        res = run_session(rules, settings, cand, i)
        played += res.rounds
        digest.update(repr((res.final, res.hands, res.wagered_total)).encode())
    dt = time.perf_counter() - t0
    return {"case": name, "rounds": played, "seconds": round(dt, 3),
            "rounds_per_sec": round(played / dt), "checksum": digest.hexdigest()[:16]}


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--rounds", type=int, default=100_000, help="rounds per case")
    ap.add_argument("--sessions", type=int, default=20)
    ap.add_argument("--repeat", type=int, default=3, help="report the best of N runs")
    ap.add_argument("--case", choices=sorted(CASES), action="append")
    ap.add_argument("--json", help="also write results to this file")
    args = ap.parse_args(argv)

    out = []
    for name in args.case or CASES:
        r = run_case(name, CASES[name], args.rounds, args.sessions, args.repeat)
        out.append(r)
        print(f"{r['case']:<24} {r['rounds_per_sec']:>9,} rounds/s  "
              f"({r['rounds']:,} rounds in {r['seconds']}s)  checksum {r['checksum']}")
    if args.json:
        Path(args.json).write_text(json.dumps(out, indent=2) + "\n")


if __name__ == "__main__":
    main()
