# Contributing

Thanks for helping. The short version:

1. Pick an open issue from the [roadmap](https://github.com/Antonio-1110/BlackJack-Simulation/issues/3),
   or open one with the template. Comment on it so nobody else starts the same thing.
2. Set up and run the tests:

   ```bash
   python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
   pip install -e ".[app,dev]"
   python -m pytest
   ```

3. Make the change in the files the issue lists, with a test. Keep it small.
4. Open a pull request that says `Closes #N`.

## Where things go

- **A new play or bet strategy:** a new module in `blackjack_sim/strategies/play/` or
  `blackjack_sim/strategies/betting/`, registered with `@register_play` /
  `@register_bet`. README §2–§6 walk through designing, parameterising and testing one.
- **A rule or game mode:** `blackjack_sim/engine/` (every house rule is a field on
  `Rules`). Check the house edge against a published figure (README §11).
- **The browser Strategy Lab:** `web/` and `blackjack_sim/playground.py`. Build and try
  it locally:

  ```bash
  python scripts/build_web.py build/web
  python scripts/smoke_web.py build/web     # what CI checks before deploying
  python -m http.server -d build/web        # http://localhost:8000
  ```

  The page can only use the pure-Python parts of the package: numpy and pandas are not
  loaded in the browser.

## Things to know

- README examples are tests: `tests/test_readme.py` runs every Python block in
  README.md, so update them when you change an API.
- Merging to `main` redeploys the live Strategy Lab at
  <https://antonio-1110.github.io/BlackJack-Simulation/>.
- Several people and AI sessions work here in parallel. [AGENTS.md](AGENTS.md) has the
  rules that keep them out of each other's way; they apply to everyone.
