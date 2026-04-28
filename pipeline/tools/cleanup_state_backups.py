#!/usr/bin/env python3
"""Prune `state_backups/` according to a retention policy.

The `state_backups/` garden grows by ~3 files per story ship (one each
for vocab_state, grammar_state, and a regenerator-pass copy). At 56
shipped stories that's ~170 files in the top level alone, plus the
~830 files under `state_backups/regenerate_all_stories/`. This CLI
prunes both directories to a sensible retention window so the working
tree, git status, and clones stay fast.

Default policy:
    * Keep the **N most-recent** backup files per stem (default 5).
    * Keep all files newer than **D days** (default 7).
    * Files matching neither rule are deleted.

The "stem" is the part of the filename before the timestamp, so
`vocab_state` and `grammar_state` are pruned independently — losing
all your vocab backups while keeping all your grammar backups would
be unsafe.

Usage:
    # Dry-run (default) — print what would be deleted, change nothing.
    python3 pipeline/tools/cleanup_state_backups.py

    # Actually delete.
    python3 pipeline/tools/cleanup_state_backups.py --apply

    # Aggressive prune for a clean slate (keep last 2, last 1 day).
    python3 pipeline/tools/cleanup_state_backups.py --keep 2 --days 1 --apply

    # Limit to a sub-directory (regenerate_all_stories shards its backups).
    python3 pipeline/tools/cleanup_state_backups.py --subdir regenerate_all_stories --apply
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable

# Make `_paths` importable when invoked as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _paths import STATE_BACKUPS, Backup  # noqa: E402


def _stem_of(path: Path) -> str:
    """Return the filename stem with the trailing _<date>_<time> chopped."""
    parts = path.stem.rsplit("_", 2)
    return "_".join(parts[:-2]) if len(parts) >= 3 else path.stem


def plan_pruning(
    files: Iterable[Path],
    *,
    keep: int,
    days: int,
    now: datetime | None = None,
) -> tuple[list[Path], list[Path]]:
    """Return (to_keep, to_delete) given a retention policy.

    Pure function — does no filesystem mutation. Easy to unit-test if
    we ever add a test for this CLI.
    """
    now = now or datetime.now()
    cutoff = now - timedelta(days=days)

    # Group by stem so we keep the N most-recent of EACH state file.
    by_stem: dict[str, list[Path]] = defaultdict(list)
    for f in files:
        by_stem[_stem_of(f)].append(f)

    keep_set: set[Path] = set()
    for stem, group in by_stem.items():
        # Sort newest-first so we keep the head.
        group.sort(key=lambda p: Backup.parse_timestamp(p) or datetime.min, reverse=True)
        keep_set.update(group[:keep])
        for p in group[keep:]:
            ts = Backup.parse_timestamp(p)
            if ts is None or ts >= cutoff:
                keep_set.add(p)

    to_keep = sorted(keep_set)
    to_delete = sorted(set(files) - keep_set)
    return to_keep, to_delete


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--keep", type=int, default=5, help="Minimum copies to retain per state-file stem (default 5).")
    ap.add_argument("--days", type=int, default=7, help="Keep all files newer than this many days (default 7).")
    ap.add_argument("--subdir", default=None, help="Optional sub-directory under state_backups/ to limit pruning to.")
    ap.add_argument("--all-subdirs", action="store_true", help="Prune the top level AND every sub-directory.")
    ap.add_argument("--apply", action="store_true", help="Actually delete files. Without this, prints a plan only.")
    args = ap.parse_args(argv)

    if not STATE_BACKUPS.exists():
        print(f"No backup directory at {STATE_BACKUPS}; nothing to do.")
        return 0

    targets: list[tuple[str | None, Path]] = []
    if args.all_subdirs:
        targets.append((None, STATE_BACKUPS))
        for sub in sorted(p for p in STATE_BACKUPS.iterdir() if p.is_dir()):
            targets.append((sub.name, sub))
    else:
        sub = args.subdir
        targets.append((sub, STATE_BACKUPS / sub if sub else STATE_BACKUPS))

    overall_deleted = 0
    overall_kept = 0
    for label, base in targets:
        if not base.exists():
            continue
        files = [p for p in base.iterdir() if p.is_file()]
        if not files:
            continue
        keep, delete = plan_pruning(files, keep=args.keep, days=args.days)
        overall_kept += len(keep)
        overall_deleted += len(delete)
        loc = f"state_backups/{label}/" if label else "state_backups/"
        print(f"\n[{loc}] keep {len(keep)} / delete {len(delete)}")
        for p in delete:
            ts = Backup.parse_timestamp(p)
            stamp = ts.isoformat() if ts else "(no-ts)"
            print(f"  - {p.name}  [{stamp}]")
            if args.apply:
                p.unlink()

    verb = "deleted" if args.apply else "would delete"
    print(f"\nTotal: kept {overall_kept}, {verb} {overall_deleted} files.")
    if not args.apply and overall_deleted:
        print("(dry-run — re-run with --apply to actually delete)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
