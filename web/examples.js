// Starter strategies for the editor. Each one is a complete, runnable module.
window.EXAMPLES = [
  {
    name: "Basic strategy + press when ahead",
    code: `from blackjack_sim.engine import Action
from blackjack_sim.strategies import BetStrategy, Param
from blackjack_sim.strategies.play.basic import BasicStrategy


class MyPlay(BasicStrategy):
    """Basic strategy, except always stand on 16 against a 10."""

    def play(self, d):
        # d.hand.total, d.hand.is_soft, d.dealer_value (1 = Ace), d.legal ...
        if d.hand.total == 16 and not d.hand.is_soft and d.dealer_value == 10:
            return Action.STAND
        return super().play(d)  # everything else: the normal chart


class MyBet(BetStrategy):
    """Bet more while the session is in profit; back to one unit after two losses."""

    params = (
        Param("unit", float, 10.0, "Base bet."),
        Param("press_units", float, 3.0, "Units to bet while in profit."),
    )

    def reset(self):  # runs at the start of every session
        self.losses_in_a_row = 0

    def bet(self, ctx):
        # ctx.bankroll, ctx.profit, ctx.round_index, ctx.shoe ...
        if self.losses_in_a_row >= 2 or ctx.profit <= 0:
            return self.unit
        return self.unit * self.press_units

    def update(self, result):  # runs after every round you played
        self.losses_in_a_row = self.losses_in_a_row + 1 if result.lost else 0
`,
  },
  {
    name: "Dealer bust hunter (play only)",
    code: `from blackjack_sim.engine import Action
from blackjack_sim.strategies import PlayStrategy


class DealerBustHunter(PlayStrategy):
    """Stand early against weak dealer upcards, otherwise draw to 17.

    No bet strategy here, so it bets the table minimum every round."""

    def play(self, d):
        total = d.hand.total
        weak_dealer = 2 <= d.dealer_value <= 6

        if Action.DOUBLE in d.legal and total in (10, 11) and weak_dealer:
            return Action.DOUBLE
        if weak_dealer and total >= 12 and not d.hand.is_soft:
            return Action.STAND
        return Action.HIT if total < 17 else Action.STAND
`,
  },
  {
    name: "Hi-Lo card counting spread",
    code: `import math

from blackjack_sim.engine import HI_LO
from blackjack_sim.strategies import BetStrategy
from blackjack_sim.strategies.play.basic import BasicStrategy


class CountingPlay(BasicStrategy):
    """Basic strategy, and take insurance when the count is high."""

    def take_insurance(self, d):
        return HI_LO.true_count(d.shoe) >= 3


class CountSpread(BetStrategy):
    """Bet 1 to 8 units by the true count; sit out bad shoes."""

    def bet(self, ctx):
        unit = ctx.rules.table_min
        tc = math.floor(HI_LO.true_count(ctx.shoe))
        if tc < -1:
            return 0  # 0 means sit this round out
        return unit * min(8, max(1, tc))
`,
  },
  {
    name: "Martingale (bet only)",
    code: `from blackjack_sim.strategies import BetStrategy


class Martingale(BetStrategy):
    """Double the bet after every loss, go back to one unit after a win.

    Plays basic strategy, since there's no play strategy here."""

    def reset(self):
        self.level = 0

    def bet(self, ctx):
        return ctx.rules.table_min * 2 ** self.level

    def update(self, result):
        if result.won:
            self.level = 0
        elif result.lost:
            self.level += 1
`,
  },
];
