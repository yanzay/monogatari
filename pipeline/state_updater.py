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
    #
    # Phase B derive-on-read (2026-05-01): `first_story`,
    # `last_seen_story`, and `occurrences` are NO LONGER stored on
    # vocab_state entries. They are derived from corpus first/last
    # appearance + true occurrence count by
    # `pipeline/derived_state.derive_vocab_attributions()` and projected
    # for the reader by `pipeline/build_vocab_attributions.py`. As a
    # result this section now:
    #
    #   * Mints brand-new word records with definition metadata only
    #     (surface, kana, reading, pos, meanings, optional verb/adj class).
    #     No attribution fields written.
    #   * Existing-word records are not mutated. The corpus walk picks
    #     up that the word reappears in this story and the projection
    #     reflects it next time `regenerate_all_stories --apply` runs.
    #
    # The pre-Phase-B occurrence counter logic was the source of a
    # systematic drift bug: stored `occurrences` was lower than corpus
    # reality by 1-15+ per word because the bump path missed shared-
    # mint cases and ran only at ship time (skipping rebuilds). Killing
    # the storage kills the drift class entirely.
    added_words   = []
    updated_words = []

    # Collect all word_ids used in this story (still useful for the
    # summary report, even though we no longer write attribution fields).
    header_word_ids = {
        tok["word_id"]
        for sec_name in ("title",)
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

    for wid in all_word_ids:
        if wid in story_new_words:
            # Brand-new word — add to vocab with definition metadata only.
            if wid in new_vocab["words"]:
                # Already present (shouldn't happen in normal flow, but safe)
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
                #  - No `first_story`, `last_seen_story`, or `occurrences`
                #    is written. They are derived per
                #    `pipeline/derived_state.derive_vocab_attributions`.
                defn = plan_word_defs.get(wid, {})
                reading = (defn.get("reading", "") or "").replace(" ", "")
                entry = {
                    "id":              wid,
                    "surface":         defn.get("surface", wid),
                    "kana":            defn.get("kana", ""),
                    "reading":         reading,
                    "pos":             defn.get("pos", "noun"),
                    "meanings":        defn.get("meanings", []),
                }
                if defn.get("verb_class"):
                    entry["verb_class"] = defn["verb_class"]
                if defn.get("adj_class"):
                    entry["adj_class"] = defn["adj_class"]
                new_vocab["words"][wid] = entry
                added_words.append(wid)
        else:
            # Existing word — no mutation; the corpus walk picks up reappearance.
            if wid in new_vocab["words"]:
                updated_words.append(wid)

    # ── 1b. Bump next_word_id past every word now in vocab ───────────────────
    # Without this the field stays stuck at the value it had when the previous
    # story shipped, so the next planner sees stale "next free id" data.
    if new_vocab.get("words"):
        max_n = max(int(wid[1:]) for wid in new_vocab["words"])
        new_vocab["next_word_id"] = f"W{max_n + 1:05d}"

    # ── 2. Add new grammar points ─────────────────────────────────────────────
    #
    # Phase A derive-on-read (2026-05-01): `intro_in_story`,
    # `first_story`, and `last_seen_story` are NO LONGER stored on
    # grammar_state entries. They are derived from corpus first/last
    # appearance by `pipeline/derived_state.py` and projected for the
    # reader by `pipeline/build_grammar_attributions.py`. As a result
    # this section has TWO cases (down from three):
    #
    #   (a) gid is brand-new to grammar_state — build a fresh entry
    #       from the plan's new_grammar_definitions block (requires
    #       title/short/long). Defining metadata only — NO attribution
    #       fields.
    #   (b) gid already exists in grammar_state — no-op. The fact that
    #       it appears in `story.new_grammar` is incorporated into
    #       derived attributions via the corpus walk; nothing to write.
    #
    # The §2b sweep that used to bump `last_seen_story` is also gone —
    # the derivation reads it directly from token positions in the
    # corpus, so any reader sees the post-ship value automatically once
    # the manifest projection is rebuilt by regenerate_all_stories.
    added_grammar = []
    plan_grammar_defs = (plan or {}).get("new_grammar_definitions", {})
    for gid in story_new_grammar:
        if gid in new_grammar["points"]:
            # Case (b): nothing to write. The point's intro_in_story
            # will reflect this story automatically once the corpus is
            # walked. Treat it as "added in this ship" for summary
            # reporting only.
            added_grammar.append(gid)
            continue

        # Case (a): brand-new gid — definition required.
        defn = plan_grammar_defs.get(gid)
        if not defn or not defn.get("title") or not defn.get("short") or not defn.get("long"):
            # Refuse to write a placeholder. Surfacing the error here is the
            # whole point — the planner should have produced a full definition.
            raise ValueError(
                f"Cannot ship: new_grammar '{gid}' has no complete definition in plan."
                " Add it to plan.new_grammar_definitions (title/short/long required)."
            )

        entry = {
            "id":              gid,
            "title":           defn["title"],
            "short":           defn["short"],
            "long":            defn["long"],
            "jlpt":            defn.get("jlpt"),
            "catalog_id":      defn.get("catalog_id"),
            "prerequisites":   list(defn.get("prerequisites", []) or []),
        }
        # Optional reference fields — only emit when present and non-null;
        # the JSON schema requires them to be strings, so a `None` from a
        # missing plan field would break the post-ship schema test.
        for ref_key in ("genki_ref", "bunpro_ref", "jlpt_sensei_ref", "notes"):
            ref_val = defn.get(ref_key)
            if isinstance(ref_val, str) and ref_val:
                entry[ref_key] = ref_val
        new_grammar["points"][gid] = entry
        added_grammar.append(gid)

    # ── 2b. (removed) `last_seen_story` is no longer stored ──────────────────
    # The derivation in `pipeline/derived_state.py` computes it on demand
    # from corpus token positions; the reader gets it via the manifest
    # projection. This eliminates the bookkeeping bug class entirely.
    grammar_reinforced: list[str] = []
    # Compute reinforced gids for the summary only (informational, no writes).
    used_gids: set[str] = set()
    for sec_name in ("title",):
        for tok in (story.get(sec_name) or {}).get("tokens", []):
            for g in (tok.get("grammar_id"), (tok.get("inflection") or {}).get("grammar_id")):
                if g:
                    used_gids.add(g)
    for sent in story.get("sentences", []):
        for tok in sent.get("tokens", []):
            for g in (tok.get("grammar_id"), (tok.get("inflection") or {}).get("grammar_id")):
                if g:
                    used_gids.add(g)
    for gid in used_gids:
        if gid in new_grammar["points"] and gid not in story_new_grammar:
            grammar_reinforced.append(gid)

    # ── 3. Update metadata ────────────────────────────────────────────────────
    now = datetime.now(timezone.utc).isoformat()
    new_vocab["last_story_id"] = story_id
    new_vocab["updated_at"]    = now
    new_vocab["version"]       = vocab.get("version", 1)

    new_grammar["version"] = grammar.get("version", 1)

    summary = {
        "story_id":           story_id,
        "words_added":        added_words,
        "words_updated":      updated_words,
        "grammar_added":      added_grammar,
        "grammar_reinforced": grammar_reinforced,
        "updated_at":         now,
    }
    return new_vocab, new_grammar, summary


# ── Backup helper ─────────────────────────────────────────────────────────────
# Thin shim so historical callers (`from state_updater import backup`) keep
# working while the canonical implementation lives in `_paths.Backup`.

from _paths import Backup as _Backup, read_json as load_json, write_json  # noqa: E402,F401


def backup(path: Path) -> Path:
    """Copy path to state_backups/filename_YYYYMMDD_HHMMSS.json. Back-compat shim."""
    return _Backup.save(path)


# ── CLI ───────────────────────────────────────────────────────────────────────


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
