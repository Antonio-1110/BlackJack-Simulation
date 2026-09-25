"""Name -> class registry so strategies can be chosen from JSON and the UI.

A strategy spec is a dict: ``{"type": "martingale", "params": {"base_units": 1}}``.
"""

from __future__ import annotations

import random
from typing import Any, TypeVar

from .base import BetStrategy, Configurable, PlayStrategy

PLAY_STRATEGIES: dict[str, type[PlayStrategy]] = {}
BET_STRATEGIES: dict[str, type[BetStrategy]] = {}

T = TypeVar("T", bound=type[Configurable])


def register_play(cls: T) -> T:
    _register(PLAY_STRATEGIES, cls)
    return cls


def register_bet(cls: T) -> T:
    _register(BET_STRATEGIES, cls)
    return cls


def _register(table: dict, cls: type[Configurable]) -> None:
    if not cls.key:
        raise ValueError(f"{cls.__name__} needs a 'key'")
    if cls.key in table:
        raise ValueError(f"duplicate strategy key {cls.key!r}")
    table[cls.key] = cls


def _create(table: dict, kind: str, spec: dict[str, Any] | str, rng: random.Random | None):
    if isinstance(spec, str):
        spec = {"type": spec}
    key = spec.get("type")
    if key not in table:
        raise ValueError(f"Unknown {kind} strategy {key!r}; available: {sorted(table)}")
    return table[key](rng=rng, **(spec.get("params") or {}))


def create_play(spec: dict[str, Any] | str, rng: random.Random | None = None) -> PlayStrategy:
    return _create(PLAY_STRATEGIES, "play", spec, rng)


def create_bet(spec: dict[str, Any] | str, rng: random.Random | None = None) -> BetStrategy:
    return _create(BET_STRATEGIES, "bet", spec, rng)


def default_params(cls: type[Configurable]) -> dict[str, Any]:
    return {p.name: p.default for p in cls.params}


def describe(table: dict[str, type[Configurable]]) -> list[dict[str, Any]]:
    """Machine-readable listing of strategies and their parameters."""
    return [
        {
            "type": cls.key,
            "label": cls.label or cls.key,
            "description": cls.description,
            "params": [
                {
                    "name": p.name,
                    "kind": p.kind.__name__,
                    "default": p.default,
                    "help": p.help,
                    "min": p.min,
                    "max": p.max,
                    "choices": p.choices,
                }
                for p in cls.params
            ],
        }
        for cls in table.values()
    ]
