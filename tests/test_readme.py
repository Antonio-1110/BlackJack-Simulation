"""Run every ```python example in the README, in order, so the docs can't go stale."""

import re
from pathlib import Path

README = Path(__file__).resolve().parents[1] / "README.md"


def test_readme_python_examples_run():
    blocks = re.findall(r"```python\n(.*?)```", README.read_text(), flags=re.S)
    assert len(blocks) >= 5
    namespace: dict = {}
    for i, code in enumerate(blocks):
        try:
            exec(compile(code, f"README.md[python block {i}]", "exec"), namespace)
        except Exception as e:  # pragma: no cover - failure path
            raise AssertionError(f"README python block {i} failed: {e!r}\n{code}") from e
