#!/usr/bin/env python3
"""Delete orphan audio files that no longer correspond to live data.

Two failure modes this CLI cleans up:

1.  **Orphan word audio** — `audio/words/W*.mp3` files whose `wid` no
    longer appears in `data/vocab_state.json::words`. These are left
    behind by re-shipping a story whose first attempt minted a wid
    that the second attempt dropped (an ID-changing re-ship; see
    AGENTS.md "Audio cleanup after an ID-changing re-ship").

2.  **Orphan sentence audio** — `audio/story_<N>/sX.mp3` files whose
    sentence index `X` exceeds the current sentence count for story
    `N`. These are left behind by re-shipping a story with fewer
    sentences than the previous attempt.

3.  **Stray legacy per-story word audio** — `audio/story_<N>/w_W*.mp3`.
    The audio layout was migrated 2026-04-29 from per-story to flat
    `audio/words/`. Any `w_W*.mp3` file under a story directory is
    stale and should be deleted; its content has already been moved
    to `audio/words/`.

Usage:
    # Dry-run (default).
    python3 pipeline/tools/cleanup_audio_orphans.py

    # Actually delete.
    python3 pipeline/tools/cleanup_audio_orphans.py --apply
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _paths import (  # noqa: E402
    AUDIO,
    AUDIO_WORDS,
    iter_stories,
    load_vocab,
)

WID_FILE_RE = re.compile(r"^(W\d{5})\.mp3$")
SENT_FILE_RE = re.compile(r"^s(\d+)\.mp3$")
LEGACY_WORD_FILE_RE = re.compile(r"^w_(W\d{5})\.mp3$")


def find_word_orphans() -> list[Path]:
    """Files under audio/words/ whose wid is not in vocab_state."""
    if not AUDIO_WORDS.exists():
        return []
    vocab = load_vocab()
    known = set(vocab.get("words", {}).keys())
    orphans: list[Path] = []
    for path in sorted(AUDIO_WORDS.iterdir()):
        m = WID_FILE_RE.match(path.name)
        if not m:
            continue
        if m.group(1) not in known:
            orphans.append(path)
    return orphans


def find_sentence_orphans() -> list[Path]:
    """sX.mp3 files where X >= sentence count for that story."""
    if not AUDIO.exists():
        return []
    sentence_counts: dict[int, int] = {}
    for sid, story in iter_stories():
        sentence_counts[sid] = len(story.get("sentences") or [])

    orphans: list[Path] = []
    for story_dir in sorted(AUDIO.iterdir()):
        if not story_dir.is_dir():
            continue
        if not story_dir.name.startswith("story_"):
            continue
        try:
            sid = int(story_dir.name.split("_", 1)[1])
        except (ValueError, IndexError):
            continue
        max_idx = sentence_counts.get(sid, 0)  # 0 ⇒ story doesn't exist
        for path in sorted(story_dir.iterdir()):
            m = SENT_FILE_RE.match(path.name)
            if not m:
                continue
            idx = int(m.group(1))
            if idx >= max_idx:
                orphans.append(path)
    return orphans


def find_legacy_word_orphans() -> list[Path]:
    """w_W*.mp3 files left over under audio/story_*/ from the pre-flat layout."""
    if not AUDIO.exists():
        return []
    orphans: list[Path] = []
    for story_dir in sorted(AUDIO.iterdir()):
        if not story_dir.is_dir() or not story_dir.name.startswith("story_"):
            continue
        for path in sorted(story_dir.iterdir()):
            if LEGACY_WORD_FILE_RE.match(path.name):
                orphans.append(path)
    return orphans


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="Actually delete files. Default is dry-run.")
    args = ap.parse_args(argv)

    word_orphans = find_word_orphans()
    sent_orphans = find_sentence_orphans()
    legacy_orphans = find_legacy_word_orphans()

    print(f"audio/words/ orphans:        {len(word_orphans)}")
    for p in word_orphans:
        print(f"  - {p.relative_to(AUDIO.parent)}")
    print(f"audio/story_*/ sentence orphans: {len(sent_orphans)}")
    for p in sent_orphans:
        print(f"  - {p.relative_to(AUDIO.parent)}")
    print(f"audio/story_*/ legacy w_*.mp3 orphans: {len(legacy_orphans)}")
    for p in legacy_orphans:
        print(f"  - {p.relative_to(AUDIO.parent)}")

    total = len(word_orphans) + len(sent_orphans) + len(legacy_orphans)
    if total == 0:
        print("\nNothing to clean up.")
        return 0

    if not args.apply:
        print(f"\n(dry-run — re-run with --apply to delete {total} file(s))")
        return 0

    for p in (*word_orphans, *sent_orphans, *legacy_orphans):
        p.unlink()
    print(f"\nDeleted {total} orphan file(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
