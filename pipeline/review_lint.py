#!/usr/bin/env python3
"""
Review-honesty lint.

Added 2026-04-22 after a library audit found several reviews with free-text
notes containing the words "repetitive" / "similar to story N" / "calque" /
"awkward" while still scoring originality 4 or 5. The score didn't reflect
the criticism the reviewer had already written down. This module enforces
that consistency.

If the `notes` (or any per-dimension `comment`) contains a critical
keyword, the corresponding dimension cannot be scored above 3. The check
is intentionally conservative — only fires on words that almost always
indicate a genuine prose-level criticism.

Public entry point
------------------
    review_honesty_issues(review) -> list[str]
"""
from __future__ import annotations

import re

# (keyword pattern, dimension whose score must be ≤ 3, why)
HONESTY_RULES: list[tuple[str, str, str]] = [
    # Originality
    (r"\brepetit",       "originality", "the notes describe the story as repetitive"),
    (r"\bsimilar to (?:story_?)?\d", "originality", "the notes flag similarity to a prior story"),
    (r"\bsame (?:scene|setting|opener|closer|template)", "originality",
                         "the notes say the story recycles a scene/setting/opener/closer"),
    (r"\brecycle",       "originality", "the notes describe the story as recycled"),
    (r"\bworksheet",     "originality", "the notes describe the prose as worksheet-like"),
    (r"\bparallel.*pair","originality", "the notes flag parallel-pair construction"),
    # Naturalness / coherence
    (r"\bcalque",        "naturalness", "the notes flag calque English in the gloss"),
    (r"\bawkward",       "naturalness", "the notes describe the prose as awkward"),
    (r"\bnonsens",       "coherence",   "the notes describe the sentence as nonsense"),
    (r"\bdoesn't make sense", "coherence", "the notes say the sentence doesn't make sense"),
    (r"\bmistransl",     "coherence",   "the notes flag a mistranslation"),
    (r"\bmoon at breakfast", "coherence", "the notes flag a time/setting mismatch"),
    # Voice
    (r"\btic\b",         "voice",       "the notes describe an over-used adjective as a tic"),
    (r"\boveruse",       "voice",       "the notes flag overuse of a word/construction"),
]

# Maximum score allowed for a dimension whose honesty rule fired.
HONESTY_CEILING = 3


def review_honesty_issues(review: dict) -> list[str]:
    """Return a list of human-readable error strings (empty if review is honest).

    Looks at:
      - review["notes"]              (top-level free text)
      - review["suggestions"]        (list of strings)
      - review["scores"][d_comment]  (if reviewer attached per-dimension comments)
    """
    if not isinstance(review, dict):
        return []

    # Collect all text the reviewer wrote, lowercased and with section
    # prefix so the error message can point at the right place.
    fragments: list[tuple[str, str]] = []
    notes = review.get("notes")
    if isinstance(notes, str):
        fragments.append(("notes", notes.lower()))
    suggestions = review.get("suggestions")
    if isinstance(suggestions, list):
        for i, s in enumerate(suggestions):
            if isinstance(s, str):
                fragments.append((f"suggestions[{i}]", s.lower()))
    scores = review.get("scores") or {}
    if isinstance(scores, dict):
        for k, v in scores.items():
            if k.endswith("_comment") and isinstance(v, str):
                fragments.append((f"scores.{k}", v.lower()))

    errors: list[str] = []
    for pattern, dim, why in HONESTY_RULES:
        for section, text in fragments:
            if not re.search(pattern, text):
                continue
            score = scores.get(dim) if isinstance(scores, dict) else None
            if isinstance(score, int) and score > HONESTY_CEILING:
                errors.append(
                    f"Honesty mismatch: scores.{dim} = {score}, but {section} "
                    f"contains '{pattern}' ({why}). A reviewer who writes that "
                    f"criticism cannot then score {dim} above {HONESTY_CEILING}. "
                    f"Either rewrite the story so the criticism no longer applies, "
                    f"or lower the score to honestly reflect the prose."
                )
                break  # one error per rule is enough
    return errors
