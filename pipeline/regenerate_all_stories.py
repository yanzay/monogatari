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
from typing import Optional

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
    for sect in ("title",):
        for tok in story.get(sect, {}).get("tokens", []):
            for f in TOKEN_AUDIO_FIELDS:
                tok.pop(f, None)
    for sn in story.get("sentences", []):
        for f in SENTENCE_AUDIO_FIELDS:
            sn.pop(f, None)
        for tok in sn.get("tokens", []):
            for f in TOKEN_AUDIO_FIELDS:
                tok.pop(f, None)


def _normalize_first_occurrence_flags(stories_dir: Path) -> None:
    """Honest library-wide first-occurrence pass.

    A `word_id` (resp. `grammar_id`) is marked `is_new` (resp. `is_new_grammar`)
    on EXACTLY ONE token in EXACTLY ONE story — the first story (by id) and,
    within that story, the first token in document order (title →
    sentences in source order) where the id appears.

    Story-level `new_words` and `new_grammar` arrays are recomputed to be
    exactly the ids that fired their flag in this story.

    No hints, no heuristics, no canonical fallback. The shipped library IS
    the source of truth.
    """
    seen_words: set[str] = set()
    seen_grammars: set[str] = set()
    paths = sorted(stories_dir.glob("story_*.json"), key=lambda p: int(p.stem.split("_")[1]))
    for path in paths:
        story = json.loads(path.read_text(encoding="utf-8"))

        # Strip any pre-existing flags so we have a clean slate.
        for _, t in _all_section_tokens(story):
            t.pop("is_new", None)
            t.pop("is_new_grammar", None)

        # Identify which words/grammars are first-seen in this story.
        first_in_story_words:    list[str] = []
        first_in_story_grammars: list[str] = []
        for _, t in _all_section_tokens(story):
            wid = t.get("word_id")
            if wid and wid not in seen_words:
                seen_words.add(wid)
                if wid not in first_in_story_words:
                    first_in_story_words.append(wid)
            gid = t.get("grammar_id")
            if not gid:
                infl = t.get("inflection")
                if isinstance(infl, dict):
                    gid = infl.get("grammar_id")
            if gid and gid not in seen_grammars:
                seen_grammars.add(gid)
                if gid not in first_in_story_grammars:
                    first_in_story_grammars.append(gid)

        # Stamp is_new on the FIRST SENTENCE occurrence of each new word
        # (validator semantics: title is decorative, the flag
        # belongs to the body). Fall back to title only when the
        # word never appears in any sentence in this story.
        sentence_first_word: dict[str, dict] = {}
        for sn in story.get("sentences", []):
            for t in sn.get("tokens", []):
                wid = t.get("word_id")
                if wid in first_in_story_words and wid not in sentence_first_word:
                    sentence_first_word[wid] = t
        title_first_word: dict[str, dict] = {}
        for sect in ("title",):
            for t in story.get(sect, {}).get("tokens", []):
                wid = t.get("word_id")
                if wid in first_in_story_words and wid not in title_first_word:
                    title_first_word[wid] = t
        for wid in first_in_story_words:
            target = sentence_first_word.get(wid) or title_first_word.get(wid)
            if target is not None:
                target["is_new"] = True

        # Same treatment for grammar.
        def _gid_of(t: dict) -> Optional[str]:
            g = t.get("grammar_id")
            if g:
                return g
            infl = t.get("inflection")
            if isinstance(infl, dict):
                return infl.get("grammar_id")
            return None

        sentence_first_g: dict[str, dict] = {}
        for sn in story.get("sentences", []):
            for t in sn.get("tokens", []):
                g = _gid_of(t)
                if g in first_in_story_grammars and g not in sentence_first_g:
                    sentence_first_g[g] = t
        title_first_g: dict[str, dict] = {}
        for sect in ("title",):
            for t in story.get(sect, {}).get("tokens", []):
                g = _gid_of(t)
                if g in first_in_story_grammars and g not in title_first_g:
                    title_first_g[g] = t
        for gid in first_in_story_grammars:
            target = sentence_first_g.get(gid) or title_first_g.get(gid)
            if target is not None:
                target["is_new_grammar"] = True

        story["new_words"] = first_in_story_words
        story["new_grammar"] = first_in_story_grammars

        path.write_text(json.dumps(story, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _refresh_vocab_metadata(vocab: dict, stories_dir: Path) -> None:
    """Recompute occurrences / first_story / last_seen_story for every word
    by scanning all shipped stories. Mirrors state_updater semantics:
    occurrences = number of stories the word appears in (not raw token count).
    """
    word_ids = set(vocab.get("words", {}).keys())
    # `occurrences` mirrors state_updater semantics: one increment per story
    # the word appears in, counting `sentences` only.
    sent_seen_in: dict[str, list[str]] = {wid: [] for wid in word_ids}
    # `first_story` / `last_seen_story` count ANY appearance (incl. title)
    any_seen_in: dict[str, list[str]] = {wid: [] for wid in word_ids}
    for path in sorted(stories_dir.glob("story_*.json"), key=lambda p: int(p.stem.split("_")[1])):
        story = json.loads(path.read_text(encoding="utf-8"))
        sid = path.stem
        sent_used: set[str] = set()
        any_used: set[str] = set()
        for sn in story.get("sentences", []):
            for t in sn.get("tokens", []):
                wid = t.get("word_id")
                if wid and wid in word_ids:
                    sent_used.add(wid)
                    any_used.add(wid)
        for sect in ("title",):
            for t in story.get(sect, {}).get("tokens", []):
                wid = t.get("word_id")
                if wid and wid in word_ids:
                    any_used.add(wid)
        for wid in sent_used:
            sent_seen_in[wid].append(sid)
        for wid in any_used:
            any_seen_in[wid].append(sid)
    for wid, w in vocab["words"].items():
        sents = sent_seen_in.get(wid, [])
        any_ = any_seen_in.get(wid, [])
        if sents or any_:
            w["occurrences"] = len(sents)
            if any_:
                w["first_story"] = any_[0]
                w["last_seen_story"] = any_[-1]


def _all_section_tokens(story: dict) -> list[tuple[str, dict]]:
    """Walk all tokens in (section_name, token) pairs, in document order."""
    out = []
    for sect_name in ("title",):
        for t in story.get(sect_name, {}).get("tokens", []):
            out.append((sect_name, t))
    for sn in story.get("sentences", []):
        for t in sn.get("tokens", []):
            out.append((f"sentence_{sn.get('idx')}", t))
    return out


def _carry_over_canonical_grammar(
    canon: dict,
    regen: dict,
    hint_grammar: set[str],
) -> int:
    """
    For each grammar_id in hint_grammar that isn't tagged on ANY regen token,
    find canonical's first occurrence (by section + surface), then locate the
    matching surface in regen and copy the grammar_id over.

    Returns the number of tags carried over.
    """
    # Build set of grammar_ids already present in regen
    present_in_regen: set[str] = set()
    for _, t in _all_section_tokens(regen):
        gid = t.get("grammar_id")
        if gid:
            present_in_regen.add(gid)
        infl = t.get("inflection")
        if isinstance(infl, dict) and infl.get("grammar_id"):
            present_in_regen.add(infl["grammar_id"])

    missing = hint_grammar - present_in_regen
    if not missing:
        return 0

    n_carried = 0
    for gid in missing:
        # Find canon's first token carrying this gid
        canon_loc = None
        for sect, t in _all_section_tokens(canon):
            if t.get("grammar_id") == gid or (
                isinstance(t.get("inflection"), dict)
                and t["inflection"].get("grammar_id") == gid
            ):
                canon_loc = (sect, t)
                break
        if not canon_loc:
            continue
        sect_name, canon_tok = canon_loc
        canon_surface = canon_tok.get("t")

        # Find matching regen token by section + surface
        regen_target = None
        for sect, t in _all_section_tokens(regen):
            if sect == sect_name and t.get("t") == canon_surface:
                regen_target = t
                break
        # Fallback: any section with same surface
        if regen_target is None:
            for _, t in _all_section_tokens(regen):
                if t.get("t") == canon_surface:
                    regen_target = t
                    break
        if regen_target is None:
            continue

        # Morphological aux tags that the converter often slaps on a verb
        # token; if canonical instead used a more specific LEXICAL tag (like
        # G021_aru_iru), we should override.
        # When canonical assigns a more specific lexical/discourse tag, allow
        # overriding the converter's generic morphological/particle tag.
        REPLACEABLE_AUX = {
            # Morphological aux on verbs
            "G026_masu_nonpast", "G013_mashita_past",
            "G036_masen", "G046_masen_deshita",
            "G022_i_adj",
            # Generic particles overridable by specific patterns
            # (e.g. と→G014_to_omoimasu in と思います context)
            "G010_to_and", "G006_kara_from", "G005_wo_object",
            "G001_wa_topic", "G002_ga_subject", "G009_mo_also",
            "G017_de_means", "G004_ni_location",
        }
        # Copy the grammar_id; respect canonical's placement (token-level
        # vs inside inflection)
        if canon_tok.get("grammar_id") == gid:
            existing = regen_target.get("grammar_id")
            if not existing or existing in REPLACEABLE_AUX:
                regen_target["grammar_id"] = gid
                n_carried += 1
        else:
            # gid was inside canon's inflection block
            infl = regen_target.setdefault("inflection", {})
            if not infl.get("grammar_id"):
                infl["grammar_id"] = gid
                n_carried += 1

    return n_carried


def regen_one(canon_path: Path, vocab: dict, grammar: dict) -> tuple[dict, dict, dict]:
    """Regenerate one story. Returns (bilingual_spec, regenerated, report)."""
    canon = json.loads(canon_path.read_text(encoding="utf-8"))
    spec = extract_spec(canon)
    regen, report = build_story(spec, vocab, grammar)
    # Carry over any grammar tags the converter didn't know how to emit
    # (so the validator's reinforcement / first-occurrence checks see the
    # right set of gids on tokens). is_new_grammar / new_grammar are NOT
    # set here — the library-wide first-occurrence pass owns those fields.
    canon_all_gids: set[str] = set()
    for _, t in _all_section_tokens(canon):
        if t.get("grammar_id"):
            canon_all_gids.add(t["grammar_id"])
        if isinstance(t.get("inflection"), dict) and t["inflection"].get("grammar_id"):
            canon_all_gids.add(t["inflection"]["grammar_id"])
    n = _carry_over_canonical_grammar(canon, regen, canon_all_gids)
    if n:
        report.setdefault("carried_grammar", n)
    # Demote 思います / 言います to role=aux when an earlier token in the
    # SAME sentence is と tagged with G014_to_omoimasu / G028_to_iimasu.
    # Canonical treats these as quotative aux verbs in this construction
    # even when the topic (e.g. 私は) intervenes between と and the verb.
    AUX_AFTER_TO = {
        "思います": "G014_to_omoimasu",
        "言います": "G028_to_iimasu",
    }
    for sn in regen.get("sentences", []):
        toks = sn.get("tokens", [])
        # Find a と with the relevant gid first; then any subsequent
        # 思います/言います in the same sentence becomes aux.
        active_gids: set[str] = set()
        for tok in toks:
            if tok.get("t") == "と":
                gid = tok.get("grammar_id")
                if gid in ("G014_to_omoimasu", "G028_to_iimasu"):
                    active_gids.add(gid)
            if tok.get("t") in AUX_AFTER_TO and AUX_AFTER_TO[tok["t"]] in active_gids:
                tok["role"] = "aux"
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

    if args.apply:
        # Honest library-wide first-occurrence pass for is_new / is_new_grammar
        # and per-story new_words / new_grammar arrays. Runs after every story
        # has been written so the walk sees the final shipped state.
        _normalize_first_occurrence_flags(ROOT / "stories")
        # Recompute occurrences / first_story / last_seen_story for all words
        # by scanning the regenerated stories. This keeps vocab_state in sync
        # with the actual library and satisfies the state-integrity tests.
        vpath = ROOT / "data" / "vocab_state.json"
        _refresh_vocab_metadata(vocab, ROOT / "stories")
        # Update next_word_id to max+1
        max_n = max(int(k[1:]) for k in vocab["words"].keys() if k.startswith("W"))
        vocab["next_word_id"] = f"W{max_n + 1:05d}"
        # Strip JMdict semicolons in meanings (split on '; ' → take first)
        # for ALL words (handles both freshly minted and previously appended).
        for w in vocab["words"].values():
            cleaned = []
            for m in w.get("meanings", []):
                if isinstance(m, str) and "; " in m:
                    cleaned.append(m.split("; ")[0].strip())
                else:
                    cleaned.append(m)
            w["meanings"] = cleaned
            # Drop the _minted_by marker if present
            w.pop("_minted_by", None)
        vpath.write_text(
            json.dumps(vocab, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        if minted_records:
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
