"""Write experiment results to disk (CSV + the exact config used)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .experiment import ExperimentResult


def percentile_frame(result: ExperimentResult, percentiles=(5, 25, 50, 75, 95)) -> pd.DataFrame:
    """Per-round bankroll percentiles and mean, one block of columns per candidate."""
    frames = []
    for cand in result.candidates:
        paths = cand.paths(result.config.session.rounds)
        data = {f"{cand.name}|p{p}": np.percentile(paths, p, axis=0) for p in percentiles}
        data[f"{cand.name}|mean"] = paths.mean(axis=0)
        frames.append(pd.DataFrame(data))
    df = pd.concat(frames, axis=1)
    df.index.name = "round"
    return df


def sessions_frame(result: ExperimentResult) -> pd.DataFrame:
    rows = []
    for cand in result.candidates:
        for i, s in enumerate(cand.sessions):
            rows.append(
                {
                    "candidate": cand.name,
                    "session": i,
                    "rounds": s.rounds,
                    "hands": s.hands,
                    "net": s.net,
                    "final_bankroll": s.final,
                    "initial_bet_total": s.initial_bet_total,
                    "wagered_total": s.wagered_total,
                    "max_bet": s.max_bet,
                    "max_drawdown": s.max_drawdown,
                    "ruined": s.ruined,
                    "hit_target": s.hit_target,
                    "hit_stop_loss": s.hit_stop_loss,
                }
            )
    return pd.DataFrame(rows)


def write_results(result: ExperimentResult, out_dir: str | Path) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "config.json").write_text(json.dumps(result.config.to_dict(), indent=2) + "\n")
    result.summary_frame().to_csv(out / "summary.csv")
    sessions_frame(result).to_csv(out / "sessions.csv", index=False)
    percentile_frame(result).to_csv(out / "bankroll_percentiles.csv")
    for cand in result.candidates:
        log = cand.sessions[0].log if cand.sessions else None
        if log:
            safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in cand.name)
            pd.DataFrame(log).to_csv(out / f"hand_log_{safe}.csv", index=False)
    return out
