"""Table rules.

Every house-rule variation lives here as data, so the engine never needs to be
edited to try a different game. Add a new field here, read it in
:mod:`blackjack_sim.engine.table`, and it becomes configurable from JSON and
the frontend automatically.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Any

DOUBLE_OPTIONS = ("any", "9-11", "10-11")
SURRENDER_OPTIONS = ("none", "late")


@dataclass(frozen=True)
class Rules:
    # Shoe
    num_decks: int = 6
    penetration: float = 0.75
    burn_cards: int = 1
    continuous_shuffle: bool = False

    # Dealer
    dealer_hits_soft_17: bool = False
    dealer_peeks: bool = True
    """US hole-card game. If False (European no-hole-card), the dealer's second
    card is drawn after the players act, and a dealer blackjack takes doubles
    and splits too unless ``no_peek_original_bets_only`` is set."""
    no_peek_original_bets_only: bool = False

    # Payouts
    blackjack_payout: float = 1.5
    insurance: bool = True

    # Player options
    double_on: str = "any"
    double_after_split: bool = True
    max_split_hands: int = 4
    resplit_aces: bool = False
    hit_split_aces: bool = False
    surrender: str = "none"
    charlie_cards: int = 0
    """If > 0, a hand reaching this many cards without busting wins
    automatically (e.g. 5 = "five card Charlie"). 0 disables it."""

    # Limits
    table_min: float = 10.0
    table_max: float = 1000.0

    def __post_init__(self) -> None:
        errors = []
        if self.num_decks < 1:
            errors.append("num_decks must be >= 1")
        if not 0.1 <= self.penetration <= 1.0:
            errors.append("penetration must be between 0.1 and 1.0")
        if self.double_on not in DOUBLE_OPTIONS:
            errors.append(f"double_on must be one of {DOUBLE_OPTIONS}")
        if self.surrender not in SURRENDER_OPTIONS:
            errors.append(f"surrender must be one of {SURRENDER_OPTIONS}")
        if self.max_split_hands < 1:
            errors.append("max_split_hands must be >= 1 (1 disables splitting)")
        if self.charlie_cards and self.charlie_cards < 3:
            errors.append("charlie_cards must be 0 (off) or >= 3")
        if self.blackjack_payout <= 0:
            errors.append("blackjack_payout must be positive")
        if self.table_min <= 0 or self.table_max < self.table_min:
            errors.append("need 0 < table_min <= table_max")
        if errors:
            raise ValueError("Invalid rules: " + "; ".join(errors))

    def can_double_total(self, total: int, soft: bool) -> bool:
        if self.double_on == "any":
            return True
        if soft:
            return False
        if self.double_on == "9-11":
            return 9 <= total <= 11
        return 10 <= total <= 11

    # ----------------------------------------------------------- (de)serialise
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "Rules":
        data = dict(data or {})
        known = {f.name for f in fields(cls)}
        unknown = set(data) - known
        if unknown:
            raise ValueError(f"Unknown rule(s): {sorted(unknown)}")
        return cls(**data)
