#!/usr/bin/env python3
"""
Monogatari — Stage 3 Validator
Deterministic validation of story_N.json against vocab_state.json,
grammar_state.json, and an optional plan.json.

Usage:
    python3 pipeline/validate.py stories/story_1.json \
        [--plan pipeline/plan.json] \
        [--vocab data/vocab_state.json] \
        [--grammar data/grammar_state.json]

Exit codes: 0 = valid, 1 = invalid, 2 = usage error.
"""

import argparse
import json
import sys
import unicodedata
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


# ── Conjugation Engine (Section 6) ───────────────────────────────────────────

# Godan te/ta form shift table (final kana → te suffix, ta suffix)
GODAN_TE: dict[str, tuple[str, str]] = {
    "く": ("いて",  "いた"),
    "ぐ": ("いで",  "いだ"),
    "す": ("して",  "した"),
    "つ": ("って",  "った"),
    "る": ("って",  "った"),
    "う": ("って",  "った"),
    "ぬ": ("んで",  "んだ"),
    "ぶ": ("んで",  "んだ"),
    "む": ("んで",  "んだ"),
}

# Godan nai form (final kana → nai stem)
GODAN_NAI_STEM: dict[str, str] = {
    "く": "か", "ぐ": "が", "す": "さ", "つ": "た", "る": "ら",
    "う": "わ", "ぬ": "な", "ぶ": "ば", "む": "ま",
}

# Godan masu stem (final kana → masu stem)
GODAN_MASU_STEM: dict[str, str] = {
    "く": "き", "ぐ": "ぎ", "す": "し", "つ": "ち", "る": "り",
    "う": "い", "ぬ": "に", "ぶ": "び", "む": "み",
}

# Irregular verbs: base → {form: surface}
IRREGULAR: dict[str, dict[str, str]] = {
    "する":  {"dictionary": "する", "masu": "します",  "te": "して",  "ta": "した",
              "nai": "しない", "negative_past": "しなかった", "potential": "できる",
              "volitional": "しよう"},
    "くる":  {"dictionary": "くる", "masu": "きます",  "te": "きて",  "ta": "きた",
              "nai": "こない", "negative_past": "こなかった", "potential": "こられる",
              "volitional": "こよう"},
    "来る":  {"dictionary": "来る", "masu": "来ます", "te": "来て",  "ta": "来た",
              "nai": "来ない", "negative_past": "来なかった", "potential": "来られる",
              "volitional": "来よう"},
    "いく":  {"te": "いって", "ta": "いった"},  # special godan irregular
    "行く":  {"te": "行って", "ta": "行った"},
}


def conjugate(base: str, form: str, verb_class: Optional[str]) -> Optional[str]:
    """Return the expected surface for a given base + form + class.
    Returns None if the combination is unknown / unsupported."""

    # Irregular check first
    if base in IRREGULAR and form in IRREGULAR[base]:
        return IRREGULAR[base][form]

    form = form.lower().replace("-", "_")

    if verb_class == "ichidan":
        if not base.endswith("る"):
            return None
        stem = base[:-1]
        table = {
            "dictionary":    base,
            "masu":          stem + "ます",
            "te":            stem + "て",
            "te_form":       stem + "て",
            "ta":            stem + "た",
            "nai":           stem + "ない",
            "negative_past": stem + "なかった",
            "potential":     stem + "られる",
            "volitional":    stem + "よう",
        }
        return table.get(form)

    if verb_class == "godan":
        if not base:
            return None
        final = base[-1]
        stem  = base[:-1]
        if form in ("te", "te_form") and final in GODAN_TE:
            te_suf, _ = GODAN_TE[final]
            return stem + te_suf
        if form == "ta" and final in GODAN_TE:
            _, ta_suf = GODAN_TE[final]
            return stem + ta_suf
        if form in ("masu", "masu_form"):
            masu_stem = GODAN_MASU_STEM.get(final)
            return (stem + masu_stem + "ます") if masu_stem else None
        if form in ("nai", "negative"):
            nai_stem = GODAN_NAI_STEM.get(final)
            return (stem + nai_stem + "ない") if nai_stem else None
        if form == "dictionary":
            return base
        return None

    if verb_class in ("i_adjective", "i-adjective", "i_adj"):
        if not base.endswith("い"):
            return None
        stem = base[:-1]
        table = {
            "dictionary":    base,
            "adverb":        stem + "く",
            "te":            stem + "くて",
            "te_form":       stem + "くて",
            "ta":            stem + "かった",
            "past":          stem + "かった",
            "nai":           stem + "くない",
            "negative_past": stem + "くなかった",
        }
        return table.get(form)

    return None


# ── Validation errors ─────────────────────────────────────────────────────────

@dataclass
class ValidationError:
    check: int
    message: str
    location: str = ""

    def __str__(self) -> str:
        loc = f" [{self.location}]" if self.location else ""
        return f"[Check {self.check}]{loc} {self.message}"


@dataclass
class ValidationResult:
    valid: bool
    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_error(self, check: int, msg: str, location: str = "") -> None:
        self.errors.append(ValidationError(check, msg, location))
        self.valid = False

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)


# ── Main Validator ────────────────────────────────────────────────────────────

REQUIRED_STORY_FIELDS = {
    "story_id": int,
    "title": dict,
    "subtitle": dict,
    "new_words": list,
    "new_grammar": list,
    "all_words_used": list,
    "sentences": list,
}

REQUIRED_TOKEN_FIELDS_CONTENT  = {"t", "role", "word_id"}
REQUIRED_TOKEN_FIELDS_PARTICLE = {"t", "role", "grammar_id"}
REQUIRED_TOKEN_FIELDS_AUX      = {"t", "role", "grammar_id"}
REQUIRED_SENTENCE_FIELDS       = {"idx", "tokens", "gloss_en"}

SENTENCE_MIN = 5
SENTENCE_MAX = 8
REUSE_QUOTA  = 0.60   # ≥ 60% of content tokens must be words with occurrences < 5
GLOSS_MIN_RATIO = 0.8
GLOSS_MAX_RATIO = 3.0


def has_kanji(text: str) -> bool:
    return any("一" <= ch <= "龯" for ch in text)


def collect_text_sections(story: dict) -> list[tuple[str, list[dict]]]:
    sections: list[tuple[str, list[dict]]] = []
    for field_name in ("title", "subtitle"):
        obj = story.get(field_name, {})
        if isinstance(obj, dict) and isinstance(obj.get("tokens"), list):
            sections.append((field_name, obj["tokens"]))
    for i, sent in enumerate(story.get("sentences", [])):
        if isinstance(sent, dict) and isinstance(sent.get("tokens"), list):
            sections.append((f"sentence {i}", sent["tokens"]))
    return sections


def token_location(section_name: str, index: int, token: dict) -> str:
    return f"{section_name} token {index} ('{token.get('t', '?')}')"


def expected_reading(word: dict, surface: str, inflection: Optional[dict]) -> Optional[str]:
    if inflection and isinstance(inflection, dict):
        base = inflection.get("base_r") or inflection.get("base") or word.get("kana", "")
        form = inflection.get("form", "")
        vclass = word.get("verb_class") or word.get("adj_class")
        if word.get("pos") == "adjective":
            vclass = word.get("adj_class", "") + "_adjective"
        return conjugate(base, form, vclass)
    return word.get("kana")


def extract_used_grammar(token: dict) -> list[str]:
    used: list[str] = []
    gid = token.get("grammar_id")
    if gid:
        used.append(gid)
    inf = token.get("inflection")
    if inf and isinstance(inf, dict) and inf.get("grammar_id"):
        used.append(inf["grammar_id"])
    return used


def first_indices(items: list[str]) -> dict[str, int]:
    seen: dict[str, int] = {}
    for idx, item in enumerate(items):
        if item not in seen:
            seen[item] = idx
    return seen


def is_dictionary_surface(word: dict, token: dict) -> bool:
    inf = token.get("inflection")
    if inf and isinstance(inf, dict):
        return inf.get("form") == "dictionary"
    surface = token.get("t", "")
    reading = token.get("r", surface)
    return surface == word.get("surface") or surface == word.get("kana") or reading == word.get("kana")


def is_dictionary_grammar_token(token: dict) -> bool:
    inf = token.get("inflection")
    if inf and isinstance(inf, dict):
        return inf.get("form") == "dictionary"
    return True


def ensure_ordered_unique(items: list[str]) -> bool:
    return len(items) == len(dict.fromkeys(items))


def prerequisites_satisfied(grammar_ids: set[str], grammar_points: dict, grammar_id: str) -> list[str]:
    point = grammar_points.get(grammar_id, {})
    prereqs = point.get("prerequisites", []) if isinstance(point, dict) else []
    return [gid for gid in prereqs if gid not in grammar_ids]


def content_word_ids(tokens: list[dict]) -> list[str]:
    return [tok["word_id"] for tok in tokens if tok.get("role") == "content" and tok.get("word_id")]


def grammar_ids_in_tokens(tokens: list[dict]) -> list[str]:
    ids: list[str] = []
    for tok in tokens:
        ids.extend(extract_used_grammar(tok))
    return ids


def repeated_ids(ids: list[str], wanted: set[str]) -> dict[str, int]:
    counts = {item: 0 for item in wanted}
    for item in ids:
        if item in counts:
            counts[item] += 1
    return counts


def token_matches_jp_text(tokens: list[dict], jp_text: str) -> bool:
    return "".join(tok.get("t", "") for tok in tokens) == jp_text


def token_has_required_metadata(token: dict) -> bool:
    role = token.get("role")
    if role == "content":
        return REQUIRED_TOKEN_FIELDS_CONTENT.issubset(token)
    if role == "particle":
        return REQUIRED_TOKEN_FIELDS_PARTICLE.issubset(token)
    if role == "aux":
        return REQUIRED_TOKEN_FIELDS_AUX.issubset(token)
    return role == "punct"


def dictionary_form_expected_for_first_occurrence(section_index: int) -> bool:
    return section_index < 3


def natural_gloss(gloss: str) -> bool:
    return bool(gloss.strip())


def occurrence_section_name(section_name: str) -> str:
    return section_name


def collect_all_tokens(story: dict) -> list[dict]:
    return [tok for _, tokens in collect_text_sections(story) for tok in tokens]


def collect_sentence_tokens(story: dict) -> list[dict]:
    return [tok for sent in story.get("sentences", []) for tok in sent.get("tokens", [])]


def sentence_sections(story: dict) -> list[tuple[str, list[dict]]]:
    return [(name, tokens) for name, tokens in collect_text_sections(story) if name.startswith("sentence ")]


def title_subtitle_sections(story: dict) -> list[tuple[str, list[dict]]]:
    return [(name, tokens) for name, tokens in collect_text_sections(story) if name in {"title", "subtitle"}]


def count_non_punct_tokens(tokens: list[dict]) -> int:
    return len([tok for tok in tokens if tok.get("role") != "punct"])


def count_content_tokens(tokens: list[dict]) -> int:
    return len([tok for tok in tokens if tok.get("role") == "content"])


def text_sections_with_index(story: dict) -> list[tuple[int, str, list[dict]]]:
    return [(idx, name, tokens) for idx, (name, tokens) in enumerate(collect_text_sections(story))]


def story_grammar_ids(story: dict) -> set[str]:
    ids: set[str] = set()
    for tok in collect_all_tokens(story):
        ids.update(extract_used_grammar(tok))
    return ids


def story_word_ids(story: dict) -> list[str]:
    ids: list[str] = []
    for tok in collect_all_tokens(story):
        wid = tok.get("word_id")
        if wid:
            ids.append(wid)
    return ids


def first_occurrence_map(story: dict) -> tuple[dict[str, tuple[int, str, dict]], dict[str, tuple[int, str, dict]]]:
    words: dict[str, tuple[int, str, dict]] = {}
    grammar: dict[str, tuple[int, str, dict]] = {}
    for section_index, section_name, tokens in text_sections_with_index(story):
        for tok in tokens:
            wid = tok.get("word_id")
            if wid and wid not in words:
                words[wid] = (section_index, section_name, tok)
            for gid in extract_used_grammar(tok):
                if gid not in grammar:
                    grammar[gid] = (section_index, section_name, tok)
    return words, grammar


def ids_in_first_seen_order(story: dict) -> list[str]:
    seen: list[str] = []
    for wid in story_word_ids(story):
        if wid not in seen:
            seen.append(wid)
    return seen


def words_repeated_twice(story: dict, wanted: set[str]) -> dict[str, int]:
    return repeated_ids(story_word_ids(story), wanted)


def grammar_repeated(story: dict, wanted: set[str]) -> dict[str, int]:
    return repeated_ids(list(story_grammar_ids_sequence(story)), wanted)


def story_grammar_ids_sequence(story: dict) -> list[str]:
    ids: list[str] = []
    for tok in collect_all_tokens(story):
        ids.extend(extract_used_grammar(tok))
    return ids


def new_ids_marked_once(story: dict, key: str, flag: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for tok in collect_all_tokens(story):
        if tok.get(flag):
            item = tok.get(key) or tok.get("inflection", {}).get(key)
            if item:
                counts[item] = counts.get(item, 0) + 1
    return counts


def validate_title_subtitle_tokens(story: dict, result: ValidationResult) -> None:
    for section_name, tokens in title_subtitle_sections(story):
        text_obj = story.get(section_name, {})
        jp_text = text_obj.get("jp", "") if isinstance(text_obj, dict) else ""
        if not tokens:
            result.add_error(1, f"'{section_name}' missing token list", section_name)
            continue
        if not token_matches_jp_text(tokens, jp_text):
            result.add_error(1, f"{section_name} tokens do not re-join to jp text '{jp_text}'", section_name)


def validate(
    story: dict,
    vocab: dict,
    grammar: dict,
    plan: Optional[dict] = None,
) -> ValidationResult:

    result = ValidationResult(valid=True)
    known_words   = set(vocab.get("words", {}).keys())
    known_grammar = set(grammar.get("points", {}).keys())

    # Words allowed in this story = existing vocab + plan new_words
    plan_new_words   = set(plan["new_words"])   if plan else set()
    plan_new_grammar = set(plan["new_grammar"]) if plan else set()
    allowed_words    = known_words | plan_new_words
    allowed_grammar  = known_grammar | plan_new_grammar

    # ── Check 1: Schema validity ──────────────────────────────────────────────
    for field_name, expected_type in REQUIRED_STORY_FIELDS.items():
        if field_name not in story:
            result.add_error(1, f"Missing required field '{field_name}'")
        elif not isinstance(story[field_name], expected_type):
            result.add_error(1, f"Field '{field_name}' has wrong type: "
                                f"expected {expected_type.__name__}, "
                                f"got {type(story[field_name]).__name__}")

    for field_name in ("jp", "en"):
        for obj_name in ("title", "subtitle"):
            obj = story.get(obj_name, {})
            if isinstance(obj, dict) and field_name not in obj:
                result.add_error(1, f"'{obj_name}' missing '{field_name}' field")

    sentences = story.get("sentences", [])
    for i, sent in enumerate(sentences):
        loc = f"sentence {i}"
        if not isinstance(sent, dict):
            result.add_error(1, f"Sentence {i} is not a dict", loc)
            continue
        for sf in REQUIRED_SENTENCE_FIELDS:
            if sf not in sent:
                result.add_error(1, f"Sentence missing field '{sf}'", loc)
        if not isinstance(sent.get("tokens"), list):
            result.add_error(1, "Tokens is not a list", loc)
            continue
        for j, tok in enumerate(sent["tokens"]):
            tloc = f"sentence {i} token {j}"
            if not isinstance(tok, dict):
                result.add_error(1, "Token is not a dict", tloc)
                continue
            if "t" not in tok:
                result.add_error(1, "Token missing 't'", tloc)
            if "role" not in tok:
                result.add_error(1, "Token missing 'role'", tloc)
            role = tok.get("role")
            if role not in ("content", "particle", "aux", "punct"):
                result.add_error(1, f"Unknown role '{role}'", tloc)
            if role == "content" and "word_id" not in tok and "grammar_id" not in tok:
                result.add_error(1, "Content token missing both 'word_id' and 'grammar_id'", tloc)

    if result.errors:
        # Stop early — further checks assume schema is valid
        return result

    validate_title_subtitle_tokens(story, result)
    if result.errors:
        return result

    # Collect all tokens across titles/subtitles/sentences, but keep length checks sentence-only.
    all_tokens = collect_all_tokens(story)
    sentence_tokens = collect_sentence_tokens(story)
    content_tokens = [tok for tok in sentence_tokens if tok.get("role") == "content"]
    first_word_occurrence, first_grammar_occurrence = first_occurrence_map(story)
    grammar_points = grammar.get("points", {})
    words_dict = vocab.get("words", {})
    used_story_grammar = story_grammar_ids(story)
    used_word_ids_sequence = story_word_ids(story)
    used_grammar_sequence = story_grammar_ids_sequence(story)
    marked_new_words = new_ids_marked_once(story, "word_id", "is_new")
    marked_new_grammar = new_ids_marked_once(story, "grammar_id", "is_new_grammar")
    declared_all_words = story.get("all_words_used", [])
    declared_new_words = set(story.get("new_words", []))
    declared_new_grammar = set(story.get("new_grammar", []))

    if not ensure_ordered_unique(declared_all_words):
        result.add_error(4, "all_words_used must not contain duplicates")
    if result.errors:
        return result

    for section_name, tokens in collect_text_sections(story):
        for j, tok in enumerate(tokens):
            loc = token_location(section_name, j, tok)
            if not token_has_required_metadata(tok):
                result.add_error(1, f"Token missing required metadata for role '{tok.get('role')}'", loc)
            if has_kanji(tok.get("t", "")) and tok.get("role") == "content" and "r" not in tok:
                result.add_error(1, "Kanji content token missing 'r' reading", loc)
    if result.errors:
        return result

    # ── Check 2: Closed vocabulary ────────────────────────────────────────────
    for section_name, tokens in collect_text_sections(story):
        for j, tok in enumerate(tokens):
            if tok["role"] not in ("content", "aux"):
                continue
            wid = tok.get("word_id")
            if not wid:
                continue
            loc = token_location(section_name, j, tok)
            if wid not in allowed_words:
                result.add_error(2, f"word_id '{wid}' not in vocab_state or plan new_words", loc)
            inf = tok.get("inflection")
            if inf and isinstance(inf, dict):
                base_wid = inf.get("word_id")
                if base_wid and base_wid not in allowed_words:
                    result.add_error(2, f"inflection.word_id '{base_wid}' not in vocab", loc)

    # ── Check 3: Closed grammar ───────────────────────────────────────────────
    for section_name, tokens in collect_text_sections(story):
        for j, tok in enumerate(tokens):
            for gid in extract_used_grammar(tok):
                if gid not in allowed_grammar:
                    result.add_error(3, f"grammar_id '{gid}' not in grammar_state or plan", token_location(section_name, j, tok))
    for gid in used_story_grammar:
        missing_prereqs = prerequisites_satisfied(used_story_grammar, grammar_points, gid)
        if missing_prereqs:
            result.add_error(3, f"grammar_id '{gid}' missing prerequisites: {missing_prereqs}")

    # ── Check 4: Budget ───────────────────────────────────────────────────────
    story_new_words   = declared_new_words
    story_new_grammar = declared_new_grammar

    if plan:
        extra   = story_new_words - plan_new_words
        missing = plan_new_words - story_new_words
        if extra:
            result.add_error(4, f"Extra new_words not in plan: {sorted(extra)}")
        if missing:
            result.add_error(4, f"Planned new_words missing from story: {sorted(missing)}")

        extra_g = story_new_grammar - plan_new_grammar
        if extra_g:
            result.add_error(4, f"Extra new_grammar not in plan: {sorted(extra_g)}")

    word_ids_used = set(used_word_ids_sequence)
    for wid in story_new_words:
        if wid not in word_ids_used:
            result.add_error(4, f"new_word '{wid}' declared but never used in tokens")

    # Reuse minima: in a normal story we expect each new word/grammar
    # to appear at least twice for reinforcement. Bootstrap/intro stories
    # introduce many new items and can't always meet that — so the rule
    # is relaxed when the story carries an unusually large new-word budget.
    bootstrap_story = len(story_new_words) >= 8 or len(story_new_grammar) >= 4
    new_word_min_uses    = 1 if bootstrap_story else 2
    new_grammar_min_uses = 1 if bootstrap_story else 2

    repeated_new_words = words_repeated_twice(story, story_new_words)
    for wid, count in repeated_new_words.items():
        if count < new_word_min_uses:
            result.add_error(4, f"new_word '{wid}' must appear at least {new_word_min_uses} time(s) (found {count})")

    repeated_new_grammar = repeated_ids(used_grammar_sequence, story_new_grammar)
    for gid, count in repeated_new_grammar.items():
        if count < new_grammar_min_uses:
            result.add_error(4, f"new_grammar '{gid}' must appear at least {new_grammar_min_uses} time(s) (found {count})")

    if ids_in_first_seen_order(story) != declared_all_words:
        result.add_error(4, "all_words_used must list every word_id exactly once in first-seen order")

    declared_all = set(declared_all_words)
    if declared_all != word_ids_used:
        extra   = word_ids_used - declared_all
        missing = declared_all - word_ids_used
        if extra:
            result.add_error(4, f"Words used in tokens but missing from all_words_used: {sorted(extra)}")
        if missing:
            result.add_error(4, f"Words in all_words_used but not found in tokens: {sorted(missing)}")

    def _first_sentence_word(wid: str):
        for sec_idx, name, tokens in text_sections_with_index(story):
            if not name.startswith("sentence "):
                continue
            for t in tokens:
                if t.get("word_id") == wid:
                    return sec_idx, name, t
        return None

    def _first_sentence_grammar(gid: str):
        for sec_idx, name, tokens in text_sections_with_index(story):
            if not name.startswith("sentence "):
                continue
            for t in tokens:
                if gid in extract_used_grammar(t):
                    return sec_idx, name, t
        return None

    for wid in story_new_words:
        occ = first_word_occurrence.get(wid)
        if not occ:
            continue
        section_index, section_name, tok = occ
        # Title/subtitle uses are decorative; the spec's "first introduction"
        # belongs to the body, so use the first sentence occurrence when present.
        if section_name in ("title", "subtitle"):
            sentence_intro = _first_sentence_word(wid)
            if sentence_intro:
                section_index, section_name, tok = sentence_intro
        if not tok.get("is_new"):
            result.add_error(4, f"First occurrence of new_word '{wid}' must have is_new: true", occurrence_section_name(section_name))

    for gid in story_new_grammar:
        occ = first_grammar_occurrence.get(gid)
        if not occ:
            continue
        section_index, section_name, tok = occ
        if section_name in ("title", "subtitle"):
            sentence_intro = _first_sentence_grammar(gid)
            if sentence_intro:
                section_index, section_name, tok = sentence_intro
        if not tok.get("is_new_grammar"):
            result.add_error(4, f"First occurrence of new_grammar '{gid}' must have is_new_grammar: true", occurrence_section_name(section_name))

    for wid, count in marked_new_words.items():
        if wid in story_new_words and count > 1:
            result.add_error(4, f"new_word '{wid}' marked is_new more than once ({count})")
    for gid, count in marked_new_grammar.items():
        if gid in story_new_grammar and count > 1:
            result.add_error(4, f"new_grammar '{gid}' marked is_new_grammar more than once ({count})")

    # ── Check 5: Surface ↔ ID consistency + inflection ───────────────────────
    words_dict = vocab.get("words", {})
    for section_name, tokens in collect_text_sections(story):
        for j, tok in enumerate(tokens):
            wid = tok.get("word_id")
            if not wid:
                continue
            loc = token_location(section_name, j, tok)
            word = words_dict.get(wid)
            if not word:
                continue

            surface = tok["t"]
            inf = tok.get("inflection")

            if inf and isinstance(inf, dict):
                base = inf.get("base") or inf.get("base_r") or word.get("kana", "")
                form = inf.get("form", "")
                expected = expected_reading(word, surface, inf)
                if expected is None:
                    result.add_warning(
                        f"[Check 5] {loc}: Could not compute expected surface for base='{base}' form='{form}' — skipping"
                    )
                else:
                    tok_r = tok.get("r", surface)
                    if tok_r != expected and surface != expected:
                        result.add_error(
                            5,
                            f"Inflection mismatch: surface='{surface}' (reading='{tok_r}'), expected '{expected}' for base='{base}' form='{form}'",
                            loc,
                        )
            else:
                tok_r = tok.get("r", surface)
                dict_surface = word.get("surface", "")
                dict_kana = word.get("kana", "")
                if surface != dict_surface and tok_r != dict_kana and surface != dict_kana:
                    result.add_error(
                        5,
                        f"Surface mismatch: token='{surface}' (reading='{tok_r}'), dict surface='{dict_surface}' / kana='{dict_kana}'",
                        loc,
                    )

    # ── Check 6: Reuse quota ──────────────────────────────────────────────────
    # The reuse rule says ≥ 60% of content tokens must reference words with
    # occurrences < 5 — i.e. the story should be doing real reinforcement of
    # under-practiced vocabulary. Bootstrap stories (lots of new words at once)
    # are exempt because they're introducing words, not reinforcing them.
    if content_tokens and not bootstrap_story:
        reinforcement_count = 0
        for tok in content_tokens:
            wid = tok.get("word_id")
            if wid:
                word = words_dict.get(wid)
                occ  = word.get("occurrences", 0) if word else 0
                if occ < 5:
                    reinforcement_count += 1
        ratio = reinforcement_count / len(content_tokens)
        if ratio < REUSE_QUOTA:
            result.add_error(
                6,
                f"Reuse quota not met: {ratio:.0%} of content tokens have occurrences < 5 (minimum {REUSE_QUOTA:.0%}). ({reinforcement_count}/{len(content_tokens)})"
            )

    # ── Check 7: Length progression ──────────────────────────────────────────
    # Length is now governed by the library-wide progression curve in
    # pipeline/progression.py — the plan's target_word_count and max_sentences
    # are advisory and must themselves agree with the curve (enforced by
    # validate_plan, not here).
    try:
        from progression import (
            target_sentences as _tgt_sent,
            target_content_tokens as _tgt_content,
            sentence_band as _sent_band,
            content_band as _content_band,
        )
        _PROGRESSION_OK = True
    except Exception:
        _PROGRESSION_OK = False

    n_sentences = len(sentences)
    n_content = len(content_tokens)

    if _PROGRESSION_OK:
        sid = story.get("story_id")
        # story_id == 0 is reserved for test fixtures and other in-pipeline
        # uses where progression doesn't apply; fall back to the historic
        # absolute range there.
        if isinstance(sid, int) and sid > 0:
            smin, smax = _sent_band(sid)
            cmin, cmax = _content_band(sid)
            if not (smin <= n_sentences <= smax):
                result.add_error(
                    7,
                    f"Sentence count {n_sentences} outside progression band [{smin}, {smax}] "
                    f"for story_id={sid} (target {_tgt_sent(sid)}; see pipeline/progression.py)"
                )
            if not (cmin <= n_content <= cmax):
                result.add_error(
                    7,
                    f"Content token count {n_content} outside progression band [{cmin}, {cmax}] "
                    f"for story_id={sid} (target {_tgt_content(sid)}; see pipeline/progression.py)"
                )
        else:
            # No story_id: fall back to the historic absolute range
            if not (SENTENCE_MIN <= n_sentences <= SENTENCE_MAX):
                result.add_error(7, f"Sentence count {n_sentences} out of range [{SENTENCE_MIN}, {SENTENCE_MAX}]")
    else:
        # progression.py unavailable: keep the old behavior so the pipeline
        # never silently breaks if someone moves files around.
        if not (SENTENCE_MIN <= n_sentences <= SENTENCE_MAX):
            result.add_error(7, f"Sentence count {n_sentences} out of range [{SENTENCE_MIN}, {SENTENCE_MAX}]")
        if plan:
            target = plan.get("target_word_count", 0)
            if target and not (target * 0.7 <= n_content <= target * 1.3):
                result.add_error(7, f"Content token count {n_content} is outside 70–130% of plan target {target}")

    if plan:
        max_sentences = plan.get("max_sentences", SENTENCE_MAX)
        if n_sentences > max_sentences:
            result.add_error(7, f"Sentence count {n_sentences} exceeds plan max {max_sentences}")

    # ── Check 8: Forbidden topics (keyword heuristic) ────────────────────────
    FORBIDDEN_KEYWORDS = {
        "violence", "kill", "murder", "war", "gun", "weapon", "bomb",
        "romance", "love", "kiss", "sex", "naked",
        "politics", "election", "president", "government",
        "drug", "alcohol", "drunk", "blood", "death", "suicide",
    }
    for i, sent in enumerate(sentences):
        gloss = sent.get("gloss_en", "").lower()
        found = FORBIDDEN_KEYWORDS & set(gloss.split())
        if found:
            result.add_error(
                8,
                f"Forbidden topic keyword(s) in gloss: {sorted(found)}",
                f"sentence {i}"
            )

    # ── Check 9: Gloss sanity ─────────────────────────────────────────────────
    for i, sent in enumerate(sentences):
        gloss = sent.get("gloss_en", "")
        if not gloss.strip():
            result.add_error(9, "Empty gloss_en", f"sentence {i}")
            continue
        jp_tokens = [tok for tok in sent["tokens"] if tok.get("role") != "punct"]
        jp_count  = len(jp_tokens)
        en_count  = len(gloss.split())
        if jp_count > 0:
            ratio = en_count / jp_count
            if not (GLOSS_MIN_RATIO <= ratio <= GLOSS_MAX_RATIO):
                result.add_warning(
                    f"[Check 9] sentence {i}: gloss length ratio {ratio:.1f} (EN words {en_count} / JP tokens {jp_count}) outside expected range [{GLOSS_MIN_RATIO}, {GLOSS_MAX_RATIO}]"
                )

    # ── Check 10: Round-trip ──────────────────────────────────────────────────
    for i, sent in enumerate(sentences):
        joined = "".join(tok["t"] for tok in sent["tokens"])
        if "  " in joined:
            result.add_error(10, "Double space in joined tokens", f"sentence {i}")
        import re
        if re.search(r'[a-zA-Z]{2,}', joined):
            result.add_error(10, f"Stray ASCII in joined tokens: '{joined}'", f"sentence {i}")
        if not joined.endswith(("。", "？", "！", "…", "、")):
            result.add_error(
                10,
                f"Sentence does not end with expected punctuation: '{joined[-3:]}'",
                f"sentence {i}"
            )

    return result


# ── CLI ───────────────────────────────────────────────────────────────────────

def load_json(path: str, label: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"ERROR: {label} file not found: {path}", file=sys.stderr)
        sys.exit(2)
    except json.JSONDecodeError as e:
        print(f"ERROR: {label} is not valid JSON: {e}", file=sys.stderr)
        sys.exit(2)


def main() -> None:
    parser = argparse.ArgumentParser(description="Monogatari story validator")
    parser.add_argument("story",   help="Path to story_N.json")
    parser.add_argument("--plan",    default=None, help="Path to plan.json (optional)")
    parser.add_argument("--vocab",   default="data/vocab_state.json")
    parser.add_argument("--grammar", default="data/grammar_state.json")
    parser.add_argument("--json",    action="store_true", help="Output results as JSON")
    args = parser.parse_args()

    story   = load_json(args.story,   "story")
    vocab   = load_json(args.vocab,   "vocab_state")
    grammar = load_json(args.grammar, "grammar_state")
    plan    = load_json(args.plan,    "plan") if args.plan else None

    result  = validate(story, vocab, grammar, plan)

    if args.json:
        out = {
            "valid": result.valid,
            "errors": [{"check": e.check, "location": e.location, "message": e.message}
                       for e in result.errors],
            "warnings": result.warnings,
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        if result.valid:
            print("✓ VALID")
        else:
            print("✗ INVALID")
        if result.errors:
            print(f"\n{len(result.errors)} error(s):")
            for e in result.errors:
                print(f"  {e}")
        if result.warnings:
            print(f"\n{len(result.warnings)} warning(s):")
            for w in result.warnings:
                print(f"  {w}")

    sys.exit(0 if result.valid else 1)


if __name__ == "__main__":
    main()
