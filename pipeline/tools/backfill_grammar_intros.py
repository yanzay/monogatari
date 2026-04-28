#!/usr/bin/env python3
"""Backfill `intro_in_story` (and `first_story`) on data/grammar_state.json.

History: every G0XX point in `data/grammar_state.json` was bulk-loaded
without `intro_in_story`, even points that have been used since story 1.
The agent_brief and validator coverage logic both filter on
`intro_in_story is not None` to know whether a point is "covered" for
its tier — so without this backfill, the brief reports "0 grammar
introduced" and the curriculum stalls.

This tool is idempotent: it walks every shipped `stories/story_N.json`,
finds the EARLIEST story whose `new_grammar` lists each gid, and writes
that story id back into `intro_in_story`. Points that aren't yet
introduced anywhere are left as `intro_in_story: None`.

Usage:
    python3 pipeline/tools/backfill_grammar_intros.py [--dry-run]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running from anywhere
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))           # pipeline/
sys.path.insert(0, str(HERE))                  # pipeline/tools/

from _paths import DATA, iter_stories, write_json  # noqa: E402
import json  # noqa: E402


def collect_intros() -> dict[str, int]:
    """gid → earliest shipped story_N that lists gid in new_grammar."""
    earliest: dict[str, int] = {}
    for sid, story in iter_stories():
        for gid in story.get("new_grammar") or []:
            if not isinstance(gid, str):
                continue
            if gid not in earliest or earliest[gid] > sid:
                earliest[gid] = sid
    return earliest


def backfill(dry_run: bool = False) -> dict:
    state_path = DATA / "grammar_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    earliest = collect_intros()

    changes: list[tuple[str, int, dict]] = []   # (gid, story_id, before)
    skipped_no_state: list[str] = []
    points = state.get("points") or {}
    for gid, sid in earliest.items():
        entry = points.get(gid)
        if entry is None:
            skipped_no_state.append(gid)
            continue
        before = {
            "intro_in_story": entry.get("intro_in_story"),
            "first_story":    entry.get("first_story"),
        }
        already = (
            entry.get("intro_in_story") == sid
            and entry.get("first_story") == f"story_{sid}"
        )
        if already:
            continue
        if not dry_run:
            entry["intro_in_story"] = sid
            entry["first_story"] = f"story_{sid}"
        changes.append((gid, sid, before))

    summary = {
        "changes": [
            {"gid": gid, "intro_in_story": sid, "before": before}
            for gid, sid, before in changes
        ],
        "skipped_no_state_entry": skipped_no_state,
        "dry_run": dry_run,
        "state_path": str(state_path),
        "total_state_points": len(points),
        "total_used_points": len(earliest),
    }

    if not dry_run and changes:
        write_json(state_path, state)

    return summary


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would change but don't write the file")
    args = ap.parse_args()

    summary = backfill(dry_run=args.dry_run)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
