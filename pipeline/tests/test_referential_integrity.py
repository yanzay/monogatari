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
    # Manifest may have either {stories:[...]} or [{...},...] or {<id>: {...}}
    if isinstance(manifest, dict) and "stories" in manifest:
        entries = manifest["stories"]
    elif isinstance(manifest, list):
        entries = manifest
    elif isinstance(manifest, dict):
        entries = [{"id": k, **v} for k, v in manifest.items()]
    else:
        entries = []
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

    Audio is referenced by convention: audio/story_N/sentence_M.mp3 and
    audio/story_N/word_W#####.mp3. We verify each audio/story_N corresponds
    to a shipped stories/story_N.json.
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
    """audio/story_N/word_W*.mp3 must reference word_ids that exist in vocab."""
    audio_dir = root / "audio"
    if not audio_dir.exists():
        pytest.skip("no audio directory")

    known_words = set(vocab["words"].keys())
    bad = []
    for story_audio in sorted(audio_dir.iterdir()):
        if not story_audio.is_dir():
            continue
        for f in story_audio.glob("w_*.mp3"):
            wid = f.stem.replace("w_", "")
            if wid not in known_words:
                bad.append(f"{story_audio.name}/{f.name}: unknown word_id")
    assert not bad, "Audio files for unknown word_ids:\n  " + "\n  ".join(bad)
