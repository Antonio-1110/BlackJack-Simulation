"""Basic strategy (multi-deck) with optional Hi-Lo index plays.

The charts are the standard 4-8 deck charts. They adapt to the rule set:
dealer hits/stands on soft 17, double after split and surrender availability.
When a chart action is not allowed (e.g. double on a 3-card hand, or the table
only allows doubling on 10-11) the usual fallback is used: ``D`` -> hit,
``Ds`` -> stand, ``Rh`` -> hit, ``Rs`` -> stand, ``Rp`` -> split.

For 1-2 deck games or exotic rules the chart is close but not exactly optimal.
"""

from __future__ import annotations

from ...engine import HI_LO, Action, Decision
from ..base import Param, PlayStrategy
from ..registry import register_play

_COLUMNS = "2 3 4 5 6 7 8 9 T A"


def _parse(chart: str) -> dict[int, list[str]]:
    rows: dict[int, list[str]] = {}
    for line in chart.strip().splitlines():
        label, cells = line.split(":")
        key = {"A": 1, "T": 10}.get(label.strip(), None)
        rows[key if key is not None else int(label)] = cells.split()
    return rows


# Dealer upcard columns: 2 3 4 5 6 7 8 9 T A
HARD = _parse(
    """
     8: H  H  H  H  H  H  H  H  H  H
     9: H  D  D  D  D  H  H  H  H  H
    10: D  D  D  D  D  D  D  D  H  H
    11: D  D  D  D  D  D  D  D  D  H
    12: H  H  S  S  S  H  H  H  H  H
    13: S  S  S  S  S  H  H  H  H  H
    14: S  S  S  S  S  H  H  H  H  H
    15: S  S  S  S  S  H  H  H  Rh H
    16: S  S  S  S  S  H  H  Rh Rh Rh
    17: S  S  S  S  S  S  S  S  S  S
    """
)

SOFT = _parse(
    """
    12: H  H  H  H  H  H  H  H  H  H
    13: H  H  H  D  D  H  H  H  H  H
    14: H  H  H  D  D  H  H  H  H  H
    15: H  H  D  D  D  H  H  H  H  H
    16: H  H  D  D  D  H  H  H  H  H
    17: H  D  D  D  D  H  H  H  H  H
    18: S  Ds Ds Ds Ds S  S  H  H  H
    19: S  S  S  S  S  S  S  S  S  S
    """
)

# Ph = split only if double after split is allowed, otherwise play as a total.
# "-" = never split, play as a total.
PAIRS = _parse(
    """
     A: P  P  P  P  P  P  P  P  P  P
     T: -  -  -  -  -  -  -  -  -  -
     9: P  P  P  P  P  -  P  P  -  -
     8: P  P  P  P  P  P  P  P  P  P
     7: P  P  P  P  P  P  -  -  -  -
     6: Ph P  P  P  P  -  -  -  -  -
     5: -  -  -  -  -  -  -  -  -  -
     4: -  -  -  Ph Ph -  -  -  -  -
     3: Ph Ph P  P  P  P  -  -  -  -
     2: Ph Ph P  P  P  P  -  -  -  -
    """
)

# Changes when the dealer hits soft 17: (table, total, upcard) -> code
H17_CHANGES = {
    ("hard", 11, 1): "D",
    ("hard", 15, 1): "Rh",
    ("hard", 17, 1): "Rs",
    ("soft", 18, 2): "Ds",
    ("soft", 19, 6): "Ds",
    ("pair", 8, 1): "Rp",
}

# Illustrious 18 (Hi-Lo true count). (total, upcard) -> (index, at_or_above, below)
INDEX_PLAYS = {
    (16, 10): (0, "S", "H"),
    (15, 10): (4, "S", "H"),
    (10, 10): (4, "D", "H"),
    (12, 3): (2, "S", "H"),
    (12, 2): (3, "S", "H"),
    (11, 1): (1, "D", "H"),
    (9, 2): (1, "D", "H"),
    (10, 1): (4, "D", "H"),
    (9, 7): (3, "D", "H"),
    (16, 9): (5, "S", "H"),
    (13, 2): (-1, "S", "H"),
    (12, 4): (0, "S", "H"),
    (12, 5): (-2, "S", "H"),
    (12, 6): (-1, "S", "H"),
    (13, 3): (-2, "S", "H"),
}
PAIR_INDEX_PLAYS = {(10, 5): 5, (10, 6): 4}  # split tens at or above this TC
INSURANCE_INDEX = 3


def _col(up: int) -> int:
    return 9 if up == 1 else up - 2


@register_play
class BasicStrategy(PlayStrategy):
    key = "basic"
    label = "Basic strategy"
    description = (
        "Standard multi-deck basic strategy, adjusted for H17/S17, DAS and surrender. "
        "Optionally adds the Hi-Lo 'Illustrious 18' index plays and insurance at TC >= +3."
    )
    params = (
        Param("deviations", bool, False, "Use Hi-Lo index plays (card counting)."),
    )

    def _code(self, table: str, row: int, up: int, h17: bool) -> str:
        if h17:
            override = H17_CHANGES.get((table, row, up))
            if override:
                return override
        chart = {"hard": HARD, "soft": SOFT, "pair": PAIRS}[table]
        return chart[row][_col(up)]

    def play(self, d: Decision) -> Action:
        hand, up, legal, rules = d.hand, d.dealer_value, d.legal, d.rules
        h17 = rules.dealer_hits_soft_17
        tc = HI_LO.true_count(d.shoe) if self.deviations else 0.0

        if Action.SPLIT in legal:
            pv = hand.pair_value
            code = self._code("pair", pv, up, h17)
            if self.deviations and (pv, up) in PAIR_INDEX_PLAYS and tc >= PAIR_INDEX_PLAYS[(pv, up)]:
                code = "P"
            if code == "P" or (code == "Ph" and rules.double_after_split):
                return Action.SPLIT
            if code == "Rp":
                return Action.SURRENDER if Action.SURRENDER in legal else Action.SPLIT

        total = hand.total
        if hand.is_soft:
            code = "S" if total >= 19 and not (h17 and total == 19 and up == 6) else None
            if code is None:
                code = self._code("soft", min(total, 19), up, h17)
        elif total >= 18:
            code = "S"
        else:
            code = self._code("hard", max(total, 8), up, h17)
            surrendering = code in ("Rh", "Rs") and Action.SURRENDER in legal
            if self.deviations and not surrendering:
                play = INDEX_PLAYS.get((total, up))
                if play and not (h17 and total == 11 and up == 1):
                    index, above, below = play
                    if (total, up) == (10, 1) and h17:
                        index = 3
                    code = above if tc >= index else below
        return _resolve(code, legal)

    def take_insurance(self, d: Decision) -> bool:
        return self.deviations and HI_LO.true_count(d.shoe) >= INSURANCE_INDEX


def _resolve(code: str, legal: tuple[Action, ...]) -> Action:
    if code == "H":
        return Action.HIT
    if code == "S":
        return Action.STAND
    if code == "D":
        return Action.DOUBLE if Action.DOUBLE in legal else Action.HIT
    if code == "Ds":
        return Action.DOUBLE if Action.DOUBLE in legal else Action.STAND
    if code == "Rh":
        return Action.SURRENDER if Action.SURRENDER in legal else Action.HIT
    if code == "Rs":
        return Action.SURRENDER if Action.SURRENDER in legal else Action.STAND
    raise ValueError(f"bad chart code {code!r}")
