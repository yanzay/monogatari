#!/usr/bin/env python3
"""One-shot migration: rename every G###_slug grammar id to its
catalog-form N?_slug. Eliminates the dual-namespace indirection
(grammar_state keyed by G###, grammar_catalog keyed by N?) by
adopting the catalog form as canonical.

Why
---
The G### prefix encoded *introduction order* (G001 = first introduced,
G002 = second, etc.) — a derivable value (sorted({intro_in_story})
index) that was being stored as part of the id, forcing a `catalog_id`
join field on every state point. Same shape of bug Phases A+B killed:
storing a derivable value in the id itself.

After this migration:
  - state and catalog both keyed by N5_wa_topic / N4_te_iku / N3_..., etc.
  - the `catalog_id` field on state points becomes redundant (deleted in
    a sibling commit).
  - the introduction-order index is recoverable as
    `sorted({intro_in_story for gid in attributions}.index(...))` if any
    UI ever needs it (no current consumer does).

Operating mode
--------------
Dry-run by default. Prints, per file, how many literal G###_slug
substring occurrences will be rewritten and what they will become.
With --apply, performs the rewrites in place. The rename map is loaded
from /tmp/g_to_n_rename.json (produced by Phase 0 of the migration).

Files touched
-------------
- stories/story_*.json
- pipeline/inputs/story_*.bilingual.json
- pipeline/{text_to_story,semantic_lint,lookup,validate,grammar_progression,
  build_grammar_attributions,regenerate_all_stories,author_loop}.py
- pipeline/tests/test_*.py (only test_*.py, not conftest)
- src/lib/data/types.ts (none expected; gid is opaque)
- tests/unit/util/grammar.test.ts, tests/unit/state/popup.test.ts
- data/grammar_state.json (special: also rename the dict KEY, not
  just substring values)
- data/grammar_attributions.json (special: rename dict KEY)
- AGENTS.md, docs/spec.md, docs/v2-strategy-2026-04-27.md
- static/{stories,data}/* — symlinks to the above; auto-mirrored

NOT touched
-----------
- legacy/, state_backups/, .author-scratch/, build/, .svelte-kit/
- engagement_baseline.json, story_raw.json, text_to_story.report.json
  (local working artifacts; will regenerate on next pipeline pass)

Usage
-----
    python3 pipeline/tools/rename_gids.py             # dry-run
    python3 pipeline/tools/rename_gids.py --apply     # do it
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
RENAME_MAP_PATH = Path("/tmp/g_to_n_rename.json")

# Globs of files to scan + rewrite. Order matters: stories/specs first
# (data), then source code, then docs.
TARGET_GLOBS = [
    "stories/story_*.json",
    "pipeline/inputs/story_*.bilingual.json",
    "pipeline/text_to_story.py",
    "pipeline/semantic_lint.py",
    "pipeline/lookup.py",
    "pipeline/validate.py",
    "pipeline/grammar_progression.py",
    "pipeline/build_grammar_attributions.py",
    "pipeline/regenerate_all_stories.py",
    "pipeline/author_loop.py",
    "pipeline/state_updater.py",
    "pipeline/derived_state.py",
    "pipeline/tests/test_dictionary_form_attribution.py",
    "pipeline/tests/test_state_integrity.py",
    "pipeline/tests/test_surface_grammar_consistency.py",
    "pipeline/tests/test_semantic_lint_rules.py",
    "pipeline/tests/test_validate_unit.py",
    "pipeline/tools/story.py",
    "src/lib/data/types.ts",
    "src/lib/data/corpus.ts",
    "tests/unit/util/grammar.test.ts",
    "tests/unit/state/popup.test.ts",
    "docs/spec.md",
    "docs/v2-strategy-2026-04-27.md",
    "AGENTS.md",
]

# Special-case JSON files whose top-level dict KEYS are gids (not just
# values inside text). These need a structural rewrite, not a string
# substitution.
JSON_KEY_REWRITE_FILES = [
    "data/grammar_state.json",
    "data/grammar_attributions.json",
]


def load_rename_map() -> dict[str, str]:
    if not RENAME_MAP_PATH.exists():
        sys.exit(
            f"ERROR: rename map missing at {RENAME_MAP_PATH}.\n"
            "  Run Phase 0 first to generate it."
        )
    return json.loads(RENAME_MAP_PATH.read_text())


def build_pattern(rename_map: dict[str, str]) -> re.Pattern:
    """Build a regex matching ANY G###_slug from the map, longest-first.

    Longest-first matching ensures `G001_wa_topic_extra` (hypothetical)
    wouldn't be wrongly truncated to `G001_wa_topic` + `_extra`.
    Currently no such collisions, but defensive.
    """
    keys = sorted(rename_map.keys(), key=len, reverse=True)
    # Word-boundary on both sides — gids can be embedded in:
    #   "grammar_id": "G001_wa_topic"   <- followed by " (closing quote)
    #   GRAMMAR_WA = "G001_wa_topic"    <- followed by " or end-of-line
    #   See G055_plain_nonpast_pair      <- prose, followed by space
    # The G prefix uniquely starts each gid; `\b` works because '_' is a
    # word character so `G001_wa_topic\b` stops at the slug end.
    return re.compile(r"\b(" + "|".join(re.escape(k) for k in keys) + r")\b")


def rewrite_text(text: str, pattern: re.Pattern, rename_map: dict[str, str]) -> tuple[str, int]:
    """Return (rewritten_text, n_replacements)."""
    n = 0

    def _sub(m: re.Match) -> str:
        nonlocal n
        n += 1
        return rename_map[m.group(1)]

    return pattern.sub(_sub, text), n


def rewrite_file(path: Path, pattern: re.Pattern, rename_map: dict[str, str]) -> tuple[int, str]:
    """Rewrite a single file. Returns (n_replacements, new_content_unwritten).
    Caller decides whether to actually write."""
    if not path.exists():
        return 0, ""
    original = path.read_text(encoding="utf-8")
    rewritten, n = rewrite_text(original, pattern, rename_map)
    return n, rewritten


def rewrite_json_keys(path: Path, rename_map: dict[str, str]) -> tuple[int, str]:
    """For grammar_state.json + grammar_attributions.json, the gids
    are dict KEYS, not just embedded substrings. Rewrite the structure
    THEN do the substring pass over the serialized result so that
    embedded refs (prerequisites lists, comments inside `notes`,
    cross-refs in `long`, etc.) also get rewritten."""
    if not path.exists():
        return 0, ""
    data = json.loads(path.read_text(encoding="utf-8"))
    n = 0

    if path.name == "grammar_state.json":
        new_points = {}
        for gid, p in data["points"].items():
            new_gid = rename_map.get(gid, gid)
            if new_gid != gid:
                n += 1
            # Also update the embedded id field
            if "id" in p:
                old_id = p["id"]
                p["id"] = rename_map.get(old_id, old_id)
                if p["id"] != old_id:
                    n += 1
            # Drop the now-redundant catalog_id field (it equals the new key)
            if "catalog_id" in p:
                p.pop("catalog_id")
                n += 1
            new_points[new_gid] = p
        data["points"] = new_points
    elif path.name == "grammar_attributions.json":
        new_attrs = {}
        for gid, attr in data.get("attributions", {}).items():
            new_gid = rename_map.get(gid, gid)
            if new_gid != gid:
                n += 1
            new_attrs[new_gid] = attr
        data["attributions"] = new_attrs

    serialized = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    # Second pass: substring rewrite to catch embedded refs (prereqs,
    # cross-refs in description text, etc.)
    pattern = build_pattern(rename_map)
    serialized, n_embedded = rewrite_text(serialized, pattern, rename_map)
    n += n_embedded

    return n, serialized


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="Actually write the rewritten files.")
    args = ap.parse_args(argv)

    rename_map = load_rename_map()
    pattern = build_pattern(rename_map)
    print(f"Loaded {len(rename_map)} G→N renames.\n")

    total = 0
    files_touched = 0

    # 1. Substring-rewrite pass
    for glob in TARGET_GLOBS:
        for path in sorted(ROOT.glob(glob)):
            n, new_content = rewrite_file(path, pattern, rename_map)
            if n > 0:
                rel = path.relative_to(ROOT)
                print(f"  [{n:4d}] {rel}")
                total += n
                files_touched += 1
                if args.apply:
                    path.write_text(new_content, encoding="utf-8")

    # 2. JSON key-rewrite pass (special files)
    for rel_path in JSON_KEY_REWRITE_FILES:
        path = ROOT / rel_path
        n, new_content = rewrite_json_keys(path, rename_map)
        if n > 0:
            print(f"  [{n:4d}] {rel_path}  (keys + structural)")
            total += n
            files_touched += 1
            if args.apply:
                path.write_text(new_content, encoding="utf-8")

    print(f"\nTotal: {total} replacements across {files_touched} files.")
    if not args.apply:
        print("(dry-run — re-run with --apply to actually rewrite)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
