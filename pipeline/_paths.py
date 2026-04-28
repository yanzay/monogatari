"""Shared path discovery + JSON I/O for the whole pipeline package.

Replaces six copies of `ROOT = Path(__file__).resolve().parent.parent` and
three different `load_json` variants scattered across the package.

Import this from anywhere under `pipeline/` (including `pipeline/tools/`):

    from _paths import ROOT, STORIES, DATA, INPUTS, AUDIO, AUDIO_WORDS
    from _paths import VOCAB_STATE, GRAMMAR_STATE, GRAMMAR_CATALOG
    from _paths import FORBIDDEN_PATTERNS, ENGAGEMENT_BASELINE
    from _paths import iter_stories, iter_specs, load_story, load_spec
    from _paths import load_vocab, load_grammar, load_grammar_catalog
    from _paths import read_json, write_json
    from _paths import Backup
"""
from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable, Iterator

# ── Canonical paths ──────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parent.parent
PIPELINE = ROOT / "pipeline"
INPUTS = PIPELINE / "inputs"
STORIES = ROOT / "stories"
DATA = ROOT / "data"
AUDIO = ROOT / "audio"
AUDIO_WORDS = AUDIO / "words"
STATE_BACKUPS = ROOT / "state_backups"

VOCAB_STATE = DATA / "vocab_state.json"
GRAMMAR_STATE = DATA / "grammar_state.json"
GRAMMAR_CATALOG = DATA / "grammar_catalog.json"

# Pipeline-local config files (live alongside the .py modules, not under data/).
FORBIDDEN_PATTERNS = PIPELINE / "forbidden_patterns.json"
ENGAGEMENT_BASELINE = PIPELINE / "engagement_baseline.json"

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


# ── Back-compat alias ────────────────────────────────────────────────────────
# Some legacy call sites used `load_json(path)`. Prefer `read_json(path)` in new
# code; the alias is kept so old imports don't have to change in lockstep.
load_json = read_json


# ── State backups ────────────────────────────────────────────────────────────

class Backup:
    """Single source of truth for `state_backups/` writes.

    Centralises the three pre-existing call sites
    (`state_updater.backup`, `regenerate_all_stories.main`,
    `precheck.main`) behind one factory. All backups land under
    `STATE_BACKUPS` with a deterministic
    `<filename>_<YYYYMMDD_HHMMSS>.json` suffix; an optional
    `subdir` lets callers shard their backups by tool. Filenames are
    parseable with `Backup.parse_timestamp()` so retention scripts
    can sort + prune without opening files.
    """

    TIMESTAMP_FMT = "%Y%m%d_%H%M%S"

    @classmethod
    def now(cls) -> str:
        return datetime.now().strftime(cls.TIMESTAMP_FMT)

    @classmethod
    def save(
        cls,
        path: Path | str,
        *,
        subdir: str | None = None,
        timestamp: str | None = None,
    ) -> Path:
        """Copy `path` into `state_backups[/subdir]/<stem>_<ts><suffix>`.

        Returns the path of the created backup file. No-ops if the source
        does not exist (returns a Path that does not exist) — this matches
        the historical behaviour of `state_updater.backup` which would
        crash, but here we keep callers simple.
        """
        src = Path(path)
        if not src.exists():
            raise FileNotFoundError(f"Backup source missing: {src}")
        ts = timestamp or cls.now()
        dest_dir = STATE_BACKUPS / subdir if subdir else STATE_BACKUPS
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{src.stem}_{ts}{src.suffix}"
        shutil.copy2(src, dest)
        return dest

    @classmethod
    def parse_timestamp(cls, path: Path | str) -> datetime | None:
        """Extract the timestamp from a backup filename, or None if unparseable."""
        stem = Path(path).stem  # drop suffix
        # Stems look like 'vocab_state_20260428_214221'.
        parts = stem.rsplit("_", 2)
        if len(parts) < 3:
            return None
        try:
            return datetime.strptime("_".join(parts[-2:]), cls.TIMESTAMP_FMT)
        except ValueError:
            return None

    @classmethod
    def iter_all(cls, subdir: str | None = None) -> Iterable[Path]:
        """Yield every backup file under STATE_BACKUPS[/subdir], sorted oldest-first."""
        base = STATE_BACKUPS / subdir if subdir else STATE_BACKUPS
        if not base.exists():
            return iter(())
        files = [p for p in base.iterdir() if p.is_file()]
        files.sort(key=lambda p: cls.parse_timestamp(p) or datetime.min)
        return iter(files)
