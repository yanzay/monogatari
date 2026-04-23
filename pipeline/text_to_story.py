#!/usr/bin/env python3
"""
text_to_story.py — Build pipeline/story_raw.json from a plain bilingual text.

Input (JSON):
{
  "story_id": 68,
  "title":    {"jp": "雨", "en": "Rain"},
  "subtitle": {"jp": "静かな朝", "en": "A quiet morning"},
  "sentences": [
    {"jp": "今朝は雨です。", "en": "This morning, it is raining."},
    ...
  ],
  // Optional. Used when a token is NOT yet in vocab_state.json — provides the
  // English meaning that jamdict can't pick reliably.
  "new_word_meanings": {"気分": "mood/feeling"}
}

Output:
  pipeline/story_raw.json           — same shape the writer stage produces
  pipeline/text_to_story.report.json — per-token diagnostics + unresolved items

Then run as usual:
  python3 pipeline/precheck.py --fix
  python3 pipeline/run.py --step 3
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    import jaconv  # type: ignore
except ImportError:
    jaconv = None  # type: ignore

from jp import (  # type: ignore
    JP_OK,
    Token,
    analyze_verb,
    derive_kana,
    has_kanji,
    jmdict_lookup,
    kana_to_romaji,
    katakana_to_hiragana,
    tokenize,
)


# ── Surface → grammar_id (particles / copulas / discourse markers) ──
SURFACE_TO_GRAMMAR: dict[str, str] = {
    "は":     "G001_wa_topic",
    "が":     "G002_ga_subject",
    "です":   "G003_desu",
    "に":     "G004_ni_location",
    "を":     "G005_wo_object",
    "から":   "G006_kara_from",
    "も":     "G009_mo_also",
    "と":     "G010_to_and",
    "や":     "G011_ya_partial",
    "そして": "G012_soshite_then",
    "の":     "G015_no_possessive",
    "な":     "G016_na_adjective",
    "で":     "G017_de_means",
    "ね":     "G034_ne_confirm",
    "か":     "G037_ka_question",
    "だ":     "G024_da",
    "でも":   "G032_demo",
    # Compound particles (multi-token in UniDic)
    "について": "G041_nitsuite",
    "によって": "G042_niyotte",
    "として":   "G043_toshite",
    "のために": "G044_notameni",
    "ために":   "G044_notameni",
}

GRAMMAR_ROLE: dict[str, str] = {
    "G003_desu":         "aux",
    "G013_mashita_past": "aux",
    "G008_te_iru":       "aux",
    "G024_da":           "aux",
    "G016_na_adjective": "particle",
    "G012_soshite_then": "particle",
    "G032_demo":         "particle",
}

# Aux suffixes we glue onto a preceding verb to form a single inflected token.
VERB_SUFFIX_LEMMAS = {"ます", "た", "て", "ない", "ぬ", "う", "れる", "られる", "せる", "させる"}

# Verbs that, when following a て-form, are pulled OUT into a separate aux token
# (te-iru, te-aru, te-oku, te-shimau, te-miru). Keyed by the aux verb's lemma.
TE_AUX_VERBS = {
    "居る":   ("G008_te_iru",   "いる"),
    "有る":   ("G018_te_aru",   "ある"),
    "置く":   ("G019_te_oku",   "おく"),
    "仕舞う": ("G020_te_shimau","しまう"),
    "見る":   ("G027_te_miru",  "みる"),
}

# Reading overrides: UniDic returns formal readings for some pronouns/words.
# Map (lemma_or_surface) → preferred kana.
READING_OVERRIDES: dict[str, str] = {
    "私":   "わたし",
    "私-代名詞": "わたし",
    "今日": "きょう",
    "明日": "あした",
    "昨日": "きのう",
    "今朝": "けさ",
    "今晩": "こんばん",
    "今夜": "こんや",
    "一人": "ひとり",
    "二人": "ふたり",
    "上手": "じょうず",
    "下手": "へた",
}

# Lemma overrides: UniDic gives 有る/居る/返る where canonical uses ある/いる/帰る
# (and 帰る is a homophone-disambiguation fix vs 返る).
LEMMA_OVERRIDES: dict[str, str] = {
    "有る": "ある",
    "居る": "いる",
    "返る": "帰る",
    "為る": "する",
    "成る": "する",   # for 為る misparse → 成る
    "御":   "お",
    "私-代名詞": "私",
}

PUNCT_CHARS = set("。、！？!?…「」『』（）()[]\"'")


def _to_hira(s: str) -> str:
    """Katakana → hiragana, safe if jaconv missing."""
    if not s:
        return s
    if jaconv:
        return jaconv.kata2hira(s)
    return katakana_to_hiragana(s)


def _normalize_lemma(lemma: str) -> str:
    return LEMMA_OVERRIDES.get(lemma, lemma)


def _override_reading(lemma: str, surface: str, fallback: str) -> str:
    if lemma in READING_OVERRIDES:
        return READING_OVERRIDES[lemma]
    if surface in READING_OVERRIDES:
        return READING_OVERRIDES[surface]
    return _to_hira(fallback)


# ── Vocab index ──────────────────────────────────────────────────────────────

@dataclass
class VocabIndex:
    by_surface: dict[str, dict] = field(default_factory=dict)
    by_kana:    dict[str, dict] = field(default_factory=dict)
    # For verbs: index by dictionary-form surface AND kana, since vocab
    # records store the polite (masu) form (e.g. surface=見ます kana=みます).
    by_dict_surface: dict[str, dict] = field(default_factory=dict)
    by_dict_kana:    dict[str, dict] = field(default_factory=dict)

    @classmethod
    def build(cls, vocab_state: dict) -> "VocabIndex":
        idx = cls()
        for w in vocab_state.get("words", {}).values():
            surf = w.get("surface")
            kana = w.get("kana")
            if surf and surf not in idx.by_surface:
                idx.by_surface[surf] = w
            if kana and kana not in idx.by_kana:
                idx.by_kana[kana] = w
            # If this is a verb, also derive and index by the dictionary form.
            if w.get("pos") == "verb" and surf:
                info = analyze_verb(surf) or {}
                d_surf = info.get("lemma")
                d_kana_stem = info.get("lemma_kana") or ""
                v_class = info.get("verb_class") or w.get("verb_class") or "ichidan"
                conj = info.get("conj_type") or ""
                # Reconstruct the dict-form kana
                d_kana = ""
                if v_class == "ichidan":
                    d_kana = d_kana_stem if d_kana_stem.endswith("る") \
                        else (d_kana_stem + "る") if d_kana_stem else ""
                elif v_class == "godan":
                    d_kana = _godan_to_dict(d_kana_stem, conj)
                elif v_class == "irregular_kuru":
                    d_kana, d_surf = "くる", d_surf or "来る"
                elif v_class == "irregular_suru":
                    d_kana, d_surf = "する", d_surf or "する"
                elif v_class == "irregular_aru":
                    d_kana, d_surf = "ある", d_surf or "ある"
                if d_surf and d_surf not in idx.by_dict_surface:
                    idx.by_dict_surface[d_surf] = w
                if d_kana and d_kana not in idx.by_dict_kana:
                    idx.by_dict_kana[d_kana] = w
        return idx

    def lookup(self, surface: str, kana: Optional[str] = None) -> Optional[dict]:
        if surface in self.by_surface:
            return self.by_surface[surface]
        if surface in self.by_dict_surface:
            return self.by_dict_surface[surface]
        if kana:
            if kana in self.by_kana:
                return self.by_kana[kana]
            if kana in self.by_dict_kana:
                return self.by_dict_kana[kana]
        return None


def next_word_id(vocab_state: dict, already_minted: set[str]) -> str:
    nums = [int(k[1:]) for k in vocab_state.get("words", {}) if k.startswith("W")]
    nums += [int(k[1:]) for k in already_minted if k.startswith("W")]
    n = (max(nums) + 1) if nums else 1
    return f"W{n:05d}"


# ── Token merging ────────────────────────────────────────────────────────────
#
# fugashi/UniDic over-segments for our purposes. We greedy-merge in a single
# left-to-right pass, with these rules (in priority order):
#
#   1. でし + た        → でした (single aux token; copula past)
#   2. で(lemma=て)+い(lemma=居る)+ます/た etc. → SPLIT: previous verb keeps
#      its て-form; いる/ある/etc. become a SEPARATE te-aux token (te-iru, …)
#   3. verb + 助動詞/助詞 with lemma in VERB_SUFFIX_LEMMAS → glue onto verb
#   4. otherwise emit token as-is
#
# We carry the full chain of aux suffixes on `_aux` so the inflection
# classifier downstream knows whether we have masu / mashita / te / nai / etc.

def _new_merged(t: Token, word: Optional[dict] = None) -> dict:
    return {
        "surface": t.surface,
        "_pos1": t.pos1,
        "_pos2": t.pos2,
        "_lemma": t.lemma,
        "_lemma_kana": t.lemma_kana,
        "_reading": t.reading or t.surface,
        "_cform": t.inflection_form,
        "_ctype": t.conj_type,
        "_word": word,
        "_aux": [],
        "_force_role": None,            # if set, overrides default role
        "_force_grammar_id": None,      # if set, attaches grammar_id at top level
        "_te_aux_for_prev": False,      # marks token as a te-iru/te-aru aux
    }


def merge_tokens(raw: list[Token], vocab: VocabIndex) -> list[dict]:
    out: list[dict] = []
    i = 0
    n = len(raw)
    # Pre-compute the set of compound-grammar surfaces (multi-char keys only)
    compound_surfaces = sorted(
        (s for s in SURFACE_TO_GRAMMAR if len(s) >= 2),
        key=lambda s: -len(s),
    )

    while i < n:
        t = raw[i]

        # Rule 0: compound grammar surface (について, によって, etc.) — try
        # to glue 2–4 tokens whose joined surface matches the table.
        matched = False
        for cand in compound_surfaces:
            for end in range(min(n, i + 5), i + 1, -1):
                joined = "".join(raw[k].surface for k in range(i, end))
                if joined == cand:
                    m = _new_merged(t)
                    m["surface"] = cand
                    m["_aux"] = list(raw[i + 1:end])
                    m["_pos1"] = "助詞"
                    out.append(m)
                    i = end
                    matched = True
                    break
            if matched:
                break
        if matched:
            continue

        # Rule 1: でし + た → でした (copula past)
        if (
            t.surface == "でし" and t.lemma == "です"
            and i + 1 < n and raw[i + 1].surface == "た"
        ):
            m = _new_merged(t)
            m["surface"] = "でした"
            m["_aux"].append(raw[i + 1])
            m["_force_role"] = "aux"
            m["_force_grammar_id"] = "G013_mashita_past"
            m["_lemma"] = "です"
            out.append(m)
            i += 2
            continue

        # Rule 2: previous merged token ends with て/で AND current is one of
        # the te-aux verbs (居る/有る/置く/仕舞う/見る). Emit the aux verb as
        # a SEPARATE token; consume any trailing ます/た onto it.
        if (
            out
            and out[-1].get("_pos1") == "動詞"
            and out[-1]["surface"].endswith(("て", "で"))
            and t.pos1 == "動詞"
            and t.lemma in TE_AUX_VERBS
        ):
            gid, kana_lemma = TE_AUX_VERBS[t.lemma]
            m = _new_merged(t)
            m["_force_role"] = "aux"
            m["_force_grammar_id"] = gid
            m["_lemma"] = kana_lemma
            # Glue trailing aux suffixes (ます, ました, etc.)
            j = i + 1
            while (
                j < n
                and raw[j].pos1 in ("助動詞", "助詞")
                and raw[j].lemma in VERB_SUFFIX_LEMMAS
            ):
                m["surface"] += raw[j].surface
                m["_aux"].append(raw[j])
                j += 1
            out.append(m)
            i = j
            continue

        # Rule 3: verb suffix glue (ます/た/て/ない…) onto previous verb
        if (
            out
            and out[-1].get("_pos1") == "動詞"
            and t.pos1 in ("助動詞", "助詞")
            and t.lemma in VERB_SUFFIX_LEMMAS
        ):
            prev = out[-1]
            prev["surface"] += t.surface
            prev["_aux"].append(t)
            i += 1
            continue

        # Rule 3b: i-adjective + て (te-form: 古く+て → 古くて)
        if (
            out
            and out[-1].get("_pos1") == "形容詞"
            and t.pos1 == "助詞"
            and t.lemma == "て"
        ):
            prev = out[-1]
            prev["surface"] += t.surface
            prev["_aux"].append(t)
            i += 1
            continue

        # Try greedy multi-token vocab match (max 4 tokens) — for compounds
        # like お茶 if it's in the vocab.
        best_end = i + 1
        best_word = None
        for end in range(min(n, i + 4), i, -1):
            surf = "".join(tt.surface for tt in raw[i:end])
            w = vocab.lookup(surf)
            if w is not None:
                best_end = end
                best_word = w
                break

        if best_word is not None and best_end > i + 1:
            head = raw[i]
            m = _new_merged(head, best_word)
            m["surface"] = "".join(tt.surface for tt in raw[i:best_end])
            m["_reading"] = "".join((tt.reading or tt.surface) for tt in raw[i:best_end])
            m["_aux"] = list(raw[i + 1:best_end])
            out.append(m)
            i = best_end
            continue

        # Plain single token — try lemma in vocab
        word = vocab.lookup(t.surface) or (vocab.lookup(t.lemma) if t.lemma else None)
        out.append(_new_merged(t, word))
        i += 1
    return out


# ── Token → JSON conversion ──────────────────────────────────────────────────

@dataclass
class BuildState:
    vocab_state: dict
    grammar_state: dict
    vocab_index: VocabIndex
    new_word_meanings: dict[str, str]
    minted: dict[str, dict]               # surface → minted vocab record
    seen_word_ids: set[str]               # for is_new (within-story dedup)
    seen_grammar_ids: set[str]            # for is_new_grammar (within-story dedup)
    report: dict
    # Optional explicit hints (used during round-trip / when authoring against
    # a known-good plan). When non-empty, ONLY word_ids in this set get
    # `is_new=true`; everything else is treated as "already known".
    new_word_hint:    Optional[set[str]] = None
    new_grammar_hint: Optional[set[str]] = None


def _grammar_role(gid: str) -> str:
    return GRAMMAR_ROLE.get(gid, "particle")


def _is_known_grammar(gid: str, st: BuildState) -> bool:
    return gid in st.grammar_state.get("points", {})


def _classify_inflection(merged: dict) -> Optional[dict]:
    """
    Return {inflection: {...}, token_grammar_id: str | None} or None.

    Canonical-format conventions:
      - inflection.base    = lemma (with overrides applied)
      - inflection.base_r  = lemma in HIRAGANA, FULL form (e.g. ぬれる, not ヌレ)
      - inflection.form    = "te" | "polite_past" | "polite_nonpast" |
                             "negative_polite" | "past" | "negative" | "dictionary"
      - inflection.verb_class = "godan"|"ichidan"|"irregular_suru"|"irregular_kuru"|"irregular_aru"
      - the GRAMMAR_ID for the inflection is returned separately and goes on
        the *token*, not inside `inflection`.
    """
    surface = merged["surface"]
    if merged["_pos1"] != "動詞":
        return None
    info = analyze_verb(surface) or {}

    # Determine the canonical lemma + kana base
    lemma = _normalize_lemma(merged.get("_lemma") or info.get("lemma") or surface)
    verb_class = info.get("verb_class") or "ichidan"

    # Derive base_r (dictionary-form kana). Strategy: reconstruct from the
    # inflected stem (`lemma_kana`) + verb class. For godan, we use the
    # conj_type ("五段-カ行" → ends in く, "五段-マ行" → ends in む, etc.)
    # because the stem alone is ambiguous (い-音便, 撥音便, 促音便).
    raw_kana = _to_hira(info.get("lemma_kana") or merged.get("_lemma_kana") or "")
    conj = info.get("conj_type") or merged.get("_ctype") or ""
    base_r_hira = ""
    if raw_kana:
        if verb_class == "ichidan":
            base_r_hira = raw_kana if raw_kana.endswith("る") else raw_kana + "る"
        elif verb_class == "godan":
            base_r_hira = _godan_to_dict(raw_kana, conj)
        elif verb_class == "irregular_suru":
            base_r_hira = "する"
        elif verb_class == "irregular_kuru":
            base_r_hira = "くる"
        elif verb_class == "irregular_aru":
            base_r_hira = "ある"
    if not base_r_hira:
        if has_kanji(lemma):
            base_r_hira = _to_hira(derive_kana(lemma) or "")
        else:
            base_r_hira = _to_hira(lemma)

    # Apply hard overrides for the irregulars whose lemma is kana already.
    if lemma in ("ある", "いる", "する", "くる", "来る", "帰る"):
        kana_for = {"ある": "ある", "いる": "いる", "する": "する",
                    "くる": "くる", "来る": "くる", "帰る": "かえる"}
        base_r_hira = kana_for[lemma]

    base = lemma

    # Decide the form name + token-level grammar_id
    full = surface
    form: Optional[str] = None
    token_grammar_id: Optional[str] = None
    if full.endswith("ませんでした"):
        form, token_grammar_id = "negative_polite_past", "G013_mashita_past"
    elif full.endswith("ました"):
        form, token_grammar_id = "polite_past", "G013_mashita_past"
    elif full.endswith("ません"):
        form, token_grammar_id = "negative_polite", "G036_masen"
    elif full.endswith("ます"):
        form, token_grammar_id = "polite_nonpast", "G026_masu_nonpast"
    elif full.endswith("て") or full.endswith("で"):
        form, token_grammar_id = "te", "G007_te_form"
    elif full.endswith("た") or full.endswith("だ"):
        form, token_grammar_id = "past", "G013_mashita_past"
    elif full.endswith("ない"):
        form, token_grammar_id = "negative", "G036_masen"
    else:
        form, token_grammar_id = "dictionary", None

    # If we couldn't classify (no aux suffixes, dictionary form), still emit
    # an inflection block — canonical does this for explicit dictionary verbs
    # too. But avoid emitting for completely uninflected verbs (no aux at all
    # AND surface == lemma kana/surface).
    inflection = {
        "base": base,
        "base_r": base_r_hira,
        "form": form,
        "verb_class": verb_class,
    }
    return {"inflection": inflection, "token_grammar_id": token_grammar_id}


def _godan_stem_to_dict(stem_kana: str) -> str:
    """Legacy entry point — use _godan_to_dict with conj_type."""
    return _godan_to_dict(stem_kana, "")


# Map UniDic 五段-X行 → dictionary-form ending kana
_GODAN_CONJ_ENDING: dict[str, str] = {
    "五段-カ行": "く", "五段-ガ行": "ぐ", "五段-サ行": "す", "五段-タ行": "つ",
    "五段-ナ行": "ぬ", "五段-バ行": "ぶ", "五段-マ行": "む", "五段-ラ行": "る",
    "五段-ワア行": "う", "五段-ワ行": "う",
}


def _godan_to_dict(stem_kana: str, conj_type: str) -> str:
    """
    Convert a godan stem to its dictionary form.
    Strategy:
      1. If conj_type is given (五段-X行), strip the trailing kana of the
         stem (which is the i/onbin/etc. variant) and append the X-row 'u' kana.
      2. Otherwise, fall back to the i-row → u-row table for clean i-row stems.
      3. Return "" if neither works (caller falls back to derive_kana).
    """
    if not stem_kana:
        return ""
    if conj_type in _GODAN_CONJ_ENDING:
        return stem_kana[:-1] + _GODAN_CONJ_ENDING[conj_type]
    # Fallback: clean i-row mapping (works for 連用形-一般)
    last = stem_kana[-1]
    i_to_u = {
        "い": "う", "き": "く", "ぎ": "ぐ", "し": "す", "ち": "つ",
        "に": "ぬ", "ひ": "ふ", "び": "ぶ", "み": "む", "り": "る",
    }
    if last in i_to_u:
        return stem_kana[:-1] + i_to_u[last]
    return ""


def _ensure_word(merged: dict, st: BuildState) -> Optional[dict]:
    """
    Return the vocab record for this token (existing or freshly minted).
    Returns None for tokens that are pure grammar (particles/aux) or punct.
    """
    surface = merged["surface"]
    word = merged.get("_word")
    if word:
        return word
    # Try lemma (and the normalized lemma) fallback
    lemma = merged.get("_lemma") or ""
    for cand in (lemma, _normalize_lemma(lemma)):
        if cand:
            word = st.vocab_index.lookup(cand)
            if word:
                merged["_word"] = word
                return word
    # For verbs, try analyze_verb's lemma (more reliable for irregulars)
    if merged["_pos1"] == "動詞":
        info = analyze_verb(surface) or {}
        for cand in (info.get("lemma"), _normalize_lemma(info.get("lemma") or "")):
            if cand:
                word = st.vocab_index.lookup(cand)
                if word:
                    merged["_word"] = word
                    return word
    # Mint a new one — content tokens only (noun / verb / adj)
    if merged["_pos1"] not in ("名詞", "動詞", "形容詞", "形状詞", "副詞", "代名詞", "連体詞"):
        return None
    if surface in st.minted:
        return st.minted[surface]
    new_id = next_word_id(st.vocab_state, set(st.minted.keys()) | st.seen_word_ids)
    kana = derive_kana(lemma) if lemma else derive_kana(surface) or ""
    kana = katakana_to_hiragana(kana or "")
    pos_map = {"名詞": "noun", "動詞": "verb", "形容詞": "i_adjective",
               "形状詞": "na_adjective", "副詞": "adverb",
               "代名詞": "pronoun", "連体詞": "adnominal"}
    pos = pos_map.get(merged["_pos1"], "noun")
    meaning = st.new_word_meanings.get(surface) or st.new_word_meanings.get(lemma or "")
    if not meaning:
        # Try jamdict
        try:
            hits = jmdict_lookup(lemma or surface, max_results=1)
            if hits and hits[0].senses:
                meaning = hits[0].senses[0]
        except Exception:
            meaning = None
    rec = {
        "id": new_id,
        "surface": lemma or surface,
        "kana": kana,
        "reading": kana_to_romaji(kana),
        "pos": pos,
        "meanings": [meaning or "<TODO meaning>"],
        "_minted_by": "text_to_story",
    }
    if pos == "verb":
        info = analyze_verb(surface) or {}
        rec["verb_class"] = info.get("verb_class") or "ichidan"
    if pos == "i_adjective":
        rec["adj_class"] = "i"
    if pos == "na_adjective":
        rec["adj_class"] = "na"
    st.minted[surface] = rec
    st.report["new_words"].append(rec)
    return rec


def _mark_new_grammar(tok: dict, gid: str, st: BuildState) -> None:
    if gid in st.seen_grammar_ids:
        return
    st.seen_grammar_ids.add(gid)
    # Only set is_new_grammar when the grammar point is genuinely new for the
    # corpus state. With an explicit hint, defer to it; otherwise mark as new
    # if the grammar isn't yet in grammar_state.
    if st.new_grammar_hint is not None:
        if gid in st.new_grammar_hint:
            tok["is_new_grammar"] = True
    else:
        if not _is_known_grammar(gid, st):
            tok["is_new_grammar"] = True
            st.report["unknown_grammar"].append({"surface": tok.get("t"), "grammar_id": gid})


def _surface_reading(merged: dict, word: Optional[dict]) -> Optional[str]:
    """Pick the reading to put on a token's `r` field. Emitted for all content
    tokens (kanji or kana) — canonical includes `r` on most content tokens
    regardless of script."""
    surface = merged["surface"]
    # Prefer vocab record's kana when available and the surface matches
    if word and word.get("kana") and word.get("surface") == surface:
        return word["kana"]
    # Try override
    over = READING_OVERRIDES.get(merged.get("_lemma") or "") \
        or READING_OVERRIDES.get(surface)
    if over:
        return over
    # Compose from head reading + aux suffix surfaces (suffix tokens are kana)
    head = _to_hira(merged.get("_reading") or "")
    aux_text = "".join(t.surface for t in merged.get("_aux", []))
    composed = head + aux_text
    if not composed:
        return None
    # For pure-kana surfaces, just return the surface as-is (canonical does this).
    if not has_kanji(surface):
        return surface
    return composed


def merged_to_token_json(merged: dict, st: BuildState) -> dict:
    surface = merged["surface"]

    # Punctuation
    if surface and all(ch in PUNCT_CHARS for ch in surface):
        return {"t": surface, "role": "punct"}

    # Forced aux token (でした, te-iru / te-aru / te-oku / te-shimau / te-miru)
    if merged.get("_force_role") == "aux" and merged.get("_force_grammar_id"):
        gid = merged["_force_grammar_id"]
        tok: dict = {"t": surface, "role": "aux", "grammar_id": gid}
        # でした gets an inflection block matching canonical
        if gid == "G013_mashita_past" and merged["_lemma"] == "です":
            tok["inflection"] = {
                "base": "です",
                "base_r": "です",
                "form": "polite_past",
            }
        _mark_new_grammar(tok, gid, st)
        return tok

    # Pure grammar surface match (particles / copula / discourse)
    if merged["_pos1"] in ("助詞", "助動詞", "接続詞") and surface in SURFACE_TO_GRAMMAR:
        gid = SURFACE_TO_GRAMMAR[surface]
        tok = {"t": surface, "role": _grammar_role(gid), "grammar_id": gid}
        _mark_new_grammar(tok, gid, st)
        return tok

    # Content word (noun / verb / adjective / pronoun / adverb)
    word = _ensure_word(merged, st)
    if word is None:
        st.report["unresolved"].append({"surface": surface, "pos1": merged["_pos1"]})
        return {"t": surface, "role": "content", "word_id": "<TODO>"}

    tok = {"t": surface, "role": "content", "word_id": word["id"]}
    r = _surface_reading(merged, word)
    if r:
        tok["r"] = r

    # is_new: present and `true` on first occurrence within this story AND
    # the word is genuinely new to the corpus (or in the explicit hint set).
    if word["id"] not in st.seen_word_ids:
        st.seen_word_ids.add(word["id"])
        if st.new_word_hint is not None:
            if word["id"] in st.new_word_hint:
                tok["is_new"] = True
        else:
            if word["id"] not in st.vocab_state.get("words", {}):
                tok["is_new"] = True

    # Inflection (verbs only). Canonical places grammar_id on the TOKEN, not
    # inside `inflection`.
    cls = _classify_inflection(merged)
    if cls:
        infl = cls["inflection"]
        # Drop inflection for plain dictionary-form verbs (no aux suffixes)
        # — canonical only emits inflection when a non-dictionary form fired.
        if infl["form"] != "dictionary":
            tok["inflection"] = infl
            gid = cls["token_grammar_id"]
            if gid:
                tok["grammar_id"] = gid
                _mark_new_grammar(tok, gid, st)

    # Adjective tagging: dictionary-form i-adjectives (surface ends in い)
    # carry G022_i_adj. After Phase 3 normalization, G023_attributive was
    # collapsed into G022_i_adj.
    if (
        merged["_pos1"] == "形容詞"
        and not tok.get("inflection")  # not a te-form etc.
        and not tok.get("grammar_id")
        and surface.endswith("い")
    ):
        tok["grammar_id"] = "G022_i_adj"
        _mark_new_grammar(tok, "G022_i_adj", st)

    return tok


def tokens_for_text(jp_text: str, st: BuildState) -> list[dict]:
    raw = tokenize(jp_text)
    merged = merge_tokens(raw, st.vocab_index)
    return [merged_to_token_json(m, st) for m in merged]


# ── Build the story_raw.json document ────────────────────────────────────────

def build_story(
    spec: dict,
    vocab_state: dict,
    grammar_state: dict,
    new_word_hint: Optional[set[str]] = None,
    new_grammar_hint: Optional[set[str]] = None,
) -> tuple[dict, dict]:
    report = {"new_words": [], "unknown_grammar": [], "unresolved": []}
    st = BuildState(
        vocab_state=vocab_state,
        grammar_state=grammar_state,
        vocab_index=VocabIndex.build(vocab_state),
        new_word_meanings=spec.get("new_word_meanings", {}),
        minted={},
        seen_word_ids=set(),
        seen_grammar_ids=set(),
        report=report,
        new_word_hint=new_word_hint,
        new_grammar_hint=new_grammar_hint,
    )

    # Title and subtitle: tokens go through the same pipeline, but is_new must
    # NOT be set here (per docs/authoring G2). We process title/subtitle FIRST
    # so seen_word_ids gets populated, ensuring sentence tokens carry is_new
    # on their FIRST sentence occurrence.
    def _section(jp: str, en: str) -> dict:
        toks = tokens_for_text(jp, st)
        # Strip any is_new / is_new_grammar from title/subtitle tokens
        for t in toks:
            t.pop("is_new", None)
            t.pop("is_new_grammar", None)
        return {"jp": jp, "en": en, "tokens": toks}

    # Reset seen sets after title/subtitle so sentences get the is_new flag on
    # their first sentence-level occurrence (matches story_1.json convention).
    title = _section(spec["title"]["jp"], spec["title"]["en"])
    subtitle = _section(spec["subtitle"]["jp"], spec["subtitle"]["en"])
    st.seen_word_ids.clear()
    st.seen_grammar_ids.clear()

    sentences = []
    for idx, s in enumerate(spec["sentences"]):
        toks = tokens_for_text(s["jp"], st)
        sentences.append({
            "idx": idx,
            "tokens": toks,
            "gloss_en": s["en"],
        })

    # Build all_words_used in first-seen order across title→subtitle→sentences
    all_word_ids: list[str] = []
    seen: set[str] = set()
    for section in [title, subtitle, *sentences]:
        for t in section["tokens"]:
            wid = t.get("word_id")
            if wid and wid != "<TODO>" and wid not in seen:
                all_word_ids.append(wid)
                seen.add(wid)

    # Compute new_words / new_grammar (delta vs current state)
    existing_words = set(vocab_state.get("words", {}).keys())
    existing_grammar = set(grammar_state.get("points", {}).keys())
    new_words = [w for w in all_word_ids if w not in existing_words]

    used_grammar: list[str] = []
    seen_g: set[str] = set()
    for section in [title, subtitle, *sentences]:
        for t in section["tokens"]:
            gid = t.get("grammar_id")
            if gid and gid not in seen_g:
                used_grammar.append(gid)
                seen_g.add(gid)
            infl = t.get("inflection") or {}
            igid = infl.get("grammar_id")
            if igid and igid not in seen_g:
                used_grammar.append(igid)
                seen_g.add(igid)
    new_grammar = [g for g in used_grammar if g not in existing_grammar]

    raw = {
        "story_id": spec["story_id"],
        "title": title,
        "subtitle": subtitle,
        "new_words": new_words,
        "new_grammar": new_grammar,
        "all_words_used": all_word_ids,
        "sentences": sentences,
    }
    return raw, report


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", help="Path to bilingual story spec JSON")
    ap.add_argument("--out", default=str(ROOT / "pipeline" / "story_raw.json"),
                    help="Where to write story_raw.json")
    ap.add_argument("--report", default=str(ROOT / "pipeline" / "text_to_story.report.json"),
                    help="Where to write the diagnostics report")
    ap.add_argument("--vocab", default=str(ROOT / "data" / "vocab_state.json"))
    ap.add_argument("--grammar", default=str(ROOT / "data" / "grammar_state.json"))
    args = ap.parse_args()

    if not JP_OK:
        print("ERROR: fugashi/jaconv/jamdict are required. "
              "pip install -r requirements.txt", file=sys.stderr)
        return 2

    spec = json.loads(Path(args.input).read_text(encoding="utf-8"))
    vocab_state = json.loads(Path(args.vocab).read_text(encoding="utf-8"))
    grammar_state = json.loads(Path(args.grammar).read_text(encoding="utf-8"))

    raw, report = build_story(spec, vocab_state, grammar_state)

    Path(args.out).write_text(
        json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    Path(args.report).write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    def _rel(p: Path) -> str:
        try:
            return str(p.resolve().relative_to(ROOT))
        except ValueError:
            return str(p)
    print(f"✓ Wrote {_rel(Path(args.out))}")
    print(f"✓ Wrote {_rel(Path(args.report))}")
    print()
    print(f"  new_words         : {len(raw['new_words'])}")
    print(f"  new_grammar       : {len(raw['new_grammar'])}")
    print(f"  minted vocab recs : {len(report['new_words'])}")
    print(f"  unknown_grammar   : {len(report['unknown_grammar'])}")
    print(f"  unresolved tokens : {len(report['unresolved'])}")
    print()
    print("Next steps:")
    print("  1. Review pipeline/text_to_story.report.json for unresolved tokens")
    print("  2. If new_words were minted, append them to data/vocab_state.json")
    print("     (the report contains ready-to-paste records)")
    print("  3. python3 pipeline/precheck.py --fix")
    print("  4. python3 pipeline/run.py --step 3   # validate")
    return 0


if __name__ == "__main__":
    sys.exit(main())
