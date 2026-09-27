"""Small reference agents for :class:`BlackjackEnv`.

An agent is anything with ``act(obs, info) -> int``. These are baselines and a
worked example, not a training framework: plug the env into Stable-Baselines3,
CleanRL, etc. for serious work.
"""

from __future__ import annotations

import math
import random
from collections import defaultdict
from dataclasses import dataclass

import numpy as np

from ..strategies.play.basic import BasicStrategy
from .env import BlackjackEnv


class RandomAgent:
    """Uniformly random over the legal actions."""

    def __init__(self, seed: int | None = None) -> None:
        self.rng = np.random.default_rng(seed)

    def act(self, obs: dict, info: dict) -> int:
        return int(self.rng.choice(np.flatnonzero(info["action_mask"])))


class BasicStrategyAgent:
    """The repo's :class:`BasicStrategy`, acting through the env.

    It reads the engine :class:`Decision` the env is waiting on, so it plays
    exactly as it does in the experiment suite. That makes it the yardstick
    for learned agents and a cross-check of the env against the simulator.
    """

    def __init__(self, env: BlackjackEnv, deviations: bool = False) -> None:
        self.env = env
        self.strategy = BasicStrategy(deviations=deviations)

    def act(self, obs: dict, info: dict) -> int:
        env = self.env.unwrapped
        if env.decision is None:  # round already over
            return int(np.flatnonzero(info["action_mask"])[0])
        return env.actions.index(self.strategy(env.decision))


def state_key(obs: dict) -> tuple:
    """Discrete state for tabular learning: the classic basic-strategy inputs."""
    return (
        int(obs["player_total"]),
        int(obs["soft"]),
        int(obs["pair"]),
        int(obs["dealer_upcard"]),
        int(obs["num_cards"]) == 2,
        int(obs["num_hands"]) > 1,
    )


class QLearningAgent:
    """Tabular every-visit Monte Carlo control with epsilon-greedy exploration.

    Episodes are short and the reward only arrives at the end, so the return
    of every (state, action) in an episode is just the episode's reward.
    Illegal actions are never chosen: exploration and the greedy choice both
    respect the action mask.
    """

    def __init__(self, n_actions: int, epsilon: float = 0.1, seed: int | None = None) -> None:
        self.n_actions = n_actions
        self.epsilon = epsilon
        self.rng = random.Random(seed)
        self.q: dict[tuple, np.ndarray] = defaultdict(lambda: np.zeros(n_actions))
        self.n: dict[tuple, np.ndarray] = defaultdict(lambda: np.zeros(n_actions))
        self.training = True

    def act(self, obs: dict, info: dict) -> int:
        legal = np.flatnonzero(info["action_mask"])
        if self.training and self.rng.random() < self.epsilon:
            return int(self.rng.choice(legal))
        q = self.q[state_key(obs)]
        return int(legal[np.argmax(q[legal])])

    def learn(self, trajectory: list[tuple[tuple, int]], ret: float) -> None:
        for key, action in trajectory:
            self.n[key][action] += 1
            self.q[key][action] += (ret - self.q[key][action]) / self.n[key][action]

    def train(self, env, episodes: int, seed: int | None = None) -> None:
        self.training = True
        obs, info = env.reset(seed=seed)
        for _ in range(episodes):
            trajectory, ret, done = [], 0.0, False
            while not done:
                a = self.act(obs, info)
                trajectory.append((state_key(obs), a))
                obs, r, term, trunc, info = env.step(a)
                ret += r
                done = term or trunc
            self.learn(trajectory, ret)
            obs, info = env.reset()
        self.training = False


@dataclass
class Evaluation:
    episodes: int
    mean: float
    stderr: float

    def __str__(self) -> str:
        return f"{self.mean * 100:+.2f}% ± {self.stderr * 100:.2f}% per round ({self.episodes:,} rounds)"


def evaluate(agent, env, episodes: int, seed: int | None = None) -> Evaluation:
    """Average episode return (the edge, in units of the initial bet)."""
    returns = np.empty(episodes)
    obs, info = env.reset(seed=seed)
    for i in range(episodes):
        ret, done = 0.0, False
        while not done:
            obs, r, term, trunc, info = env.step(agent.act(obs, info))
            ret += r
            done = term or trunc
        returns[i] = ret
        obs, info = env.reset()
    return Evaluation(episodes, float(returns.mean()), float(returns.std(ddof=1) / math.sqrt(episodes)))
