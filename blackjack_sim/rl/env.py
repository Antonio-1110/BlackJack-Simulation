"""A Gymnasium environment around :meth:`Table.play_round`.

One episode is one round at a single-seat table. The shoe carries over between
episodes (it is only reshuffled at the cut card), so the true count in the
observation means the same thing it does at a real table.

* **Observation**: a ``Dict`` describing the current decision (see
  :func:`encode_decision`).
* **Action**: ``Discrete`` over :data:`PLAY_ACTIONS` (plus the two insurance
  actions when ``offer_insurance=True``). Which ones are legal right now is
  given by :meth:`BlackjackEnv.action_masks` and ``info["action_mask"]``.
* **Reward**: 0 on every step except the last, where it is the round's net
  result in units of the initial bet (+1 win, +1.5 blackjack, -2 lost double,
  -0.5 surrender, ...). The expected return per episode is the player's edge.

Rounds that end without a player decision (a natural, a dealer blackjack, or
a split-aces style auto-stand) still become an episode, so episode returns
average to the true edge. Such an episode has a single step where only
``STAND`` is legal; ``info["auto"]`` is True on its reset.

An illegal action does not raise: it is replaced by ``STAND`` (``NO_INSURANCE``
for an insurance decision), ``info["illegal_action"]`` is set and
``illegal_action_penalty`` is subtracted from that step's reward. That keeps
random exploration and ``gymnasium``'s env checker working without a wrapper.
"""

from __future__ import annotations

import random
from typing import Any

import numpy as np
import gymnasium as gym
from gymnasium import spaces

from ..engine import Action, Decision, Hand, Rules, Table
from ..engine.counting import get_system

PLAY_ACTIONS: tuple[Action, ...] = (
    Action.STAND,
    Action.HIT,
    Action.DOUBLE,
    Action.SPLIT,
    Action.SURRENDER,
)
INSURANCE_ACTIONS: tuple[Action, ...] = (Action.INSURANCE, Action.NO_INSURANCE)

MAX_TOTAL = 30  # worst possible bust: hard 20 + a ten
MAX_CARDS = 21
TRUE_COUNT_LIMIT = 50.0


class BlackjackEnv(gym.Env):
    """Play one blackjack round per episode against the engine's dealer.

    Parameters
    ----------
    rules:
        Table rules (a :class:`Rules` or a dict for :meth:`Rules.from_dict`).
    count_system:
        Counting system used for the ``true_count`` observation.
    shoe_composition:
        Add a ``seen`` entry: how many cards of each value 1..10 have been seen
        since the last shuffle.
    offer_insurance:
        Expose insurance decisions to the agent. When False (default)
        insurance is always declined and the action space has 5 actions.
    illegal_action_penalty:
        Subtracted from the reward whenever an illegal action is replaced.
    """

    metadata = {"render_modes": ["ansi"], "render_fps": 4}

    def __init__(
        self,
        rules: Rules | dict | None = None,
        count_system: str = "hi_lo",
        shoe_composition: bool = False,
        offer_insurance: bool = False,
        illegal_action_penalty: float = 0.0,
        render_mode: str | None = None,
    ) -> None:
        if render_mode is not None and render_mode not in self.metadata["render_modes"]:
            raise ValueError(f"unsupported render_mode {render_mode!r}")
        self.rules = rules if isinstance(rules, Rules) else Rules.from_dict(rules)
        self.count_system = get_system(count_system)
        self.shoe_composition = shoe_composition
        self.offer_insurance = offer_insurance
        self.illegal_action_penalty = float(illegal_action_penalty)
        self.render_mode = render_mode

        self.actions = PLAY_ACTIONS + (INSURANCE_ACTIONS if offer_insurance else ())
        self._index = {a: i for i, a in enumerate(self.actions)}
        self.action_space = spaces.Discrete(len(self.actions))

        obs: dict[str, spaces.Space] = {
            "player_total": spaces.Discrete(MAX_TOTAL + 1),
            "soft": spaces.Discrete(2),
            "pair": spaces.Discrete(2),
            "dealer_upcard": spaces.Discrete(11),  # 1 = Ace .. 10; 0 unused
            "num_cards": spaces.Discrete(MAX_CARDS + 1),
            "num_hands": spaces.Discrete(self.rules.max_split_hands + 1),
            "insurance": spaces.Discrete(2),
            "true_count": spaces.Box(
                -TRUE_COUNT_LIMIT, TRUE_COUNT_LIMIT, shape=(1,), dtype=np.float32
            ),
        }
        if shoe_composition:
            obs["seen"] = spaces.Box(
                0, 52 * self.rules.num_decks, shape=(10,), dtype=np.int64
            )
        self.observation_space = spaces.Dict(obs)

        self.table: Table | None = None
        self.decision: Decision | None = None
        self._gen = None
        self._pending_result = None
        self._last_hand: Hand | None = None
        self._last_up = 0
        self.last_result = None  # RoundResult of the last finished episode
        self._bet = self.rules.table_min

    # ------------------------------------------------------------ gym API
    def reset(
        self, *, seed: int | None = None, options: dict[str, Any] | None = None
    ) -> tuple[dict, dict]:
        super().reset(seed=seed)
        if self.table is None or seed is not None:
            table_seed = int(self.np_random.integers(2**63 - 1))
            self.table = Table(self.rules, 1, random.Random(table_seed))
        if options and options.get("shuffle"):
            self.table.shoe.shuffle()

        self._gen = self.table.play_round([self._bet])
        self._pending_result = None
        self._last_hand = None
        self.decision = self._advance(None)
        info = self._info()
        info["auto"] = self.decision is None
        return self._obs(), info

    def step(self, action: int) -> tuple[dict, float, bool, bool, dict]:
        if self._gen is None:
            raise RuntimeError("call reset() before step()")
        illegal = False
        reward = 0.0
        if self.decision is None:
            # A round that ended on its own; this step only reports the result.
            illegal = int(action) != self._index[Action.STAND]
        else:
            chosen = self.actions[int(action)]
            if chosen not in self.decision.legal:
                illegal = True
                chosen = Action.NO_INSURANCE if self.decision.kind == "insurance" else Action.STAND
            self.decision = self._advance(chosen)

        if illegal:
            reward -= self.illegal_action_penalty
        terminated = self.decision is None
        info = self._info()
        info["illegal_action"] = illegal
        if terminated:
            result = self._pending_result
            seat = result.seats[0]
            reward += seat.net / seat.initial_bet
            info["net"] = seat.net
            info["outcomes"] = tuple(h.outcome.value for h in seat.hands)
            info["dealer_total"] = result.dealer_total
            self.last_result = result
            self._gen = None
        if self.render_mode == "ansi":
            info["text"] = self.render()
        return self._obs(), float(reward), terminated, False, info

    def action_masks(self) -> np.ndarray:
        """Boolean mask of legal actions (the sb3-contrib ``MaskablePPO`` hook)."""
        mask = np.zeros(len(self.actions), dtype=bool)
        if self.decision is None:
            mask[self._index[Action.STAND]] = True
        else:
            for a in self.decision.legal:
                if a in self._index:
                    mask[self._index[a]] = True
        return mask

    def render(self) -> str | None:
        if self.render_mode != "ansi":
            return None
        hand = self._current_hand()
        text = f"dealer up {self._last_up}  player {hand!r}" if hand else "no hand"
        if self._pending_result is not None:
            r = self._pending_result
            text += f"  dealer {r.dealer_cards} = {r.dealer_total}  net {r.seats[0].net:+g}"
        return text

    # ------------------------------------------------------------ helpers
    def _advance(self, action: Action | None) -> Decision | None:
        """Send ``action`` into the round and return the next agent decision,
        answering insurance ourselves when it is not offered to the agent."""
        try:
            d = next(self._gen) if action is None else self._gen.send(action)
            while d.kind == "insurance" and not self.offer_insurance:
                d = self._gen.send(Action.NO_INSURANCE)
        except StopIteration as stop:
            self._pending_result = stop.value
            return None
        self._last_hand, self._last_up = d.hand, d.dealer_value
        return d

    def _current_hand(self) -> Hand | None:
        if self.decision is not None:
            return self.decision.hand
        if self._pending_result is not None:
            seat = self._pending_result.seats[0]
            if self._last_hand is None or self._last_hand not in seat.hands:
                self._last_hand = seat.hands[-1]
            up = self._pending_result.dealer_cards[0]
            self._last_up = 10 if up >= 10 else up
        return self._last_hand

    def _obs(self) -> dict:
        hand = self._current_hand()
        obs = encode_decision(
            hand,
            self._last_up,
            num_hands=self.decision.num_hands if self.decision else self._num_hands(),
            insurance=bool(self.decision and self.decision.kind == "insurance"),
            true_count=self.count_system.true_count(self.table.shoe),
            max_hands=self.rules.max_split_hands,
        )
        if self.shoe_composition:
            obs["seen"] = np.asarray(self.table.shoe.seen[1:], dtype=np.int64)
        return obs

    def _num_hands(self) -> int:
        if self._pending_result is not None:
            return len(self._pending_result.seats[0].hands)
        return 1

    def _info(self) -> dict:
        return {"action_mask": self.action_masks()}


def encode_decision(
    hand: Hand,
    dealer_up: int,
    num_hands: int = 1,
    insurance: bool = False,
    true_count: float = 0.0,
    max_hands: int = 4,
) -> dict:
    """The observation for one hand. Shared by the env and anything that wants
    to feed engine :class:`Decision` objects to a trained policy."""
    return {
        "player_total": min(hand.total, MAX_TOTAL),
        "soft": int(hand.is_soft),
        "pair": int(hand.is_pair),
        "dealer_upcard": int(dealer_up),
        "num_cards": min(len(hand.cards), MAX_CARDS),
        "num_hands": min(num_hands, max_hands),
        "insurance": int(insurance),
        "true_count": np.array(
            [np.clip(true_count, -TRUE_COUNT_LIMIT, TRUE_COUNT_LIMIT)], dtype=np.float32
        ),
    }
