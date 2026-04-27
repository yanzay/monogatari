"""Canonical token-walking helpers.

Replaces 5+ near-identical copies of `for sec in ('title',): for tok in …`
scattered across `validate.py`, `tools/cadence.py`, `tools/story.py`,
`tools/weave.py`, `tools/_common.py`, and `tools/vocab.py`.

A "token" is one of the dicts inside `story['title']['tokens']` or
`story['sentences'][i]['tokens']`. Helpers here NEVER mutate.
"""
from __future__ import annotations

from typing import Iterator


# ── Section iteration ────────────────────────────────────────────────────────

def iter_sections(story: dict) -> Iterator[tuple[str, list[dict]]]:
    """Yield (section_name, tokens_list) for title + every sentence.

    `section_name` is 'title' for the title block, otherwise 'sentence_{i}'
    (zero-indexed). Sentences with no `tokens` key are skipped.
    """
    title = story.get("title") or {}
    if title.get("tokens"):
        yield "title", title["tokens"]
    for i, sent in enumerate(story.get("sentences") or []):
        toks = sent.get("tokens")
        if toks:
            yield f"sentence_{i}", toks


def iter_tokens(story: dict) -> Iterator[dict]:
    """Yield every token in the story (title first, then sentences in order)."""
    for _section, tokens in iter_sections(story):
        yield from tokens


def iter_sentence_tokens(story: dict) -> Iterator[dict]:
    """Like `iter_tokens` but skips the title block."""
    for sent in story.get("sentences") or []:
        for tok in sent.get("tokens") or []:
            yield tok


# ── ID extraction ────────────────────────────────────────────────────────────

def word_ids_used(story: dict) -> set[str]:
    """All distinct `word_id` values appearing anywhere in the story."""
    return {tok["word_id"] for tok in iter_tokens(story) if tok.get("word_id")}


def grammar_ids_used(story: dict, *, include_inflection: bool = True) -> set[str]:
    """All distinct grammar-point ids appearing in the story.

    If `include_inflection` is True (the default) the helper also collects
    `tok['inflection']['grammar_id']` — the form many checks need because a
    grammar point like 'past polite' is recorded on the inflection, not on
    the surface token.
    """
    out: set[str] = set()
    for tok in iter_tokens(story):
        gid = tok.get("grammar_id")
        if gid:
            out.add(gid)
        if include_inflection:
            infl_gid = (tok.get("inflection") or {}).get("grammar_id")
            if infl_gid:
                out.add(infl_gid)
    return out


# ── Counting / classification ────────────────────────────────────────────────

def count_content_tokens(story: dict) -> int:
    """Count tokens with role='content' (used for length-progression checks)."""
    return sum(1 for t in iter_sentence_tokens(story) if t.get("role") == "content")


def joined_jp(sent: dict) -> str:
    """Round-trip the JP surface of one sentence by joining its tokens."""
    return "".join(t.get("t", "") for t in sent.get("tokens") or [])
