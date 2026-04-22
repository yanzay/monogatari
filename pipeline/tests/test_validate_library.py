"""Run the full validator on every story in the library.

This is the build-time twin of `python pipeline/validate.py
stories/story_N.json` invoked manually for every N. By living inside
the pytest suite it becomes the authoritative gate: a regression in any
of the 14 checks (1, 2, 3, 3.5, 3.6, 3.7, 3.8, 4, 5, 6, 7, 9, 10, 11) on
any of the 30 stories now fails the suite.

Test layout:
    * One parametrised test per story_*.json on disk.
    * Each test loads vocab_state.json + grammar_state.json + the
      story, runs `validate(...)` exactly as the CLI does, and asserts
      `result.valid is True`.
    * Failure messages list every error with check number + location +
      message so the offender is obvious.

This subsumes the standalone CLI invocation
(`python pipeline/validate.py ...`) for the purposes of the test suite —
that script is preserved as a one-shot author tool but its checks are
now also enforced here.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))

from validate import validate  # noqa: E402


@pytest.fixture(scope="module")
def vocab_state() -> dict:
    return json.loads((ROOT / "data" / "vocab_state.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def grammar_state() -> dict:
    return json.loads((ROOT / "data" / "grammar_state.json").read_text(encoding="utf-8"))


def _all_story_paths() -> list[Path]:
    stories_dir = ROOT / "stories"
    return sorted(
        (p for p in stories_dir.glob("story_*.json")),
        key=lambda p: int(p.stem.split("_")[1]),
    )


@pytest.mark.parametrize(
    "story_path",
    _all_story_paths(),
    ids=lambda p: p.stem,
)
def test_story_passes_all_validator_checks(
    story_path: Path,
    vocab_state: dict,
    grammar_state: dict,
) -> None:
    """Every story on disk must pass the full validator (Checks 1–11)."""
    story = json.loads(story_path.read_text(encoding="utf-8"))
    result = validate(story, vocab_state, grammar_state, plan=None)

    if not result.valid:
        # Build a readable, grouped error message for the failure output.
        by_check: dict[str, list[str]] = {}
        for err in result.errors:
            by_check.setdefault(str(err.check), []).append(
                f"  [{err.location}] {err.message}" if err.location else f"  {err.message}"
            )
        lines = [f"\n{story_path.name}: validate() reported {len(result.errors)} error(s):"]
        for check_id in sorted(by_check, key=lambda k: (len(k), k)):
            lines.append(f"\nCheck {check_id}:")
            lines.extend(by_check[check_id])
        pytest.fail("\n".join(lines))
