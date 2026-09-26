"""Command line interface.

    python -m blackjack_sim run configs/progressions.json --out results/progressions
    python -m blackjack_sim strategies
    python -m blackjack_sim dealer --decks 6 --h17
    python -m blackjack_sim init my_config.json
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime

from .engine import Rules
from .strategies import BET_STRATEGIES, PLAY_STRATEGIES
from .simulation import ExperimentConfig, dealer_outcomes, run_experiment


def _cmd_run(args: argparse.Namespace) -> int:
    import pandas as pd

    from .simulation.export import write_results

    cfg = ExperimentConfig.load(args.config)
    if args.sessions:
        cfg.session.sessions = args.sessions
    if args.rounds:
        cfg.session.rounds = args.rounds
    total = cfg.session.sessions * len(cfg.candidates)

    def progress(done: int, tot: int) -> None:
        print(f"\r  {done}/{tot} sessions", end="", file=sys.stderr, flush=True)

    print(f"Running {len(cfg.candidates)} candidate(s) x {cfg.session.sessions} sessions "
          f"x {cfg.session.rounds} rounds ({total} sessions)...", file=sys.stderr)
    result = run_experiment(cfg, workers=args.workers, progress=progress)
    print(f"\n  done in {result.elapsed:.1f}s", file=sys.stderr)

    with pd.option_context("display.width", 200, "display.max_columns", 50,
                           "display.float_format", "{:,.3f}".format):
        print(result.summary_frame().T)

    out = args.out or f"results/{datetime.now():%Y%m%d-%H%M%S}"
    write_results(result, out)
    print(f"\nResults written to {out}/")
    return 0


def _cmd_strategies(args: argparse.Namespace) -> int:
    for title, table in (("PLAY STRATEGIES", PLAY_STRATEGIES), ("BET STRATEGIES", BET_STRATEGIES)):
        print(title)
        for cls in table.values():
            print(f"  {cls.key:<14} {cls.label}")
            if cls.description:
                print(f"  {'':<14} {cls.description}")
            for p in cls.params:
                extra = f" choices={list(p.choices)}" if p.choices else ""
                print(f"  {'':<16}- {p.name} ({p.kind.__name__}, default {p.default!r}){extra}: {p.help}")
        print()
    return 0


def _cmd_dealer(args: argparse.Namespace) -> int:
    rules = Rules(num_decks=args.decks, dealer_hits_soft_17=args.h17)
    table = dealer_outcomes(rules, args.trials, args.seed)
    cols = list(next(iter(table.values())))
    print("up   " + "".join(f"{c:>10}" for c in cols))
    for up, row in table.items():
        label = "A" if up == 1 else str(up)
        print(f"{label:<5}" + "".join(f"{100 * row[c]:>9.2f}%" for c in cols))
    return 0


def _cmd_init(args: argparse.Namespace) -> int:
    ExperimentConfig().save(args.path)
    print(f"Wrote default config to {args.path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="blackjack_sim", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run an experiment from a JSON config")
    run.add_argument("config")
    run.add_argument("--out", help="output directory (default: results/<timestamp>)")
    run.add_argument("--workers", type=int, default=None, help="processes (default: all CPUs)")
    run.add_argument("--sessions", type=int, help="override session.sessions")
    run.add_argument("--rounds", type=int, help="override session.rounds")
    run.set_defaults(func=_cmd_run)

    sub.add_parser("strategies", help="list strategies and their parameters").set_defaults(
        func=_cmd_strategies)

    dealer = sub.add_parser("dealer", help="dealer outcome probabilities by upcard")
    dealer.add_argument("--decks", type=int, default=6)
    dealer.add_argument("--h17", action="store_true", help="dealer hits soft 17")
    dealer.add_argument("--trials", type=int, default=100_000)
    dealer.add_argument("--seed", type=int, default=0)
    dealer.set_defaults(func=_cmd_dealer)

    init = sub.add_parser("init", help="write a default config file")
    init.add_argument("path")
    init.set_defaults(func=_cmd_init)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (ValueError, FileNotFoundError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
