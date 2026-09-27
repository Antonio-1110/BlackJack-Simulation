"""Train a tabular agent on BlackjackEnv and compare it with basic strategy.

    python scripts/rl_vs_basic.py                     # defaults
    python scripts/rl_vs_basic.py --train 2000000 --eval 500000 --rules '{"surrender": "late"}'

Every agent is evaluated from the same seed (the rounds diverge once their
choices differ). The learned agent sees only the classic basic-strategy
inputs (total, soft, pair, upcard, first two cards, split hand), so with
enough training it should approach basic strategy from below.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # run without installing

from blackjack_sim.rl import BasicStrategyAgent, BlackjackEnv, QLearningAgent, RandomAgent, evaluate  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--train", type=int, default=500_000, help="training rounds for the learned agent")
    ap.add_argument("--eval", type=int, default=200_000, help="evaluation rounds per agent")
    ap.add_argument("--epsilon", type=float, default=0.1)
    ap.add_argument("--rules", type=json.loads, default=None, help="Rules overrides as JSON")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    env = BlackjackEnv(rules=args.rules)
    agent = QLearningAgent(env.action_space.n, epsilon=args.epsilon, seed=args.seed)
    t = time.perf_counter()
    agent.train(env, args.train, seed=args.seed)
    print(f"trained on {args.train:,} rounds in {time.perf_counter() - t:.0f}s ({len(agent.q):,} states)")

    agents = {
        "basic strategy": BasicStrategyAgent(env),
        "learned (Monte Carlo)": agent,
        "random legal": RandomAgent(args.seed),
    }
    print(f"\nedge per round, {args.eval:,} rounds each, same seed:")
    for name, a in agents.items():
        print(f"  {name:<22} {evaluate(a, env, args.eval, seed=args.seed + 1)}")

    # Where does the learned agent disagree with the chart on common hands?
    basic = BasicStrategyAgent(env)
    disagree = total = 0
    obs, info = env.reset(seed=args.seed + 2)
    for _ in range(20_000):
        done = False
        while not done:
            b = basic.act(obs, info)
            if env.decision is not None and len(env.decision.legal) > 1:
                total += 1
                disagree += agent.act(obs, info) != b
            obs, _, done, _, info = env.step(b)
        obs, info = env.reset()
    print(f"\nlearned agent agrees with basic strategy on {100 * (1 - disagree / total):.1f}% "
          f"of {total:,} decisions")


if __name__ == "__main__":
    main()
