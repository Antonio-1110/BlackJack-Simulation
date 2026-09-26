"""Blackjack simulation toolkit.

Layers (each only depends on the ones above it):

* ``engine``      -- cards, rules, hands and the round engine.
* ``strategies``  -- play strategies, bet strategies and their registry.
* ``simulation``  -- sessions, Monte Carlo experiments and statistics.

The Streamlit frontend (``app/``) and the CLI (``python -m blackjack_sim``)
sit on top.
"""

from .engine import Action, Rules, Table, play_round
from .simulation import Candidate, ExperimentConfig, SessionSettings, run_experiment, run_session

__all__ = [
    "Action",
    "Candidate",
    "ExperimentConfig",
    "Rules",
    "SessionSettings",
    "Table",
    "play_round",
    "run_experiment",
    "run_session",
]

__version__ = "0.2.0"
