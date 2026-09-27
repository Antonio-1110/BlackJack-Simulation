"""Reinforcement-learning interface: a Gymnasium environment over the engine.

Needs the optional ``gymnasium`` dependency (``pip install -e ".[rl]"``).
Importing this package registers the env as ``BlackjackSim-v0``::

    import gymnasium as gym
    import blackjack_sim.rl  # noqa: F401

    env = gym.make("BlackjackSim-v0", rules={"surrender": "late"})
"""

from gymnasium.envs.registration import register, registry

from .agents import BasicStrategyAgent, QLearningAgent, RandomAgent, evaluate
from .env import INSURANCE_ACTIONS, PLAY_ACTIONS, BlackjackEnv, encode_decision

ENV_ID = "BlackjackSim-v0"

if ENV_ID not in registry:
    register(id=ENV_ID, entry_point="blackjack_sim.rl.env:BlackjackEnv")

__all__ = [
    "ENV_ID",
    "INSURANCE_ACTIONS",
    "PLAY_ACTIONS",
    "BasicStrategyAgent",
    "BlackjackEnv",
    "QLearningAgent",
    "RandomAgent",
    "encode_decision",
    "evaluate",
]
