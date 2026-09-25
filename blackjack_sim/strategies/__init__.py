"""Play and betting strategies, plus the registry that builds them from config."""

from .base import BetContext, BetStrategy, Param, PlayStrategy
from .registry import (
    BET_STRATEGIES,
    PLAY_STRATEGIES,
    create_bet,
    create_play,
    default_params,
    describe,
    register_bet,
    register_play,
)

# Importing the modules registers the built-in strategies.
from .play import basic, simple  # noqa: E402,F401
from .betting import counting, progressions  # noqa: E402,F401

__all__ = [
    "BET_STRATEGIES",
    "BetContext",
    "BetStrategy",
    "PLAY_STRATEGIES",
    "Param",
    "PlayStrategy",
    "create_bet",
    "create_play",
    "default_params",
    "describe",
    "register_bet",
    "register_play",
]
