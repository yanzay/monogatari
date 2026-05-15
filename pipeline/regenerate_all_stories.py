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


def _preflight_dependencies() -> None:
    """Hard-fail early if the Japanese-NLP toolchain isn't importable.

    Without these, ``text_to_story.build_story`` silently produces sentences
    with empty token arrays. The orphan-vocab cleanup at the end of ``main``
    then concludes that *every* word is unreferenced and wipes
    ``data/vocab_state.json`` — a one-line traceback after a multi-minute run
    that is very expensive to recover from. Catching this up front converts a
    catastrophic data-loss bug into a one-line install hint.

    Common cause: running the regenerator with the system Python instead of
    the project venv. See README.md → "Setup" for the canonical incantation
    (``source .venv/bin/activate``).
    """
    missing: list[str] = []
    for mod in ("fugashi", "jamdict", "jaconv"):
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    if missing:
        sys.stderr.write(
            "ERROR: required Japanese-NLP packages not importable: "
            + ", ".join(missing) + "\n"
            "       The regenerator would silently produce empty token arrays\n"
            "       and the orphan-vocab cleanup would wipe data/vocab_state.json.\n"
            "       Activate the project venv first:\n"
            "         source .venv/bin/activate\n"
            "       (or `pip install -r requirements.txt` if the venv is missing)\n"
        )
        sys.exit(2)


def _assert_tokens_nonempty(sid: int, regen: dict) -> None:
    """Refuse to write a regenerated story whose sentences have no tokens.

    A non-empty bilingual spec that round-trips to zero tokens means
    ``text_to_story`` failed silently (e.g. an upstream dependency import
    raised, a fugashi tagger constructor returned None, or the bilingual
    JSON's ``sentences[].jp`` field went missing). Either way, writing the
    empty result would corrupt the shipped library and cascade into a
    vocab_state wipe at the end of ``main``. Crash loudly instead.
    """
    sentences = regen.get("sentences") or []
    if not sentences:
        return  # bilingual spec with zero sentences — let the validator complain.
    empty_idxs = [s.get("idx", i) for i, s in enumerate(sentences)
                  if not s.get("tokens")]
    if empty_idxs:
        raise RuntimeError(
            f"story {sid}: {len(empty_idxs)}/{len(sentences)} sentence(s) "
            f"produced zero tokens (sentence indices {empty_idxs[:5]}"
            f"{'...' if len(empty_idxs) > 5 else ''}). "
            "This indicates text_to_story silently failed — usually a missing "
            "Japanese-NLP dependency. Refusing to write empty tokens (would "
            "wipe vocab_state during orphan cleanup). Activate the venv: "
            "`source .venv/bin/activate`."
        )


def extract_spec(canonical: dict) -> dict:
    """Bootstrap path only: derive a bilingual spec from a shipped story.
    Used the very first time a story passes through the regenerator,
    when no pipeline/inputs/story_N.bilingual.json exists yet. Once the
    bilingual spec is on disk, it becomes the source of truth and this
    function is not called again for that story.
    """
    return {
        "story_id": canonical["story_id"],
        "title":    {"jp": canonical["title"]["jp"], "en": canonical["title"]["en"]},
        "sentences": [
            {"jp": "".join(t.get("t", "") for t in s["tokens"]), "en": s["gloss_en"]}
            for s in canonical["sentences"]
        ],
    }


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


def _stamp_first_occurrence_in_memory(library: dict[int, dict]) -> None:
    """Honest library-wide first-occurrence pass — operates in-memory.

    A `word_id` (resp. `grammar_id`) is marked `is_new` (resp. `is_new_grammar`)
    on EXACTLY ONE token in EXACTLY ONE story — the first story (by id) and,
    within that story, the first token in document order (title →
    sentences in source order) where the id appears.

    Story-level `new_words` and `new_grammar` arrays are recomputed to be
    exactly the ids that fired their flag in this story.

    `library` is mutated in place. Caller is responsible for persistence.

    No hints, no heuristics, no canonical fallback. The shipped library IS
    the source of truth.
    """
    seen_words: set[str] = set()
    seen_grammars: set[str] = set()

    def _gid_of(t: dict) -> Optional[str]:
        g = t.get("grammar_id")
        if g:
            return g
        infl = t.get("inflection")
        if isinstance(infl, dict):
            return infl.get("grammar_id")
        return None

    for sid in sorted(library):
        story = library[sid]

        # Strip any pre-existing flags so we have a clean slate.
        for _, t in _all_section_tokens(story):
            t.pop("is_new", None)
            t.pop("is_new_grammar", None)

        # Identify which words/grammars are first-seen in this story.
        first_in_story_words: list[str] = []
        first_in_story_grammars: list[str] = []
        for _, t in _all_section_tokens(story):
            wid = t.get("word_id")
            if wid and wid not in seen_words:
                seen_words.add(wid)
                if wid not in first_in_story_words:
                    first_in_story_words.append(wid)
            gid = _gid_of(t)
            if gid and gid not in seen_grammars:
                seen_grammars.add(gid)
                if gid not in first_in_story_grammars:
                    first_in_story_grammars.append(gid)

        # Stamp is_new on the FIRST SENTENCE occurrence of each new word
        # (validator semantics: title is decorative, the flag belongs to
        # the body). Fall back to title only when the word never appears
        # in any sentence in this story.
        sentence_first_word: dict[str, dict] = {}
        for sn in story.get("sentences", []):
            for t in sn.get("tokens", []):
                wid = t.get("word_id")
                if wid in first_in_story_words and wid not in sentence_first_word:
                    sentence_first_word[wid] = t
        title_first_word: dict[str, dict] = {}
        for t in (story.get("title") or {}).get("tokens", []):
            wid = t.get("word_id")
            if wid in first_in_story_words and wid not in title_first_word:
                title_first_word[wid] = t
        for wid in first_in_story_words:
            target = sentence_first_word.get(wid) or title_first_word.get(wid)
            if target is not None:
                target["is_new"] = True

        # Same treatment for grammar.
        sentence_first_g: dict[str, dict] = {}
        for sn in story.get("sentences", []):
            for t in sn.get("tokens", []):
                g = _gid_of(t)
                if g in first_in_story_grammars and g not in sentence_first_g:
                    sentence_first_g[g] = t
        title_first_g: dict[str, dict] = {}
        for t in (story.get("title") or {}).get("tokens", []):
            g = _gid_of(t)
            if g in first_in_story_grammars and g not in title_first_g:
                title_first_g[g] = t
        for gid in first_in_story_grammars:
            target = sentence_first_g.get(gid) or title_first_g.get(gid)
            if target is not None:
                target["is_new_grammar"] = True

        story["new_words"] = first_in_story_words
        story["new_grammar"] = first_in_story_grammars


def _normalize_first_occurrence_flags(stories_dir: Path) -> None:
    """Disk-backed wrapper around `_stamp_first_occurrence_in_memory`.

    Reads every shipped story, applies the library-wide pass in memory,
    then writes each one back. Used by the --apply path.
    """
    paths = sorted(stories_dir.glob("story_*.json"),
                   key=lambda p: int(p.stem.split("_")[1]))
    library: dict[int, dict] = {}
    for path in paths:
        sid = int(path.stem.split("_")[1])
        library[sid] = json.loads(path.read_text(encoding="utf-8"))

    _stamp_first_occurrence_in_memory(library)

    for path in paths:
        sid = int(path.stem.split("_")[1])
        path.write_text(
            json.dumps(library[sid], ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


# `_refresh_vocab_metadata` removed 2026-05-01 (Phase B derive-on-read).
#
# This function used to write `occurrences`, `first_story`, and
# `last_seen_story` directly onto vocab_state entries on every regen.
# Phase B made these derived: `derive_vocab_attributions(corpus)` is the
# single source of truth and `build_vocab_attributions` projects it to
# `data/vocab_attributions.json` for the reader. The old function was
# silently re-introducing the writes, leaving the corpus in a state
# where `test_vocab_state_carries_no_attribution_fields` failed after
# every `--apply`. Removed to honor the Phase B contract.


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


def regen_one(
    canon_path: Path,
    vocab: dict,
    grammar: dict,
    inputs_dir: Optional[Path] = None,
) -> tuple[dict, dict, dict]:
    """Regenerate one story. Returns (bilingual_spec, regenerated, report).

    Source-of-truth precedence:
      1. pipeline/inputs/story_N.bilingual.json (if present and non-empty) —
         the human-editable bilingual spec is the canonical input.
      2. Otherwise, extract a spec from the shipped story_N.json itself
         (initial bootstrap path).
    """
    canon = json.loads(canon_path.read_text(encoding="utf-8"))
    sid = canon.get("story_id")
    spec_path: Optional[Path] = None
    if inputs_dir is not None and sid is not None:
        candidate = inputs_dir / f"story_{sid}.bilingual.json"
        if candidate.exists():
            spec_path = candidate
    if spec_path is not None:
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
    else:
        spec = extract_spec(canon)
    regen, report = build_story(spec, vocab, grammar)
    # Sentence-level post-pass for context-sensitive grammar tagging the
    # per-token converter cannot determine alone:
    #
    #   * 何 / なに / なん → N5_nan_what (interrogative)
    #   * あの / この / その / どの → N5_kosoado (when role=content
    #     and the underlying surface is one of these demonstratives)
    #   * The quotative ~と思います / ~と言います construction:
    #       - retag と as N4_to_omoimasu / N4_to_iimasu (was N5_to_and)
    #       - demote 思います / 言います to role=aux
    #     Triggers when 思います/言います appears anywhere later in the same
    #     sentence as a と (the topic 私は often intervenes between them).
    # Surface → grammar_id maps applied during the post-pass. Some require
    # context (kosoado must be a content-pos demonstrative; 一人/二人 must
    # immediately precede the relevant noun, etc.) — handled below.
    NAN_SURFACES = {"何", "なに", "なん"}
    KOSOADO_SURFACES = {"あの", "この", "その", "どの"}
    INTERROGATIVE_GIDS = {
        "だれ": "N5_dare_who", "誰":   "N5_dare_who",
        "どこ": "N5_doko_where",
        "いつ": "N5_itsu_when",
        "なぜ": "N5_naze_doshite",
        "どうして": "N5_naze_doshite",
    }
    COUNTER_SURFACES = {"一人", "二人", "三人", "四人", "五人", "ひとり", "ふたり"}
    ARU_IRU_BASES   = {"ある", "いる"}
    QUOTATIVE_VERBS = {
        "思います": "N4_to_omoimasu",
        "言います": "N4_to_iimasu",
    }
    # ほしい — N5_hoshii (paradigm anchor for "want a thing"). Mirrored from
    # author_loop._apply_post_pass_attributions; see that function for the
    # rationale and KNOWN_AUTO_GRAMMAR_DEFINITIONS for the state-entry
    # definition.
    HOSHII_SURFACES = {"ほしい", "ほしかった", "ほしくない"}
    # Post-pass C surfaces: clause-level constructs detected by sentence shape.
    # N5_kara_because: clause-final から after a verb/adj/です stem (reason clause)
    #   — distinguished from N5_kara_from (locative/temporal から after a noun).
    # N5_masen: polite-negative verb ending ません (e.g. 来ません、待ちません).
    #   — only tag the ません token; role must be content (not already aux).
    # N5_masenka: ませんか sentence-final invitation.
    # N5_ga_but: clause-conjunctive が meaning "but" — tag the が token that
    #   immediately follows a predicate (verb/adj/です stem) and precedes another clause.
    MASEN_SURFACE    = "ません"
    MASENKA_SURFACE  = "ませんか"
    KA_SURFACE       = "か"
    for sn in regen.get("sentences", []):
        toks = sn.get("tokens", [])
        # Pass A: simple surface-based retagging
        for tok in toks:
            t = tok.get("t")
            # Interrogative content words
            if t in NAN_SURFACES:
                tok["grammar_id"] = "N5_nan_what"
            elif t in KOSOADO_SURFACES and tok.get("role") == "content":
                tok["grammar_id"] = "N5_kosoado"
            elif t in INTERROGATIVE_GIDS:
                tok["grammar_id"] = INTERROGATIVE_GIDS[t]
            elif t in COUNTER_SURFACES and tok.get("role") == "content":
                tok["grammar_id"] = "N5_counters"
            elif t in HOSHII_SURFACES and tok.get("role") == "content":
                tok["grammar_id"] = "N5_hoshii"
            # ある/いる existence verbs (lexical, not the te-iru aux).
            # Override the generic N5_masu_nonpast that the converter
            # assigns by default, but preserve more specific tags such as
            # N5_ko_arimasen (negative-polite ありません).
            elif tok.get("role") == "content":
                base = (tok.get("inflection") or {}).get("base")
                cur_gid = tok.get("grammar_id")
                if base in ARU_IRU_BASES and cur_gid in (None, "N5_masu_nonpast"):
                    tok["grammar_id"] = "N5_aru_iru"
        # Pass B: quotative と + 思います/言います construction.
        # Find the latest quotative verb in the sentence; then walk back to
        # the nearest preceding と and retag both.
        for j in range(len(toks) - 1, -1, -1):
            qv = toks[j].get("t")
            if qv in QUOTATIVE_VERBS:
                quot_gid = QUOTATIVE_VERBS[qv]
                # Find the と that precedes this verb
                for k in range(j - 1, -1, -1):
                    if toks[k].get("t") == "と" and toks[k].get("role") == "particle":
                        toks[k]["grammar_id"] = quot_gid
                        toks[j]["role"] = "aux"
                        break
        # Pass C: clause-level constructs.
        for j, tok in enumerate(toks):
            t = tok.get("t", "")
            # N5_masenka — ませんか (invitation)
            # Handles both fused single-token 「ませんか」 and the more common
            # two-token split 「ません」+「か」where か is sentence-final.
            if t == MASENKA_SURFACE:
                tok["grammar_id"] = "N5_masenka"
            elif tok.get("role") == "content" and (
                    t == MASEN_SURFACE or t.endswith(MASEN_SURFACE)):
                # N5_ko_arimasen — negative existence: ありません (or compound あり
                # ません). Must not override an already-correct tag from Pass A.
                base = (tok.get("inflection") or {}).get("base", "")
                if t in {"ありません"} or base in {"ある", "有る"}:
                    # Only set if not already tagged more specifically by Pass A
                    cur = tok.get("grammar_id") or ""
                    if cur in (None, "", "N5_masu_nonpast", "N5_masen"):
                        tok["grammar_id"] = "N5_ko_arimasen"
                else:
                    # Check if the next token is sentence-final か (invitation)
                    nxt = toks[j + 1] if j + 1 < len(toks) else None
                    nxt2 = toks[j + 2] if j + 2 < len(toks) else None
                    # 〜ません + か (sentence-final) = N5_masenka.
                    # Tag only the verb token as G041; the particle か retains
                    # its N5_ka_question tag (they co-occur legitimately).
                    if (nxt is not None and nxt.get("t") == KA_SURFACE
                            and (nxt2 is None or nxt2.get("t") in {"。", "？", "!"})):
                        tok["grammar_id"] = "N5_masenka"
                        # do NOT retag か — leave it as N5_ka_question
                    else:
                        # N5_masen — standalone polite negative (来ません, 待ちません…)
                        tok["grammar_id"] = "N5_masen"
            # N5_kara_because — から after a predicate (not a plain noun)
            # Heuristic: the token immediately before から is not role=content
            # with a noun-like grammar_id (i.e. it is a verb/adj/copula surface).
            elif t == "から" and tok.get("role") == "particle":
                prev = toks[j - 1] if j > 0 else None
                if prev is not None:
                    prev_role = prev.get("role", "")
                    prev_gid  = prev.get("grammar_id") or ""
                    # Locative/temporal から follows a noun content token tagged
                    # with no grammar_id or a noun-like id (G006 already set).
                    # Reason から follows a predicate: verb (content with masu/
                    # plain base) or copula (です/だ).
                    prev_t = prev.get("t", "")
                    is_predicate = (
                        prev_t in {"です", "だ", "ます"}
                        or prev_t.endswith("ます")  # e.g. 来ます, 歩きます
                        or prev_t.endswith("ません")  # negative predicate
                        or prev_t.endswith("した")   # past predicate
                        or prev_role in {"aux"}
                        or (prev_role == "content" and prev_gid not in (None, "", "N5_kara_from")
                            and not prev_gid.startswith("G00"))  # noun/location gids tend to be low
                    )
                    if is_predicate:
                        tok["grammar_id"] = "N5_kara_because"
            # N5_ga_but — clause-conjunctive が (follows predicate, precedes clause)
            elif t == "が" and tok.get("role") == "particle":
                prev = toks[j - 1] if j > 0 else None
                nxt  = toks[j + 1] if j + 1 < len(toks) else None
                if prev is not None and nxt is not None:
                    prev_t = prev.get("t", "")
                    # Contrastive が follows a predicate surface. The build's
                    # tokenizer collapses 〜ます/〜ません/〜ました into single
                    # multi-mora content tokens (e.g. "読みません"), so the
                    # bare-suffix set isn't enough — also check suffix shape.
                    is_predicate = (
                        prev_t in {"です", "だ", "ます", "せん"}
                        or prev_t.endswith("ます")
                        or prev_t.endswith("ません")
                        or prev_t.endswith("した")
                        or prev.get("role") == "aux"
                    )
                    if is_predicate:
                        tok["grammar_id"] = "N5_ga_but"
    strip_audio(regen)
    return spec, regen, report


def _collect_used_word_ids(stories_dir: Path) -> set[str]:
    """All word_ids referenced by any shipped story (title + sentences)."""
    used: set[str] = set()
    for path in stories_dir.glob("story_*.json"):
        try:
            s = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for sn in s.get("sentences", []):
            for t in sn.get("tokens", []):
                if t.get("word_id"):
                    used.add(t["word_id"])
        for t in (s.get("title") or {}).get("tokens", []):
            if t.get("word_id"):
                used.add(t["word_id"])
    return used


def _prune_orphan_vocab(vocab: dict, used_wids: set[str]) -> tuple[list[str], bool]:
    """Drop unreferenced word entries.

    Returns (orphan_ids, refused). `refused` is True if the orphan list is
    suspiciously large (>50% of vocab) — caller should abort the run.
    """
    orphans = [wid for wid in list(vocab.get("words", {}))
               if wid not in used_wids]
    total = len(vocab.get("words", {}))
    if total and len(orphans) > total // 2:
        return orphans, True
    for wid in orphans:
        del vocab["words"][wid]
    return orphans, False


def _refresh_next_word_id(vocab: dict) -> None:
    """Set vocab['next_word_id'] = 'W{max+1:05d}' over current keys.

    Empty-vocab safe: returns 'W00001' when no words have been minted yet
    (the v2.5 reload state). The legacy implementation crashed with
    `ValueError: max() iterable argument is empty` on an empty corpus.
    """
    nums = [int(k[1:]) for k in vocab.get("words", {}) if k.startswith("W")]
    max_n = max(nums) if nums else 0
    vocab["next_word_id"] = f"W{max_n + 1:05d}"


def _clean_jmdict_meanings(vocab: dict) -> None:
    """Trim '; '-joined JMdict meaning strings down to the first sense and
    drop the per-word _minted_by audit marker."""
    for w in vocab["words"].values():
        cleaned = []
        for m in w.get("meanings", []):
            if isinstance(m, str) and "; " in m:
                cleaned.append(m.split("; ")[0].strip())
            else:
                cleaned.append(m)
        w["meanings"] = cleaned
        w.pop("_minted_by", None)


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

    # Hard-fail before doing any work if the NLP toolchain is missing — see
    # _preflight_dependencies() docstring for why this matters.
    _preflight_dependencies()

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
        from _paths import Backup as _Backup, VOCAB_STATE as _VOCAB  # noqa: E402
        ts = _Backup.now()
        # Backup vocab_state too (we'll append minted entries)
        _Backup.save(_VOCAB, subdir="regenerate_all_stories", timestamp=ts)
        bak_dir = ROOT / "state_backups" / "regenerate_all_stories"

    minted_records: list[dict] = []
    n_total = len(story_paths)

    # ── Phase 1: regenerate every story in memory ────────────────────────────
    # We must complete every story BEFORE doing the library-wide
    # first-occurrence pass, otherwise the per-story `is_new` / `new_words` /
    # `new_grammar` arrays would always come out empty (the converter is
    # per-story; first-occurrence is library-wide). This was the historical
    # cause of the regenerator reporting all stories as "would change" in
    # dry-run mode even when the bytes after normalization were identical.
    regen_library: dict[int, dict] = {}
    spec_by_sid: dict[int, dict] = {}
    report_by_sid: dict[int, dict] = {}
    for canon_path in story_paths:
        sid = int(canon_path.stem.split("_")[1])
        try:
            spec, regen, report = regen_one(canon_path, vocab, grammar, inputs_dir=args.inputs_dir)
            # Defensive: a non-empty bilingual spec must produce non-empty
            # token arrays. If it doesn't, abort the whole run before the
            # orphan-vocab cleanup wipes data/vocab_state.json.
            _assert_tokens_nonempty(sid, regen)
        except RuntimeError as e:
            # Token-emptiness assertions are fatal — proceeding would corrupt
            # vocab_state. Stop the whole run, do NOT continue.
            print(f"  ✗ story {sid}: {e}")
            print()
            print("Aborting before vocab_state is touched. No files written this run.")
            return 2
        except Exception as e:
            print(f"  ✗ story {sid}: {type(e).__name__}: {e}")
            continue
        regen_library[sid] = regen
        spec_by_sid[sid] = spec
        report_by_sid[sid] = report

    # ── Phase 2: library-wide first-occurrence pass (in memory) ──────────────
    # Single-story regen always reports `is_new=*` / `new_words=[]` /
    # `new_grammar=[]` — those flags are *library-wide* properties that depend
    # on every prior story. We must apply that pass here even in dry-run so
    # the byte-comparison against the shipped library is meaningful.
    #
    # Single-story regen (--story N) skips this pass: we can't honestly
    # compute first-occurrence flags from one story alone, so the diff in
    # that mode is informational only ("token shape changed" rather than
    # "would change after a real regen").
    if args.story is None:
        _stamp_first_occurrence_in_memory(regen_library)

    # ── Phase 3: diff and (optionally) persist ───────────────────────────────
    n_changed = 0
    for canon_path in story_paths:
        sid = int(canon_path.stem.split("_")[1])
        if sid not in regen_library:
            continue  # error during phase 1 — already reported
        regen = regen_library[sid]
        report = report_by_sid[sid]
        spec = spec_by_sid[sid]

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
            # Backup current story (uses central Backup factory)
            from _paths import Backup as _Backup  # noqa: E402
            _Backup.save(canon_path, subdir="regenerate_all_stories", timestamp=ts)
            # Bilingual spec is the source of truth — only write it if it
            # doesn't already exist (i.e., bootstrap path). Once authored,
            # it's edited by humans and must NEVER be overwritten by
            # round-tripping through the shipped story.
            spec_path = args.inputs_dir / f"story_{sid}.bilingual.json"
            if not spec_path.exists():
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
                    # Phase B derive-on-read (2026-05-01): brand-new word
                    # records carry definition metadata only. `first_story`,
                    # `last_seen_story`, and `occurrences` are derived from
                    # the corpus by `derived_state.derive_vocab_attributions`
                    # and projected to `data/vocab_attributions.json`.
                    rec = {k: v for k, v in w.items() if not k.startswith("_")}
                    vocab["words"][w["id"]] = rec
                    minted_records.append(rec)

    if args.apply:
        # Refresh the reader-app manifest (stories/index.json) so it always
        # reflects the current shipped library after a regen. Done here rather
        # than as a separate post-step so authors never ship a stale manifest.
        from build_manifest import write_manifest as _write_manifest
        _root = _write_manifest(ROOT / "stories")
        n_pages = len(_root.get("pages", []))
        print(f"Refreshed stories/index.json + {n_pages} page(s) "
              f"({_root['n_stories']} stories)")
        # Phase A derive-on-read (2026-05-01): write the grammar-attribution
        # projection so the reader app gets fresh intro_in_story /
        # last_seen_story values without walking every story JSON. Same
        # rationale as the manifest refresh above — a stale projection
        # would make the grammar tab show wrong "introduced" filters.
        from build_grammar_attributions import write_attributions as _write_g_attrs
        _write_g_attrs()
        from derived_state import (
            derive_grammar_attributions as _derive_g,
            derive_vocab_attributions   as _derive_v,
        )
        print(f"Refreshed grammar_attributions.json ({len(_derive_g())} attributed gids)")
        # Phase B derive-on-read (2026-05-01): same treatment for vocab
        # first_story / last_seen_story / occurrences. The pre-Phase-B
        # state had `occurrences` drifting low by 5-15+ per word
        # because state_updater only counted tokens *new to this ship*
        # rather than re-counting from corpus. WordPopup and the vocab
        # route consume the projection; reader code joins it onto each
        # word in `loadVocabIndex()`.
        from build_vocab_attributions import write_attributions as _write_v_attrs
        _write_v_attrs()
        print(f"Refreshed vocab_attributions.json ({len(_derive_v())} attributed wids)")
        # Honest library-wide first-occurrence pass for is_new / is_new_grammar
        # and per-story new_words / new_grammar arrays. Runs after every story
        # has been written so the walk sees the final shipped state.
        _normalize_first_occurrence_flags(ROOT / "stories")
        # Recompute occurrences / first_story / last_seen_story for all words
        # by scanning the regenerated stories. This keeps vocab_state in sync
        # with the actual library and satisfies the state-integrity tests.
        vpath = ROOT / "data" / "vocab_state.json"
        # Drop any orphan vocab entries (words minted in past runs but no
        # longer referenced by any shipped story). The 50%-orphan safety net
        # in _prune_orphan_vocab catches silent text_to_story failures that
        # produce empty token arrays.
        used_wids = _collect_used_word_ids(ROOT / "stories")
        orphans, refused = _prune_orphan_vocab(vocab, used_wids)
        if refused:
            sys.stderr.write(
                f"REFUSING to drop {len(orphans)} orphan vocab record(s) — "
                f"that's more than half of vocab_state ({len(vocab.get('words', {}))}).\n"
                "       This almost always means text_to_story produced empty\n"
                "       token arrays. Activate the project venv and re-run:\n"
                "         source .venv/bin/activate\n"
            )
            return 2
        if orphans:
            print(f"Dropped {len(orphans)} orphan vocab record(s): {', '.join(orphans)}")
        # _refresh_vocab_metadata removed 2026-05-01 (Phase B derive-on-read).
        # The projection at static/data/vocab_attributions.json (rebuilt above)
        # is the single source of truth; vocab_state.json no longer carries
        # `occurrences`, `first_story`, or `last_seen_story`.
        _refresh_next_word_id(vocab)
        _clean_jmdict_meanings(vocab)
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
