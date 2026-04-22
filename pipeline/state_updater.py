#!/usr/bin/env python3
"""
Monogatari — Stage 5: State Updater
Pure function: reads a validated story_N.json and updates vocab_state.json
and grammar_state.json in place. Keeps a dated backup of previous state.

Usage:
    python3 pipeline/state_updater.py \
        stories/story_2.json \
        [--vocab data/vocab_state.json] \
        [--grammar data/grammar_state.json] \
        [--plan pipeline/plan.json] \
        [--dry-run]
"""

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path


# ── Core update logic ─────────────────────────────────────────────────────────

def update_state(
    story: dict,
    vocab: dict,
    grammar: dict,
    plan: dict | None = None,
) -> tuple[dict, dict, dict]:
    """
    Returns (new_vocab, new_grammar, summary_dict).
    Does NOT write files — caller handles I/O.
    """
    import copy
    new_vocab   = copy.deepcopy(vocab)
    new_grammar = copy.deepcopy(grammar)

    story_id      = story["story_id"]
    story_new_words   = set(story.get("new_words", []))
    story_new_grammar = set(story.get("new_grammar", []))

    # Get new word definitions from plan (if available)
    plan_word_defs = {}
    if plan:
        plan_word_defs = plan.get("new_word_definitions", {})

    # ── 1. Add / update words ─────────────────────────────────────────────────
    added_words   = []
    updated_words = []

    # Collect all word_ids used in this story.
    #
    # `first_story` and `last_seen_story` are computed from title + subtitle +
    # sentences (a word that debuts in the title genuinely debuts there, and
    # the same for "last seen" — a learner reads the subtitle when revisiting
    # a story).
    #
    # `occurrences` (the lifetime practice counter) is computed from
    # **sentences only**. The repo's permanent integrity test
    # (`test_lifetime_occurrences_match_state_updater_semantics`) defines this
    # as the contract — title and subtitle are headers, not body beats, and
    # counting them inflated the per-word practice count for words that
    # appeared as headline-only motifs (this drift was caught after story 27,
    # which had 朝 in the subtitle but not in any sentence). See v0.16 in
    # docs/authoring.md for the full rationale.
    header_word_ids = {
        tok["word_id"]
        for sec_name in ("title", "subtitle")
        for tok in (story.get(sec_name) or {}).get("tokens", [])
        if tok.get("word_id")
    }
    body_word_ids = {
        tok["word_id"]
        for sent in story.get("sentences", [])
        for tok in sent.get("tokens", [])
        if tok.get("word_id")
    }
    all_word_ids = header_word_ids | body_word_ids

    # The repo convention is `first_story = "story_<N>"` (string), while
    # `last_seen_story = <N>` (int). State_updater used to emit the int for
    # both, which the integrity tests rejected on the next ship — see
    # docs/authoring.md § "v0.11" and pipeline/NOTES_FOR_FUTURE_AGENTS.md.
    first_story_label = f"story_{story_id}"

    for wid in all_word_ids:
        # Practice counter only counts sentence-level appearances; headers
        # (title/subtitle) are tracked for first_story/last_seen_story but
        # don't bump occurrences.
        in_body = wid in body_word_ids
        if wid in story_new_words:
            # Brand-new word — add to vocab
            if wid in new_vocab["words"]:
                # Already present (shouldn't happen in normal flow, but safe)
                if in_body:
                    new_vocab["words"][wid]["occurrences"] += 1
                new_vocab["words"][wid]["last_seen_story"] = story_id
                updated_words.append(wid)
            else:
                # Build entry from plan definitions or minimal scaffold.
                # Notes:
                #  - `grammar_tags` is intentionally NOT written. The field
                #    was deprecated and the integrity test rejects entries
                #    that carry it (see test_vocab_no_dead_grammar_tags_field).
                #  - `reading` is normalised to a single-token romaji string
                #    (no spaces). Spaces in romaji break the
                #    test_vocab_reading_is_ascii_no_spaces invariant.
                defn = plan_word_defs.get(wid, {})
                reading = (defn.get("reading", "") or "").replace(" ", "")
                entry = {
                    "id":              wid,
                    "surface":         defn.get("surface", wid),
                    "kana":            defn.get("kana", ""),
                    "reading":         reading,
                    "pos":             defn.get("pos", "noun"),
                    "meanings":        defn.get("meanings", []),
                    "first_story":     first_story_label,
                    "occurrences":     1 if in_body else 0,
                    "last_seen_story": story_id,
                }
                if defn.get("verb_class"):
                    entry["verb_class"] = defn["verb_class"]
                if defn.get("adj_class"):
                    entry["adj_class"] = defn["adj_class"]
                new_vocab["words"][wid] = entry
                added_words.append(wid)
        else:
            # Existing word — increment occurrence counter (sentences only)
            if wid in new_vocab["words"]:
                if in_body:
                    new_vocab["words"][wid]["occurrences"] += 1
                new_vocab["words"][wid]["last_seen_story"] = story_id
                updated_words.append(wid)

    # ── 1b. Bump next_word_id past every word now in vocab ───────────────────
    # Without this the field stays stuck at the value it had when the previous
    # story shipped, so the next planner sees stale "next free id" data.
    if new_vocab.get("words"):
        max_n = max(int(wid[1:]) for wid in new_vocab["words"])
        new_vocab["next_word_id"] = f"W{max_n + 1:05d}"

    # ── 2. Add new grammar points ─────────────────────────────────────────────
    added_grammar = []
    plan_grammar_defs = (plan or {}).get("new_grammar_definitions", {})
    for gid in story_new_grammar:
        if gid in new_grammar["points"]:
            continue

        defn = plan_grammar_defs.get(gid)
        if not defn or not defn.get("title") or not defn.get("short") or not defn.get("long"):
            # Refuse to write a placeholder. Surfacing the error here is the
            # whole point — the planner should have produced a full definition.
            raise ValueError(
                f"Cannot ship: new_grammar '{gid}' has no complete definition in plan."
                " Add it to plan.new_grammar_definitions (title/short/long required)."
            )

        new_grammar["points"][gid] = {
            "id":            gid,
            "title":         defn["title"],
            "short":         defn["short"],
            "long":          defn["long"],
            "genki_ref":     defn.get("genki_ref"),
            "jlpt":          defn.get("jlpt"),
            "catalog_id":    defn.get("catalog_id"),
            "first_story":   first_story_label,
            "prerequisites": list(defn.get("prerequisites", []) or []),
        }
        added_grammar.append(gid)

    # ── 3. Update metadata ────────────────────────────────────────────────────
    now = datetime.now(timezone.utc).isoformat()
    new_vocab["last_story_id"] = story_id
    new_vocab["updated_at"]    = now
    new_vocab["version"]       = vocab.get("version", 1)

    new_grammar["version"] = grammar.get("version", 1)

    summary = {
        "story_id":      story_id,
        "words_added":   added_words,
        "words_updated": updated_words,
        "grammar_added": added_grammar,
        "updated_at":    now,
    }
    return new_vocab, new_grammar, summary


# ── Backup helper ─────────────────────────────────────────────────────────────

def backup(path: Path) -> Path:
    """Copy path to state_backups/filename_YYYYMMDD_HHMMSS.json."""
    backup_dir = Path("state_backups")
    backup_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest  = backup_dir / f"{path.stem}_{stamp}{path.suffix}"
    shutil.copy2(path, dest)
    return dest


# ── CLI ───────────────────────────────────────────────────────────────────────

def load_json(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Monogatari State Updater (Stage 5)")
    parser.add_argument("story",     help="Path to validated story_N.json")
    parser.add_argument("--vocab",   default="data/vocab_state.json")
    parser.add_argument("--grammar", default="data/grammar_state.json")
    parser.add_argument("--plan",    default=None)
    parser.add_argument("--dry-run", action="store_true",
                        help="Show changes without writing files")
    args = parser.parse_args()

    story   = load_json(args.story)
    vocab   = load_json(args.vocab)
    grammar = load_json(args.grammar)
    plan    = load_json(args.plan) if args.plan else None

    new_vocab, new_grammar, summary = update_state(story, vocab, grammar, plan)

    print(f"Story {summary['story_id']} state update:")
    print(f"  Words added:   {summary['words_added']}")
    print(f"  Words updated: {len(summary['words_updated'])} words")
    print(f"  Grammar added: {summary['grammar_added']}")

    if args.dry_run:
        print("\n[dry-run] No files written.")
        return

    # Backup existing state
    vocab_path   = Path(args.vocab)
    grammar_path = Path(args.grammar)
    bv = backup(vocab_path)
    bg = backup(grammar_path)
    print(f"\nBackups: {bv}, {bg}")

    # Write updated state
    write_json(vocab_path,   new_vocab)
    write_json(grammar_path, new_grammar)
    print(f"✓ Updated {vocab_path}")
    print(f"✓ Updated {grammar_path}")

    # Copy validated story to stories/
    story_id  = story["story_id"]
    dest_path = Path(f"stories/story_{story_id}.json")
    dest_path.parent.mkdir(exist_ok=True)
    # Strip internal metadata fields before shipping
    shipping = {k: v for k, v in story.items() if not k.startswith("_")}
    write_json(dest_path, shipping)
    print(f"✓ Story shipped to {dest_path}")


if __name__ == "__main__":
    main()
