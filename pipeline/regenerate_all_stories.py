#!/usr/bin/env python3
"""
Regenerate every shipped story by extracting its bilingual JP+EN spec and
running it back through pipeline/text_to_story.py.

This produces a fully deterministic, schema-consistent library where every
story is the exact output of the converter.

Audio fields (audio paths, audio_hash, word_audio, word_audio_hash,
checksum) are intentionally STRIPPED — audio is regenerated separately by
pipeline/audio_builder.py.

Usage:
    python3 pipeline/regenerate_all_stories.py --dry-run
    python3 pipeline/regenerate_all_stories.py --apply
    python3 pipeline/regenerate_all_stories.py --apply --story 12   # one story
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))

from text_to_story import build_story  # type: ignore
from text_to_story_roundtrip import extract_spec  # type: ignore


# Story-level fields that are populated by audio_builder.py / state_updater.py
# and should NOT come from the converter.
AUDIO_FIELDS = {
    "checksum",
    "word_audio",
    "word_audio_hash",
}
# Per-sentence fields produced by audio_builder
SENTENCE_AUDIO_FIELDS = {"audio", "audio_hash"}
# Per-token fields produced by audio_builder
TOKEN_AUDIO_FIELDS = {"audio_hash"}


def strip_audio(story: dict) -> None:
    """Remove all audio-related fields IN PLACE."""
    for f in AUDIO_FIELDS:
        story.pop(f, None)
    for sect in ("title", "subtitle"):
        for tok in story.get(sect, {}).get("tokens", []):
            for f in TOKEN_AUDIO_FIELDS:
                tok.pop(f, None)
    for sn in story.get("sentences", []):
        for f in SENTENCE_AUDIO_FIELDS:
            sn.pop(f, None)
        for tok in sn.get("tokens", []):
            for f in TOKEN_AUDIO_FIELDS:
                tok.pop(f, None)


def regen_one(canon_path: Path, vocab: dict, grammar: dict) -> tuple[dict, dict, dict]:
    """Regenerate one story. Returns (bilingual_spec, regenerated, report)."""
    canon = json.loads(canon_path.read_text(encoding="utf-8"))
    spec = extract_spec(canon)
    new_words_hint = set(canon.get("new_words") or [])
    new_grammar_hint = set(canon.get("new_grammar") or [])
    regen, report = build_story(
        spec, vocab, grammar,
        new_word_hint=new_words_hint,
        new_grammar_hint=new_grammar_hint,
    )
    # Preserve any plan_ref from canonical (informational only)
    if "plan_ref" in canon and "plan_ref" not in regen:
        regen["plan_ref"] = canon["plan_ref"]
    strip_audio(regen)
    return spec, regen, report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true",
                    help="Actually write to stories/. Default is dry-run.")
    ap.add_argument("--dry-run", action="store_true",
                    help="(default) Don't write anything.")
    ap.add_argument("--story", type=int, default=None,
                    help="Regenerate a single story by id.")
    ap.add_argument("--inputs-dir", type=Path,
                    default=ROOT / "pipeline" / "inputs",
                    help="Where to write bilingual specs.")
    args = ap.parse_args()

    if not args.apply:
        print("DRY RUN — pass --apply to actually write files.")

    vocab = json.loads((ROOT / "data" / "vocab_state.json").read_text(encoding="utf-8"))
    grammar = json.loads((ROOT / "data" / "grammar_state.json").read_text(encoding="utf-8"))

    args.inputs_dir.mkdir(parents=True, exist_ok=True)

    if args.story is not None:
        story_paths = [ROOT / "stories" / f"story_{args.story}.json"]
    else:
        story_paths = sorted(
            (ROOT / "stories").glob("story_*.json"),
            key=lambda p: int(p.stem.split("_")[1]),
        )

    if args.apply:
        bak_dir = ROOT / "state_backups" / "regenerate_all_stories"
        bak_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Backup vocab_state too (we'll append minted entries)
        vpath = ROOT / "data" / "vocab_state.json"
        shutil.copy(vpath, bak_dir / f"vocab_state_{ts}.json")

    minted_records: list[dict] = []
    n_changed = 0
    n_total = len(story_paths)
    for canon_path in story_paths:
        sid = int(canon_path.stem.split("_")[1])
        try:
            spec, regen, report = regen_one(canon_path, vocab, grammar)
        except Exception as e:
            print(f"  ✗ story {sid}: {type(e).__name__}: {e}")
            continue

        # Stable serialization for diff comparison
        canon_text = canon_path.read_text(encoding="utf-8").rstrip()
        new_text   = json.dumps(regen, ensure_ascii=False, indent=2)
        if canon_text == new_text:
            print(f"  · story {sid:3d}: identical")
            continue

        n_changed += 1
        n_unresolved = len(report.get("unresolved", []))
        n_minted     = len(report.get("new_words", []))
        n_unknown    = len(report.get("unknown_grammar", []))
        flags = []
        if n_unresolved: flags.append(f"unresolved={n_unresolved}")
        if n_minted:     flags.append(f"minted={n_minted}")
        if n_unknown:    flags.append(f"unknown_g={n_unknown}")
        print(f"  ★ story {sid:3d}: would change ({', '.join(flags) or 'no warnings'})")

        if args.apply:
            # Backup current story
            shutil.copy(canon_path, bak_dir / f"{canon_path.stem}_{ts}.json")
            # Write bilingual spec
            spec_path = args.inputs_dir / f"story_{sid}.bilingual.json"
            spec_path.write_text(
                json.dumps(spec, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            # Write regenerated story (audio-stripped)
            canon_path.write_text(new_text + "\n", encoding="utf-8")
            # Append any minted vocab to the live vocab dict so subsequent
            # stories see them.
            for w in report.get("new_words", []):
                if w["id"] not in vocab["words"]:
                    rec = {k: v for k, v in w.items() if not k.startswith("_")}
                    rec["first_story"] = canon_path.stem
                    rec["last_seen_story"] = canon_path.stem
                    rec["occurrences"] = 1
                    vocab["words"][w["id"]] = rec
                    minted_records.append(rec)

    if args.apply and minted_records:
        # Persist minted vocab back to data/vocab_state.json
        vpath = ROOT / "data" / "vocab_state.json"
        vpath.write_text(
            json.dumps(vocab, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print()
        print(f"Appended {len(minted_records)} minted vocab record(s) to vocab_state.json:")
        for r in minted_records:
            print(f"  + {r['id']}  {r['surface']:6s} ({r.get('pos')})  {r['meanings'][0][:50]}")

    print()
    print(f"Total stories:    {n_total}")
    print(f"Stories changed:  {n_changed}")
    if not args.apply:
        print()
        print("Run again with --apply to write changes.")
    else:
        print()
        print(f"Backups: state_backups/regenerate_all_stories/")
        print(f"Bilingual specs: {args.inputs_dir.relative_to(ROOT)}/")
        print()
        print("Next steps:")
        print("  python3 -m pytest pipeline/tests/")
        print("  python3 pipeline/audio_builder.py stories/story_N.json   # for affected stories")
    return 0


if __name__ == "__main__":
    sys.exit(main())
