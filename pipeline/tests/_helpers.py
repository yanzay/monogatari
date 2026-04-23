"""Helpers shared between test modules. (conftest fixtures don't import cleanly cross-module.)"""
from __future__ import annotations


def iter_tokens(story: dict):
    """Yield (section_name, sentence_idx_or_None, token_idx, token) for every token."""
    for sec_name in ("title",):
        sec = story.get(sec_name) or {}
        for j, tok in enumerate(sec.get("tokens", [])):
            yield (sec_name, None, j, tok)
    for i, sent in enumerate(story.get("sentences", [])):
        for j, tok in enumerate(sent.get("tokens", [])):
            yield ("sentence", i, j, tok)
