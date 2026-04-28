"""Class C: Cross-file referential integrity.

Stories ↔ audio ↔ engagement baselines ↔ stories index.
"""
from __future__ import annotations
import json
from pathlib import Path

import pytest


def test_stories_manifest_lists_every_story(root, story_paths):
    manifest_path = root / "stories" / "index.json"
    if not manifest_path.exists():
        pytest.skip("stories/index.json manifest not present")
    with manifest_path.open() as f:
        manifest = json.load(f)
    # Supported manifest shapes:
    #   v1 list:                  [{...}, ...]
    #   v1 dict:                  {"<id>": {...}, ...}
    #   v1 inline:                {"stories": [...], ...}
    #   v2 paginated:             {"version": 2, "pages": [{"path": "...",
    #                              "n_stories": ...}, ...], ["stories": [...]]}
    #     For v2 with no inlined "stories" (corpora > page_size), we walk the
    #     page payloads under stories/index/p{NNN}.json and aggregate.
    entries: list = []
    if isinstance(manifest, dict) and "pages" in manifest and "stories" not in manifest:
        # v2 paginated — load every page payload.
        for page_meta in manifest["pages"]:
            page_path = root / page_meta["path"]
            if not page_path.exists():
                pytest.fail(f"Manifest references missing page payload: {page_path}")
            with page_path.open() as f:
                page = json.load(f)
            entries.extend(page.get("stories", []))
    elif isinstance(manifest, dict) and "stories" in manifest:
        entries = manifest["stories"]
    elif isinstance(manifest, list):
        entries = manifest
    elif isinstance(manifest, dict):
        entries = [{"id": k, **v} for k, v in manifest.items()
                   if isinstance(v, dict)]
    def normalise(sid):
        if isinstance(sid, int):
            return f"story_{sid}"
        if isinstance(sid, str):
            if sid.startswith("story_"):
                return sid
            if sid.isdigit():
                return f"story_{sid}"
            return sid.replace(".json", "").split("/")[-1]
        return None

    listed = set()
    for entry in entries:
        if isinstance(entry, dict):
            sid = entry.get("story_id") or entry.get("id") or entry.get("path", "")
        else:
            sid = entry
        n = normalise(sid)
        if n:
            listed.add(n)
    on_disk = {p.stem for p in story_paths}
    missing = on_disk - listed
    extra = listed - on_disk
    assert not missing, f"Stories on disk but missing from manifest: {missing}"
    assert not extra, f"Manifest entries with no corresponding file: {extra}"


def test_engagement_baseline_covers_every_story(root, stories):
    # Baseline lives in pipeline/, not at root
    baseline_path = root / "pipeline" / "engagement_baseline.json"
    if not baseline_path.exists():
        pytest.skip("pipeline/engagement_baseline.json not present")
    with baseline_path.open() as f:
        baseline = json.load(f)
    if isinstance(baseline, dict):
        if "reviews" in baseline:
            entries = baseline["reviews"]
        else:
            entries = [{"story_id": k, **v} for k, v in baseline.items() if isinstance(v, dict)]
    else:
        entries = baseline
    def normalise(sid):
        if isinstance(sid, int):
            return f"story_{sid}"
        if isinstance(sid, str):
            if sid.startswith("story_"):
                return sid
            if sid.isdigit():
                return f"story_{sid}"
        return None

    rated = set()
    for entry in entries:
        if isinstance(entry, dict):
            sid = entry.get("story_id") or entry.get("id")
            n = normalise(sid)
            if n:
                rated.add(n)
        else:
            n = normalise(entry)
            if n:
                rated.add(n)
    on_disk = {s["_id"] for s in stories}
    missing = on_disk - rated
    assert not missing, f"Stories without engagement baseline: {missing}"


def test_audio_manifest_files_exist_on_disk(root, stories):
    """Every audio file referenced in a story's audio.sentence_audio / word_audio must exist."""
    bad = []
    for story in stories:
        audio = story.get("audio", {})
        sentence_audio = audio.get("sentence_audio", [])
        word_audio = audio.get("word_audio", {})
        for entry in sentence_audio:
            path = entry.get("file") if isinstance(entry, dict) else entry
            if path:
                full = root / path
                if not full.exists():
                    bad.append(f"{story['_id']} sentence audio missing: {path}")
        for wid, path in word_audio.items():
            if path:
                full = root / path
                if not full.exists():
                    bad.append(f"{story['_id']} word audio missing for {wid}: {path}")
    assert not bad, "Missing audio files:\n  " + "\n  ".join(bad)


def test_audio_directory_matches_shipped_stories(root, stories):
    """Audio folders must correspond to shipped story files (no orphan story_N folder).

    Layout (as of 2026-04-29):
      audio/story_<N>/s<idx>.mp3   — per-sentence audio (story-scoped)
      audio/words/<word_id>.mp3    — per-word audio (flat, decoupled
                                     from any story)

    The flat words/ directory is allowed; only orphan story_N dirs fail.
    """
    audio_dir = root / "audio"
    if not audio_dir.exists():
        pytest.skip("no audio directory")

    shipped_ids = {s["_id"] for s in stories}
    on_disk_dirs = {d.name for d in audio_dir.iterdir() if d.is_dir() and d.name.startswith("story_")}
    orphan_dirs = on_disk_dirs - shipped_ids
    assert not orphan_dirs, f"Audio folders for non-existent stories: {sorted(orphan_dirs)}"


def test_audio_sentence_files_match_story_sentence_count(root, stories):
    """audio/story_N/sentence_*.mp3 should have one file per shipped sentence."""
    audio_dir = root / "audio"
    if not audio_dir.exists():
        pytest.skip("no audio directory")

    bad = []
    for story in stories:
        story_audio = audio_dir / story["_id"]
        if not story_audio.exists():
            continue  # audio not yet generated for this story
        sentence_files = sorted(story_audio.glob("s*.mp3"))
        n_sentences = len(story.get("sentences", []))
        if len(sentence_files) != n_sentences:
            bad.append(
                f"{story['_id']}: {len(sentence_files)} audio files vs {n_sentences} sentences"
            )
    assert not bad, "Audio/sentence count mismatch:\n  " + "\n  ".join(bad)


def test_audio_word_files_only_for_known_words(root, stories, vocab):
    """audio/words/<wid>.mp3 must reference word_ids that exist in vocab.

    As of 2026-04-29 word audio lives in a flat per-word directory
    (`audio/words/`), decoupled from any story. The orphan check also
    rejects any leftover legacy `audio/story_<N>/w_*.mp3` files — they
    should have been migrated to the flat layout and a stray one would
    indicate a half-completed move.
    """
    audio_dir = root / "audio"
    if not audio_dir.exists():
        pytest.skip("no audio directory")

    known_words = set(vocab["words"].keys())
    bad = []

    # Flat per-word directory (current layout).
    words_dir = audio_dir / "words"
    if words_dir.is_dir():
        for f in words_dir.glob("*.mp3"):
            wid = f.stem
            if wid not in known_words:
                bad.append(f"words/{f.name}: unknown word_id")

    # Legacy per-story word audio — should be empty after the migration.
    legacy = []
    for story_audio in sorted(audio_dir.iterdir()):
        if not story_audio.is_dir() or not story_audio.name.startswith("story_"):
            continue
        for f in story_audio.glob("w_*.mp3"):
            legacy.append(f"{story_audio.name}/{f.name}")
    assert not legacy, (
        "Legacy per-story word audio still on disk (should be in audio/words/): "
        + ", ".join(legacy)
    )

    assert not bad, "Audio files for unknown word_ids:\n  " + "\n  ".join(bad)


# ── v0.13: content-vs-audio drift detection ──────────────────────────────────
#
# These tests catch the failure mode where JP tokens are edited post-ship
# (e.g. a typo fix or the 2026-04-22 semantic-sanity audit) but the audio
# files on disk still speak the old tokens. The audio_builder now writes a
# 12-char SHA-256 prefix of the exact TTS-input string into every sentence
# (`audio_hash`) and into a parallel map for word audio (`word_audio_hash`).
# Recomputing the hash here and comparing flags any drift instantly.
#
# Companion check: any 0-byte audio file is also caught here, regardless of
# whether the hash matches — that's how the broken story 13 ship slipped
# through previously (manifest said has_audio:true; files were 0 bytes).
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))


def _recompute_sentence_hash(sent: dict) -> str:
    from audio_builder import _audio_hash, sentence_audio_text
    return _audio_hash(sentence_audio_text(sent))


def _recompute_word_hash(surface_or_kana: str) -> str:
    from audio_builder import _audio_hash
    return _audio_hash(surface_or_kana)


def test_audio_no_zero_byte_files(root, stories):
    """Every shipped audio file must be > 0 bytes. Catches ship failures
    where the TTS call returned an error but the empty file was still
    created (story 13 lived in this state for a release)."""
    audio_dir = root / "audio"
    if not audio_dir.exists():
        pytest.skip("no audio directory")
    bad = []
    for story in stories:
        story_audio = audio_dir / story["_id"]
        if not story_audio.exists():
            continue
        for f in sorted(story_audio.iterdir()):
            if f.is_file() and f.suffix.lower() in (".mp3", ".wav", ".ogg"):
                if f.stat().st_size == 0:
                    bad.append(f"{story['_id']}/{f.name}: 0 bytes")
    assert not bad, "Zero-byte audio files:\n  " + "\n  ".join(bad)


def test_sentence_audio_hash_matches_tokens(stories):
    """Each sentence's stored `audio_hash` (written by audio_builder when
    the .mp3 was generated) must equal the recomputed hash of its current
    JP tokens. Mismatch == audio drift, and the story must be regenerated
    via `pipeline/audio_builder.py ... --backend google --force`.

    Stories that have not yet been built with v0.13 (no `audio_hash` field
    on any sentence) are skipped — the next backfill will populate them.
    """
    drifted = []
    not_yet_hashed = []
    for story in stories:
        any_hash = any("audio_hash" in s for s in story.get("sentences", []))
        if not any_hash:
            not_yet_hashed.append(story["_id"])
            continue
        for sent in story.get("sentences", []):
            stored = sent.get("audio_hash")
            if not stored:
                drifted.append(
                    f"{story['_id']} s{sent.get('idx', '?')}: missing audio_hash"
                )
                continue
            actual = _recompute_sentence_hash(sent)
            if stored != actual:
                drifted.append(
                    f"{story['_id']} s{sent.get('idx', '?')}: "
                    f"stored {stored} != current {actual} "
                    f"— regenerate audio with --force"
                )
    if not_yet_hashed:
        # Soft-skip individual stories, but still fail if any *hashed*
        # story has drifted. This lets v0.13 land before backfilling all
        # 16 stories at once.
        print(f"\n  (audio_hash not yet present on: {not_yet_hashed})")
    assert not drifted, "Audio drift detected:\n  " + "\n  ".join(drifted)


def test_word_audio_hash_matches_vocab(stories, vocab):
    """Each story's `word_audio_hash[wid]` must match the current vocab
    surface for that word. Mismatch == the dictionary form of the word
    was edited after the audio was built, and the word audio must be
    regenerated."""
    drifted = []
    for story in stories:
        wah = story.get("word_audio_hash") or {}
        if not wah:
            continue  # story not yet hashed under v0.13
        for wid, stored in wah.items():
            word = vocab["words"].get(wid)
            if not word:
                drifted.append(f"{story['_id']} {wid}: word not in vocab")
                continue
            text = word.get("surface") or word.get("kana") or ""
            actual = _recompute_word_hash(text)
            if stored != actual:
                drifted.append(
                    f"{story['_id']} word_audio[{wid}]: "
                    f"stored {stored} != current {actual} "
                    f"(surface now '{text}') — regenerate audio with --force"
                )
    assert not drifted, "Word audio drift detected:\n  " + "\n  ".join(drifted)
