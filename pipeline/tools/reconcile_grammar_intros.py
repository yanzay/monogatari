#!/usr/bin/env python3
"""DEPRECATED 2026-05-01 — Phase A derive-on-read removed the field this tool reconciles.

`data/grammar_state.json::points[gid].intro_in_story` is no longer
stored. It is derived from the corpus on every read by
`pipeline/derived_state.derive_grammar_attributions()` and projected
for the reader by `pipeline/build_grammar_attributions.py`. There is
nothing left to reconcile because there is no longer any cached
attribution that could disagree with the corpus.

This file is preserved as a no-op against the current state schema
for back-compat with external callers. Running it on a Phase-A state
will report "already in sync" because the field is absent everywhere.

To rebuild the manifest projection that took over this responsibility:
    python3 pipeline/build_grammar_attributions.py

To verify the projection is in sync with the corpus:
    python3 -m pytest pipeline/tests/test_state_integrity.py::test_grammar_attribution_manifest_in_sync_with_corpus

──────────────────── ORIGINAL DOCSTRING (for reference) ────────────────────

Reconcile `data/grammar_state.json::points[gid].intro_in_story` with corpus reality.

Why this exists
---------------
Every time a story is re-shipped (especially after spec edits to s0
or early sentences that change WHICH story first uses a particle/
construction), the `intro_in_story` field in `data/grammar_state.json`
can drift from the actual corpus first-occurrence. The
`state_updater` doesn't reset existing attributions; the regenerator
uses one rule, the validator another. Symptom: pytest reports that
story N "introduces 2 new grammar points" when a rewrite shifted one
intro from N+k back to N.

This CLI walks all shipped stories in order, records the FIRST story
each `grammar_id` appears in (across title + sentence tokens, both at
the top level and under `inflection`), and rewrites
`grammar_state.points[gid].intro_in_story` to match. Entries no
longer present anywhere in the corpus are reset to `None` so they
become candidates for re-introduction.

Usage:
    # Dry-run by default — print what WOULD change, change nothing.
    python3 pipeline/tools/reconcile_grammar_intros.py

    # Apply changes (writes a backup via _paths.Backup first).
    python3 pipeline/tools/reconcile_grammar_intros.py --apply

Per AGENTS.md, this should run AFTER
`regenerate_all_stories.py --apply` and BEFORE the final pytest;
then run regenerate ONE MORE TIME so per-story `new_grammar` arrays
match the reconciled state. (TODO: fold this into the gauntlet.)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _paths import (  # noqa: E402
    GRAMMAR_STATE,
    Backup,
    iter_stories,
    read_json,
    write_json,
)


def first_use_by_grammar(stories_dir: Path | None = None) -> dict[str, int]:
    """Return {grammar_id: first_story_id} from the shipped corpus."""
    first_use: dict[str, int] = {}
    for story_id, story in iter_stories(stories_dir):
        # Title block (a story doesn't always have one but check anyway).
        title = story.get("title")
        sections: list[dict] = []
        if isinstance(title, dict):
            sections.append(title)
        for sent in story.get("sentences") or []:
            sections.append(sent)

        for section in sections:
            for tok in section.get("tokens") or []:
                gids = (
                    tok.get("grammar_id"),
                    (tok.get("inflection") or {}).get("grammar_id"),
                )
                for gid in gids:
                    if gid and gid not in first_use:
                        first_use[gid] = story_id
    return first_use


def reconcile(state: dict, first_use: dict[str, int]) -> list[tuple[str, int | None, int | None]]:
    """Mutate `state` in-place; return list of (gid, old, new) changes."""
    changes: list[tuple[str, int | None, int | None]] = []
    points: dict = state.get("points") or {}

    # 1) Clear stale attributions that no longer occur anywhere.
    for gid, point in points.items():
        if gid not in first_use and point.get("intro_in_story") is not None:
            old = point["intro_in_story"]
            point["intro_in_story"] = None
            changes.append((gid, old, None))

    # 2) Set every observed first-use to its actual first story.
    for gid, story_id in first_use.items():
        if gid not in points:
            # Auto-tagged grammar id that was never registered in
            # grammar_state. text_to_story.KNOWN_AUTO_GRAMMAR_DEFINITIONS
            # is responsible for these — reconcile is not the place to
            # mint state entries, just warn loudly.
            print(f"  [warn] grammar_id {gid!r} appears in story {story_id} but has no grammar_state entry.")
            continue
        old = points[gid].get("intro_in_story")
        if old != story_id:
            points[gid]["intro_in_story"] = story_id
            changes.append((gid, old, story_id))

    return changes


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="Write the reconciled grammar_state. Default is dry-run.")
    args = ap.parse_args(argv)

    state = read_json(GRAMMAR_STATE)
    first_use = first_use_by_grammar()
    changes = reconcile(state, first_use)

    if not changes:
        print("grammar_state intro_in_story is already in sync with the corpus.")
        return 0

    cleared = sum(1 for _, _, new in changes if new is None)
    moved = sum(1 for _, _, new in changes if new is not None)
    print(f"Detected {len(changes)} drift(s): {moved} attribution(s) to update, {cleared} to clear.\n")
    for gid, old, new in changes:
        print(f"  {gid}: {old!r} -> {new!r}")

    if not args.apply:
        print("\n(dry-run — re-run with --apply to write changes)")
        return 0

    backup = Backup.save(GRAMMAR_STATE, subdir="reconcile_grammar_intros")
    write_json(GRAMMAR_STATE, state)
    print(f"\nWrote reconciled grammar_state. Backup: {backup}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
