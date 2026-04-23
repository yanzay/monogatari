"""Shared infrastructure for the pipeline/tools/ CLIs.

Centralizes:
- ROOT path discovery
- vocab/grammar state load + save
- bilingual-spec read/write
- access to the deterministic converter (`build_story`)
- a coarse `iter_stories()` helper
"""
from __future__ import annotations
import json
import sys
from pathlib import Path
from typing import Iterable, Iterator

ROOT = Path(__file__).resolve().parents[2]
PIPELINE = ROOT / "pipeline"
INPUTS = PIPELINE / "inputs"
STORIES = ROOT / "stories"
DATA = ROOT / "data"

# Make `text_to_story`, `progression`, etc. importable.
if str(PIPELINE) not in sys.path:
    sys.path.insert(0, str(PIPELINE))


# ------------------------------------------------------------------ I/O

def load_vocab() -> dict:
    return json.loads((DATA / "vocab_state.json").read_text())


def load_grammar() -> dict:
    return json.loads((DATA / "grammar_state.json").read_text())


def load_grammar_catalog() -> dict:
    return json.loads((DATA / "grammar_catalog.json").read_text())


def load_spec(story_id: int) -> dict:
    return json.loads((INPUTS / f"story_{story_id}.bilingual.json").read_text())


def save_spec(story_id: int, spec: dict) -> None:
    path = INPUTS / f"story_{story_id}.bilingual.json"
    path.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n")


def load_story(story_id: int) -> dict:
    return json.loads((STORIES / f"story_{story_id}.json").read_text())


def _spec_id(path) -> int:
    # path.stem is e.g. "story_18.bilingual" so split twice
    return int(path.name.split("_")[1].split(".")[0])


def iter_specs() -> Iterator[tuple[int, dict]]:
    for path in sorted(INPUTS.glob("story_*.bilingual.json"), key=_spec_id):
        yield _spec_id(path), json.loads(path.read_text())


def iter_stories() -> Iterator[tuple[int, dict]]:
    for path in sorted(STORIES.glob("story_*.json"),
                       key=lambda p: int(p.stem.split("_")[1])):
        sid = int(path.stem.split("_")[1])
        yield sid, json.loads(path.read_text())


# ------------------------------------------------------------------ converter

def build(spec: dict, vocab: dict | None = None, grammar: dict | None = None):
    """Run the deterministic converter on a spec without touching disk."""
    from text_to_story import build_story
    if vocab is None:
        vocab = load_vocab()
    if grammar is None:
        grammar = load_grammar()
    return build_story(spec, vocab, grammar)


# ------------------------------------------------------------------ pretty

def color(text: str, c: str) -> str:
    if not sys.stdout.isatty():
        return text
    codes = {"red": 31, "green": 32, "yellow": 33, "blue": 34,
             "magenta": 35, "cyan": 36, "bold": 1, "dim": 2}
    return f"\033[{codes.get(c, 0)}m{text}\033[0m"


def parse_id_arg(arg: str | int) -> int:
    """Accept '12' or 'story_12' or 12."""
    if isinstance(arg, int):
        return arg
    s = str(arg)
    if s.startswith("story_"):
        s = s.split("_", 1)[1]
    return int(s)


def list_word_occurrences(stories: Iterable[tuple[int, dict]], wid: str) -> list[tuple[int, str]]:
    """Return [(story_id, surface)] for every occurrence of word_id wid."""
    out = []
    for sid, story in stories:
        seen_surfaces = []
        for sec in ("title",):
            for tok in (story.get(sec) or {}).get("tokens", []):
                if tok.get("word_id") == wid:
                    seen_surfaces.append(tok.get("t", "?"))
        for sn in story.get("sentences", []):
            for tok in sn.get("tokens", []):
                if tok.get("word_id") == wid:
                    seen_surfaces.append(tok.get("t", "?"))
        if seen_surfaces:
            out.append((sid, ", ".join(seen_surfaces)))
    return out


def list_grammar_occurrences(stories: Iterable[tuple[int, dict]], gid: str) -> list[tuple[int, str]]:
    out = []
    for sid, story in stories:
        seen = []
        for sec in ("title",):
            for tok in (story.get(sec) or {}).get("tokens", []):
                if tok.get("grammar_id") == gid:
                    seen.append(tok.get("t", "?"))
        for sn in story.get("sentences", []):
            for tok in sn.get("tokens", []):
                if tok.get("grammar_id") == gid:
                    seen.append(tok.get("t", "?"))
        if seen:
            out.append((sid, ", ".join(seen)))
    return out
