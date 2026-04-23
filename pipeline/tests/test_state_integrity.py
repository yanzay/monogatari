"""Class B: State integrity invariants.

Validates that vocab_state.json and grammar_state.json are internally
consistent and match what's actually in the stories.
"""
from __future__ import annotations
from collections import Counter
import re

import pytest
from _helpers import iter_tokens

VALID_POS = {
    "noun", "verb", "i_adjective", "na_adjective", "adverb",
    "pronoun", "expression", "particle", "interjection", "conjunction",
    "counter", "prefix", "suffix",
}
# Note: the legacy bare "adjective" tag was deliberately removed on
# 2026-04-23 in favour of the canonical i_adjective / na_adjective split.
# The bare tag silently bypassed the inflection check (Check 5) because
# validate.py couldn't pick the right conjugation table without an
# explicit class. Keep this set strict — see test_vocab_adjective_pos_canonical
# below for the migration guardrail.

VALID_VERB_CLASS = {
    "ichidan", "godan", "irregular", "irregular_kuru", "irregular_suru",
    "irregular_aru",
}

VALID_JLPT = {"N5", "N4", "N3", "N2", "N1"}

# Known na-adjectives whose kana happens to end in い. Maintained explicitly
# so the kana-shape heuristic doesn't false-positive against them. Add new
# exceptions here only after consulting a reference.
NA_ADJECTIVES_ENDING_IN_I = {
    "きれい",   # きれい (clean, beautiful) — classic exception
    "ゆうめい", # 有名 (famous) — though usually written 有名 (no い in stem)
    "きらい",   # 嫌い (dislike)
    "とくい",   # 得意 (good at)
    "にがて",   # not い-ending but listed for reference
}


# ── Vocab integrity ─────────────────────────────────────────────────────

def test_vocab_word_ids_match_field(vocab):
    """vocab.words[wid].id must equal wid."""
    bad = [(wid, w.get("id")) for wid, w in vocab["words"].items() if w.get("id") != wid]
    assert not bad, f"word_id key/field mismatch: {bad}"


def test_vocab_next_word_id_monotonic(vocab):
    """next_word_id must be > max existing wid."""
    next_id = vocab["next_word_id"]
    max_existing = max(int(w[1:]) for w in vocab["words"].keys())
    next_n = int(next_id[1:])
    assert next_n > max_existing, (
        f"next_word_id={next_id} (n={next_n}) but max existing word_id is W{max_existing:05d}"
    )


def test_vocab_word_id_format(vocab):
    """All word_ids must match W##### format."""
    pat = re.compile(r"^W\d{5}$")
    bad = [wid for wid in vocab["words"] if not pat.match(wid)]
    assert not bad, f"Malformed word_ids: {bad}"


def test_vocab_required_fields(vocab):
    """Every word must have surface, kana, pos, meanings, occurrences, first_story."""
    required = {"id", "surface", "kana", "pos", "meanings", "occurrences", "first_story"}
    bad = []
    for wid, w in vocab["words"].items():
        missing = required - set(w.keys())
        if missing:
            bad.append(f"{wid}: missing {sorted(missing)}")
    assert not bad, "\n  ".join(bad)


def test_vocab_pos_in_known_set(vocab):
    bad = [(wid, w["pos"]) for wid, w in vocab["words"].items()
           if w.get("pos") not in VALID_POS]
    assert not bad, f"Unknown POS values: {bad}\n  Valid: {sorted(VALID_POS)}"


def test_vocab_adjective_pos_canonical(vocab):
    """Adjectives must use the canonical i_adjective / na_adjective POS labels.

    The bare "adjective" tag was removed from VALID_POS on 2026-04-23 because
    it silently bypassed the validator's inflection check (Check 5) — without
    an explicit i/na class, validate.py could not pick the right conjugation
    table, so 寒くて vs 寒じゃなくて kinds of mistakes shipped unchecked.

    This test is the explicit drift guardrail. It catches:
      * Any new vocab entry that re-introduces pos="adjective".
      * Any hyphenated variant (i-adjective / na-adjective) that bypasses the
        VALID_POS set check (which only flags "not in set", not "looks like a
        forbidden legacy form").
    """
    bad: list[str] = []
    for wid, w in vocab["words"].items():
        pos = w.get("pos", "")
        if pos == "adjective":
            bad.append(
                f"{wid} ({w.get('surface')}): pos='adjective' is a forbidden "
                f"legacy tag — use 'i_adjective' or 'na_adjective' instead "
                f"(the canonical class enables Check 5 inflection validation)."
            )
        elif pos in ("i-adjective", "na-adjective"):
            bad.append(
                f"{wid} ({w.get('surface')}): pos={pos!r} uses the hyphenated "
                f"legacy form — use {pos.replace('-', '_')!r} instead."
            )
    assert not bad, "Non-canonical adjective POS labels:\n  " + "\n  ".join(bad)


def test_vocab_i_adjective_kana_consistency(vocab):
    """i-adjectives must end in い in kana; na-adjectives must not (with whitelist).

    A semantic guardrail against the actual mistake we just cleaned up:
    several i-adjectives had been tagged as plain "adjective" (or worse, as
    na_adjective), which broke conjugation handling. The shape of the kana
    form is a reliable test:

      * i-adjective dictionary form ALWAYS ends in い (e.g. 寒い → さむい).
      * na-adjective dictionary form usually does NOT end in い
        (e.g. 静か → しずか). The known い-ending na-adjectives are listed
        in NA_ADJECTIVES_ENDING_IN_I above.

    This is the kind of test that fails *loudly* when someone scaffolds a
    new word and JMdict mislabels it, or when a manual edit gets the class
    wrong. False-positives can be added to the whitelist deliberately.
    """
    bad: list[str] = []
    for wid, w in vocab["words"].items():
        pos = w.get("pos", "")
        kana = (w.get("kana") or "").strip()
        if not kana:
            continue
        ends_i = kana.endswith("い")

        if pos == "i_adjective" and not ends_i:
            bad.append(
                f"{wid} ({w.get('surface')}, kana={kana!r}): tagged "
                f"i_adjective but kana does not end in 'い'. Either the "
                f"tag is wrong or this is a rare exception; in the latter "
                f"case add a comment in vocab_state.json explaining why."
            )
        elif pos == "na_adjective" and ends_i and kana not in NA_ADJECTIVES_ENDING_IN_I:
            bad.append(
                f"{wid} ({w.get('surface')}, kana={kana!r}): tagged "
                f"na_adjective but kana ends in 'い' and is not in the "
                f"NA_ADJECTIVES_ENDING_IN_I whitelist. This is almost "
                f"certainly an i-adjective; if not, whitelist it explicitly."
            )
    assert not bad, "i/na adjective POS does not match kana shape:\n  " + "\n  ".join(bad)


def test_vocab_verb_class_in_known_set(vocab):
    bad = [(wid, w.get("verb_class")) for wid, w in vocab["words"].items()
           if w.get("pos") == "verb" and w.get("verb_class") not in VALID_VERB_CLASS]
    assert not bad, f"Unknown verb_class values: {bad}\n  Valid: {sorted(VALID_VERB_CLASS)}"


def test_vocab_no_homograph_collisions(vocab):
    """Two words with same surface AND same kana would be a duplicate."""
    seen: dict[tuple[str, str], list[str]] = {}
    for wid, w in vocab["words"].items():
        key = (w.get("surface", ""), w.get("kana", ""))
        seen.setdefault(key, []).append(wid)
    dupes = {k: v for k, v in seen.items() if len(v) > 1}
    assert not dupes, f"Duplicate (surface, kana) pairs: {dupes}"


def test_vocab_meanings_non_empty(vocab):
    bad = [wid for wid, w in vocab["words"].items() if not w.get("meanings")]
    assert not bad, f"Words with empty meanings: {bad}"


def test_vocab_meanings_no_jmdict_semicolons(vocab):
    """Catches the JMdict bleed-through pattern (e.g. 'to come; to approach; to arrive').

    Each meaning string should be a single concept; multiple meanings go in
    separate array entries.
    """
    bad = []
    for wid, w in vocab["words"].items():
        for m in w.get("meanings", []):
            if ";" in m:
                bad.append(f"{wid} ({w.get('surface','?')}): {m!r}")
    assert not bad, "JMdict semicolons in meanings:\n  " + "\n  ".join(bad)


def test_vocab_reading_is_romaji(vocab):
    """`reading` is the romaji helper for English-speaking learners.
    Must be ASCII (lowercase letters only). Catches the bug where
    `reading` was accidentally set to hiragana.
    """
    import re
    bad = []
    for wid, w in vocab["words"].items():
        reading = w.get("reading", "")
        # Must be lowercase ASCII (allow apostrophe for ん' separator and hyphen)
        if not re.match(r"^[a-z\-']+$", reading):
            bad.append(f"{wid} ({w.get('surface','?')}): reading={reading!r} (not ASCII romaji)")
    assert not bad, "reading must be lowercase romaji ASCII:\n  " + "\n  ".join(bad)


def test_vocab_reading_matches_kana(vocab):
    """`reading` (romaji) should be derivable from `kana` via standard romanisation.

    Catches divergence (e.g. someone updates kana but not reading).
    """
    try:
        import jaconv
    except ImportError:
        import pytest
        pytest.skip("jaconv not installed")
    bad = []
    for wid, w in vocab["words"].items():
        kana = w.get("kana", "")
        reading = w.get("reading", "")
        derived = jaconv.kana2alphabet(jaconv.kata2hira(kana))
        if reading != derived:
            bad.append(f"{wid} ({w.get('surface','?')}): kana={kana!r}, reading={reading!r}, derived={derived!r}")
    assert not bad, "reading does not match derived romaji from kana:\n  " + "\n  ".join(bad)


def test_vocab_no_dead_grammar_tags_field(vocab):
    """The grammar_tags field was removed (always empty, never populated).
    Catches re-introduction of forever-empty schema fields.
    """
    bad = [wid for wid, w in vocab["words"].items() if "grammar_tags" in w]
    assert not bad, f"grammar_tags field reintroduced on: {bad}"


def test_vocab_occurrences_non_negative(vocab):
    bad = [(wid, w["occurrences"]) for wid, w in vocab["words"].items()
           if w.get("occurrences", 0) < 0]
    assert not bad, f"Negative occurrences: {bad}"


# ── Grammar integrity ──────────────────────────────────────────────────

def test_grammar_ids_match_field(grammar):
    bad = [(gid, p.get("id")) for gid, p in grammar["points"].items() if p.get("id") != gid]
    assert not bad, f"grammar_id key/field mismatch: {bad}"


def test_grammar_required_fields(grammar):
    required = {"id", "title", "short", "long", "jlpt", "prerequisites"}
    bad = []
    for gid, p in grammar["points"].items():
        missing = required - set(p.keys())
        if missing:
            bad.append(f"{gid}: missing {sorted(missing)}")
    assert not bad, "\n  ".join(bad)


def test_grammar_jlpt_in_known_set(grammar):
    bad = [(gid, p.get("jlpt")) for gid, p in grammar["points"].items()
           if p.get("jlpt") not in VALID_JLPT]
    assert not bad, f"Invalid JLPT values: {bad}"


def test_grammar_no_placeholder_titles(grammar):
    """Catches the G009_mo_also bug from earlier — title should never equal id."""
    bad = [(gid, p.get("title")) for gid, p in grammar["points"].items()
           if p.get("title") == gid]
    assert not bad, f"Placeholder titles (title == id): {bad}"


def test_grammar_no_placeholder_descriptions(grammar):
    """Catches scaffold sentinels like '(added by state updater — fill in description)'."""
    sentinels = ["(added by state updater", "fill in description", "TODO", "FIXME", "TBD"]
    bad = []
    for gid, p in grammar["points"].items():
        for field in ("short", "long", "title"):
            v = p.get(field, "")
            for sent in sentinels:
                if sent in v:
                    bad.append(f"{gid}.{field} contains placeholder '{sent}'")
    assert not bad, "\n  ".join(bad)


def test_grammar_prerequisites_resolve(grammar):
    """Every prerequisite ID must reference an existing grammar point."""
    all_ids = set(grammar["points"].keys())
    bad = []
    for gid, p in grammar["points"].items():
        for prereq in p.get("prerequisites", []):
            if prereq not in all_ids:
                bad.append(f"{gid} requires {prereq} which doesn't exist")
    assert not bad, "\n  ".join(bad)


def test_grammar_no_self_prerequisite(grammar):
    bad = [gid for gid, p in grammar["points"].items() if gid in p.get("prerequisites", [])]
    assert not bad, f"Self-prerequisites: {bad}"


def test_grammar_prerequisites_acyclic(grammar):
    """No cycles in prereq graph."""
    points = grammar["points"]

    def has_cycle(start: str, visited: set[str], path: set[str]) -> bool:
        if start in path:
            return True
        if start in visited:
            return False
        path.add(start)
        for prereq in points.get(start, {}).get("prerequisites", []):
            if has_cycle(prereq, visited, path):
                return True
        path.remove(start)
        visited.add(start)
        return False

    for gid in points:
        if has_cycle(gid, set(), set()):
            pytest.fail(f"Prerequisite cycle involving {gid}")


def test_grammar_catalog_id_resolves(grammar, catalog):
    """Every catalog_id field must reference an entry that exists in the catalog."""
    catalog_ids = {e["id"] for e in catalog.get("entries", [])}
    bad = []
    for gid, p in grammar["points"].items():
        cid = p.get("catalog_id")
        if cid and cid not in catalog_ids:
            bad.append(f"{gid}.catalog_id={cid} not in catalog")
    assert not bad, "\n  ".join(bad)


# ── Cross-state ↔ stories integrity ─────────────────────────────────────

def test_every_story_word_id_exists_in_vocab(stories, vocab):
    known = set(vocab["words"].keys())
    bad = []
    for story in stories:
        for sec, sent_idx, tok_idx, tok in iter_tokens(story):
            wid = tok.get("word_id")
            if wid and wid not in known:
                bad.append(f"{story['_id']} {sec}[{sent_idx},{tok_idx}]: {wid}")
            inf = tok.get("inflection") or {}
            base_wid = inf.get("word_id")
            if base_wid and base_wid not in known:
                bad.append(f"{story['_id']} {sec}[{sent_idx},{tok_idx}]: inflection.word_id={base_wid}")
    assert not bad, "Unknown word_ids in stories:\n  " + "\n  ".join(bad)


def test_every_story_grammar_id_exists_in_grammar_state(stories, grammar):
    known = set(grammar["points"].keys())
    bad = []
    for story in stories:
        for sec, sent_idx, tok_idx, tok in iter_tokens(story):
            for gid in (tok.get("grammar_id"), (tok.get("inflection") or {}).get("grammar_id")):
                if gid and gid not in known:
                    bad.append(f"{story['_id']} {sec}[{sent_idx},{tok_idx}]: {gid}")
    assert not bad, "Unknown grammar_ids in stories:\n  " + "\n  ".join(bad)


def test_lifetime_occurrences_match_state_updater_semantics(stories, vocab):
    """vocab.words[wid].occurrences should equal the number of STORIES that use the word.

    This matches state_updater.py's semantics (one increment per story, regardless
    of how many tokens reference the word, and only counting `sentences`, not
    title). Catches state drift after post-ship edits.
    """
    expected: Counter[str] = Counter()
    for story in stories:
        wids_in_this_story: set[str] = set()
        for sent in story.get("sentences", []):
            for tok in sent.get("tokens", []):
                wid = tok.get("word_id")
                if wid:
                    wids_in_this_story.add(wid)
        for wid in wids_in_this_story:
            expected[wid] += 1

    bad = []
    for wid, w in vocab["words"].items():
        declared = w.get("occurrences", 0)
        observed = expected.get(wid, 0)
        if declared != observed:
            bad.append(f"{wid} ({w.get('surface','?')}): declared={declared}, expected={observed}")
    assert not bad, "Lifetime occurrence drift (state_updater semantics):\n  " + "\n  ".join(bad)


def test_first_story_is_actually_first(stories, vocab):
    """vocab.first_story should be the earliest story_N.json that uses the word."""
    first_seen: dict[str, str] = {}
    for story in sorted(stories, key=lambda s: int(s["_id"].split("_")[1])):
        for sec, sent_idx, tok_idx, tok in iter_tokens(story):
            wid = tok.get("word_id")
            if wid and wid not in first_seen:
                first_seen[wid] = story["_id"]

    bad = []
    for wid, w in vocab["words"].items():
        declared = w.get("first_story")
        observed = first_seen.get(wid)
        if observed and declared != observed:
            bad.append(f"{wid} ({w.get('surface','?')}): declared first_story={declared}, actually first appears in {observed}")
    assert not bad, "first_story drift:\n  " + "\n  ".join(bad)


def test_no_orphan_vocab_words(stories, vocab):
    """Every word in vocab_state should be used in at least one story."""
    used: set[str] = set()
    for story in stories:
        for sec, sent_idx, tok_idx, tok in iter_tokens(story):
            for wid in (tok.get("word_id"), (tok.get("inflection") or {}).get("word_id")):
                if wid:
                    used.add(wid)
    orphans = [(wid, w.get("surface", "?")) for wid, w in vocab["words"].items() if wid not in used]
    assert not orphans, f"Vocab words never used in any story: {orphans}"


def test_no_orphan_grammar_points(stories, grammar):
    """Every grammar point should be used in at least one story.

    Some grammar points encode context-sensitive constructions the converter
    cannot disambiguate from surface alone (e.g. が as `but` vs `subject`,
    から as `because` vs `from`, ほしい requires preceding が). They live in
    the catalog as catalog entries but are not tagged on tokens by the
    deterministic converter. They're explicitly listed here as deferred:
    the catalog references stay valid (so docs/UI can describe them); the
    test just doesn't fail when they're not yet wired up.
    """
    DEFERRED_CONTEXT_GIDS = {
        "G030_kara_reason",       # から as causal vs から as origin
        "G041_masenka_invitation",# ませんか as invitation vs question
        "G049_ga_but",            # が as `but` clause-conjunction vs subject
        "G055_plain_nonpast_pair",# plain dict-form deliberate pair w/ polite
        "G057_ga_hoshii",         # NPがほしい construction
        "G058_temo_ii",           # ~てもいい permission
    }
    used: set[str] = set()
    for story in stories:
        for sec, sent_idx, tok_idx, tok in iter_tokens(story):
            for gid in (tok.get("grammar_id"), (tok.get("inflection") or {}).get("grammar_id")):
                if gid:
                    used.add(gid)
    orphans = [
        gid for gid in grammar["points"]
        if gid not in used and gid not in DEFERRED_CONTEXT_GIDS
    ]
    assert not orphans, (
        f"Grammar points never used in any story: {orphans}\n"
        f"(if a gid is genuinely context-sensitive and intentionally untagged, "
        f"add it to DEFERRED_CONTEXT_GIDS with a comment.)"
    )
