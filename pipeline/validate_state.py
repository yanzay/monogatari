#!/usr/bin/env python3
"""
Monogatari — State quality validator.

Distinct from `pipeline/validate.py` (which validates a single story).
This script ensures the **state files themselves** (`vocab_state.json`,
`grammar_state.json`) are well-formed and contain no placeholder/scaffold
entries that the State Updater might have left behind.

Exit code 0 = clean, 1 = issues found.

Usage:
    python3 pipeline/validate_state.py \
        --vocab data/vocab_state.json \
        --grammar data/grammar_state.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


# Sentinel strings produced by the legacy state-updater scaffold path.
# We treat any of these as "this entry is incomplete and must not ship".
GRAMMAR_PLACEHOLDER_SHORTS = {
    "(added by state updater — fill in description)",
    "(added by state updater)",
    "TODO",
    "",
}

REQUIRED_GRAMMAR_FIELDS = ("id", "title", "short", "long", "first_story", "prerequisites", "jlpt")
VALID_JLPT_LABELS       = {"N5", "N4", "N3", "N2", "N1"}
REQUIRED_WORD_FIELDS    = ("id", "surface", "kana", "reading", "pos", "meanings",
                           "first_story", "occurrences")


def _is_placeholder_title(gid: str, title: str | None) -> bool:
    if not title:
        return True
    # If the title is literally the same as the id, the updater never replaced it.
    return title.strip() == gid.strip()


def _is_placeholder_short(short: str | None) -> bool:
    if short is None:
        return True
    return short.strip() in GRAMMAR_PLACEHOLDER_SHORTS


def validate_grammar_state(grammar: dict) -> list[str]:
    errors: list[str] = []
    points = grammar.get("points", {})
    if not isinstance(points, dict) or not points:
        errors.append("grammar_state.points is empty or not a dict")
        return errors

    known_ids = set(points.keys())

    for gid, gp in points.items():
        if not isinstance(gp, dict):
            errors.append(f"{gid}: entry is not an object")
            continue
        for field in REQUIRED_GRAMMAR_FIELDS:
            if field not in gp:
                errors.append(f"{gid}: missing required field '{field}'")

        if gp.get("_needs_review"):
            errors.append(f"{gid}: marked _needs_review=true (unfilled scaffold)")

        if _is_placeholder_title(gid, gp.get("title")):
            errors.append(f"{gid}: 'title' is a placeholder ('{gp.get('title')}') — fill in the human-readable name")
        if _is_placeholder_short(gp.get("short")):
            errors.append(f"{gid}: 'short' is empty or a placeholder — write a one-line description")
        if not (gp.get("long") or "").strip():
            errors.append(f"{gid}: 'long' is empty — write the full explanation")
        if gp.get("id") and gp["id"] != gid:
            errors.append(f"{gid}: inner id '{gp['id']}' does not match map key")

        # prerequisites must point at known grammar
        for p in gp.get("prerequisites", []) or []:
            if p not in known_ids:
                errors.append(f"{gid}: prerequisite '{p}' is not a known grammar id")

        # jlpt must be a valid label so Check 3.5 can use it
        jlpt = gp.get("jlpt")
        if jlpt is not None and jlpt not in VALID_JLPT_LABELS:
            errors.append(
                f"{gid}: 'jlpt' must be one of {sorted(VALID_JLPT_LABELS)} "
                f"(got {jlpt!r})"
            )

    return errors


def validate_vocab_state(vocab: dict) -> list[str]:
    errors: list[str] = []
    words = vocab.get("words", {})
    if not isinstance(words, dict):
        errors.append("vocab_state.words is not a dict")
        return errors

    for wid, w in words.items():
        if not isinstance(w, dict):
            errors.append(f"{wid}: entry is not an object")
            continue
        for field in REQUIRED_WORD_FIELDS:
            if field not in w:
                errors.append(f"{wid}: missing required field '{field}'")

        if w.get("id") and w["id"] != wid:
            errors.append(f"{wid}: inner id '{w['id']}' does not match map key")

        # Placeholder/scaffold detection
        if (w.get("surface") or "").strip() in ("", wid):
            errors.append(f"{wid}: 'surface' is empty or equals the id — fill in the actual surface form")
        if not (w.get("kana") or "").strip():
            errors.append(f"{wid}: 'kana' is empty — fill in the kana reading")
        if not (w.get("reading") or "").strip():
            errors.append(f"{wid}: 'reading' is empty — fill in the romaji")
        meanings = w.get("meanings") or []
        if not meanings or all(not (m or "").strip() for m in meanings):
            errors.append(f"{wid}: 'meanings' is empty — at least one English gloss required")

    return errors


def main() -> None:
    ap = argparse.ArgumentParser(description="Validate vocab/grammar state files")
    ap.add_argument("--vocab",   default="data/vocab_state.json")
    ap.add_argument("--grammar", default="data/grammar_state.json")
    ap.add_argument("--strict",  action="store_true",
                    help="Exit non-zero on warnings as well as errors")
    args = ap.parse_args()

    vocab_path   = Path(args.vocab)
    grammar_path = Path(args.grammar)

    if not vocab_path.exists():
        print(f"ERROR: vocab file not found: {vocab_path}", file=sys.stderr)
        sys.exit(2)
    if not grammar_path.exists():
        print(f"ERROR: grammar file not found: {grammar_path}", file=sys.stderr)
        sys.exit(2)

    vocab   = json.loads(vocab_path.read_text(encoding="utf-8"))
    grammar = json.loads(grammar_path.read_text(encoding="utf-8"))

    errs = []
    errs += [("grammar", e) for e in validate_grammar_state(grammar)]
    errs += [("vocab",   e) for e in validate_vocab_state(vocab)]

    if not errs:
        print(f"✓ State clean ({len(vocab.get('words', {}))} words, "
              f"{len(grammar.get('points', {}))} grammar points)")
        sys.exit(0)

    print(f"✗ State has {len(errs)} issue(s):")
    for kind, msg in errs:
        print(f"  - [{kind}] {msg}")
    sys.exit(1)


if __name__ == "__main__":
    main()
