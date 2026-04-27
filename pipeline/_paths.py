"""Shared path discovery + JSON I/O for the whole pipeline package.

Replaces six copies of `ROOT = Path(__file__).resolve().parent.parent` and
three different `load_json` variants scattered across the package.

Import this from anywhere under `pipeline/` (including `pipeline/tools/`):

    from _paths import ROOT, STORIES, DATA, INPUTS
    from _paths import iter_stories, iter_specs, load_story, load_spec
    from _paths import load_vocab, load_grammar, load_grammar_catalog
    from _paths import read_json, write_json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Iterator

# ── Canonical paths ──────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parent.parent
PIPELINE = ROOT / "pipeline"
INPUTS = PIPELINE / "inputs"
STORIES = ROOT / "stories"
DATA = ROOT / "data"

VOCAB_STATE = DATA / "vocab_state.json"
GRAMMAR_STATE = DATA / "grammar_state.json"
GRAMMAR_CATALOG = DATA / "grammar_catalog.json"

# Make sibling modules importable when this package is run as scripts.
if str(PIPELINE) not in sys.path:
    sys.path.insert(0, str(PIPELINE))


# ── Story-id helpers ─────────────────────────────────────────────────────────

def parse_story_id(arg: str | int | Path) -> int:
    """Accept 12, '12', 'story_12', or a Path like 'story_12.json'."""
    if isinstance(arg, int):
        return arg
    if isinstance(arg, Path):
        arg = arg.stem
    s = str(arg)
    # Strip "story_" prefix and any ".bilingual" / ".json" suffix.
    if s.startswith("story_"):
        s = s[len("story_"):]
    s = s.split(".")[0]
    return int(s)


# ── JSON I/O ─────────────────────────────────────────────────────────────────

def read_json(path: Path | str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: Path | str, data: dict, *, sort_keys: bool = False) -> None:
    """Write JSON deterministically with a trailing newline."""
    Path(path).write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=sort_keys) + "\n",
        encoding="utf-8",
    )


# ── State / catalog loaders ──────────────────────────────────────────────────

def load_vocab() -> dict:
    return read_json(VOCAB_STATE)


def load_grammar() -> dict:
    return read_json(GRAMMAR_STATE)


def load_grammar_catalog() -> dict:
    return read_json(GRAMMAR_CATALOG)


# ── Story / spec loaders ─────────────────────────────────────────────────────

def story_path(story_id: int) -> Path:
    return STORIES / f"story_{story_id}.json"


def spec_path(story_id: int) -> Path:
    return INPUTS / f"story_{story_id}.bilingual.json"


def load_story(story_id: int) -> dict:
    return read_json(story_path(story_id))


def load_spec(story_id: int) -> dict:
    return read_json(spec_path(story_id))


def save_spec(story_id: int, spec: dict) -> None:
    write_json(spec_path(story_id), spec)


# ── Library iteration ────────────────────────────────────────────────────────

def _id_from_path(p: Path) -> int:
    """Best-effort id parser; raises ValueError for unparseable names."""
    return parse_story_id(p)


def iter_stories(stories_dir: Path | None = None) -> Iterator[tuple[int, dict]]:
    """Yield (story_id, story) for every shipped story, in numeric order.

    Bad / unreadable files are skipped silently — the validator and other
    callers historically did the same.
    """
    base = stories_dir or STORIES
    paths = []
    for path in base.glob("story_*.json"):
        try:
            paths.append((_id_from_path(path), path))
        except (ValueError, IndexError):
            continue
    for sid, path in sorted(paths):
        try:
            yield sid, read_json(path)
        except Exception:
            continue


def iter_specs(inputs_dir: Path | None = None) -> Iterator[tuple[int, dict]]:
    """Yield (story_id, bilingual_spec) for every spec, in numeric order."""
    base = inputs_dir or INPUTS
    paths = []
    for path in base.glob("story_*.bilingual.json"):
        try:
            paths.append((_id_from_path(path), path))
        except (ValueError, IndexError):
            continue
    for sid, path in sorted(paths):
        yield sid, read_json(path)


def list_story_ids(stories_dir: Path | None = None) -> list[int]:
    """Sorted list of every shipped story id."""
    return [sid for sid, _ in iter_stories(stories_dir)]
