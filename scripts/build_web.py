"""Build the browser playground into a folder of static files.

    python scripts/build_web.py            # writes build/web/
    python -m http.server -d build/web     # then open http://localhost:8000

The output is plain files (the page plus ``blackjack_sim.zip``), so any static
host works; the GitHub Pages workflow publishes exactly this folder.
"""

from __future__ import annotations

import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# The RL package needs gymnasium, which the browser doesn't have.
SKIP_DIRS = {"__pycache__", "rl"}


def build(out: Path) -> Path:
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(ROOT / "web", out)
    package = ROOT / "blackjack_sim"
    with zipfile.ZipFile(out / "blackjack_sim.zip", "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(package.rglob("*.py")):
            rel = path.relative_to(package)
            if SKIP_DIRS.intersection(rel.parts[:-1]):
                continue
            zf.write(path, Path("blackjack_sim") / rel)
    (out / ".nojekyll").touch()
    return out


if __name__ == "__main__":
    target = build(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "build" / "web")
    print(f"Built {target}")
