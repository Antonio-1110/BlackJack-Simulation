"""Streamlit frontend for configuring and comparing blackjack strategies.

Run with:  streamlit run app/streamlit_app.py
"""

from __future__ import annotations

import json
import sys
from concurrent.futures.process import BrokenProcessPool
from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from blackjack_sim.engine import Rules  # noqa: E402
from blackjack_sim.engine.rules import DOUBLE_OPTIONS, SURRENDER_OPTIONS  # noqa: E402
from blackjack_sim.simulation import (  # noqa: E402
    SUMMARY_COLUMNS,
    Candidate,
    ExperimentConfig,
    SessionSettings,
    run_experiment,
)
from blackjack_sim.simulation.export import percentile_frame, sessions_frame  # noqa: E402
from blackjack_sim.strategies import BET_STRATEGIES, PLAY_STRATEGIES, default_params  # noqa: E402

MAX_CANDIDATES = 8
# Categorical palette, fixed slot order (never cycled). Light / dark steps.
PALETTE_LIGHT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
PALETTE_DARK = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"]

st.set_page_config(page_title="Blackjack strategy lab", page_icon="🃏", layout="wide")


# ----------------------------------------------------------------- state
def _init_state() -> None:
    if "config" not in st.session_state:
        preset = ROOT / "configs" / "progressions.json"
        cfg = ExperimentConfig.load(preset) if preset.exists() else ExperimentConfig()
        _set_config(cfg.to_dict())
    st.session_state.setdefault("result", None)


def _set_config(data: dict) -> None:
    """Replace the whole config; bumping the version gives every widget a fresh key."""
    st.session_state["config"] = data
    st.session_state["version"] = st.session_state.get("version", 0) + 1
    st.session_state["cands"] = [
        {"uid": i, **c} for i, c in enumerate(data["candidates"])
    ]
    st.session_state["next_uid"] = len(data["candidates"])


def _key(*parts) -> str:
    return "_".join(str(p) for p in (st.session_state["version"], *parts))


def _is_dark() -> bool:
    try:
        return st.context.theme.type == "dark"
    except Exception:
        return False


def _palette() -> list[str]:
    return PALETTE_DARK if _is_dark() else PALETTE_LIGHT


# --------------------------------------------------------------- widgets
def param_widget(param, value, key: str):
    label = param.name.replace("_", " ").capitalize()
    if param.kind is bool:
        return st.checkbox(label, value=bool(value), key=key, help=param.help or None)
    if param.choices:
        options = list(param.choices)
        index = options.index(value) if value in options else 0
        return st.selectbox(label, options, index=index, key=key, help=param.help or None)
    if param.kind is int:
        return int(st.number_input(
            label, value=int(value), step=1, key=key, help=param.help or None,
            min_value=int(param.min) if param.min is not None else None,
            max_value=int(param.max) if param.max is not None else None,
        ))
    if param.kind is float:
        return float(st.number_input(
            label, value=float(value), step=float(param.step or 0.1), key=key, help=param.help or None,
            min_value=float(param.min) if param.min is not None else None,
            max_value=float(param.max) if param.max is not None else None,
            format="%g",
        ))
    return st.text_input(label, value=str(value), key=key, help=param.help or None)


def strategy_picker(title: str, registry: dict, spec: dict, key: str) -> dict:
    keys = list(registry)
    current = spec.get("type", keys[0])
    choice = st.selectbox(
        title, keys, index=keys.index(current) if current in keys else 0,
        format_func=lambda k: registry[k].label or k, key=_key(key, "type"),
    )
    cls = registry[choice]
    if cls.description:
        st.caption(cls.description)
    values = default_params(cls)
    if choice == current:
        values.update(spec.get("params") or {})
    params = {}
    cols = st.columns(2)
    for i, p in enumerate(cls.params):
        with cols[i % 2]:
            params[p.name] = param_widget(p, values[p.name], _key(key, choice, p.name))
    return {"type": choice, "params": params}


def rules_sidebar(data: dict) -> dict:
    r = {**Rules().to_dict(), **data}
    st.subheader("Shoe")
    r["num_decks"] = int(st.number_input("Decks", 1, 8, int(r["num_decks"]), key=_key("decks")))
    r["penetration"] = st.slider("Penetration (cut card)", 0.3, 0.95, float(r["penetration"]), 0.05,
                                 key=_key("pen"), help="Fraction of the shoe dealt before reshuffling.")
    r["continuous_shuffle"] = st.checkbox("Continuous shuffler", bool(r["continuous_shuffle"]), key=_key("csm"))
    st.subheader("Dealer & payouts")
    r["dealer_hits_soft_17"] = st.checkbox("Dealer hits soft 17 (H17)", bool(r["dealer_hits_soft_17"]),
                                           key=_key("h17"))
    r["dealer_peeks"] = st.checkbox("Dealer peeks for blackjack", bool(r["dealer_peeks"]), key=_key("peek"),
                                    help="Off = European no-hole-card game.")
    if not r["dealer_peeks"]:
        r["no_peek_original_bets_only"] = st.checkbox(
            "Dealer BJ takes original bets only", bool(r["no_peek_original_bets_only"]), key=_key("obo"))
    payouts = {"3:2": 1.5, "6:5": 1.2, "1:1": 1.0, "2:1": 2.0}
    current = next((k for k, v in payouts.items() if abs(v - r["blackjack_payout"]) < 1e-9), "3:2")
    r["blackjack_payout"] = payouts[st.selectbox("Blackjack pays", list(payouts),
                                                 index=list(payouts).index(current), key=_key("bj"))]
    r["insurance"] = st.checkbox("Insurance offered", bool(r["insurance"]), key=_key("ins"))
    st.subheader("Player options")
    r["double_on"] = st.selectbox("Double on", DOUBLE_OPTIONS, index=DOUBLE_OPTIONS.index(r["double_on"]),
                                  key=_key("dbl"))
    r["double_after_split"] = st.checkbox("Double after split", bool(r["double_after_split"]), key=_key("das"))
    r["max_split_hands"] = int(st.number_input("Max hands after splitting", 1, 8, int(r["max_split_hands"]),
                                               key=_key("split")))
    r["resplit_aces"] = st.checkbox("Resplit aces", bool(r["resplit_aces"]), key=_key("rsa"))
    r["hit_split_aces"] = st.checkbox("Hit split aces", bool(r["hit_split_aces"]), key=_key("hsa"))
    r["surrender"] = st.selectbox("Surrender", SURRENDER_OPTIONS,
                                  index=SURRENDER_OPTIONS.index(r["surrender"]), key=_key("sur"))
    r["charlie_cards"] = int(st.number_input("Charlie (auto-win at N cards, 0 = off)", 0, 10,
                                             int(r["charlie_cards"]), key=_key("charlie")))
    st.subheader("Table limits")
    c1, c2 = st.columns(2)
    r["table_min"] = c1.number_input("Min bet", 1.0, value=float(r["table_min"]), key=_key("tmin"))
    r["table_max"] = c2.number_input("Max bet", 1.0, value=float(r["table_max"]), key=_key("tmax"))
    return r


def session_sidebar(data: dict) -> dict:
    s = {**SessionSettings().__dict__, **data}
    c1, c2 = st.columns(2)
    s["rounds"] = int(c1.number_input("Rounds / session", 1, 1_000_000, int(s["rounds"]), step=100,
                                      key=_key("rounds")))
    s["sessions"] = int(c2.number_input("Sessions", 1, 100_000, int(s["sessions"]), step=100,
                                        key=_key("sessions"), help="Monte Carlo repetitions per candidate."))
    s["bankroll"] = st.number_input("Starting bankroll", 1.0, value=float(s["bankroll"]), step=100.0,
                                    key=_key("bankroll"))
    c1, c2 = st.columns(2)
    s["win_target"] = c1.number_input("Win target (0 = off)", 0.0, value=float(s["win_target"]), step=50.0,
                                      key=_key("target"))
    s["stop_loss"] = c2.number_input("Stop loss (0 = off)", 0.0, value=float(s["stop_loss"]), step=50.0,
                                     key=_key("stop"))
    s["other_players"] = int(st.number_input("Other players at the table", 0, 6, int(s["other_players"]),
                                             key=_key("others"),
                                             help="Flat-betting basic-strategy players that use up cards."))
    s["seed"] = int(st.number_input("Random seed", 0, value=int(s["seed"]), key=_key("seed")))
    return s


# ---------------------------------------------------------------- charts
def _color_scale(names: list[str]) -> alt.Scale:
    return alt.Scale(domain=names, range=_palette()[: len(names)])


def _downsample(n: int, max_points: int = 400) -> np.ndarray:
    return np.unique(np.linspace(0, n, min(n + 1, max_points)).astype(int))


def bankroll_chart(result, show_band: bool, stat: str = "median") -> alt.Chart:
    pct = percentile_frame(result)
    idx = _downsample(len(pct) - 1)
    names = [c.name for c in result.candidates]
    rows = []
    sub = pct.iloc[idx]
    for i, name in enumerate(names):
        rows.append(pd.DataFrame({
            "round": sub.index, "candidate": name, "cid": f"c{i}", "median": sub[f"{name}|p50"].values,
            "mean": sub[f"{name}|mean"].values, "p5": sub[f"{name}|p5"].values,
            "p95": sub[f"{name}|p95"].values,
        }))
    df = pd.concat(rows)
    color = alt.Color("candidate:N", scale=_color_scale(names), legend=alt.Legend(title=None, orient="top"))
    base = alt.Chart(df).encode(x=alt.X("round:Q", title="Round"))
    hover = alt.selection_point(fields=["round"], nearest=True, on="pointerover", empty=False)
    lines = base.mark_line(strokeWidth=2).encode(
        y=alt.Y(f"{stat}:Q", title=f"Bankroll ({stat} across sessions)", scale=alt.Scale(zero=False)),
        color=color,
    )
    layers = []
    if show_band:
        layers.append(base.mark_area(opacity=0.12).encode(y="p5:Q", y2="p95:Q", color=color))
    layers.append(lines)
    rule = base.mark_rule(color="#898781").encode(
        opacity=alt.condition(hover, alt.value(0.6), alt.value(0)),
        tooltip=[alt.Tooltip("round:Q", title="Round")] + [
            alt.Tooltip(f"c{i}:Q", title=n, format=",.0f") for i, n in enumerate(names)
        ],
    ).transform_pivot("cid", value=stat, groupby=["round"]).add_params(hover)
    points = lines.mark_point(size=60, filled=True).encode(
        opacity=alt.condition(hover, alt.value(1), alt.value(0))
    )
    return alt.layer(*layers, rule, points).properties(height=380)


def final_distribution_chart(result) -> alt.Chart:
    names = [c.name for c in result.candidates]
    df = pd.DataFrame(
        [{"candidate": c.name, "net": s.net} for c in result.candidates for s in c.sessions]
    )
    lo, hi = np.percentile(df["net"], [0.5, 99.5])
    df = df[(df["net"] >= lo) & (df["net"] <= hi)]
    color = alt.Color("candidate:N", scale=_color_scale(names), legend=None)
    base = alt.Chart()
    bars = base.mark_bar(cornerRadiusTopLeft=2, cornerRadiusTopRight=2).encode(
        x=alt.X("net:Q", bin=alt.Bin(maxbins=40), title="Session profit"),
        y=alt.Y("count():Q", title="Sessions"),
        color=color,
        tooltip=[alt.Tooltip("net:Q", bin=alt.Bin(maxbins=40), title="Profit range", format=",.0f"),
                 alt.Tooltip("count():Q", title="Sessions")],
    )
    zero = base.mark_rule(color="#898781", strokeDash=[4, 3]).encode(x=alt.datum(0))
    return alt.layer(bars, zero, data=df).properties(height=150, width=720).facet(
        row=alt.Row("candidate:N", title=None, sort=names, header=alt.Header(labelAngle=0, labelAlign="left"))
    ).resolve_scale(y="independent")


def risk_return_chart(summary: pd.DataFrame) -> alt.Chart:
    names = list(summary.index)
    df = summary.reset_index()
    color = alt.Color("candidate:N", scale=_color_scale(names), legend=alt.Legend(title=None, orient="top"))
    base = alt.Chart(df).encode(
        x=alt.X("std_net:Q", title="Risk: std dev of session profit"),
        y=alt.Y("mean_net:Q", title="Return: mean session profit"),
    )
    pts = base.mark_circle(size=140, stroke="white", strokeWidth=2, opacity=1).encode(
        color=color,
        tooltip=["candidate", alt.Tooltip("mean_net:Q", format=",.1f", title="Mean profit"),
                 alt.Tooltip("std_net:Q", format=",.1f", title="Std dev"),
                 alt.Tooltip("edge_pct:Q", format=".2f", title="Edge %"),
                 alt.Tooltip("prob_profit:Q", format=".0%", title="P(profit)")],
    )
    labels = base.mark_text(align="left", dx=10, dy=-6).encode(text="candidate")
    zero = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(color="#898781", strokeDash=[4, 3]).encode(y="y:Q")
    return (zero + pts + labels).properties(height=380)


def sample_paths_chart(cand, rounds: int, n: int, color: str) -> alt.Chart:
    paths = cand.paths(rounds)[:n]
    idx = _downsample(rounds)
    df = pd.DataFrame(
        [(i, int(r), float(paths[i, r])) for i in range(len(paths)) for r in idx],
        columns=["session", "round", "bankroll"],
    )
    return alt.Chart(df).mark_line(strokeWidth=1.5, opacity=0.45, color=color).encode(
        x=alt.X("round:Q", title="Round"),
        y=alt.Y("bankroll:Q", title="Bankroll", scale=alt.Scale(zero=False)),
        detail="session:N",
        tooltip=["session", "round", alt.Tooltip("bankroll:Q", format=",.0f")],
    ).properties(height=320)


# ------------------------------------------------------------------- page
def main() -> None:
    _init_state()
    cfg = st.session_state["config"]

    st.title("Blackjack strategy lab")
    st.caption(
        "Pick table rules, then compare player profiles (a play strategy plus a bet-sizing strategy) "
        "over many simulated sessions. Every profile plays the same shuffled shoes, so the "
        "differences you see come from the strategies, not luck of the draw."
    )

    # ---- sidebar: presets, rules, session
    with st.sidebar:
        st.header("Setup")
        presets = sorted((ROOT / "configs").glob("*.json"))
        with st.expander("Load / save configuration", expanded=False):
            if presets:
                name = st.selectbox("Preset", [p.stem for p in presets], key="preset_choice")
                if st.button("Load preset"):
                    _set_config(ExperimentConfig.load(ROOT / "configs" / f"{name}.json").to_dict())
                    st.session_state["result"] = None
                    st.rerun()
            upload = st.file_uploader("Load JSON config", type="json")
            if upload is not None and st.button("Apply uploaded config"):
                try:
                    _set_config(ExperimentConfig.from_dict(json.load(upload)).to_dict())
                    st.session_state["result"] = None
                    st.rerun()
                except (ValueError, KeyError, json.JSONDecodeError) as e:
                    st.error(f"Invalid config: {e}")
        with st.expander("Table rules", expanded=False):
            rules = rules_sidebar(cfg["rules"])
        with st.expander("Sessions", expanded=True):
            session = session_sidebar(cfg["session"])
        workers = st.number_input("Worker processes", 1, 64, 4, help="Parallel processes for the simulation.")

    # ---- candidates
    st.subheader("Player profiles")
    cands = st.session_state["cands"]
    new_cands = []
    remove = None
    cols = st.columns(2)
    for i, c in enumerate(cands):
        play_label = PLAY_STRATEGIES.get(c["play"]["type"], PLAY_STRATEGIES["basic"]).label
        bet_label = BET_STRATEGIES.get(c["bet"]["type"], BET_STRATEGIES["flat"]).label
        with cols[i % 2].expander(f"**{c['name']}** · {play_label} + {bet_label}",
                                  expanded=c["uid"] == st.session_state.get("open_uid")):
            top = st.columns([6, 1])
            name = top[0].text_input("Name", c["name"], key=_key(c["uid"], "name"))
            top[0].markdown(
                f"<span style='display:inline-block;width:10px;height:10px;border-radius:2px;"
                f"background:{_palette()[i]};margin-right:6px'></span><small>chart colour</small>",
                unsafe_allow_html=True,
            )
            if top[1].button("✕", key=_key(c["uid"], "remove"), help="Remove this profile",
                             disabled=len(cands) == 1):
                remove = c["uid"]
            play = strategy_picker("Play strategy", PLAY_STRATEGIES, c["play"], f"{c['uid']}_play")
            bet = strategy_picker("Bet strategy", BET_STRATEGIES, c["bet"], f"{c['uid']}_bet")
            new_cands.append({"uid": c["uid"], "name": name, "play": play, "bet": bet})

    if remove is not None:
        st.session_state["cands"] = [c for c in new_cands if c["uid"] != remove]
        st.rerun()
    # Expander titles are drawn before their widgets, so refresh when a title would change.
    def title(c):
        return c["name"], c["play"]["type"], c["bet"]["type"]

    changed = [n["uid"] for o, n in zip(cands, new_cands) if title(o) != title(n)]
    st.session_state["cands"] = new_cands
    if changed:
        st.session_state["open_uid"] = changed[0]
        st.rerun()

    add_col, run_col, _ = st.columns([1, 1, 3])
    if add_col.button("＋ Add profile", disabled=len(cands) >= MAX_CANDIDATES):
        uid = st.session_state["next_uid"]
        st.session_state["next_uid"] += 1
        st.session_state["open_uid"] = uid
        st.session_state["cands"].append({
            "uid": uid, "name": f"Profile {len(cands) + 1}",
            "play": {"type": "basic", "params": {}}, "bet": {"type": "flat", "params": {}},
        })
        st.rerun()

    config_dict = {
        "rules": rules,
        "session": session,
        "candidates": [{k: c[k] for k in ("name", "play", "bet")} for c in st.session_state["cands"]],
    }
    st.session_state["config"] = config_dict
    try:
        experiment = ExperimentConfig.from_dict(config_dict)
        error = None
    except (ValueError, TypeError) as e:
        experiment, error = None, str(e)
    if error:
        st.error(error)

    hands = session["rounds"] * session["sessions"] * len(config_dict["candidates"])
    run = run_col.button("▶ Run simulation", type="primary", disabled=experiment is None)
    st.caption(f"Up to {hands:,} hands in total.")

    if run and experiment is not None:
        bar = st.progress(0.0, text="Simulating…")

        def progress(done, total):
            bar.progress(done / total, text=f"Simulating… {done:,}/{total:,} sessions")

        try:
            result = run_experiment(experiment, workers=int(workers), progress=progress)
        except (BrokenProcessPool, OSError, RuntimeError):
            result = run_experiment(experiment, workers=1, progress=progress)
        bar.empty()
        st.session_state["result"] = result

    result = st.session_state.get("result")
    if result is None:
        st.info("Configure the profiles and press **Run simulation**.")
        return
    show_results(result)


def show_results(result) -> None:
    cfg = result.config
    names = [c.name for c in result.candidates]
    summary = result.summary_frame()
    st.divider()
    st.subheader("Results")
    st.caption(
        f"{len(names)} profile(s) × {cfg.session.sessions:,} sessions × up to {cfg.session.rounds:,} rounds, "
        f"simulated in {result.elapsed:.1f}s."
    )

    # Headline tiles: the edge is the one number bet sizing can't change without information.
    tiles = st.columns(min(len(names), 4))
    for i, name in enumerate(names):
        row = summary.loc[name]
        tiles[i % len(tiles)].metric(
            f"{name} · profit per session",
            f"{row['mean_net']:+,.0f}",
            f"{row['edge_pct']:+.2f}% edge (± {1.96 * row['edge_se_pct']:.2f})",
            delta_color="normal",
            help="Mean profit per session. Edge = total profit / total initial bets, with a 95% interval.",
        )

    views = ["Summary", "Bankroll over time", "Profit distribution", "Risk vs return", "Hand log", "Export"]
    view = st.segmented_control("View", views, default="Summary", key="view", label_visibility="collapsed")
    view = view or "Summary"
    if view == "Summary":
        table = summary.rename(columns=SUMMARY_COLUMNS).T
        st.dataframe(table.style.format("{:,.3f}"), width="stretch", height=680)
        st.markdown(
            "**How to read this.** Without card counting, rounds are essentially independent, so any "
            "bet-sizing scheme leaves the *edge* (return per unit bet) unchanged. It only reshapes how "
            "results are spread. Martingale-style systems raise *P(profit)* but pay for it with rare, huge "
            "losses (see *P(ruin)* and the 5th percentile). Only bet sizes that track a card count "
            "change the edge itself. Differences smaller than about two standard errors are noise."
        )
    elif view == "Bankroll over time":
        c1, c2 = st.columns([1, 3])
        stat = c1.radio("Line shows", ["median", "mean"], horizontal=True,
                        help="Median = the typical session. Mean = expected value (includes rare big wins).")
        band = c2.checkbox("Show 5–95% band", value=len(names) <= 3)
        st.altair_chart(bankroll_chart(result, band, stat), width="stretch")
        st.caption("Bankroll across sessions after each round. Sessions that ended early "
                   "(ruin, target or stop loss) hold their final bankroll.")
        pick = st.selectbox("Sample sessions for", names, key="paths_for")
        n = st.slider("How many sessions", 5, min(100, cfg.session.sessions), min(30, cfg.session.sessions)) \
            if cfg.session.sessions > 5 else cfg.session.sessions
        cand = result[pick]
        st.altair_chart(sample_paths_chart(cand, cfg.session.rounds, n, _palette()[names.index(pick)]),
                        width="stretch")
    elif view == "Profit distribution":
        st.altair_chart(final_distribution_chart(result), width="stretch")
        st.caption("Distribution of session profit (outer 1% trimmed). The dashed line marks break-even.")
    elif view == "Risk vs return":
        st.altair_chart(risk_return_chart(summary), width="stretch")
        st.caption("Up and to the left is better. Bet systems without information mostly move right "
                   "(more risk) and down (bigger average loss, since more money is bet).")
    elif view == "Hand log":
        pick = st.selectbox("Profile", names, key="log_for")
        log = result[pick].sessions[0].log
        if log:
            st.caption("Every hand of session #0: use it to check the game mechanics hand by hand.")
            st.dataframe(pd.DataFrame(log), width="stretch", height=520, hide_index=True)
        else:
            st.info("No hand log was recorded.")
    elif view == "Export":
        st.download_button("Config (JSON)", json.dumps(cfg.to_dict(), indent=2), "config.json",
                           "application/json")
        st.download_button("Summary (CSV)", summary.to_csv(), "summary.csv", "text/csv")
        st.download_button("All sessions (CSV)", sessions_frame(result).to_csv(index=False), "sessions.csv",
                           "text/csv")
        st.download_button("Bankroll percentiles by round (CSV)", percentile_frame(result).to_csv(),
                           "bankroll_percentiles.csv", "text/csv")


if __name__ == "__main__":
    main()
