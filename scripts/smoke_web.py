"""Check that a built Strategy Lab folder actually works before it is published.

    python scripts/build_web.py build/web
    python scripts/smoke_web.py build/web

It imports the package from ``blackjack_sim.zip`` exactly as the browser does
(with numpy and pandas blocked, since the page doesn't download them) and runs
every example strategy from ``examples.js`` for a few rounds. A failure here
means the live page would break, so the Pages workflow runs it before deploying.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

BLOCKED = ("numpy", "pandas", "gymnasium")


class _Block:
    """Meta path finder that makes the browser-only constraints explicit."""

    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in BLOCKED:
            raise ImportError(f"{name} is not available in the browser build")
        return None


def main(folder: Path) -> int:
    for name in ("index.html", "app.js", "worker.js", "examples.js", "blackjack_sim.zip"):
        if not (folder / name).is_file():
            print(f"missing {name} in {folder}")
            return 1

    sys.meta_path.insert(0, _Block())
    sys.path.insert(0, str(folder / "blackjack_sim.zip"))
    from blackjack_sim import playground

    examples = re.findall(r"code: `(.*?)`,", (folder / "examples.js").read_text(), re.S)
    if not examples:
        print("no examples found in examples.js")
        return 1
    settings = {"session": {"rounds": 30, "sessions": 2, "seed": 1}}
    for i, code in enumerate(examples):
        out = playground.run(code, settings)
        if out.get("error"):
            print(f"example {i} failed:\n{out['error']}")
            return 1
        print(f"example {i}: {out.get('play')} / {out.get('bet')} ok")
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path("build/web")))
