"""Shared infrastructure for the pipeline/tools/ CLIs.

Thin compatibility shim — all path/IO/token-walk helpers now live in
`pipeline/_paths.py` and `pipeline/_token_walk.py` and are shared with the
top-level pipeline modules. This module re-exports them under their old
names plus a couple of tools-specific extras (color, mint_check, build).
"""
from __future__ import annotations
import sys
from pathlib import Path
from typing import Iterable

# Make the top-level pipeline package importable.
_PIPELINE = Path(__file__).resolve().parents[1]
if str(_PIPELINE) not in sys.path:
    sys.path.insert(0, str(_PIPELINE))

from _paths import (  # noqa: E402,F401  (re-exported for back-compat)
    ROOT,
    PIPELINE,
    INPUTS,
    STORIES,
    DATA,
    parse_story_id as parse_id_arg,
    load_vocab,
    load_vocab_attributed,
    load_grammar,
    load_grammar_catalog,
    load_spec,
    save_spec,
    load_story,
    iter_stories,
    iter_specs,
)
from _token_walk import iter_tokens  # noqa: E402,F401


# ── Converter access ─────────────────────────────────────────────────────────

def build(spec: dict, vocab: dict | None = None, grammar: dict | None = None):
    """Run the deterministic converter on a spec without touching disk."""
    from text_to_story import build_story
    if vocab is None:
        vocab = load_vocab()
    if grammar is None:
        grammar = load_grammar()
    return build_story(spec, vocab, grammar)


# ── Pretty printing ──────────────────────────────────────────────────────────

def color(text: str, c: str) -> str:
    if not sys.stdout.isatty():
        return text
    codes = {"red": 31, "green": 32, "yellow": 33, "blue": 34,
             "magenta": 35, "cyan": 36, "bold": 1, "dim": 2}
    return f"\033[{codes.get(c, 0)}m{text}\033[0m"


# ── Occurrence lookups (unchanged behaviour) ─────────────────────────────────

def list_word_occurrences(stories: Iterable[tuple[int, dict]],
                          wid: str) -> list[tuple[int, str]]:
    out = []
    for sid, story in stories:
        seen = [tok.get("t", "?") for tok in iter_tokens(story)
                if tok.get("word_id") == wid]
        if seen:
            out.append((sid, ", ".join(seen)))
    return out


def list_grammar_occurrences(stories: Iterable[tuple[int, dict]],
                             gid: str) -> list[tuple[int, str]]:
    out = []
    for sid, story in stories:
        seen = [tok.get("t", "?") for tok in iter_tokens(story)
                if tok.get("grammar_id") == gid]
        if seen:
            out.append((sid, ", ".join(seen)))
    return out


def mint_check(jp: str) -> list[dict]:
    """Tokenize a candidate JP sentence and return its `new_words` mint list."""
    spec = {"story_id": 999, "title": {"jp": jp, "en": "preview"},
            "sentences": [{"jp": jp, "en": "preview"}]}
    _story, report = build(spec)
    return list(report.get("new_words") or [])
