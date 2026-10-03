# Blackjack Simulation

A blackjack engine plus a Monte Carlo suite for testing **play strategies** (how you
play a hand) and **bet-sizing strategies** (how much you bet each round), with a
Streamlit frontend for configuring and comparing them, and a browser **Strategy Lab**
where you type a strategy in Python and hit Run (see [§13](#13-the-browser-strategy-lab)).

**Try the Strategy Lab online:** <https://antonio-1110.github.io/BlackJack-Simulation/>
(nothing to install; it runs in your browser).

```bash
pip install -r requirements.txt        # or: pip install -e ".[app,dev]"
streamlit run app/streamlit_app.py     # the frontend
python -m blackjack_sim run configs/progressions.json   # the same from the CLI
python -m pytest                       # tests
python scripts/build_web.py && python -m http.server -d build/web   # the Strategy Lab
```

**Contents**

1. [How a simulation works](#1-how-a-simulation-works)
2. [Designing a play strategy](#2-designing-a-play-strategy)
3. [Designing a bet strategy](#3-designing-a-bet-strategy)
4. [Reference: all the information available](#4-reference-all-the-information-available)
5. [Parameters: making a strategy configurable](#5-parameters-making-a-strategy-configurable)
6. [Registering, running and testing your strategy](#6-registering-running-and-testing-your-strategy)
7. [Design advice and pitfalls](#7-design-advice-and-pitfalls)
8. [Configuring experiments and table rules](#8-configuring-experiments-and-table-rules)
9. [Reading the results](#9-reading-the-results)
10. [Project layout](#10-project-layout)
11. [Validation and history](#11-validation-and-history)
12. [Reinforcement learning: the Gymnasium environment](#12-reinforcement-learning-the-gymnasium-environment)
13. [The browser Strategy Lab](#13-the-browser-strategy-lab)

---

## 1. How a simulation works

A **player profile** (called a *candidate* in configs) is one **play strategy** plus
one **bet strategy**. They are two separate objects with separate jobs:

| | Play strategy | Bet strategy |
|---|---|---|
| Decides | hit / stand / double / split / surrender, and insurance | how much to wager before the cards come out |
| Called | once per decision, possibly several times per round | once per round, before the deal |
| Sees | a `Decision`: your hand, the dealer upcard, legal actions, the shoe | a `BetContext`: bankroll, profit, round number, the shoe |
| Learns results | no | yes, through `update(result)` after every round it played |

An **experiment** plays many independent **sessions** per profile. A session is one
player sitting down with a starting bankroll for up to N rounds. Every round runs
in this order:

```text
 1. Shuffle if the cut card was reached       (shoe counts reset to zero)
 2. bet_strategy.bet(ctx)          -> wager    (clamped to limits, see §3)
 3. Deal: your card, dealer upcard, your card, dealer hole card (face down)
 4. If the upcard is an Ace:  play_strategy.take_insurance(decision)
 5. Dealer peeks; with a blackjack the round ends here
 6. For each of your hands:   play_strategy.play(decision)  until the hand is done
 7. Dealer reveals the hole card and draws
 8. Settle bets
 9. bet_strategy.update(result)
10. Stop the session if you are broke, hit the win target, or hit the stop loss
```

Some decisions are never asked because only one choice is possible. A hand that
reaches 21 stands automatically, a bust ends the hand, and split aces get one card
each unless the rules say otherwise. **You only get asked when you really have a
choice.**

---

## 2. Designing a play strategy

Subclass `PlayStrategy`, give it a unique `key`, and implement `play(decision)`.
It must return **one of `decision.legal`**. Returning anything else raises an
error, so you can't accidentally cheat the rules.

```python
from blackjack_sim.engine import Action
from blackjack_sim.strategies import Param, PlayStrategy, register_play


@register_play
class DealerBustHunter(PlayStrategy):
    """Stand early against weak dealer upcards, otherwise draw to 17."""

    key = "bust_hunter"
    label = "Dealer bust hunter"
    description = "Stand on 12+ against a 2-6, hit to 17 against 7-A, double 10/11 against weak cards."
    params = (Param("stand_vs_weak", int, 12, "Stand on this total or more against 2-6.", 12, 21),)

    def play(self, d):
        total = d.hand.total
        weak_dealer = 2 <= d.dealer_value <= 6

        if Action.DOUBLE in d.legal and total in (10, 11) and weak_dealer:
            return Action.DOUBLE
        if weak_dealer and total >= self.stand_vs_weak and not d.hand.is_soft:
            return Action.STAND
        return Action.HIT if total < 17 else Action.STAND
```

That is a complete, working strategy. It shows up in the frontend's *Play strategy*
dropdown and in configs as `{"type": "bust_hunter"}`.

**Handling each action.** Check `Action.X in d.legal` before choosing `DOUBLE`,
`SPLIT` or `SURRENDER`. Whether they're allowed depends on the table rules, the
number of cards, earlier splits and your remaining bankroll. `HIT` and `STAND` are
always legal when you're asked, except on split aces, where only `STAND` (and
possibly a re-split) is allowed.

| Action | Legal when |
|---|---|
| `STAND` | always |
| `HIT` | always, except split aces when `hit_split_aces` is off |
| `DOUBLE` | first two cards of a hand; total allowed by `double_on`; after a split only with `double_after_split`; you can afford another bet |
| `SPLIT` | two cards of equal value (any two ten-value cards count); fewer than `max_split_hands` hands; aces again only with `resplit_aces`; you can afford it |
| `SURRENDER` | `surrender = "late"`; first two cards; not after a split |

**Insurance** is a separate question. When the dealer shows an Ace, the engine calls
`take_insurance(decision)`, which returns `True` or `False`. The default is
`False`: insurance is a losing bet unless you are counting cards.

**Building on basic strategy.** Most good strategies are "basic strategy, except…".
Subclass `BasicStrategy` and override only the cases you care about:

```python
from blackjack_sim.engine import HI_LO, Action
from blackjack_sim.strategies import register_play
from blackjack_sim.strategies.play.basic import BasicStrategy


@register_play
class BasicPlus16v10(BasicStrategy):
    key = "basic_plus_16v10"
    label = "Basic + count-based 16 v 10"
    description = "Basic strategy, but stand on hard 16 vs 10 when the Hi-Lo true count is positive."

    def play(self, d):
        hand = d.hand
        if (hand.total == 16 and not hand.is_soft and d.dealer_value == 10
                and HI_LO.true_count(d.shoe) > 0 and Action.SURRENDER not in d.legal):
            return Action.STAND
        return super().play(d)  # everything else: the normal chart

    def take_insurance(self, d):
        return HI_LO.true_count(d.shoe) >= 3
```

---

## 3. Designing a bet strategy

Subclass `BetStrategy` and implement `bet(ctx)`. Optionally implement
`update(result)` to learn from each round, and `reset()` to set up per-session
state.

```python
from blackjack_sim.strategies import BetStrategy, Param, register_bet


@register_bet
class PressWhenAhead(BetStrategy):
    """Bet more while the session is in profit, go back to one unit after two losses in a row."""

    key = "press_when_ahead"
    label = "Press when ahead"
    params = (
        Param("unit", float, 10.0, "Base bet.", 1.0),
        Param("press_units", float, 3.0, "Units to bet while in profit.", 1.0),
    )

    def reset(self):                     # called at the start of every session
        self.losses_in_a_row = 0

    def bet(self, ctx):
        if self.losses_in_a_row >= 2 or ctx.profit <= 0:
            return self.unit
        return self.unit * self.press_units

    def update(self, result):            # called after every round you played
        self.losses_in_a_row = self.losses_in_a_row + 1 if result.lost else 0
```

**What happens to the number you return:**

| You return | What is actually bet |
|---|---|
| `> 0` | clamped to `[table_min, table_max]`, and never more than your bankroll |
| `0` or less | you **sit out** this round. Cards are still dealt to the dealer and other seats, so the shoe advances and the count keeps moving, and `update()` is not called |

The session ends as **ruined** when your bankroll drops below the table minimum.
You always know the bet that was really placed, because `result.initial_bet` in
`update()` holds it.

**Counting-based betting.** `ctx.shoe` is the live shoe, already shuffled if a
shuffle was due, so a fresh shoe reads a count of zero. The count helpers take it
directly:

```python
import math

from blackjack_sim.engine import get_system
from blackjack_sim.strategies import BetStrategy, Param, register_bet


@register_bet
class SimpleSpread(BetStrategy):
    key = "simple_spread"
    label = "Simple count spread"
    params = (
        Param("unit", float, 10.0, "Base bet.", 1.0),
        Param("system", str, "hi_lo", "Counting system.", choices=("hi_lo", "omega_ii", "zen")),
    )

    def bet(self, ctx):
        tc = math.floor(get_system(self.system).true_count(ctx.shoe))
        if tc < -1:
            return 0                                # sit out bad shoes
        return self.unit * min(8, max(1, tc))       # 1 to 8 units
```

---

## 4. Reference: all the information available

### What a play strategy sees: `Decision`

| Field | Type | Meaning |
|---|---|---|
| `d.kind` | `str` | `"play"`, or `"insurance"` (routed to `take_insurance` for you) |
| `d.hand` | `Hand` | the hand being played (see below) |
| `d.dealer_value` | `int` | dealer upcard value, **1 = Ace**, 2-10 (faces are 10) |
| `d.dealer_up` | `int` | dealer upcard rank 1-13, if you care about J/Q/K |
| `d.legal` | `tuple[Action]` | what you're allowed to do right now |
| `d.hand_index` / `d.num_hands` | `int` | which of your hands this is, and how many you have (after splits) |
| `d.rules` | `Rules` | the table rules (see §8), e.g. `d.rules.dealer_hits_soft_17` |
| `d.shoe` | `Shoe` | card-counting information (see below) |
| `d.seat` | `int` | your seat number (0 in normal experiments) |

### A hand: `Hand`

| Field | Meaning |
|---|---|
| `hand.total` | best total, with an Ace counted as 11 when that doesn't bust |
| `hand.is_soft` | `True` if an Ace is currently counted as 11 |
| `hand.hard` | total with every Ace counted as 1 |
| `hand.cards` | list of ranks, 1 = Ace, 11/12/13 = J/Q/K (don't modify it) |
| `hand.is_pair`, `hand.pair_value` | two cards of equal value, and that value (1 = Aces) |
| `hand.is_blackjack` | natural 21 (never true after a split) |
| `hand.is_split`, `hand.split_depth` | whether the hand came from a split, and how many splits deep |
| `hand.from_split_aces` | hand started from splitting aces |
| `hand.bet`, `hand.doubled` | money on this hand, and whether it was doubled |

### Counting information: `Shoe`

Everything a real player could legitimately know from watching the table:

| Field | Meaning |
|---|---|
| `shoe.seen[v]` | how many cards of value `v` (1 = Ace … 10) have been **seen face up** since the shuffle. This includes other players' cards and the dealer's upcard; the hole card is added once it's turned over |
| `shoe.seen_total` | total cards seen since the shuffle |
| `shoe.unseen_cards` | cards not yet seen (still in the shoe, plus the burn card and the hole card) |
| `shoe.decks_remaining` | `unseen_cards / 52`, the divisor for a true count |
| `shoe.num_decks`, `shoe.total_cards`, `shoe.penetration` | shoe setup |
| `shoe.dealt` | cards drawn since the shuffle |
| `shoe.needs_shuffle` | the cut card has come out (a shuffle happens before the next round) |
| `shoe.shuffles` | number of shuffles so far this session |

Ready-made count systems (`from blackjack_sim.engine import HI_LO, get_system`):

```text
HI_LO.running_count(shoe)      HI_LO.true_count(shoe)
get_system("hi_lo" | "hi_opt_i" | "hi_opt_ii" | "omega_ii" | "zen" | "wong_halves" | "ko")
```

To build your own, pass one tag per card value (Ace first):
`CountSystem("My count", tags=(-1, 1, 1, 1, 1, 1, 0, 0, 0, -1))`.

### What a bet strategy sees: `BetContext`

| Field | Meaning |
|---|---|
| `ctx.bankroll` | current bankroll |
| `ctx.starting_bankroll` | bankroll at the start of the session |
| `ctx.profit` | `bankroll - starting_bankroll` |
| `ctx.round_index` | 0-based round number within the session |
| `ctx.rules` | table rules: `ctx.rules.table_min`, `ctx.rules.table_max`, … |
| `ctx.shoe` | the shoe, same fields as above |

### What a bet strategy learns afterwards: `SeatResult` in `update(result)`

| Field | Meaning |
|---|---|
| `result.net` | money won (+) or lost (−) this round, including doubles, splits and insurance |
| `result.won` / `result.lost` | `net > 0` / `net < 0` (a push is neither) |
| `result.initial_bet` | the bet actually placed (after clamping) |
| `result.wagered` | all money risked this round (doubles, splits, insurance included) |
| `result.hands` | the final hands: each has `.cards`, `.total`, `.outcome`, `.net`, `.doubled` |
| `result.insurance_bet`, `result.insurance_net` | insurance taken and its result |

A hand's `.outcome` is one of `blackjack`, `win`, `push`, `lose`, `bust`,
`surrender` (`from blackjack_sim.engine import Outcome`).

### What is deliberately hidden

- **The dealer's hole card**, until it's turned over at the end of the round.
- **The order of the remaining cards.** Attributes starting with `_` (such as
  `shoe._cards`) are engine internals. Reading them is looking at the future, and
  your results would be meaningless.
- **The bankroll, inside a play strategy.** `Decision` doesn't carry it; `legal`
  already leaves out doubles and splits you can't afford.
- **A shared channel between your two strategies.** They only share what's on the
  table, meaning the shoe. If a play decision should depend on your bet, read
  `d.hand.bet`.

---

## 5. Parameters: making a strategy configurable

Everything you list in `params` becomes an attribute (`self.unit`), a JSON config
field and a frontend widget, with validation for free.

```text
Param(name, kind, default, help="", min=None, max=None, step=None, choices=None)
```

| `kind` | Frontend widget | Notes |
|---|---|---|
| `int` / `float` | number box | `min` / `max` are enforced; `step` sets the +/- increment |
| `bool` | checkbox | |
| `str` | text box | with `choices=(...)` it becomes a dropdown |

- Use `reset()` for **state that changes during a session**, like streak counters or
  progression levels. It runs once when the object is created and again at the
  start of every session.
- Override `validate()` for checks across parameters, and raise `ValueError`
  with a clear message. The frontend shows it as an error and won't run.
- Need randomness? Use **`self.rng`** (a seeded `random.Random`), never the global
  `random` module. That keeps runs reproducible and keeps the dealt cards identical
  across profiles.

```python
from blackjack_sim.strategies import BetStrategy, Param, register_bet


@register_bet
class RandomLadder(BetStrategy):
    key = "random_ladder"
    label = "Random ladder"
    description = "Bet a random whole number of units between min and max; optionally skip rounds."
    params = (
        Param("unit", float, 10.0, "Money per unit.", 1.0),
        Param("min_units", int, 1, "Smallest bet, in units.", 1),
        Param("max_units", int, 4, "Largest bet, in units.", 1),
        Param("skip_chance", float, 0.0, "Chance to sit a round out.", 0.0, 0.95, 0.05),
    )

    def validate(self):
        if self.max_units < self.min_units:
            raise ValueError("max_units must be at least min_units")

    def bet(self, ctx):
        if self.rng.random() < self.skip_chance:
            return 0
        return self.unit * self.rng.randint(self.min_units, self.max_units)
```

---

## 6. Registering, running and testing your strategy

**Where to put it.** Add a file under `blackjack_sim/strategies/play/` or
`blackjack_sim/strategies/betting/`, then import it in
`blackjack_sim/strategies/__init__.py` next to the built-in ones:

```text
from .play import basic, simple, my_play_strategy
from .betting import counting, progressions, my_bet_strategy
```

The `@register_play` / `@register_bet` decorator does the rest: the strategy
appears in the frontend, in `python -m blackjack_sim strategies`, and in JSON
configs. Keys must be unique.

**Try it quickly** from Python, without the frontend:

```python
from blackjack_sim import Candidate, ExperimentConfig, Rules, SessionSettings, run_experiment

config = ExperimentConfig(
    rules=Rules(num_decks=6),
    session=SessionSettings(rounds=500, sessions=50, bankroll=1000, seed=1),
    candidates=[
        Candidate("Baseline", play={"type": "basic"}, bet={"type": "flat", "params": {"unit": 10}}),
        Candidate("Mine", play={"type": "bust_hunter"}, bet={"type": "press_when_ahead"}),
    ],
)
result = run_experiment(config, workers=1)
print(result.summary_frame()[["edge_pct", "edge_se_pct", "mean_net", "prob_ruin"]])

# Every hand of the first session, to check your logic hand by hand:
for row in result["Mine"].sessions[0].log[:5]:
    print(row["player"], "vs", row["dealer"], "->", row["outcome"], row["net"])
```

**Unit-test a decision** by building the exact situation. `tests/test_strategies.py`
has more examples, and `tests/test_engine.py` shows how to stack the shoe for whole
rounds.

```python
import math
import random

from blackjack_sim.engine import Action, Decision, Hand, Rules, Table
from blackjack_sim.strategies import create_play

table = Table(Rules(), num_seats=1, rng=random.Random(0))
hand = Hand(bet=10)
for card in (10, 2):           # hard 12
    hand.add(card)
legal = table.legal_actions(hand, num_hands=1, available=math.inf)
decision = Decision("play", 0, 0, hand, 1, 4, legal, table)   # dealer shows a 4

assert create_play("bust_hunter")(decision) is Action.STAND
assert create_play("basic")(decision) is Action.STAND
```

The test suite also plays every registered strategy for a few hundred rounds
(`test_every_play_strategy_plays_legal_moves`), so an illegal move shows up as a
failing test.

---

## 7. Design advice and pitfalls

- **Always include a baseline.** Compare against basic strategy with flat betting,
  under the same rules and seed. Because every profile gets the same shuffled
  shoes, the difference is the effect of your strategy, not luck.
- **Know what can and can't work.** Without counting, rounds are (almost)
  independent, so **no bet-sizing scheme changes the edge** (profit per unit bet).
  Progressions only reshape the results: more small wins and rare huge losses
  (Martingale), or the reverse (Paroli). They can still be the right choice if you
  care about something other than expected value, such as the chance of reaching
  a target. The summary reports `prob_target`, `prob_ruin` and percentiles for
  exactly that. Only bets that follow **real information** (the count) change the
  edge.
- **Mind the noise.** One hand has a standard deviation of about 1.15 bets, while
  edges are fractions of a percent. Look at `edge_se_pct` and treat differences
  under about two standard errors as noise. About 1 million hands gives roughly
  ±0.1%.
- **Play decisions are where the edge comes from.** Deviating from basic strategy
  without count information almost always costs money; the *Play strategies*
  preset shows how much.
- **Bet sizing drives risk.** Bigger or more variable bets magnify both the loss
  rate and the swings. Compare `avg_bet`, `sd_per_hand` and `worst_max_drawdown`,
  not just the mean.
- **Table limits and bankroll bite.** A Martingale capped at `table_max`, or one that
  runs out of money, can't recover its losses. That's the real-world failure mode
  the simulator models.
- **Keep state in `reset()`, not `__init__`.** Otherwise one session's streak
  leaks into the next.
- **Use `self.rng` for anything random.** A play strategy that uses randomness, or
  draws a different number of cards, will drift onto different cards than the
  baseline. That's still fair, just noisier to compare.

---

## 8. Configuring experiments and table rules

An experiment is a JSON file (or the same settings in the frontend):

```json
{
  "rules":   { "num_decks": 6, "dealer_hits_soft_17": false, "blackjack_payout": 1.5 },
  "session": { "rounds": 1000, "sessions": 1000, "bankroll": 1000, "win_target": 0,
               "stop_loss": 0, "other_players": 0, "seed": 12345 },
  "candidates": [
    { "name": "Flat",       "play": {"type": "basic"}, "bet": {"type": "flat",       "params": {"unit": 10}} },
    { "name": "Martingale", "play": {"type": "basic"}, "bet": {"type": "martingale", "params": {"unit": 10}} }
  ]
}
```

Rules you leave out keep their defaults. `python -m blackjack_sim strategies`
lists every strategy and its parameters; `python -m blackjack_sim init my.json`
writes a full default config to start from.

**Session settings:** `rounds` (maximum per session), `sessions` (Monte Carlo
repetitions), `bankroll`, `win_target` / `stop_loss` (end a session once up/down
that much; 0 = off), `other_players` (extra basic-strategy seats that only use up
cards) and `seed`.

**Table rules** (`blackjack_sim/engine/rules.py`):

| Rule | Default | Meaning |
|---|---|---|
| `num_decks` | 6 | decks in the shoe |
| `penetration` | 0.75 | share of the shoe dealt before the cut card |
| `burn_cards` | 1 | cards burned after each shuffle |
| `continuous_shuffle` | false | reshuffle every round (a CSM) |
| `dealer_hits_soft_17` | false | H17 when true, S17 when false |
| `dealer_peeks` | true | US hole-card game; false = European no-hole-card |
| `no_peek_original_bets_only` | false | no-hole-card: a dealer blackjack only takes the original bet |
| `blackjack_payout` | 1.5 | 1.5 = 3:2, 1.2 = 6:5 |
| `insurance` | true | insurance offered against an Ace |
| `double_on` | `"any"` | `"any"`, `"9-11"` or `"10-11"` |
| `double_after_split` | true | DAS |
| `max_split_hands` | 4 | hands you can split up to (1 disables splitting) |
| `resplit_aces` / `hit_split_aces` | false | split-aces rules |
| `surrender` | `"none"` | `"none"` or `"late"` |
| `charlie_cards` | 0 | auto-win with this many cards without busting (0 = off) |
| `table_min` / `table_max` | 10 / 1000 | betting limits |

To add a new variant, add a field to `Rules` and read it in
`blackjack_sim/engine/table.py`. Add a widget for it in `rules_sidebar()` in the
app.

---

## 9. Reading the results

Per profile, the summary reports:

| Column | Meaning |
|---|---|
| `edge_pct` ± `edge_se_pct` | total profit ÷ total initial bets, in %. This is the number bet sizing can't change without information |
| `mean_net`, `median_net`, `p05_net`, `p95_net`, `std_net` | the distribution of session profit |
| `prob_profit` | share of sessions that ended up |
| `prob_ruin` | share of sessions that fell below the table minimum |
| `prob_target`, `prob_stop_loss` | share of sessions that hit the win target or the stop loss |
| `avg_bet`, `max_bet`, `avg_hands` | how much and how long you played |
| `ev_per_hand`, `sd_per_hand` | expected result and volatility per hand, in money |
| `avg_max_drawdown`, `worst_max_drawdown` | largest peak-to-trough drop in a session |

The frontend adds bankroll-over-time charts (median or mean, with a 5–95% band),
profit histograms, a risk-vs-return chart, a hand-by-hand log and CSV downloads.
The CLI writes the same data to `results/<timestamp>/`.

---

## 10. Project layout

```text
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
├── playground.py           # runs code typed into the browser Strategy Lab
├── rl/                     # Gymnasium env (optional dependency)
│   ├── env.py              # BlackjackEnv: one round per episode, action masks
│   └── agents.py           # random, basic-strategy and tabular Monte Carlo agents
├── simulation/
│   ├── config.py           # ExperimentConfig <-> JSON
│   ├── session.py          # one player + bankroll over N rounds
│   ├── experiment.py       # many sessions per profile, in parallel, + summary stats
│   ├── analysis.py         # dealer outcome table (sanity check)
│   └── export.py           # CSV output
└── __main__.py             # CLI
app/streamlit_app.py        # frontend
web/                        # the browser Strategy Lab (static page, Python via Pyodide)
scripts/build_web.py        # builds web/ + the zipped package into build/web
configs/*.json              # example experiments: progressions, counting, play strategies
scripts/rl_vs_basic.py      # train a tabular agent and compare it with basic strategy
tests/                      # engine, strategy, simulation, RL env and README-example tests
```

Each layer only depends on the one above it. The engine never imports a strategy,
and strategies never touch files or the UI.

---

## 11. Validation and history

**Validation.** The engine reproduces published results:

- 6-deck S17 DAS 3:2 basic strategy comes out at a −0.42% ± 0.05% edge
  (published ≈ −0.40%).
- H17 costs about 0.2%, late surrender saves about 0.08%, and 6:5 costs about 1.4%.
- Dealer bust rates match an exact infinite-deck calculation (`python -m blackjack_sim dealer`).

**Changes from the original prototype.** Fixed in the old `blackjack.py`:

- no natural blackjack payout (it paid 1:1) and no dealer peek
- no double, split, surrender or insurance
- the H17 rule only applied if the dealer's first two cards were soft 17
- soft 21 could be hit, and the sigmoid strategy treated the Ace upcard as 1
- P&L was computed after the fact from a CSV, so bets couldn't react to the count

The Linear, Sigmoid and Discrete strategies live on as `linear`, `sigmoid` and
`threshold`.

## 12. Reinforcement learning: the Gymnasium environment

`blackjack_sim.rl.BlackjackEnv` wraps the round engine as a
[Gymnasium](https://gymnasium.farama.org/) environment. It needs the optional
dependency: `pip install -e ".[rl]"`. Importing `blackjack_sim.rl` also registers
it as `BlackjackSim-v0` for `gymnasium.make`.

| | |
|---|---|
| Episode | one round at a single-seat table; the shoe carries over between episodes and is only reshuffled at the cut card |
| Observation | `Dict`: `player_total`, `soft`, `pair`, `dealer_upcard` (1 = Ace), `num_cards`, `num_hands`, `insurance` (is this an insurance decision), `true_count`; plus `seen` (cards of each value seen since the shuffle) with `shoe_composition=True` |
| Action | `Discrete(5)`: stand, hit, double, split, surrender (`env.actions` has the order). With `offer_insurance=True` it is `Discrete(7)` with insurance / no insurance; otherwise insurance is always declined |
| Legal actions | `env.action_masks()` and `info["action_mask"]`, built from the engine's `decision.legal` (the hook `sb3-contrib`'s `MaskablePPO` looks for) |
| Reward | 0 until the round ends, then the round's net result in units of the initial bet: +1 win, +1.5 blackjack, −2 lost double, −0.5 surrender. Mean episode return is the edge |

Rounds that end without a choice (a natural, a dealer blackjack) are still an
episode, a single step where only stand is legal and `info["auto"]` is set on
reset, so average returns stay equal to the true edge. An illegal action never
raises: it is played as stand (no insurance for an insurance decision),
`info["illegal_action"]` is set and `illegal_action_penalty` (default 0) is
subtracted. The env passes `gymnasium.utils.env_checker.check_env`, and a seed
passed to `reset(seed=...)` reproduces the whole shoe.

```python
from blackjack_sim.rl import BasicStrategyAgent, BlackjackEnv, RandomAgent, evaluate

env = BlackjackEnv(rules={"surrender": "late"})
obs, info = env.reset(seed=0)
print(obs["player_total"], obs["dealer_upcard"], info["action_mask"])

print("basic strategy", evaluate(BasicStrategyAgent(env), env, 2_000, seed=1))
print("random legal  ", evaluate(RandomAgent(0), env, 2_000, seed=1))
```

`scripts/rl_vs_basic.py` trains a tabular Monte Carlo agent on the env and
compares it with basic strategy and a random agent. With the defaults (500k
training rounds) the learned agent agrees with the chart on about 89% of
decisions and loses about 2.6% per round against basic strategy's 0.4 to 0.8%;
more training rounds close the gap.

```bash
python scripts/rl_vs_basic.py --train 2000000 --eval 500000
```

Still open from the roadmap: a bet-sizing env, and an adapter that runs a
trained policy as a `PlayStrategy` inside the experiment suite.

---

## 13. The browser Strategy Lab

**Live at <https://antonio-1110.github.io/BlackJack-Simulation/>.**

`web/` is a static page where you write a strategy in a code editor, set the table
(players, decks, penetration, soft 17, insurance and the other house rules) and the
simulation (rounds, sessions, bankroll, stop loss, win target), then hit **Run** to see
your profit, your return per dollar bet, and how the bankroll moves over a session,
next to basic strategy with a flat bet on the same cards.

There is no server. The page loads [Pyodide](https://pyodide.org) (CPython compiled to
WebAssembly) in a Web Worker and runs this package inside the browser tab, so
anyone's code only ever runs on their own machine. The code in the editor is an
ordinary module like the examples in §2 and §3: define a `PlayStrategy` (or
`BasicStrategy`) subclass, a `BetStrategy` subclass, or both, without registering
them. If you define several of one kind, pick one with `PLAY = MyClass` or
`BET = MyClass`. `blackjack_sim/playground.py` is the glue; it only uses the
pure-Python parts of the package, so the page doesn't download numpy.

To run your own copy locally, for example while changing the page or the engine:

```bash
python scripts/build_web.py              # writes build/web/ (the page + blackjack_sim.zip)
python -m http.server -d build/web       # open http://localhost:8000
```

**Publishing.** `.github/workflows/pages.yml` builds the same folder and deploys it to
the live site on every push to `main`, so a merged change shows up there a minute or
two later. The repository's Pages source must stay on *GitHub Actions* (Settings →
Pages → Build and deployment); a fork needs that setting once to publish its own copy.

Pyodide runs the simulator roughly three to four times slower than regular Python,
so 50 sessions of 1,000 rounds (plus the baseline) takes several seconds. The
Stop button restarts the Python worker, which also rescues an infinite loop.
