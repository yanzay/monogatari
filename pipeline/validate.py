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
    Returns None if the combination is unknown / unsupported.

    Single source of truth: delegates to jp.expected_inflection where
    available (fugashi/UniDic-aware, irregular-aware), and only falls back
    to the local tables when jp.py isn't loaded or the form isn't covered
    there. This eliminates the "Could not compute expected surface for
    base='見る' form='polite_nonpast' — skipping" warning that affected
    every shipped story.
    """
    form_norm = form.lower().replace("-", "_")

    # Try jp.expected_inflection first.
    try:
        from jp import expected_inflection as _jp_expected_inflection
        primary = _jp_expected_inflection(base, form_norm, verb_class or "ichidan")
        if primary is not None:
            return primary
    except Exception:
        pass

    # Local fallback: irregulars + extra forms not in jp.py (potential,
    # volitional, etc.) handled below.
    if base in IRREGULAR and form_norm in IRREGULAR[base]:
        return IRREGULAR[base][form_norm]

    form = form_norm

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

    # Irregular verbs: 来る (kuru) and する (suru). Tables are tiny and total.
    if verb_class == "irregular_kuru":
        # base is normally 来る or くる
        table = {
            "dictionary":      base,
            "polite_nonpast":  "きます",  "masu":     "きます",  "masu_form": "きます",
            "polite_past":     "きました", "polite_negative": "きません",
            "te":              "きて",   "te_form":  "きて",
            "ta":              "きた",   "past":     "きた",
            "nai":             "こない", "negative": "こない",
        }
        return table.get(form)
    if verb_class == "irregular_suru":
        # base may be plain する/為る or a noun+する compound (e.g. 勉強する).
        # For compounds, strip the trailing する/為る and re-attach the
        # irregular suffix.
        prefix = base
        for tail in ("する", "為る"):
            if base.endswith(tail):
                prefix = base[: -len(tail)]
                break
        table = {
            "dictionary":      base,
            "polite_nonpast":  prefix + "します",   "masu":     prefix + "します",  "masu_form": prefix + "します",
            "polite_past":     prefix + "しました", "polite_negative": prefix + "しません",
            "te":              prefix + "して",    "te_form":  prefix + "して",
            "ta":              prefix + "した",    "past":     prefix + "した",
            "nai":             prefix + "しない",  "negative": prefix + "しない",
        }
        return table.get(form)

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

# ── Check 6 (reuse) tunables ──────────────────────────────────────────────────
# Replaces the old REUSE_QUOTA percentage (0.60) on 2026-04-22.
#
# Why we changed it: the percentage rule punished any story containing natural
# prose (the very common verbs/adjectives like 見る・いい・私 cross the
# under-practiced threshold by story 8, after which every additional natural
# sentence makes the percentage worse). It rewarded weird-noun padding and was
# the single biggest source of "the book in my hands is quiet"-style nonsense
# in the audit. The new rule asks for an absolute reinforcement floor instead:
# every story must include at least N tokens that point at under-practiced
# words, but the rest of the prose is free to be natural.
REUSE_FLOOR_TOKENS    = 6     # at least this many low-occ tokens per story
REUSE_FLOOR_FRACTION  = 0.30  # …or 30% of target_content_tokens, whichever is
                              # SMALLER (i.e. shorter stories get a smaller
                              # absolute requirement). Never below 3.
LOW_OCCURRENCE_LIMIT  = 5     # what counts as "under-practiced"

# Library-level starvation: warn if a low-occ word hasn't been seen in this
# many stories. This pushes the reinforcement decision to the next story's
# planner instead of forcing it on the current author's word arithmetic.
STARVATION_GAP_STORIES = 5

# ── Feature flag: pedagogical cadence/reinforcement rules ───────────────
# Checks 3.6 (max-per-story / bootstrap cap), 3.7 (vocab cadence floor),
# and 3.8 (reinforcement window) are temporarily disabled while the
# converter runs with honest library-wide first-occurrence semantics.
# Flip this to True to re-engage the original rules.
PEDAGOGICAL_CADENCE_ENABLED = False

# ── Check 9 (gloss) tunables ──────────────────────────────────────────────────
# The denominator is the count of JP tokens that *carry English meaning* —
# i.e. role ∈ {content, aux}. Particles (は, を, に, …) and punctuation are
# excluded because they do not surface as English words; counting them
# inflated the denominator and forced authors to pad short, faithful
# glosses (e.g. "I am happy." for 私は嬉しいです — 3 EN words / 4 non-punct
# JP tokens = 0.75) below the old 0.8 floor. Switched 2026-04-22 after
# review found 23 of the existing library's natural glosses sitting at
# ratio 0.80–0.95 only because は/が/を/です were inflating the count.
#
# Warning band: ratios outside this trigger a warning (advisory).
GLOSS_MIN_RATIO = 0.7
GLOSS_MAX_RATIO = 3.0
# Error band: ratios outside this trigger a hard error (almost always means
# the gloss is mistranslated — see the audit's "open the door" / "leave the
# tea ready" cases). Promoted from warning-only on 2026-04-22.
GLOSS_ERROR_MIN_RATIO = 0.4
GLOSS_ERROR_MAX_RATIO = 4.0


def has_kanji(text: str) -> bool:
    return any("一" <= ch <= "龯" for ch in text)


def collect_text_sections(story: dict) -> list[tuple[str, list[dict]]]:
    sections: list[tuple[str, list[dict]]] = []
    for field_name in ("title",):
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
        pos = word.get("pos", "")
        # Canonical POS labels (i_adjective / na_adjective) carry the class
        # directly. Fall back to adj_class for the legacy schema where
        # pos == "adjective" + adj_class == "i" / "na" / "irregular".
        if pos in ("i_adjective", "na_adjective"):
            vclass = pos
        elif pos == "adjective":
            ac = word.get("adj_class", "")
            vclass = (ac + "_adjective") if ac else None
        else:
            vclass = word.get("verb_class") or word.get("adj_class")
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


def _expand_grammar_closure(grammar_ids: set[str], grammar_points: dict) -> set[str]:
    """Return the transitive closure of `grammar_ids` under the prerequisites
    relation. A grammar id whose own prerequisite chain includes G_X effectively
    means G_X is in play (e.g., using でした implies です is in play, since
    G013_mashita_past lists G003_desu as a prerequisite). This avoids spurious
    'missing prerequisite' errors for derived forms that don't surface the base
    form directly in the story."""
    closure: set[str] = set(grammar_ids)
    pending = list(grammar_ids)
    while pending:
        gid = pending.pop()
        point = grammar_points.get(gid, {})
        if not isinstance(point, dict):
            continue
        for pre in point.get("prerequisites", []) or []:
            if pre not in closure:
                closure.add(pre)
                pending.append(pre)
    return closure


def prerequisites_satisfied(grammar_ids: set[str], grammar_points: dict, grammar_id: str) -> list[str]:
    point = grammar_points.get(grammar_id, {})
    prereqs = point.get("prerequisites", []) if isinstance(point, dict) else []
    closure = _expand_grammar_closure(grammar_ids, grammar_points)
    return [gid for gid in prereqs if gid not in closure]


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


def title_sections(story: dict) -> list[tuple[str, list[dict]]]:
    return [(name, tokens) for name, tokens in collect_text_sections(story) if name == "title"]


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


def validate_title_tokens(story: dict, result: ValidationResult) -> None:
    for section_name, tokens in title_sections(story):
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
        for obj_name in ("title",):
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

    validate_title_tokens(story, result)
    if result.errors:
        return result

    # Collect all tokens across titles/sentences, but keep length checks sentence-only.
    all_tokens = collect_all_tokens(story)
    sentence_tokens = collect_sentence_tokens(story)
    content_tokens = [tok for tok in sentence_tokens if tok.get("role") == "content"]
    first_word_occurrence, first_grammar_occurrence = first_occurrence_map(story)
    # Merge any new grammar definitions from the plan so prerequisite
    # checks see new points (which are not yet in grammar_state).
    grammar_points = dict(grammar.get("points", {}))
    if plan:
        for gid, gdef in (plan.get("new_grammar_definitions", {}) or {}).items():
            grammar_points.setdefault(gid, gdef)
    # Same for new word definitions, used by surface/inflection consistency.
    words_dict = dict(vocab.get("words", {}))
    if plan:
        for wid, wdef in (plan.get("new_word_definitions", {}) or {}).items():
            words_dict.setdefault(wid, wdef)
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

    # ── Check 3.5: Grammar tier progression (JLPT-aligned) ───────────────────
    # A story may only INTRODUCE grammar from its current tier or earlier.
    # Re-using an already-existing point (regardless of tier) is always fine;
    # only declared new_grammar is gated. Story_id 0 is the test-fixture
    # sentinel — skip the check there to keep unit-test fixtures simple.
    sid_for_tier = story.get("story_id", 0)
    if sid_for_tier and sid_for_tier > 0:
        try:
            from grammar_progression import (
                is_grammar_legal_for_story,
                active_tier,
                grammar_tier,
                tier_label,
            )
            for gid in declared_new_grammar:
                # Look up jlpt label — prefer plan's new_grammar_definitions
                # (so a story being authored can declare its own jlpt before
                # the point has been written into grammar_state.json), then
                # fall back to grammar_state.
                jlpt = None
                if plan:
                    new_defs = plan.get("new_grammar_definitions", {}) or {}
                    if gid in new_defs:
                        jlpt = new_defs[gid].get("jlpt")
                if jlpt is None:
                    gp = grammar_points.get(gid, {})
                    jlpt = gp.get("jlpt")
                if not is_grammar_legal_for_story(jlpt, sid_for_tier):
                    g_tier = grammar_tier(jlpt)
                    s_tier = active_tier(sid_for_tier)
                    result.add_error(
                        "3.5",
                        f"grammar_id '{gid}' (jlpt={jlpt}, tier {g_tier}) cannot be "
                        f"introduced in story {sid_for_tier} which is in {tier_label(s_tier)}. "
                        f"Cross-tier introductions are blocked — wait until story "
                        f"{[lo for t, lo, _, _ in __import__('grammar_progression').TIER_WINDOWS if t == g_tier][0]}+ "
                        f"or pick an earlier-tier alternative."
                    )
        except ImportError:
            # grammar_progression module missing — soft-skip (back-compat)
            pass

    # ── Check 3.6 / 3.7 / 3.8: library-wide cadence + reinforcement ─────────
    # These three checks are the build-time twin of the pytest suite's
    # test_grammar_introduction_cadence and test_introduced_grammar_is_reinforced.
    # Running them at validate-time means a regression is caught BEFORE the
    # story is shipped, not at next pytest run.
    #
    #   Check 3.6 — cadence (max-per-story + 5-story rolling minimum)
    #   Check 3.8 — reinforcement (each new point reappears in next 5 stories)
    #
    # Like the pytest, both rules are LIBRARY-WIDE: they need every
    # story_*.json on disk, not just the one being validated. Soft-skip on:
    #   * test fixtures (story_id <= 0)
    #   * missing stories/ directory
    #   * missing grammar_progression module
    if sid_for_tier and sid_for_tier > 0:
        try:
            from grammar_progression import (
                BOOTSTRAP_END,
                BOOTSTRAP_MAX_TOTAL,
                MAX_NEW_PER_STORY,
                CADENCE_WINDOW,
                MIN_NEW_PER_WINDOW,
                REINFORCEMENT_WINDOW,
                MIN_REINFORCEMENT_USES,
            )
            from pathlib import Path as _Path
            stories_dir = _Path(__file__).resolve().parent.parent / "stories"
            if stories_dir.is_dir():
                # Load every story on disk; substitute the in-memory copy for
                # the story currently being validated so unsaved edits are
                # reflected in the cadence/reinforcement counts.
                library: dict[int, dict] = {}
                for path in stories_dir.glob("story_*.json"):
                    try:
                        n = int(path.stem.split("_")[1])
                    except (ValueError, IndexError):
                        continue
                    if n == sid_for_tier:
                        library[n] = story
                    else:
                        try:
                            library[n] = json.loads(path.read_text(encoding="utf-8"))
                        except Exception:
                            continue
                if sid_for_tier not in library:
                    library[sid_for_tier] = story

                def _intros_of(d: dict) -> list[str]:
                    out: list[str] = []
                    for x in d.get("new_grammar") or []:
                        if isinstance(x, str):
                            out.append(x)
                        elif isinstance(x, dict):
                            for k in ("id", "grammar_id", "catalog_id"):
                                if k in x:
                                    out.append(x[k])
                                    break
                    return out

                def _grammar_used(d: dict) -> set[str]:
                    u: set[str] = set()
                    for sec in ("title",):
                        for tok in (d.get(sec) or {}).get("tokens", []):
                            for gid in (tok.get("grammar_id"),
                                        (tok.get("inflection") or {}).get("grammar_id")):
                                if gid:
                                    u.add(gid)
                    for sent in d.get("sentences", []):
                        for tok in sent.get("tokens", []):
                            for gid in (tok.get("grammar_id"),
                                        (tok.get("inflection") or {}).get("grammar_id")):
                                if gid:
                                    u.add(gid)
                    return u

                intros_by_n: dict[int, list[str]] = {n: _intros_of(d) for n, d in library.items()}
                used_by_n:   dict[int, set[str]]  = {n: _grammar_used(d) for n, d in library.items()}

                # Check 3.6 (cadence: max-per-story / bootstrap-cap / rolling
                # minimum) is intentionally disabled. With the honest
                # library-wide first-occurrence semantics now in force, the
                # `new_grammar` array is whatever it is — pacing is no longer
                # a story-authoring constraint.

                if PEDAGOGICAL_CADENCE_ENABLED:  # Check 3.8 — temporarily skipped
                    # ── Check 3.8: reinforcement of new grammar in next stories ─
                    # For each grammar point introduced in this story, verify it
                    # reappears in at least MIN_REINFORCEMENT_USES of the next
                    # REINFORCEMENT_WINDOW stories. Because validate may run on a
                    # not-yet-shipped story whose followups don't exist yet, only
                    # require what's present.
                    my_intros = intros_by_n.get(sid_for_tier, [])
                    if my_intros:
                        followups = [i for i in range(sid_for_tier + 1,
                                                      sid_for_tier + 1 + REINFORCEMENT_WINDOW)
                                     if i in library]
                        if followups:
                            required = min(MIN_REINFORCEMENT_USES, len(followups))
                            for gid in my_intros:
                                hits = [i for i in followups if gid in used_by_n.get(i, set())]
                                if len(hits) < required:
                                    result.add_error(
                                        "3.8",
                                        f"new_grammar '{gid}' introduced here is not "
                                        f"reinforced: it reappears in only {len(hits)} "
                                        f"of the next {len(followups)} stories "
                                        f"(stories {hits or 'none'}); needs ≥ {required}. "
                                        f"Either add a token using {gid} in one of "
                                        f"stories {followups[0]}..{followups[-1]}, or "
                                        f"defer this introduction to a later story "
                                        f"where the surface is already present."
                                    )
                    # Also flag REVERSE: if a *prior* story introduced a point that
                    # this story was expected to reinforce but didn't, blame this
                    # story too — it's the followup that missed its job.
                    for prior in range(max(1, sid_for_tier - REINFORCEMENT_WINDOW), sid_for_tier):
                        prior_intros = intros_by_n.get(prior, [])
                        if not prior_intros:
                            continue
                        followups = [i for i in range(prior + 1, prior + 1 + REINFORCEMENT_WINDOW)
                                     if i in library]
                        if not followups:
                            continue
                        required = min(MIN_REINFORCEMENT_USES, len(followups))
                        for gid in prior_intros:
                            hits = [i for i in followups if gid in used_by_n.get(i, set())]
                            if len(hits) < required and sid_for_tier in followups:
                                result.add_warning(
                                    f"[Check 3.8] story {prior} introduced '{gid}' but "
                                    f"this story (in its reinforcement window) doesn't "
                                    f"use it. Consider weaving the surface back in "
                                    f"({len(hits)}/{required} reinforcement uses so far)."
                                )
        except ImportError:
            # grammar_progression module missing — soft-skip (back-compat)
            pass

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

    # Reuse minima — relaxed for new vocabulary on 2026-04-22.
    #
    # Old rule: every new word AND every new grammar point had to appear ≥ 2x
    # in the same story. That was the engine of the "私は本を読みます。
    # 友達も本を読みます。" parallel-construction worksheet feel — the agent
    # had no choice but to repeat the noun in the next sentence, even when the
    # natural flow would have introduced it once and then moved on.
    #
    # New rule:
    #   * new GRAMMAR still requires ≥ 2 occurrences per story (a structural
    #     pattern needs to be visible twice for the learner to recognise it
    #     as a pattern rather than a one-off).
    #   * new VOCABULARY needs only ≥ 1 occurrence in the introducing story.
    #     Reinforcement is now a LIBRARY-level concern handled by Check 6's
    #     starvation alarm and by the next planner's --weak word suggestions.
    bootstrap_story = len(story_new_words) >= 8 or len(story_new_grammar) >= 4

    # ── Check 3.7: Vocabulary cadence floor (HARD error) ──────────────────
    # After the bootstrap window, every story must introduce at least
    # MIN_NEW_WORDS_PER_STORY new vocabulary items. A graded reader that
    # stops growing vocabulary stops being a graded reader. Bootstrap
    # stories (story_id <= BOOTSTRAP_END) are exempt because they load
    # foundational vocabulary in bulk. See pipeline/grammar_progression.py
    # for the constants and the rationale.
    if PEDAGOGICAL_CADENCE_ENABLED:  # Check 3.7 — temporarily skipped
        sid_for_vocab_cadence = story.get("story_id")
        if isinstance(sid_for_vocab_cadence, int) and sid_for_vocab_cadence > 0:
            try:
                from grammar_progression import (
                    BOOTSTRAP_END as _BOOT_END,
                    MIN_NEW_WORDS_PER_STORY as _MIN_NEW_WORDS,
                )
                if sid_for_vocab_cadence > _BOOT_END:
                    if len(story_new_words) < _MIN_NEW_WORDS:
                        result.add_error(
                            "3.7",
                            f"story {sid_for_vocab_cadence} introduces "
                            f"{len(story_new_words)} new vocabulary item(s) "
                            f"(minimum {_MIN_NEW_WORDS} per story after the "
                            f"bootstrap window 1..{_BOOT_END}). A graded reader "
                            f"that stops growing its vocabulary stops being a "
                            f"graded reader; declare more new_words in the plan "
                            f"or defer this story until vocabulary catches up."
                        )
            except Exception:
                # Soft-skip if grammar_progression cannot be imported (e.g. test
                # fixtures running validate() in isolation). The library-level
                # pytest still enforces the rule.
                pass

    new_word_min_uses    = 1                 # always 1 (new vocab) — see above.
    # Same-story new-grammar redundancy lowered to 1 on 2026-04-22 with the
    # introduction of Check 3.8 (library-wide reinforcement). The old "≥2 in
    # introducing story" rule was a proxy for "the learner sees the pattern
    # twice"; now Check 3.8 enforces ≥1 reuse in each of the next 5 stories,
    # which is a stronger and more spaced signal. Keeping ≥2 here would force
    # the introducing story to over-pack a single sentence-pattern, working
    # against natural prose. Bootstrap stories also use ≥1 (unchanged).
    new_grammar_min_uses = 1

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
        # Title uses are decorative; the spec's "first introduction"
        # belongs to the body, so use the first sentence occurrence when present.
        if section_name == "title":
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
        if section_name == "title":
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

    # ── Check 6: Reinforcement floor (replaces old reuse-quota percentage) ───
    # The library still wants every story to do *some* real reinforcement of
    # under-practiced vocabulary, but the old "≥ 60 % of content tokens must
    # be low-occ" rule punished any story that contained natural prose (common
    # verbs/adjectives like 見る・いい・私 cross the threshold by story 8, after
    # which every natural sentence makes the percentage worse). That regime
    # was the single biggest cause of nonsense lines like 「本は静かです」 in
    # the 2026-04-22 audit: weird, low-occ-noun-heavy sentences were cheaper
    # to write than natural ones.
    #
    # The replacement rule asks for an *absolute floor* of reinforcement
    # tokens. Hit the floor and you're done — the rest of the prose is free
    # to be as natural as it needs to be.
    #
    # IMPORTANT: occurrences are still measured AS OF THE STORY'S SHIP TIME,
    # not the current lifetime total (so re-validating an older story against
    # the current vocab_state never retroactively fails it). We do this by
    # subtracting this story's own uses AND every later story's uses from
    # the lifetime total.
    if content_tokens and not bootstrap_story:
        sid = story.get("story_id", 0)

        # Build the discount table (same logic as before — count STORIES, not
        # tokens, to match state_updater.py's per-story-once increment rule).
        discount: dict[str, int] = {}
        def stories_using(story_obj: dict) -> set[str]:
            wids: set[str] = set()
            for sent in story_obj.get("sentences", []):
                for tok in sent.get("tokens", []):
                    wid = tok.get("word_id")
                    if wid:
                        wids.add(wid)
            return wids

        if sid > 0:
            for wid in stories_using(story):
                discount[wid] = discount.get(wid, 0) + 1
            try:
                from pathlib import Path
                stories_dir = Path(__file__).resolve().parent.parent / "stories"
                for path in stories_dir.glob("story_*.json"):
                    try:
                        other_sid = int(path.stem.split("_")[1])
                    except (ValueError, IndexError):
                        continue
                    if other_sid <= sid:
                        continue
                    try:
                        other = json.loads(path.read_text(encoding="utf-8"))
                    except Exception:
                        continue
                    for wid in stories_using(other):
                        discount[wid] = discount.get(wid, 0) + 1
            except Exception:
                pass

        reinforcement_count = 0
        for tok in content_tokens:
            wid = tok.get("word_id")
            if wid:
                word = words_dict.get(wid)
                lifetime_occ = word.get("occurrences", 0) if word else 0
                effective_occ = max(0, lifetime_occ - discount.get(wid, 0))
                if effective_occ < LOW_OCCURRENCE_LIMIT:
                    reinforcement_count += 1

        # Compute the absolute floor for this story's size. Use the
        # progression curve's target_content_tokens if available; fall back
        # to the actual content-token count otherwise.
        try:
            from progression import target_content_tokens as _tgt_for_floor
            target_content = _tgt_for_floor(sid) if isinstance(sid, int) and sid > 0 else len(content_tokens)
        except Exception:
            target_content = len(content_tokens)
        proportional_floor = int(target_content * REUSE_FLOOR_FRACTION)
        floor = max(3, min(REUSE_FLOOR_TOKENS, proportional_floor))

        if reinforcement_count < floor:
            result.add_error(
                6,
                f"Reinforcement floor not met: {reinforcement_count} content "
                f"token(s) point at under-practiced words (occ<{LOW_OCCURRENCE_LIMIT}), "
                f"need at least {floor}. Add a sentence that reuses a recently-"
                f"introduced noun, verb, or adjective. (Lifetime targets are in "
                f"`pipeline/lookup.py --weak`.)"
            )

        # Library-level starvation alarm (warning only). For each known word
        # with effective_occ < LOW_OCCURRENCE_LIMIT that has *not* been used
        # within the last STARVATION_GAP_STORIES stories, surface a warning so
        # the next planner can prioritise it. Skip on test fixtures.
        if isinstance(sid, int) and sid > 0:
            try:
                from pathlib import Path
                stories_dir = Path(__file__).resolve().parent.parent / "stories"
                # Build {wid -> last_story_id_using_it} from history (≤ sid).
                last_seen: dict[str, int] = {}
                for path in stories_dir.glob("story_*.json"):
                    try:
                        other_sid = int(path.stem.split("_")[1])
                    except (ValueError, IndexError):
                        continue
                    if other_sid > sid:
                        continue
                    try:
                        other = json.loads(path.read_text(encoding="utf-8"))
                    except Exception:
                        continue
                    for wid in stories_using(other):
                        if other_sid > last_seen.get(wid, 0):
                            last_seen[wid] = other_sid
                # Add this story's words too (in case it isn't on disk yet).
                for wid in stories_using(story):
                    if sid > last_seen.get(wid, 0):
                        last_seen[wid] = sid
                starved: list[str] = []
                for wid, w in words_dict.items():
                    occ = w.get("occurrences", 0)
                    if occ <= 0 or occ >= LOW_OCCURRENCE_LIMIT:
                        continue
                    last = last_seen.get(wid, 0)
                    if last == 0:
                        # Word in vocab but never used in any story on disk
                        # — likely just declared in a plan, skip.
                        continue
                    if sid - last >= STARVATION_GAP_STORIES:
                        starved.append(f"{wid} (occ={occ}, last seen story_{last})")
                if starved:
                    result.add_warning(
                        f"[Check 6] Library starvation alarm — these under-practiced "
                        f"words have not appeared in the last {STARVATION_GAP_STORIES} "
                        f"stories; consider planning a story around one of them: "
                        + ", ".join(sorted(starved)[:8])
                        + ("…" if len(starved) > 8 else "")
                    )
            except Exception:
                pass

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

    # ── Check 8: REMOVED ─────────────────────────────────────────────────────
    # The forbidden-topic / forbidden-keyword check was removed 2026-04-22 by
    # explicit product decision: "remove all 'forbidden' words, phrases and
    # themes checks, everything should be allowed". The validator no longer
    # imposes any topic, theme, or content restrictions on stories. Subject
    # matter is the author's choice; the validator only checks that the
    # story is mechanically well-formed and pedagogically coherent.
    #
    # Check 8 is intentionally left as a numbered no-op so that downstream
    # error parsers / docs that reference "Check 8" by number don't have to
    # be renumbered. Future content policies, if any, should live OUTSIDE
    # the validator (e.g. as an opt-in linter) rather than as a hard gate.

    # ── Check 9: Gloss sanity ─────────────────────────────────────────────────
    # Two-tier: extreme ratios (< 0.5 or > 4.0) are almost always
    # mistranslations (the audit's "open the door" gloss for ドアを見て was
    # ratio 1.5 — passed the warning band but was nonsense semantically).
    # The phrase-level checks in semantic_lint.py catch the latter; the
    # error band here catches the obvious cases of gloss inflation/elision.
    for i, sent in enumerate(sentences):
        gloss = sent.get("gloss_en", "")
        if not gloss.strip():
            result.add_error(9, "Empty gloss_en", f"sentence {i}")
            continue
        # Count only tokens that carry English meaning. Particles do not
        # surface as English words and inflated the denominator under the
        # pre-2026-04-22 metric, forcing natural short glosses to be padded.
        jp_meaning_tokens = [
            tok for tok in sent["tokens"]
            if tok.get("role") in ("content", "aux")
        ]
        jp_count = len(jp_meaning_tokens)
        en_count = len(gloss.split())
        if jp_count > 0:
            ratio = en_count / jp_count
            if ratio < GLOSS_ERROR_MIN_RATIO or ratio > GLOSS_ERROR_MAX_RATIO:
                result.add_error(
                    9,
                    f"Gloss length ratio {ratio:.1f} (EN words {en_count} / JP meaning-bearing tokens {jp_count}) "
                    f"outside hard error band [{GLOSS_ERROR_MIN_RATIO}, {GLOSS_ERROR_MAX_RATIO}] "
                    f"— this almost always means the gloss invents content not in the JP "
                    f"or omits content that is.",
                    f"sentence {i}"
                )
            elif not (GLOSS_MIN_RATIO <= ratio <= GLOSS_MAX_RATIO):
                result.add_warning(
                    f"[Check 9] sentence {i}: gloss length ratio {ratio:.1f} (EN words {en_count} / JP meaning-bearing tokens {jp_count}) outside expected range [{GLOSS_MIN_RATIO}, {GLOSS_MAX_RATIO}]"
                )

    # ── Check 11: Semantic-sanity lint ──────────────────────────────────────
    # Conservative pattern checks for the kinds of nonsense the mechanical
    # validators silently allow (e.g. inanimate-thing-is-quiet, future-X-eaten-
    # today, ~と思います for self-known facts, smuggled verb word_ids,
    # unestablished motifs). See pipeline/semantic_lint.py for rule docs.
    try:
        from semantic_lint import semantic_sanity_lint
        for issue in semantic_sanity_lint(story, vocab):
            if issue.severity == "error":
                result.add_error(11, issue.message, issue.location)
            else:
                result.add_warning(f"[Check 11] {issue.location}: {issue.message}")
    except ImportError:
        pass  # module missing — soft-skip (back-compat)

    # ── Check 12: Motif-rotation lint (library-level, warning only) ─────────
    # Surfaces high-vocabulary-overlap with the previous N stories so the
    # author / engagement reviewer can decide whether the continuation is
    # justified. Warning only — never blocks ship.
    try:
        from semantic_lint import motif_rotation_lint
        sid_for_motif = story.get("story_id")
        if isinstance(sid_for_motif, int) and sid_for_motif > 0:
            try:
                from pathlib import Path
                stories_dir = Path(__file__).resolve().parent.parent / "stories"
                prior_stories: list[dict] = []
                for path in stories_dir.glob("story_*.json"):
                    try:
                        other_sid = int(path.stem.split("_")[1])
                    except (ValueError, IndexError):
                        continue
                    if other_sid >= sid_for_motif:
                        continue
                    try:
                        prior_stories.append(json.loads(path.read_text(encoding="utf-8")))
                    except Exception:
                        continue
                for issue in motif_rotation_lint(story, prior_stories):
                    result.add_warning(f"[Check 12] {issue.message}")
            except Exception:
                pass
    except ImportError:
        pass

    # ── Check 13: Anti-repetition opener guard (HARD error) ─────────────────
    # Refuse a story if its sentence-0 opener template (first N chars of the
    # joined JP) matches any of the previous K stories OR is on the library
    # opener blocklist. Config lives in pipeline/forbidden_patterns.json.
    try:
        from pathlib import Path as _Path
        cfg_path = _Path(__file__).resolve().parent / "forbidden_patterns.json"
        if cfg_path.is_file():
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            rules = cfg.get("rules", {})
            window = int(rules.get("consecutive_opener_window", 3))
            n_chars = int(rules.get("consecutive_opener_template_max_chars", 8))
            blocklist = list(rules.get("library_opener_blocklist", []))
            grandfather_until = int(rules.get("grandfather_until_story_id", 0))

            sid_for_opener = story.get("story_id")
            grandfathered = (
                isinstance(sid_for_opener, int)
                and sid_for_opener > 0
                and sid_for_opener <= grandfather_until
            )

            def _emit_check13(msg: str, loc: str = "sentence 0") -> None:
                if grandfathered:
                    result.add_warning(f"[Check 13 (grandfathered)] {loc}: {msg}")
                else:
                    result.add_error(13, msg, loc)

            def _emit_check14(msg: str, loc: str = "title") -> None:
                if grandfathered:
                    result.add_warning(f"[Check 14 (grandfathered)] {loc}: {msg}")
                else:
                    result.add_error(14, msg, loc)

            if (
                isinstance(sid_for_opener, int)
                and sid_for_opener > 0
                and sentences
                and sentences[0].get("tokens")
            ):
                s0_text = "".join(t.get("t", "") for t in sentences[0]["tokens"])
                s0_template = s0_text[:n_chars]

                # Blocklist check (always-on, station-keeping)
                for banned in blocklist:
                    if s0_text.startswith(banned):
                        _emit_check13(
                            f"Sentence 0 opens with the library-blocked template "
                            f"'{banned}'. The opener must vary; pick a different "
                            f"shape. Edit pipeline/forbidden_patterns.json only "
                            f"with a justification comment."
                        )
                        break

                # Sliding-window check vs. previous K stories
                stories_dir = _Path(__file__).resolve().parent.parent / "stories"
                prior_openers: list[tuple[int, str]] = []
                if stories_dir.is_dir():
                    for path in stories_dir.glob("story_*.json"):
                        try:
                            other_sid = int(path.stem.split("_")[1])
                        except (ValueError, IndexError):
                            continue
                        if other_sid >= sid_for_opener or other_sid <= 0:
                            continue
                        try:
                            other = json.loads(path.read_text(encoding="utf-8"))
                        except Exception:
                            continue
                        other_sents = other.get("sentences") or []
                        if not other_sents or not other_sents[0].get("tokens"):
                            continue
                        other_s0 = "".join(
                            t.get("t", "") for t in other_sents[0]["tokens"]
                        )
                        prior_openers.append((other_sid, other_s0[:n_chars]))
                prior_openers.sort(key=lambda x: -x[0])
                for other_sid, other_template in prior_openers[:window]:
                    if other_template and other_template == s0_template:
                        _emit_check13(
                            f"Sentence 0 opener template '{s0_template}' matches "
                            f"story_{other_sid}'s opener verbatim (within the "
                            f"last {window} stories). Pre-check item 5 of the "
                            f"engagement-review prompt requires a fresh opener."
                        )
                        break

            # ── Check 14: Title must not be the new-grammar surface form ────
            if rules.get("title_must_not_equal_grammar_form", True):
                title_text = ""
                title = story.get("title") or {}
                if isinstance(title, dict):
                    title_text = title.get("jp") or "".join(
                        t.get("t", "") for t in title.get("tokens", [])
                    )
                title_text = title_text.strip()
                new_grammar = story.get("new_grammar") or []
                if title_text and isinstance(new_grammar, list):
                    grammar_table = grammar.get("points", {}) if isinstance(grammar, dict) else {}
                    for gid in new_grammar:
                        if not isinstance(gid, str):
                            continue
                        gpoint = grammar_table.get(gid) or {}
                        gsurfaces = gpoint.get("surfaces") or gpoint.get("surface_forms") or []
                        if isinstance(gsurfaces, str):
                            gsurfaces = [gsurfaces]
                        for surf in gsurfaces:
                            if not isinstance(surf, str) or not surf:
                                continue
                            if title_text == surf or title_text.endswith(surf):
                                # Allow title to *contain* the form mid-phrase,
                                # but a bare title that is the form (or ends
                                # with it after a noun) is the failure mode we
                                # want to catch ("待ちません", "行きましょう",
                                # "新しい傘がほしい" is borderline; require the
                                # title surface to be at least 1.5x the form
                                # surface to escape).
                                if len(title_text) < int(len(surf) * 1.5):
                                    _emit_check14(
                                        f"Title '{title_text}' is essentially the "
                                        f"new-grammar surface form '{surf}' "
                                        f"(grammar {gid}). Re-title the story so "
                                        f"the form is not the headline — the form "
                                        f"should serve the plot, not be the plot."
                                    )
                                    break
    except Exception:  # never let a guardrail crash the validator
        pass

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
