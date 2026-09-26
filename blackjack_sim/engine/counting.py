"""Card counting systems.

A count is derived from the shoe's record of *seen* cards, so any number of
systems can be read at any time without strategies having to watch the deal
themselves.
"""

from __future__ import annotations

from dataclasses import dataclass

from .cards import Shoe


@dataclass(frozen=True)
class CountSystem:
    name: str
    tags: tuple[float, ...]  # tag for card value 1 (Ace) .. 10
    balanced: bool = True

    def running_count(self, shoe: Shoe) -> float:
        seen = shoe.seen
        return sum(self.tags[v - 1] * seen[v] for v in range(1, 11))

    def true_count(self, shoe: Shoe) -> float:
        """Running count per remaining deck (balanced systems only make sense)."""
        return self.running_count(shoe) / shoe.decks_remaining


#                   A   2    3    4    5    6    7    8    9   10
HI_LO = CountSystem("Hi-Lo", (-1, 1, 1, 1, 1, 1, 0, 0, 0, -1))
HI_OPT_I = CountSystem("Hi-Opt I", (0, 0, 1, 1, 1, 1, 0, 0, 0, -1))
HI_OPT_II = CountSystem("Hi-Opt II", (0, 1, 1, 2, 2, 1, 1, 0, 0, -2))
OMEGA_II = CountSystem("Omega II", (0, 1, 1, 2, 2, 2, 1, 0, -1, -2))
ZEN = CountSystem("Zen", (-1, 1, 1, 2, 2, 2, 1, 0, 0, -2))
WONG_HALVES = CountSystem("Wong Halves", (-1, 0.5, 1, 1, 1.5, 1, 0.5, 0, -0.5, -1))
KO = CountSystem("KO", (-1, 1, 1, 1, 1, 1, 1, 0, 0, -1), balanced=False)

SYSTEMS: dict[str, CountSystem] = {
    s.name.lower().replace(" ", "_").replace("-", "_"): s
    for s in (HI_LO, HI_OPT_I, HI_OPT_II, OMEGA_II, ZEN, WONG_HALVES, KO)
}


def get_system(name: str) -> CountSystem:
    key = name.lower().replace(" ", "_").replace("-", "_")
    try:
        return SYSTEMS[key]
    except KeyError:
        raise ValueError(f"Unknown count system {name!r}; choose from {sorted(SYSTEMS)}") from None
