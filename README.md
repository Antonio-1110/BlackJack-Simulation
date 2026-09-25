# Blackjack Simulation

A blackjack engine plus a Monte Carlo suite for testing **play strategies** (how you
play a hand) and **bet-sizing strategies** (how much you bet each round), with a
Streamlit frontend for configuring and comparing them.

```bash
pip install -r requirements.txt        # or: pip install -e ".[app,dev]"
streamlit run app/streamlit_app.py     # the frontend
python -m blackjack_sim run configs/progressions.json   # the same from the CLI
python -m pytest                       # tests
```

## Layout

```
blackjack_sim/
├── engine/                 # game mechanics only: no betting systems, no files
│   ├── cards.py            # Shoe (cut card, burn card, tracks seen cards for counting)
│   ├── rules.py            # Rules dataclass: every house rule is a field
│   ├── hand.py             # Hand, Action, Outcome
│   ├── table.py            # the round engine (a generator that yields Decisions)
│   └── counting.py         # Hi-Lo, KO, Omega II, Zen, Wong Halves...
├── strategies/
│   ├── base.py             # PlayStrategy / BetStrategy interfaces + Param schema
│   ├── registry.py         # "type" name -> class, used by JSON configs and the UI
│   ├── play/basic.py       # basic strategy (H17/S17, DAS, surrender) + Illustrious 18
│   ├── play/simple.py      # threshold, mimic dealer, legacy linear/sigmoid, random
│   ├── betting/progressions.py  # flat, Martingale, Paroli, D'Alembert, Fibonacci,
│   │                            # Oscar's Grind, 1-3-2-6, random volatility, proportional
│   └── betting/counting.py      # true-count bet spread (with optional Wonging)
├── simulation/
│   ├── config.py           # ExperimentConfig <-> JSON
│   ├── session.py          # one player + bankroll over N rounds
│   ├── experiment.py       # many sessions per profile, in parallel, + summary stats
│   ├── analysis.py         # dealer outcome table (sanity check)
│   └── export.py           # CSV output
└── __main__.py             # CLI
app/streamlit_app.py        # frontend
configs/*.json              # example experiments
tests/                      # engine, strategy and simulation tests
```

Each layer only depends on the one above it. The engine never imports a strategy,
and strategies never touch files or the UI.

## Configuring experiments

An experiment is a JSON file (or the same settings in the frontend):

```json
{
  "rules":   { "num_decks": 6, "dealer_hits_soft_17": false, "blackjack_payout": 1.5, "...": "..." },
  "session": { "rounds": 1000, "sessions": 1000, "bankroll": 1000, "win_target": 0, "stop_loss": 0, "seed": 12345 },
  "candidates": [
    { "name": "Flat",       "play": {"type": "basic"}, "bet": {"type": "flat",       "params": {"unit": 10}} },
    { "name": "Martingale", "play": {"type": "basic"}, "bet": {"type": "martingale", "params": {"unit": 10, "multiplier": 2}} }
  ]
}
```

`python -m blackjack_sim strategies` lists every strategy and its parameters.

**Common random numbers:** session *i* of every profile is dealt from the same
shuffled shoe. Two profiles with the same play strategy see identical cards, so
differences between them come from the strategy, not from luck.

### Rule variations

All in `Rules` (`engine/rules.py`): decks, penetration, burn cards, continuous
shuffler, H17/S17, dealer peek or European no-hole-card (with an original-bets-only
option), blackjack payout (3:2, 6:5...), insurance, double on any/9-11/10-11, double
after split, max split hands, resplit/hit split aces, late surrender, N-card
Charlie, and table limits.

To add a new variant, add a field to `Rules` and read it in `engine/table.py`.
The frontend's rule panel is in `rules_sidebar()` in the app.

### Adding a strategy

```python
from blackjack_sim.strategies import BetStrategy, Param, register_bet

@register_bet
class TripleAfterTwoLosses(BetStrategy):
    key = "triple_after_two"
    label = "Triple after two losses"
    params = (Param("unit", float, 10.0, "Base bet"),)

    def reset(self):
        self.losses = 0

    def bet(self, ctx):             # ctx: bankroll, profit, round index, shoe (for counts)
        return self.unit * (3 if self.losses >= 2 else 1)

    def update(self, result):       # result.net, result.initial_bet, result.hands...
        self.losses = self.losses + 1 if result.lost else 0
```

Import the module (e.g. from `strategies/__init__.py`) and it shows up in the CLI,
JSON configs and the frontend. The frontend builds the parameter widgets from
`params`. Play strategies work the same way: subclass `PlayStrategy` and
implement `play(decision)`, which returns one of `decision.legal`.

## What the numbers mean

The **Summary** view reports, per profile:

- **Edge**: total profit divided by total initial bets, with a standard error.
- **Mean, median and percentiles** of session profit.
- **P(profit)**: share of sessions that end up.
- **P(ruin)**: share of sessions where the bankroll fell below the table minimum.
- **Drawdowns.**
- **Per-hand EV and volatility.**

The main finding the suite is built to test: **without information, bet sizing
can't change the edge.** Rounds are (almost) independent, so every bet carries the
same expected loss per unit. Progressions like Martingale only reshape the
distribution: many sessions end slightly up, and a few end with catastrophic
losses. The `random` bet strategy isolates pure bet-size volatility. Its edge
matches flat betting, while its spread and risk of ruin grow. Only bets that track
the player's actual advantage (the `count_spread` strategy) move the edge. Try
`configs/counting.json`.

## Validation

The engine reproduces published results: 6-deck S17 DAS 3:2 basic strategy comes
out at a -0.42% ± 0.05% edge (published ≈ -0.40%). H17 costs about 0.2%, late
surrender saves about 0.08%, and 6:5 costs about 1.4%. Dealer bust rates match an
exact infinite-deck calculation. The *Hand log* view (and
`hand_log_*.csv` from the CLI) shows every hand of a session, so you can check the
mechanics by hand.

## Changes from the original prototype

Bugs fixed in the old `blackjack.py`:

- no natural blackjack payout (it paid 1:1) and no dealer peek
- no double, split, surrender or insurance
- the H17 rule only applied if the dealer's first two cards were soft 17
- soft 21 could be hit, and the Ace upcard was treated as 1 in the sigmoid strategy
- P&L was computed after the fact from a CSV, so bets couldn't react to the count
  and doubles/blackjacks were paid wrongly

The Linear, Sigmoid and Discrete strategies live on as `linear`, `sigmoid` and
`threshold`. The customtkinter GUI is replaced by the Streamlit app.

## Towards Gymnasium

`Table.play_round()` is a generator that yields a `Decision` (hand, dealer
upcard, legal actions, shoe state) and receives an `Action`. A Gymnasium
environment is a thin wrapper around it: `reset()` starts a round, `step(action)`
sends the action, and a round ending returns the reward. No engine changes are
needed.
