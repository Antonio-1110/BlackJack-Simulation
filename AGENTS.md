# Working on this repo (humans and AI agents)

Several sessions (people or Claude) often work here at the same time. These rules keep
them from stepping on each other. README.md explains what the project does; this file
explains how to change it.

## Commands

```bash
pip install -e ".[app,dev]"                  # everything, editable
python -m pytest                             # all tests; must pass before every push
python scripts/build_web.py build/web        # build the browser Strategy Lab
python scripts/smoke_web.py build/web        # run its examples the way the browser does
python -m http.server -d build/web           # try the Lab at http://localhost:8000
```

`tests/test_readme.py` runs every ```` ```python ```` block in README.md, so a README
example that stops working fails the tests.

## Branches

- Commit small and often to `main`, and push after every commit:
  `git pull --rebase origin main`, run the tests, `git push origin main`.
- A session that can only push to its own branch (Claude cloud sessions push to
  `claude/...`) opens a small draft PR instead, and keeps it short-lived.
- Never force-push `main`, rewrite history, or revert someone else's commit to make
  yours fit. On a rebase conflict, keep both sides' intent; if that's unclear, ask.
- Never leave `main` broken. Push only passing code, stubbed or unwired if unfinished.
- Every push to `main` that touches `web/`, `blackjack_sim/` or the build scripts
  redeploys the live Strategy Lab (`.github/workflows/pages.yml`).

## Issues are the to-do list

1. Find the issue, or create one with a **Files** section (the files it owns) and a
   **Blocked by** list. The issue template has both.
2. Labelled `in-progress`? Someone owns it; leave it alone.
3. Claim it: add `in-progress` and comment `Claimed by <who/which session>`.
4. Finish with `Closes #N` in the last commit (or the PR body) and remove the label.
   Tick it off in the roadmap, issue #3. Extra work you find becomes a new issue.

Only edit the files your issue lists. Split issues along file lines; if two tasks need
the same file, make one block the other.

## Shared files

Anyone may make small, additive edits (add a line, a field, a command; don't reorder,
reformat or rename) to: `README.md`, `AGENTS.md`, `pyproject.toml`,
`requirements.txt`, `blackjack_sim/__main__.py` (CLI wiring),
`blackjack_sim/strategies/registry.py` and the `__init__.py` files. Push those edits
right away. Anything bigger is its own issue.

## Layout (one area per kind of work)

| Area | Path |
|---|---|
| Game mechanics | `blackjack_sim/engine/` |
| Play strategies | `blackjack_sim/strategies/play/` (one module per family) |
| Bet strategies | `blackjack_sim/strategies/betting/` |
| Experiments, stats, export | `blackjack_sim/simulation/` |
| Gymnasium env | `blackjack_sim/rl/` |
| Browser Strategy Lab | `web/`, `blackjack_sim/playground.py`, `scripts/build_web.py`, `scripts/smoke_web.py` |
| Streamlit frontend | `app/` |
| Example experiments | `configs/` |
| Tests | `tests/` (one file per area) |

New strategies are new modules that register themselves with `@register_play` /
`@register_bet`; prefer adding a file over editing a central one.

## Other rules

- Secrets come from environment variables and are never committed; list any new
  variable in README.md. (There are none today.)
- Strategies only see what a player at a real table could see (README §4).
- Nothing here places real bets or connects to a real casino.
