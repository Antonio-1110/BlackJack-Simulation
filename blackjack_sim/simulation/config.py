"""Experiment configuration (plain dataclasses <-> JSON)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ..engine import Rules
from ..strategies import create_bet, create_play


@dataclass
class Candidate:
    """One player profile to evaluate: a play strategy plus a bet strategy."""

    name: str
    play: dict[str, Any] = field(default_factory=lambda: {"type": "basic", "params": {}})
    bet: dict[str, Any] = field(default_factory=lambda: {"type": "flat", "params": {}})

    def validate(self) -> None:
        # Building the objects runs the parameter validation.
        create_play(self.play)
        create_bet(self.bet)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Candidate":
        return cls(
            name=data["name"],
            play=_spec(data.get("play", "basic")),
            bet=_spec(data.get("bet", "flat")),
        )


@dataclass
class SessionSettings:
    rounds: int = 1000
    """Maximum rounds per session."""
    sessions: int = 500
    """Independent sessions (Monte Carlo repetitions) per candidate."""
    bankroll: float = 1000.0
    stop_loss: float = 0.0
    """Stop a session once down this much (0 = off). Running out of money
    (bankroll below the table minimum) always ends a session."""
    win_target: float = 0.0
    """Stop a session once up this much (0 = off)."""
    other_players: int = 0
    """Extra seats playing flat-minimum basic strategy. They only use up cards."""
    seed: int = 12345

    def validate(self) -> None:
        if self.rounds < 1 or self.sessions < 1:
            raise ValueError("rounds and sessions must be >= 1")
        if self.bankroll <= 0:
            raise ValueError("bankroll must be positive")
        if self.stop_loss < 0 or self.win_target < 0:
            raise ValueError("stop_loss and win_target must be >= 0 (0 = off)")
        if not 0 <= self.other_players <= 6:
            raise ValueError("other_players must be between 0 and 6")


@dataclass
class ExperimentConfig:
    rules: Rules = field(default_factory=Rules)
    session: SessionSettings = field(default_factory=SessionSettings)
    candidates: list[Candidate] = field(default_factory=lambda: [Candidate("Flat")])

    def validate(self) -> "ExperimentConfig":
        self.session.validate()
        if not self.candidates:
            raise ValueError("need at least one candidate")
        names = [c.name for c in self.candidates]
        if len(set(names)) != len(names):
            raise ValueError(f"candidate names must be unique: {names}")
        for c in self.candidates:
            try:
                c.validate()
            except ValueError as e:
                raise ValueError(f"candidate {c.name!r}: {e}") from None
        return self

    # ------------------------------------------------------------------- JSON
    def to_dict(self) -> dict[str, Any]:
        return {
            "rules": self.rules.to_dict(),
            "session": asdict(self.session),
            "candidates": [asdict(c) for c in self.candidates],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExperimentConfig":
        unknown = set(data) - {"rules", "session", "candidates"}
        if unknown:
            raise ValueError(f"Unknown config section(s): {sorted(unknown)}")
        session_data = data.get("session") or {}
        known = set(SessionSettings.__dataclass_fields__)
        bad = set(session_data) - known
        if bad:
            raise ValueError(f"Unknown session setting(s): {sorted(bad)}")
        return cls(
            rules=Rules.from_dict(data.get("rules")),
            session=SessionSettings(**session_data),
            candidates=[Candidate.from_dict(c) for c in data.get("candidates", [])]
            or [Candidate("Flat")],
        ).validate()

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2) + "\n")

    @classmethod
    def load(cls, path: str | Path) -> "ExperimentConfig":
        return cls.from_dict(json.loads(Path(path).read_text()))


def _spec(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        return {"type": value, "params": {}}
    return {"type": value["type"], "params": dict(value.get("params") or {})}
