import random

import numpy as np
import pytest

gym = pytest.importorskip("gymnasium")
from gymnasium.utils.env_checker import check_env  # noqa: E402

from blackjack_sim.engine import Action, Rules, Table, play_round  # noqa: E402
from blackjack_sim.rl import (  # noqa: E402
    ENV_ID,
    BasicStrategyAgent,
    BlackjackEnv,
    QLearningAgent,
    RandomAgent,
    evaluate,
)
from blackjack_sim.strategies.play.basic import BasicStrategy  # noqa: E402

A, J, Q, K = 1, 11, 12, 13


def stacked(cards, **kw):
    """An env whose next episode deals ``cards`` (same order as test_engine.deal)."""
    env = BlackjackEnv(**kw)
    env.reset(seed=0)
    env.table.prepare_round()
    env.table.shoe.stack(cards)
    obs, info = env.reset()
    return env, obs, info


def act(env, action):
    return env.step(env.actions.index(action))


# ------------------------------------------------------------------ checker
@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"shoe_composition": True, "offer_insurance": True, "illegal_action_penalty": 1.0},
        {"rules": {"surrender": "late", "dealer_hits_soft_17": True, "dealer_peeks": False}},
    ],
)
def test_env_checker(kwargs):
    check_env(BlackjackEnv(**kwargs), skip_render_check=True)


def test_registered():
    env = gym.make(ENV_ID, rules={"num_decks": 2})
    assert env.unwrapped.rules.num_decks == 2
    check_env(env.unwrapped, skip_render_check=True)


def test_spaces():
    assert BlackjackEnv().action_space.n == 5
    env = BlackjackEnv(offer_insurance=True, shoe_composition=True)
    assert env.action_space.n == 7
    assert "seen" in env.observation_space.spaces


# ------------------------------------------------------------------ rounds
def test_stand_win():
    env, obs, info = stacked([K, 9, 9, 8])  # player K 9, dealer 9 8
    assert obs["player_total"] == 19 and obs["dealer_upcard"] == 9
    assert obs["soft"] == 0 and obs["pair"] == 0 and obs["num_cards"] == 2
    assert not info["auto"]
    obs, reward, term, trunc, info = act(env, Action.STAND)
    assert term and not trunc
    assert reward == 1.0 and info["outcomes"] == ("win",)


def test_rewards_in_units_of_the_bet():
    env, *_ = stacked([6, 9, 5, K, 10])  # 11 vs 9 (hole K), double gets 10
    _, reward, term, *_ = act(env, Action.DOUBLE)
    assert term and reward == 1.0 * 2

    env, *_ = stacked([K, 10, 6, 9, 10])  # hard 16 vs 10, hit gets 10 and busts
    _, reward, term, _, info = act(env, Action.HIT)
    assert term and reward == -1.0 and info["outcomes"] == ("bust",)

    env, *_ = stacked([K, 10, 6, 9], rules={"surrender": "late"})
    _, reward, term, *_ = act(env, Action.SURRENDER)
    assert term and reward == -0.5


def test_natural_is_a_one_step_episode():
    env, obs, info = stacked([A, 9, K, 7])
    assert info["auto"] and env.decision is None
    assert info["action_mask"].tolist() == [True, False, False, False, False]
    assert obs["player_total"] == 21
    _, reward, term, *_ = act(env, Action.STAND)
    assert term and reward == 1.5


def test_split_is_several_steps_one_reward():
    # 8 8 vs 6 (hole K): split, first hand gets 3 -> 11, doubles and gets 9 -> 20;
    # second hand gets 10 -> 18 and stands; dealer draws 7 and busts
    env, obs, info = stacked([8, 6, 8, K, 3, 9, 10, 7])
    assert obs["pair"] == 1 and info["action_mask"][env.actions.index(Action.SPLIT)]
    obs, reward, term, *_ = act(env, Action.SPLIT)
    assert not term and reward == 0.0
    assert obs["num_hands"] == 2 and obs["player_total"] == 11
    obs, reward, term, *_ = act(env, Action.DOUBLE)
    assert not term and obs["player_total"] == 18
    _, reward, term, _, info = act(env, Action.STAND)
    # dealer 6 K 7 = 23 busts: +2 on the double, +1 on the other hand
    assert term and reward == 3.0 and info["outcomes"] == ("win", "win")


def test_insurance_declined_unless_offered():
    env, obs, info = stacked([K, A, 9, 5])  # 19 vs Ace, no dealer blackjack
    assert obs["insurance"] == 0 and obs["player_total"] == 19

    env, obs, info = stacked([K, A, 9, 5], offer_insurance=True)
    assert obs["insurance"] == 1
    mask = info["action_mask"]
    assert [env.actions[i] for i in np.flatnonzero(mask)] == [Action.INSURANCE, Action.NO_INSURANCE]
    obs, reward, term, *_ = act(env, Action.INSURANCE)
    assert not term and obs["insurance"] == 0
    _, reward, term, _, info = act(env, Action.STAND)  # dealer A 5 draws K: 16, then 10 busts
    assert term and env.last_result.seats[0].insurance_bet == 5
    assert reward == pytest.approx((info["net"]) / 10)


def test_illegal_action_is_replaced_and_penalised():
    env, *_ = stacked([K, 9, 9, 8], illegal_action_penalty=0.25)
    _, reward, term, _, info = act(env, Action.SPLIT)  # not a pair
    assert info["illegal_action"] and term  # played as a stand
    assert reward == 1.0 - 0.25


def test_mask_matches_engine_legal_actions():
    env = BlackjackEnv(rules={"surrender": "late"})
    obs, info = env.reset(seed=3)
    agent = RandomAgent(3)
    for _ in range(500):
        done = False
        while not done:
            if env.decision is not None:
                legal = {env.actions[i] for i in np.flatnonzero(info["action_mask"])}
                assert legal == set(env.decision.legal)
            obs, _, done, _, info = env.step(agent.act(obs, info))
        obs, info = env.reset()


# ------------------------------------------------------------ reproducibility
def rollout(seed, n=300):
    env = BlackjackEnv(shoe_composition=True)
    agent = RandomAgent(seed)
    out = []
    obs, info = env.reset(seed=seed)
    for _ in range(n):
        done = False
        while not done:
            obs, r, done, _, info = env.step(agent.act(obs, info))
            out.append((obs["player_total"], obs["dealer_upcard"], tuple(obs["seen"]), r))
        obs, info = env.reset()
    return out


def test_seeded_reproducibility():
    assert rollout(7) == rollout(7)
    assert rollout(7) != rollout(8)


def test_basic_strategy_agent_matches_the_simulator():
    """Through the env, basic strategy plays exactly the rounds play_round plays."""
    rules = Rules(surrender="late")
    env = BlackjackEnv(rules=rules)
    env.reset(seed=11)
    env.table = Table(rules, 1, random.Random(99))  # reset() without a seed keeps it
    table = Table(rules, 1, random.Random(99))
    agent = BasicStrategyAgent(env)
    policy = BasicStrategy()

    obs, info = env.reset()
    for _ in range(2000):
        expected = play_round(table, [rules.table_min], [policy]).seats[0].net / rules.table_min
        ret, done = 0.0, False
        while not done:
            obs, r, done, _, info = env.step(agent.act(obs, info))
            ret += r
        assert ret == pytest.approx(expected)
        obs, info = env.reset()


def test_learning_agent_beats_random():
    env = BlackjackEnv()
    agent = QLearningAgent(env.action_space.n, seed=0)
    agent.train(env, 20_000, seed=0)
    learned = evaluate(agent, env, 5_000, seed=1)
    rand = evaluate(RandomAgent(0), env, 5_000, seed=1)
    assert learned.mean > rand.mean + 0.2
