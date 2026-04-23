#!/usr/bin/env python3
"""
Unit tests for pipeline/validate.py

Run with:  python3 -m pytest pipeline/tests/test_validate_unit.py -v
           (or:  python3 pipeline/tests/test_validate_unit.py     — direct mode)

This file was relocated from pipeline/test_validate.py in v0.20 (2026-04-22)
when all per-check validation was consolidated into the pytest suite. The
hand-rolled run_tests() harness is preserved verbatim and wrapped by a single
pytest entrypoint (test_validate_unit_suite) for collection.
"""
import copy
import sys
import json
from pathlib import Path

# Make sure we can import the validator (parent dir is pipeline/)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from validate import validate, conjugate

# ── Fixtures ──────────────────────────────────────────────────────────────────

VOCAB = {
    "version": 1,
    "words": {
        "W00001": {"id": "W00001", "surface": "今朝", "kana": "けさ",   "reading": "kesa",
                   "pos": "noun",      "meanings": ["this morning"], "occurrences": 1},
        "W00002": {"id": "W00002", "surface": "雨",   "kana": "あめ",   "reading": "ame",
                   "pos": "noun",      "meanings": ["rain"],         "occurrences": 1},
        "W00003": {"id": "W00003", "surface": "私",   "kana": "わたし", "reading": "watashi",
                   "pos": "pronoun",   "meanings": ["I"],            "occurrences": 1},
        "W00004": {"id": "W00004", "surface": "窓",   "kana": "まど",   "reading": "mado",
                   "pos": "noun",      "meanings": ["window"],       "occurrences": 1},
        "W00005": {"id": "W00005", "surface": "外",   "kana": "そと",   "reading": "soto",
                   "pos": "noun",      "meanings": ["outside"],      "occurrences": 1},
        "W00006": {"id": "W00006", "surface": "見ます","kana": "みます", "reading": "mimasu",
                   "pos": "verb",      "verb_class": "ichidan",
                   "meanings": ["to see"], "occurrences": 1},
        "W00008": {"id": "W00008", "surface": "濡れる","kana": "ぬれる", "reading": "nureru",
                   "pos": "verb",      "verb_class": "ichidan",
                   "meanings": ["to get wet"], "occurrences": 1},
    }
}

GRAMMAR = {
    "version": 1,
    "points": {
        "G001_wa_topic":    {"id": "G001_wa_topic",    "title": "は", "short": "topic", "long": "...", "first_story": 1, "prerequisites": []},
        "G002_ga_subject":  {"id": "G002_ga_subject",  "title": "が", "short": "subj",  "long": "...", "first_story": 1, "prerequisites": []},
        "G005_wo_object":   {"id": "G005_wo_object",   "title": "を", "short": "obj",   "long": "...", "first_story": 1, "prerequisites": []},
        "G006_kara_from":   {"id": "G006_kara_from",   "title": "から","short": "from",  "long": "...", "first_story": 1, "prerequisites": []},
        "G007_te_form":     {"id": "G007_te_form",     "title": "て", "short": "te",    "long": "...", "first_story": 1, "prerequisites": []},
        "G008_te_iru":      {"id": "G008_te_iru",      "title": "ている","short": "prog","long": "...", "first_story": 1, "prerequisites": []},
    }
}

# A minimal valid story (2 sentences — below SENTENCE_MIN, but useful as base)
# We'll use 5 sentences in the "valid" fixture (small enough to keep tests
# readable). story_id is 0, which signals to validate.py's Check 7 that the
# story is a test fixture and the progression curve does not apply.
def make_valid_story():
    return {
        "story_id": 0,
        "title": {
            "jp": "雨",
            "en": "Rain",
            "tokens": [
                {"t": "雨", "r": "あめ", "word_id": "W00002", "role": "content"}
            ],
        },
        "plan_ref": None,
        "new_words": ["W00001", "W00002", "W00003", "W00004", "W00005"],
        "new_grammar": ["G006_kara_from"],
        "all_words_used": ["W00002", "W00001", "W00003", "W00004", "W00005", "W00006"],
        # NB: 見ます is the masu form of 見る; we accept the dict surface in fixture for brevity
        "sentences": [
            {
                "idx": 0,
                "tokens": [
                    {"t": "今朝", "r": "けさ", "word_id": "W00001", "role": "content", "is_new": True},
                    {"t": "は", "grammar_id": "G001_wa_topic", "role": "particle"},
                    {"t": "雨", "r": "あめ", "word_id": "W00002", "role": "content", "is_new": True},
                    {"t": "です", "grammar_id": "G001_wa_topic", "role": "aux"},
                    {"t": "。", "role": "punct"},
                ],
                "gloss_en": "This morning, it is raining.",
                "audio": None,
            },
            {
                "idx": 1,
                "tokens": [
                    {"t": "私", "r": "わたし", "word_id": "W00003", "role": "content", "is_new": True},
                    {"t": "は", "grammar_id": "G001_wa_topic", "role": "particle"},
                    {"t": "窓", "r": "まど", "word_id": "W00004", "role": "content", "is_new": True},
                    {"t": "から", "grammar_id": "G006_kara_from", "role": "particle", "is_new_grammar": True},
                    {"t": "外", "r": "そと", "word_id": "W00005", "role": "content", "is_new": True},
                    {"t": "を", "grammar_id": "G005_wo_object", "role": "particle"},
                    {"t": "見ます", "r": "みます", "word_id": "W00006", "role": "content"},
                    {"t": "。", "role": "punct"},
                ],
                "gloss_en": "I look outside through the window.",
                "audio": None,
            },
            {
                "idx": 2,
                "tokens": [
                    {"t": "雨", "r": "あめ", "word_id": "W00002", "role": "content"},
                    {"t": "は", "grammar_id": "G001_wa_topic", "role": "particle"},
                    {"t": "窓", "r": "まど", "word_id": "W00004", "role": "content"},
                    {"t": "から", "grammar_id": "G006_kara_from", "role": "particle"},
                    {"t": "見ます", "r": "みます", "word_id": "W00006", "role": "content"},
                    {"t": "。", "role": "punct"},
                ],
                "gloss_en": "I watch the rain from the window.",
                "audio": None,
            },
            {
                "idx": 3,
                "tokens": [
                    {"t": "私", "r": "わたし", "word_id": "W00003", "role": "content"},
                    {"t": "は", "grammar_id": "G001_wa_topic", "role": "particle"},
                    {"t": "外", "r": "そと", "word_id": "W00005", "role": "content"},
                    {"t": "を", "grammar_id": "G005_wo_object", "role": "particle"},
                    {"t": "見ます", "r": "みます", "word_id": "W00006", "role": "content"},
                    {"t": "。", "role": "punct"},
                ],
                "gloss_en": "I look outside again.",
                "audio": None,
            },
            {
                "idx": 4,
                "tokens": [
                    {"t": "今朝", "r": "けさ", "word_id": "W00001", "role": "content"},
                    {"t": "は", "grammar_id": "G001_wa_topic", "role": "particle"},
                    {"t": "雨", "r": "あめ", "word_id": "W00002", "role": "content"},
                    {"t": "です", "grammar_id": "G001_wa_topic", "role": "aux"},
                    {"t": "。", "role": "punct"},
                ],
                "gloss_en": "This morning is rainy too.",
                "audio": None,
            },
        ],
        "word_audio": {},
        "checksum": None,
    }



def make_valid_plan(story=None):
    s = story or make_valid_story()
    return {
        "new_words": list(s["new_words"]),
        "new_grammar": list(s["new_grammar"]),
        "target_word_count": 20,
        "max_sentences": 8,
    }


def refresh_used_word_ids(story):
    used = []
    for section in [story.get("title", {})]:
        for tok in section.get("tokens", []):
            wid = tok.get("word_id")
            if wid and wid not in used:
                used.append(wid)
    for sent in story.get("sentences", []):
        for tok in sent.get("tokens", []):
            wid = tok.get("word_id")
            if wid and wid not in used:
                used.append(wid)
    story["all_words_used"] = used
    return story


def remove_title_tokens(story):
    story["title"].pop("tokens", None)
    return story


def mark_first_occurrences(story):
    seen_words = set()
    seen_grammar = set()
    for sent in story.get("sentences", []):
        for tok in sent.get("tokens", []):
            wid = tok.get("word_id")
            if wid and wid in story.get("new_words", []) and wid not in seen_words:
                tok["is_new"] = True
                seen_words.add(wid)
            gid = tok.get("grammar_id")
            if gid and gid in story.get("new_grammar", []) and gid not in seen_grammar:
                tok["is_new_grammar"] = True
                seen_grammar.add(gid)
    return story


def make_story_without_title_tokens():
    return remove_title_tokens(make_valid_story())


def make_valid_story_for_legacy_checks():
    return make_valid_story()




















































































































n = None
n































































































































n = None































































    

# ── Test helpers ──────────────────────────────────────────────────────────────

PASS = "\033[32m✓\033[0m"
FAIL = "\033[31m✗\033[0m"

results = []

def check(name, condition, detail=""):
    ok = bool(condition)
    results.append((name, ok, detail))
    symbol = PASS if ok else FAIL
    print(f"  {symbol} {name}" + (f": {detail}" if detail and not ok else ""))
    return ok

def errors_for_check(result, n):
    return [e for e in result.errors if e.check == n]

def run_tests():
    print("\n── Conjugation engine ────────────────────────────────────────────")
    check("ichidan te-form: 見る→見て",       conjugate("見る",   "te_form",  "ichidan")  == "見て")
    check("ichidan te-form: ぬれる→ぬれて",   conjugate("ぬれる", "te_form",  "ichidan")  == "ぬれて")
    check("ichidan masu: 見る→見ます",         conjugate("見る",   "masu",     "ichidan")  == "見ます")
    check("ichidan nai: 見る→見ない",          conjugate("見る",   "nai",      "ichidan")  == "見ない")
    check("godan te: 書く→書いて",             conjugate("書く",   "te",       "godan")    == "書いて")
    check("godan te: 飲む→飲んで",             conjugate("飲む",   "te",       "godan")    == "飲んで")
    check("godan te: 話す→話して",             conjugate("話す",   "te",       "godan")    == "話して")
    check("godan te: 行く (irregular)→行って", conjugate("行く",   "te",       "godan")    == "行って")
    check("irregular する te→して",            conjugate("する",   "te",       None)       == "して")
    check("irregular くる te→きて",            conjugate("くる",   "te",       None)       == "きて")
    check("i-adj te: 寒い→寒くて",            conjugate("寒い",   "te_form",  "i_adjective") == "寒くて")
    check("i-adj past: 寒い→寒かった",        conjugate("寒い",   "past",     "i_adjective") == "寒かった")
    check("unknown form returns None",          conjugate("食べる", "imperative","ichidan") is None)

    print("\n── Check 1: Schema validity ──────────────────────────────────────")
    # Missing required field
    s = make_valid_story()
    del s["sentences"]
    r = validate(s, VOCAB, GRAMMAR)
    check("Missing 'sentences' → invalid", not r.valid)
    check("Error on check 1", errors_for_check(r, 1))

    # Wrong type
    s = make_valid_story()
    s["story_id"] = "not-an-int"
    r = validate(s, VOCAB, GRAMMAR)
    check("Wrong type story_id → check 1 error", errors_for_check(r, 1))

    # Token missing role
    s = make_valid_story()
    del s["sentences"][0]["tokens"][0]["role"]
    r = validate(s, VOCAB, GRAMMAR)
    check("Token missing 'role' → check 1 error", errors_for_check(r, 1))

    print("\n── Check 2: Closed vocabulary ────────────────────────────────────")
    s = make_valid_story()
    s["sentences"][0]["tokens"][0]["word_id"] = "W99999"
    r = validate(s, VOCAB, GRAMMAR)
    check("Unknown word_id → check 2 error", errors_for_check(r, 2))

    # Allowed via plan
    s = make_valid_story()
    s["sentences"][0]["tokens"][0]["word_id"] = "W99999"
    s["new_words"].append("W99999")
    s["all_words_used"].append("W99999")
    plan = {"new_words": ["W99999"] + s["new_words"][:-1],
            "new_grammar": s["new_grammar"], "target_word_count": 20, "max_sentences": 8}
    # Can't test fully without the word in vocab, but plan check should allow it
    r = validate(s, VOCAB, GRAMMAR, plan)
    check("Word allowed via plan.new_words → no check 2 error",
          not errors_for_check(r, 2))

    print("\n── Check 3: Closed grammar ───────────────────────────────────────")
    s = make_valid_story()
    s["sentences"][0]["tokens"][1]["grammar_id"] = "G999_unknown"
    r = validate(s, VOCAB, GRAMMAR)
    check("Unknown grammar_id → check 3 error", errors_for_check(r, 3))

    print("\n── Check 1b: Title tokenisation and metadata ─────────────")
    s = make_valid_story()
    s["title"]["tokens"] = [{"t": "雨", "r": "あめ", "role": "content", "word_id": "W00002"}]
    r = validate(s, VOCAB, GRAMMAR)
    check("Title tokens supported → still valid", r.valid, str(r.errors) if r.errors else "")

    s = make_valid_story()
    # Title with text/token mismatch (tokens claim 朝 but jp text says 雨) → check 1 error
    s["title"] = {"jp": "雨", "en": "Rain",
                  "tokens": [{"t": "朝", "r": "あさ", "role": "content", "word_id": "W00001"}]}
    r = validate(s, VOCAB, GRAMMAR)
    check("Mismatched title tokens → check 1 error", errors_for_check(r, 1))

    s = make_valid_story()
    s["title"]["tokens"] = [{"t": "の", "role": "particle"}]
    r = validate(s, VOCAB, GRAMMAR)
    check("Particle without grammar_id → check 1 error", errors_for_check(r, 1))

    print("\n── Check 4: Budget ───────────────────────────────────────────────")
    # Extra new word not in plan
    s = make_valid_story()
    plan = {"new_words": ["W00001"], "new_grammar": [], "target_word_count": 20, "max_sentences": 8}
    r = validate(s, VOCAB, GRAMMAR, plan)
    check("Extra new_words vs plan → check 4 error", errors_for_check(r, 4))

    # New word declared but never used
    s = make_valid_story()
    s["new_words"].append("W00008")
    r = validate(s, VOCAB, GRAMMAR)
    check("Declared new_word never used → check 4 error", errors_for_check(r, 4))

    # all_words_used mismatch
    s = make_valid_story()
    s["all_words_used"].append("W00008")
    r = validate(s, VOCAB, GRAMMAR)
    check("all_words_used has undeclared word → check 4 error", errors_for_check(r, 4))

    s = make_valid_story()
    s["new_words"] = ["W00001"]
    for sent in s["sentences"]:
        for tok in sent["tokens"]:
            tok.pop("is_new", None)
    r = validate(s, VOCAB, GRAMMAR)
    check("First new word must be flagged is_new", errors_for_check(r, 4))

    s = make_valid_story()
    s["new_words"] = ["W00001"]
    s["sentences"][1]["tokens"][0]["word_id"] = "W00004"
    s["sentences"][1]["tokens"][0]["t"] = "窓"
    s["sentences"][1]["tokens"][0]["r"] = "まど"
    s["all_words_used"] = ["W00001", "W00002", "W00004", "W00005", "W00006"]
    r = validate(s, VOCAB, GRAMMAR)
    check("New word appearing once → check 4 error", errors_for_check(r, 4))

    # v0.19: same-story new_grammar reuse minimum lowered from 2 → 1.
    # The library-wide reinforcement test (Check 3.8) now provides the
    # spaced-repetition guarantee. So a single in-story occurrence of a
    # new grammar point is now legal at the per-story level — Check 4 must
    # NOT flag it.
    s = make_valid_story()
    s["new_grammar"] = ["G006_kara_from"]
    s["sentences"] = s["sentences"][:5]
    for sent in s["sentences"]:
        sent["tokens"] = [tok for tok in sent["tokens"] if tok.get("grammar_id") != "G006_kara_from"]
    s["sentences"][0]["tokens"].insert(2, {"t": "から", "grammar_id": "G006_kara_from", "role": "particle", "is_new_grammar": True})
    r = validate(s, VOCAB, GRAMMAR)
    check("New grammar with single use → no check 4 error (v0.19 rule)", not errors_for_check(r, 4))

    print("\n── Check 5: Surface ↔ ID consistency ─────────────────────────────")
    # Correct inflection (ぬれて = te-form of ぬれる, ichidan)
    s = make_valid_story()
    s["sentences"][0]["tokens"] = [
        {"t": "濡れて", "r": "ぬれて", "word_id": "W00008", "role": "content",
         "inflection": {"base": "ぬれる", "base_r": "ぬれる", "form": "te_form", "grammar_id": "G007_te_form"}},
        {"t": "います",  "grammar_id": "G008_te_iru", "role": "aux"},
        {"t": "。",      "role": "punct"},
    ]
    s["all_words_used"] = ["W00001","W00002","W00003","W00004","W00005","W00008"]
    r = validate(s, VOCAB, GRAMMAR)
    check("Correct inflection → no check 5 error", not errors_for_check(r, 5))

    # Wrong inflection surface
    s = make_valid_story()
    s["sentences"][0]["tokens"] = [
        {"t": "ぬれた", "r": "ぬれた", "word_id": "W00008", "role": "content",
         "inflection": {"base": "ぬれる", "base_r": "ぬれる", "form": "te_form", "grammar_id": "G007_te_form"}},
        {"t": "。",     "role": "punct"},
    ]
    s["all_words_used"] = ["W00001","W00002","W00003","W00004","W00005","W00008"]
    r = validate(s, VOCAB, GRAMMAR)
    check("Wrong inflection surface → check 5 error", errors_for_check(r, 5))

    # Surface mismatch (no inflection block, wrong surface)
    s = make_valid_story()
    s["sentences"][0]["tokens"][0]["t"] = "あした"  # wrong surface for W00001 (今朝/けさ)
    s["sentences"][0]["tokens"][0].pop("r", None)
    r = validate(s, VOCAB, GRAMMAR)
    check("Surface mismatch (no inflection) → check 5 error", errors_for_check(r, 5))

    print("\n── Check 6: Reinforcement floor ─────────────────────────────────")
    # The 2026-04-22 reform replaced the "≥ 60% of content tokens must be
    # low-occ" percentage with an absolute floor of 6 low-occ tokens per
    # story. Test fixture (story_id=0) skips the ship-time discount and
    # reports against lifetime occurrences directly.

    # All words have lifetime occ >= 10 → zero low-occ tokens → fails floor.
    rich_vocab = copy.deepcopy(VOCAB)
    for w in rich_vocab["words"].values():
        w["occurrences"] = 10
    s = make_valid_story()
    r = validate(s, rich_vocab, GRAMMAR)
    check("All words occurrences>=10 → check 6 error (no reinforcement at all)",
          errors_for_check(r, 6))

    # Fresh vocab (occurrences=1) → all low-occ → passes floor.
    s = make_valid_story()
    r = validate(s, VOCAB, GRAMMAR)
    check("Fresh vocab (occurrences=1) → no check 6 error",
          not errors_for_check(r, 6))

    # Ship-time discount still applies for real story_ids: with lifetime
    # occ=5 + this-story discount=1, effective_occ=4 → low-occ → passes
    # the floor.
    rich_vocab = copy.deepcopy(VOCAB)
    for w in rich_vocab["words"].values():
        w["occurrences"] = 5
    s = make_valid_story()
    s["story_id"] = 999  # real id, no future stories on disk
    r = validate(s, rich_vocab, GRAMMAR)
    check("ship-time discount: lifetime occ=5 minus this-story's use=4 → low-occ → passes",
          not errors_for_check(r, 6))

    # The fixture-sentinel (story_id=0) does NOT discount. With lifetime
    # occ=5 and no discount, effective_occ stays at 5 (= LOW_OCCURRENCE_LIMIT,
    # which is NOT counted as low-occ since the threshold is "< 5"). So
    # nothing reinforces → floor not met → error.
    rich_vocab = copy.deepcopy(VOCAB)
    for w in rich_vocab["words"].values():
        w["occurrences"] = 5
    s = make_valid_story()  # story_id=0 by fixture
    r = validate(s, rich_vocab, GRAMMAR)
    check("ship-time discount: story_id=0 fixture sentinel skips discount → floor fails",
          errors_for_check(r, 6))

    print("\n── Check 7: Length ───────────────────────────────────────────────")
    # Too few sentences (1)
    s = make_valid_story()
    s["sentences"] = s["sentences"][:1]
    r = validate(s, VOCAB, GRAMMAR)
    check("1 sentence → check 7 error", errors_for_check(r, 7))

    # Too many sentences (9)
    s = make_valid_story()
    extra = copy.deepcopy(s["sentences"][0])
    extra["idx"] = 5
    for _ in range(4):
        s["sentences"].append(copy.deepcopy(extra))
    r = validate(s, VOCAB, GRAMMAR)
    check("9 sentences → check 7 error", errors_for_check(r, 7))

    # Plan max_sentences exceeded
    s = make_valid_story()  # 5 sentences
    plan = {"new_words": s["new_words"], "new_grammar": s["new_grammar"],
            "target_word_count": 40, "max_sentences": 3}
    r = validate(s, VOCAB, GRAMMAR, plan)
    check("Exceeds plan max_sentences → check 7 error", errors_for_check(r, 7))

    print("\n── Check 7: Length progression curve ────────────────────────────")
    # Story 1 (plateau, target 7): 7 sentences should pass; 5 should fail.
    s = make_valid_story()
    s["story_id"] = 1
    extra = copy.deepcopy(s["sentences"][0])
    extra["idx"] = 5
    for _ in range(2):
        s["sentences"].append(copy.deepcopy(extra))  # 5 → 7
    r = validate(s, VOCAB, GRAMMAR)
    check("story 1 with 7 sentences → no check 7 error",
          not errors_for_check(r, 7))

    s = make_valid_story()
    s["story_id"] = 1
    s["sentences"] = s["sentences"][:5]  # 5 sentences (below target plateau)
    r = validate(s, VOCAB, GRAMMAR)
    check("story 1 with 5 sentences → check 7 error (band 6-8)",
          errors_for_check(r, 7))

    # Story 11 (first +1 step, target 8): 7 sentences should fail (out of band 7-9... wait band is 7-9).
    # Use a clearer test: story 21 (target 10, band 9-11) with 7 sentences should fail.
    s = make_valid_story()
    s["story_id"] = 21
    r = validate(s, VOCAB, GRAMMAR)  # has 5 sentences
    check("story 21 with 5 sentences → check 7 error (band 9-11)",
          errors_for_check(r, 7))

    # Story_id 0 (test fixture sentinel) should bypass progression and use the
    # historic absolute range so existing fixtures keep working.
    s = make_valid_story()  # story_id=0 by fixture
    r = validate(s, VOCAB, GRAMMAR)
    check("story_id=0 fixture (5 sentences) → no check 7 error (absolute range used)",
          not errors_for_check(r, 7))

    print("\n── Check 3.5: Grammar tier progression ──────────────────────────")
    # Build a grammar fixture with one N5 point and one N4 point.
    GRAMMAR_TIERED = copy.deepcopy(GRAMMAR)
    GRAMMAR_TIERED["points"]["G_N5_test"] = {
        "id": "G_N5_test", "title": "test N5", "short": "x", "long": "x",
        "first_story": 1, "prerequisites": [], "jlpt": "N5",
    }
    GRAMMAR_TIERED["points"]["G_N4_test"] = {
        "id": "G_N4_test", "title": "test N4", "short": "x", "long": "x",
        "first_story": 11, "prerequisites": [], "jlpt": "N4",
    }
    GRAMMAR_TIERED["points"]["G_N3_test"] = {
        "id": "G_N3_test", "title": "test N3", "short": "x", "long": "x",
        "first_story": 26, "prerequisites": [], "jlpt": "N3",
    }

    # Story 5 (Tier 1, N5) introducing an N5 point → legal
    s = make_valid_story()
    s["story_id"] = 5
    s["new_grammar"] = ["G_N5_test"]
    r = validate(s, VOCAB, GRAMMAR_TIERED)
    check("story 5 introducing N5 grammar → no check 3.5 error",
          not errors_for_check(r, "3.5"))

    # Story 5 (Tier 1) introducing an N4 point → BLOCKED
    s = make_valid_story()
    s["story_id"] = 5
    s["new_grammar"] = ["G_N4_test"]
    r = validate(s, VOCAB, GRAMMAR_TIERED)
    check("story 5 introducing N4 grammar → check 3.5 error (cross-tier blocked)",
          errors_for_check(r, "3.5"))

    # Story 11 (Tier 2, N4) introducing an N4 point → legal
    s = make_valid_story()
    s["story_id"] = 11
    s["new_grammar"] = ["G_N4_test"]
    r = validate(s, VOCAB, GRAMMAR_TIERED)
    check("story 11 introducing N4 grammar → no check 3.5 error",
          not errors_for_check(r, "3.5"))

    # Story 11 (Tier 2) introducing an N3 point → BLOCKED
    s = make_valid_story()
    s["story_id"] = 11
    s["new_grammar"] = ["G_N3_test"]
    r = validate(s, VOCAB, GRAMMAR_TIERED)
    check("story 11 introducing N3 grammar → check 3.5 error (cross-tier blocked)",
          errors_for_check(r, "3.5"))

    # Story 30 (Tier 3) introducing an earlier N5 point → legal (no jumping back is fine)
    s = make_valid_story()
    s["story_id"] = 30
    s["new_grammar"] = ["G_N5_test"]
    r = validate(s, VOCAB, GRAMMAR_TIERED)
    check("story 30 introducing N5 grammar → no check 3.5 error (earlier tier always OK)",
          not errors_for_check(r, "3.5"))

    # Story_id 0 (test fixture) bypasses Check 3.5 (back-compat)
    s = make_valid_story()
    s["story_id"] = 0
    s["new_grammar"] = ["G_N3_test"]
    r = validate(s, VOCAB, GRAMMAR_TIERED)
    check("story_id=0 fixture introducing N3 → no check 3.5 error (sentinel bypass)",
          not errors_for_check(r, "3.5"))

    print("\n── Check 8: Forbidden topics — REMOVED ───────────────────────────")
    # Check 8 was removed entirely on 2026-04-22 (product decision: "remove
    # all 'forbidden' words, phrases and themes checks, everything should be
    # allowed"). The validator no longer imposes any topic restrictions, so
    # we instead assert the inverse: previously-blocked content now passes.
    s = make_valid_story()
    s["sentences"][0]["gloss_en"] = "He killed the dragon. I love you. The war."
    r = validate(s, VOCAB, GRAMMAR)
    check("Previously-forbidden phrases → no check 8 error (Check 8 deleted)",
          not errors_for_check(r, 8))

    print("\n── Check 9: Gloss sanity ─────────────────────────────────────────")
    s = make_valid_story()
    s["sentences"][0]["gloss_en"] = ""
    r = validate(s, VOCAB, GRAMMAR)
    check("Empty gloss → check 9 error", errors_for_check(r, 9))

    print("\n── Check 10: Round-trip ──────────────────────────────────────────")
    # Sentence not ending in 。
    s = make_valid_story()
    s["sentences"][0]["tokens"][-1]["t"] = "X"
    r = validate(s, VOCAB, GRAMMAR)
    check("No trailing 。 → check 10 error", errors_for_check(r, 10))

    # Double space
    s = make_valid_story()
    s["sentences"][0]["tokens"][0]["t"] = "今朝  "
    r = validate(s, VOCAB, GRAMMAR)
    check("Double space → check 10 error", errors_for_check(r, 10))

    # Stray ASCII
    s = make_valid_story()
    s["sentences"][0]["tokens"][0]["t"] = "Hello"
    r = validate(s, VOCAB, GRAMMAR)
    check("Stray ASCII → check 10 error", errors_for_check(r, 10))

    print("\n── Valid story passes all checks ─────────────────────────────────")
    s = make_valid_story()
    r = validate(s, VOCAB, GRAMMAR)
    check("Valid story → no errors", r.valid, str(r.errors) if r.errors else "")

    # Summary
    total  = len(results)
    passed = sum(1 for _, ok, _ in results if ok)
    failed = total - passed
    print(f"\n{'─'*60}")
    print(f"Results: {passed}/{total} passed" + (f", {failed} FAILED" if failed else " ✓"))
    return failed == 0


def test_validate_unit_suite() -> None:
    """Pytest wrapper around run_tests().

    The 50+ hand-rolled per-check assertions live inside run_tests() (a
    legacy single-function harness from before this project used pytest).
    Rather than rewrite each as its own pytest function, we wrap the
    whole thing: pytest collects this single test, run_tests() prints
    its rich per-check output to stdout, and the wrapper fails the test
    if any inner assertion failed.
    """
    ok = run_tests()
    assert ok, "validate.py unit-test harness reported one or more failures (see stdout above)"


if __name__ == "__main__":
    ok = run_tests()
    sys.exit(0 if ok else 1)
