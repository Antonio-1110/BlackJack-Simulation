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
        # Unrolled (same order of additions as a sum() over values 1..10, so
        # results are bit-identical): this runs several times per round.
        t, s = self.tags, shoe.seen
        return (
            0 + t[0] * s[1] + t[1] * s[2] + t[2] * s[3] + t[3] * s[4] + t[4] * s[5]
            + t[5] * s[6] + t[6] * s[7] + t[7] * s[8] + t[8] * s[9] + t[9] * s[10]
        )

    def true_count(self, shoe: Shoe) -> float:
        """Running count per remaining deck (balanced systems only make sense)."""
        unseen = shoe.total_cards - shoe.seen_total
        return self.running_count(shoe) / ((unseen if unseen > 1 else 1) / 52.0)


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
