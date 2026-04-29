#!/usr/bin/env python3
"""
text_to_story.py — Build pipeline/story_raw.json from a plain bilingual text.

Input (JSON):
{
  "story_id": 68,
  "title":    {"jp": "雨", "en": "Rain"},
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
    "まで":   "G052_made_until",
    "へ":     "G050_he_direction",
    "も":     "G009_mo_also",
    "と":     "G010_to_and",
    "や":     "G011_ya_partial",
    "そして": "G012_soshite_then",
    "の":     "G015_no_possessive",
    "な":     "G016_na_adjective",
    "で":     "G017_de_means",
    "ね":     "G034_ne_confirm",
    "よ":     "G054_yo_emphasis",
    "か":     "G037_ka_question",
    "だ":     "G024_da",
    "でも":   "G032_demo",
    "じゃ":   "G051_janai",
    "とき":   "G018_toki_when",  # temporal subordinator (when written in kana)
    # Compound particles (multi-token in UniDic)
    "について": "G027_ni_tsuite",
    "だから":   "G059_dakara",
    "ですから": "G059_dakara",
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

# ── Auto-tagged grammar IDs that may be brand-new to grammar_state ───────────
#
# When the tagger emits a grammar_id, `state_updater` needs a full state-entry
# definition (title/short/long/jlpt/catalog_id/prerequisites) to attribute it
# on ship. Pre-loaded points (e.g. G059_dakara) already exist in
# grammar_state.json and only need their `intro_in_story` patched. But some
# auto-tagged paradigms — most notably the plain dictionary form — have
# never been bulk-loaded. Without a registry, the first story to use a
# plain-form verb would crash state_updater with
# "Cannot ship: new_grammar 'G055_…' has no complete definition in plan."
#
# This registry is the single source of truth for those gids. The author_loop
# `_build_state_plan` consults it to populate `new_grammar_definitions`
# whenever the build report flags one of these as `unknown_grammar`.
#
# Schema mirrors the state-entry shape consumed by state_updater (see the
# `defn` block in `state_updater.update_state` — it expects title/short/long
# at minimum, and accepts jlpt/catalog_id/prerequisites/genki_ref/etc.).
KNOWN_AUTO_GRAMMAR_DEFINITIONS: dict[str, dict] = {
    "G055_plain_nonpast_pair": {
        "title":         "〜る/う — plain non-past (dictionary form)",
        "short":         "Plain (dictionary) form of a verb. Casual present/future affirmative; also the form used for noun-modification, 〜こと clauses, and the plain paradigm.",
        "long":          (
            "The dictionary form of a verb (e.g. 食べる, 行く, 見る, 有る) is its "
            "plain non-past form: it doubles as the lemma you look up in a "
            "dictionary AND as the casual equivalent of the polite 〜ます form. "
            "Using a verb in plain form (instead of 〜ます) shifts the register "
            "toward casual / inner-thought / written narration, and unlocks "
            "the entire plain paradigm: 〜ない (negative), 〜た (past), 〜なかった "
            "(past negative), 〜ながら (while), conditional 〜ば, 〜と思います "
            "(quotative thinking), noun-modification (〜本, 〜時), etc. In a "
            "graded reader the first plain-form usage typically appears as "
            "an existential closer (「Xは〜にある。」) or a sensory inner "
            "observation; full casual dialogue follows later."
        ),
        "jlpt":          "N5",
        "catalog_id":    "N5_dictionary_form",
        "prerequisites": [],
        "genki_ref":     "Genki I L8",
        "bunpro_ref":    "bunpro_n5",
        "jlpt_sensei_ref": "jlpt_sensei",
    },
}

# Aux suffixes we glue onto a preceding verb to form a single inflected token.
VERB_SUFFIX_LEMMAS = {
    "ます", "た", "て", "ない", "ぬ", "ず", "う", "よう",
    "たい", "ながら",
    "れる", "られる", "せる", "させる",
}
# `です` is glued to a verb only when the verb already ends in ません
# (forms 〜ませんでした). Standalone です/でした stays separate.

# Verbs that, when following a て-form, are pulled OUT into a separate aux token
# (te-iru, te-aru, te-oku, te-shimau, te-miru). Keyed by the aux verb's lemma.
TE_AUX_VERBS = {
    "居る":   ("G008_te_iru",     "いる"),
    "有る":   ("G018_te_aru",     "ある"),
    "置く":   ("G019_te_oku",     "おく"),
    "仕舞う": ("G020_te_shimau",  "しまう"),
    "見る":   ("G027_te_miru",    "みる"),
    "下さる": ("G044_te_kudasai", "ください"),
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
        # Known irregular dict-form -> polite-form mapping (UniDic homograph
        # mismatches mean the auto-built dict-form index can miss these).
        irregular_dict_to_polite = {
            "する":   "します",
            "為る":   "します",
            "降る":   "降ります",
            "無い":   "ない",
            "ない":   "ない",
            "欲しい": "欲しい",
            "時":     "時",
            "とき":   "時",
        }
        if surface in irregular_dict_to_polite:
            alias = irregular_dict_to_polite[surface]
            if alias in self.by_surface:
                return self.by_surface[alias]
            if alias in self.by_kana:
                return self.by_kana[alias]
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

        # Rule 0a (Phase 4.1, 2026-04-29): honorific-prefix merge.
        #
        # UniDic tokenizes お茶 / お皿 / お金 / ご家族 as TWO tokens:
        #   pos1=接頭辞 (prefix; lemma=御, surface=お/ご)
        #   pos1=名詞   (the noun)
        # without this rule, the prefix becomes a stranded <TODO> in the
        # build report and the noun gets minted as a separate W-id (e.g.
        # 茶 alone instead of お茶) — pedagogically wrong because every
        # textbook treats お茶 / お金 / ご飯 as the canonical learner-
        # facing lemma.
        #
        # Lexicalized prefix-noun compounds (e.g. ご飯) are already
        # tokenized as a single 名詞 by UniDic and don't enter this branch.
        # Only the productive-prefix path needs glueing.
        #
        # The merged token's surface and lemma both become the
        # concatenation (お茶 / お金 / ご家族); kana is computed from the
        # noun's reading with the appropriate prefix kana prepended.
        # pos1 is set to 名詞 so downstream rules treat it as a noun.
        if (
            t.pos1 == "接頭辞"
            and t.lemma == "御"
            and t.surface in ("お", "ご")
            and i + 1 < n
            and raw[i + 1].pos1 == "名詞"
        ):
            noun = raw[i + 1]
            m = _new_merged(noun)
            joined_surface = t.surface + noun.surface
            m["surface"] = joined_surface
            m["_lemma"] = joined_surface
            m["_aux"] = []  # the prefix is consumed into the head; no aux
            m["_pos1"] = "名詞"
            # Kana: prefix kana + noun kana (use noun.kana if present,
            # else fall back to noun.surface). The Token dataclass
            # exposes the reading via .kana on UniDic features.
            prefix_kana = "お" if t.surface == "お" else "ご"
            noun_kana = getattr(noun, "kana", None) or noun.surface
            m["_kana"] = prefix_kana + noun_kana
            out.append(m)
            i += 2
            continue

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

        # Rule 0b: じゃ + ない (+ です) → じゃない / じゃないです
        # (G051_janai). Glue 2 or 3 tokens into one aux.
        if (
            t.surface == "じゃ" and t.lemma == "だ"
            and i + 1 < n and raw[i + 1].surface == "ない"
        ):
            m = _new_merged(t)
            m["surface"] = "じゃない"
            m["_aux"].append(raw[i + 1])
            m["_force_role"] = "aux"
            m["_force_grammar_id"] = "G051_janai"
            m["_lemma"] = "じゃない"
            j = i + 2
            if j < n and raw[j].surface == "です":
                m["surface"] += raw[j].surface
                m["_aux"].append(raw[j])
                j += 1
            out.append(m)
            i = j
            continue

        # Rule 1: でし + た → でした (copula past) — but ONLY when not
        # following a verb (in which case でし is a suffix glued to make
        # 〜ませんでした).
        if (
            t.surface == "でし" and t.lemma == "です"
            and i + 1 < n and raw[i + 1].surface == "た"
            and not (out and out[-1].get("_pos1") == "動詞")
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

        # Rule 3a: ませんでした glue — when previous verb already ends in
        # ません, pull in でし+た (or でした) as a single past-negative.
        if (
            out
            and out[-1].get("_pos1") == "動詞"
            and out[-1]["surface"].endswith("ません")
            and t.surface in ("でし", "でした")
            and t.lemma == "です"
        ):
            prev = out[-1]
            prev["surface"] += t.surface
            prev["_aux"].append(t)
            # Consume the trailing た if でし
            if t.surface == "でし" and i + 1 < n and raw[i + 1].surface == "た":
                prev["surface"] += raw[i + 1].surface
                prev["_aux"].append(raw[i + 1])
                i += 2
            else:
                i += 1
            continue

        # Rule 3b: i-adjective + て (te-form: 古く+て → 古くて) OR
        #          i-adjective + た (past:    暑かっ+た → 暑かった) OR
        #          i-adjective + ない (negative: 寒く+ない → 寒くない;
        #          UniDic gives the negative aux ない as i-adjective with
        #          lemma 無い, hence the lemma alternation).
        if (
            out
            and out[-1].get("_pos1") == "形容詞"
            and t.pos1 in ("助詞", "助動詞", "形容詞")
            and t.lemma in ("て", "た", "ない", "無い")
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
    report: dict
    # NB: is_new / is_new_grammar / new_words / new_grammar are NOT decided here.
    # They are owned by the library-wide first-occurrence pass in
    # pipeline/regenerate_all_stories.py:_normalize_first_occurrence_flags
    # which runs after every story has been written and rewrites those fields
    # deterministically by walking the shipped library in id order.


def _grammar_role(gid: str) -> str:
    return GRAMMAR_ROLE.get(gid, "particle")


def extract_token_grammar(token: dict) -> list[str]:
    """Return all grammar_ids carried by a token (top-level + inflection.grammar_id)."""
    out = []
    gid = token.get("grammar_id")
    if gid:
        out.append(gid)
    infl = token.get("inflection")
    if isinstance(infl, dict):
        igid = infl.get("grammar_id")
        if igid and igid not in out:
            out.append(igid)
    return out


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
        form, token_grammar_id = "polite_past_negative", "G046_masen_deshita"
    elif full.endswith("ましょう") or full.endswith("ましょうか"):
        form, token_grammar_id = "volitional_polite", "G048_masho"
    elif full.endswith("ました"):
        form, token_grammar_id = "polite_past", "G013_mashita_past"
    elif full.endswith("ません"):
        # Special-case ありません → G035_arimasen (lexical existence-negation
        # for inanimate things), not G036_masen.
        if full == "ありません" or full.endswith("ありません"):
            form, token_grammar_id = "negative_polite", "G035_arimasen"
        else:
            form, token_grammar_id = "negative_polite", "G036_masen"
    elif full.endswith("ます"):
        form, token_grammar_id = "polite_nonpast", "G026_masu_nonpast"
    elif full.endswith("なかった"):
        form, token_grammar_id = "plain_past_negative", "G056_plain_past_pair"
    elif full.endswith("ながら"):
        form, token_grammar_id = "nagara", "G057_nagara"
    elif full.endswith("たい"):
        form, token_grammar_id = "tai", "G031_tai"
    elif full.endswith("て") or full.endswith("で"):
        form, token_grammar_id = "te", "G007_te_form"
    elif full.endswith("た") or full.endswith("だ"):
        form, token_grammar_id = "past", "G013_mashita_past"
    elif full.endswith("ない"):
        form, token_grammar_id = "negative", "G036_masen"
    else:
        # Plain dictionary form (no aux suffix). This is the canonical
        # introduction site for N5_dictionary_form. The companion
        # G055_plain_nonpast_pair entry in KNOWN_AUTO_GRAMMAR_DEFINITIONS
        # carries the state-entry definition so the first usage in the
        # corpus can ship cleanly via state_updater.
        form, token_grammar_id = "dictionary", "G055_plain_nonpast_pair"

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
    new_id = next_word_id(st.vocab_state, {r["id"] for r in st.minted.values()})
    kana = derive_kana(lemma) if lemma else derive_kana(surface) or ""
    kana = katakana_to_hiragana(kana or "")
    pos_map = {"名詞": "noun", "動詞": "verb", "形容詞": "i_adjective",
               "形状詞": "na_adjective", "副詞": "adverb",
               "代名詞": "pronoun", "連体詞": "adnominal"}
    pos = pos_map.get(merged["_pos1"], "noun")
    # UniDic appends an etymology suffix to katakana loanwords
    # (e.g. lemma='ペン-pen', 'ページ-page'). Strip it before lookup/mint.
    clean_lemma = (lemma or surface).split("-", 1)[0]
    clean_kana = kana.split("-", 1)[0] if kana else ""
    meaning = st.new_word_meanings.get(surface) or st.new_word_meanings.get(clean_lemma)
    if not meaning:
        # Try jamdict with the cleaned lemma
        try:
            hits = jmdict_lookup(clean_lemma or surface, max_results=1)
            if hits and hits[0].senses:
                meaning = hits[0].senses[0]
        except Exception:
            meaning = None
    rec = {
        "id": new_id,
        "surface": clean_lemma or surface,
        "kana": clean_kana or kana,
        "reading": kana_to_romaji(clean_kana or kana),
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


def _record_unknown_grammar(tok: dict, gid: str, st: BuildState) -> None:
    """Just a diagnostic — flagging genuinely-unknown gids in the report.
    The first-occurrence pass downstream owns is_new_grammar."""
    if not _is_known_grammar(gid, st):
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
        _record_unknown_grammar(tok, gid, st)
        return tok

    # Pure grammar surface match (particles / copula / discourse).
    # The very few nominal surfaces that act as grammar markers (とき, だから)
    # are also accepted from 名詞/接続詞.
    GRAMMAR_NOMINAL_SURFACES = {"とき", "だから", "ですから"}
    if (
        merged["_pos1"] in ("助詞", "助動詞", "接続詞")
        and surface in SURFACE_TO_GRAMMAR
    ) or surface in GRAMMAR_NOMINAL_SURFACES and surface in SURFACE_TO_GRAMMAR:
        gid = SURFACE_TO_GRAMMAR[surface]
        tok = {"t": surface, "role": _grammar_role(gid), "grammar_id": gid}
        _record_unknown_grammar(tok, gid, st)
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

    # NB: is_new is intentionally NOT set here. The deterministic
    # library-wide first-occurrence pass (run after every story is written)
    # owns this field — see _normalize_first_occurrence_flags.

    # Inflection (verbs only). Canonical places grammar_id on the TOKEN, not
    # inside `inflection`.
    cls = _classify_inflection(merged)
    if cls:
        infl = cls["inflection"]
        # Plain-form-of-polite-vocab path: the vocab record is the polite
        # 〜ます form (e.g. 見ます W00010, 出ます), but the token surface is
        # the bare dictionary form (見る, 出る). We rename `form` from
        # "dictionary" → "plain_nonpast" so downstream consumers
        # (validators, semantic_lint) can distinguish "this is a deliberate
        # plain variant of a polite-form vocab record" from "this verb's
        # canonical lemma IS the dict form" (e.g. 取る W00017). Both paths
        # carry the same grammar_id (G055_plain_nonpast_pair) because both
        # represent the same paradigm anchor — N5_dictionary_form.
        is_plain_form_of_polite_vocab = (
            infl["form"] == "dictionary"
            and word and word.get("pos") == "verb"
            and word.get("surface", "").endswith("ます")
        )
        if is_plain_form_of_polite_vocab:
            infl["form"] = "plain_nonpast"
        # Pure dictionary-form path (vocab.surface IS the dict form, e.g.
        # 取る W00017): there's nothing to back-conjugate, but we still need
        # to attach the inflection block AND tag the grammar_id so the
        # paradigm anchor (G055_plain_nonpast_pair / N5_dictionary_form)
        # gets attributed. Take the short-circuit path before the
        # masu-stem reconstruction block (which only fires for vocab
        # stored as 〜ます).
        if infl["form"] == "dictionary":
            tok["inflection"] = infl
            gid = cls["token_grammar_id"]
            if gid:
                tok["grammar_id"] = gid
                _record_unknown_grammar(tok, gid, st)
        if infl["form"] != "dictionary":
            # If we have a vocab record for this verb, prefer its truth:
            # vocab.kana is the polite-form kana (e.g. ふります for W00107).
            # We need base_r in plain dict form. Reconstruct from vocab.kana
            # by stripping ます and back-conjugating per verb_class.
            if word and word.get("kana") and word.get("pos") == "verb":
                vocab_kana = word["kana"]
                if vocab_kana.endswith("ます"):
                    stem = vocab_kana[:-2]
                    vc = word.get("verb_class") or infl.get("verb_class")
                    if vc == "ichidan":
                        infl["base_r"] = stem + "る"
                    elif vc == "godan":
                        infl["base_r"] = _godan_to_dict(stem, "")
                    elif vc == "irregular_kuru":
                        infl["base_r"] = "くる"
                    elif vc == "irregular_suru":
                        infl["base_r"] = "する"
                    elif vc == "irregular_aru":
                        infl["base_r"] = "ある"
                # Use the vocab record's surface dict-form too (strip ます).
                # For godan: vocab surface ends in masu-stem (i-row) kana such
                # as 思い・行き・飲み — we replace the trailing kana with the
                # dict-form ending derived from base_r.
                vocab_surf = word.get("surface", "")
                if vocab_surf.endswith("ます"):
                    surface_stem = vocab_surf[:-2]
                    vc = word.get("verb_class") or infl.get("verb_class")
                    if vc == "ichidan":
                        # 見ます → stem 見 → 見る
                        infl["base"] = surface_stem + "る"
                    elif vc == "godan":
                        # Replace trailing kana of stem with dict-form ending.
                        # 思い → 思う, 行き → 行く, 飲み → 飲む.
                        ending = (infl.get("base_r") or "")[-1:]
                        if surface_stem and ending:
                            if not has_kanji(surface_stem[-1]):
                                # last char is the masu-stem kana → replace it
                                infl["base"] = surface_stem[:-1] + ending
                            else:
                                # all-kanji stem (rare) → append
                                infl["base"] = surface_stem + ending
                    elif vc == "irregular_kuru":
                        infl["base"] = "来る"
                    elif vc == "irregular_suru":
                        infl["base"] = surface_stem + "する" if surface_stem else "する"
                    elif vc == "irregular_aru":
                        infl["base"] = "ある"
            tok["inflection"] = infl
            gid = cls["token_grammar_id"]
            if gid:
                tok["grammar_id"] = gid
                _record_unknown_grammar(tok, gid, st)

    # Adjective tagging.
    if merged["_pos1"] == "形容詞" and not tok.get("inflection") and not tok.get("grammar_id"):
        # Past:    暑かった/美しかった (≥ 4 chars ending in かった)
        # Te-form: 暑くて/美しくて   (ends in くて)
        # Neg:     暑くない         (ends in くない)
        if surface.endswith("かった"):
            tok["inflection"] = {"form": "i_adj_past"}
            tok["grammar_id"] = "G047_i_adj_past"
            _record_unknown_grammar(tok, "G047_i_adj_past", st)
        elif surface.endswith("くて"):
            tok["inflection"] = {"form": "i_adj_te"}
            tok["grammar_id"] = "G029_kute"
            _record_unknown_grammar(tok, "G029_kute", st)
        elif surface.endswith("くない"):
            tok["inflection"] = {"form": "i_adj_negative"}
            tok["grammar_id"] = "G038_kunai"
            _record_unknown_grammar(tok, "G038_kunai", st)
        elif surface.endswith("い"):
            tok["grammar_id"] = "G022_i_adj"
            _record_unknown_grammar(tok, "G022_i_adj", st)

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
) -> tuple[dict, dict]:
    """Build a story_raw.json document from a bilingual spec.

    NB: `is_new`, `is_new_grammar`, and the story-level `new_words` /
    `new_grammar` arrays are intentionally left empty here. They are owned
    by `regenerate_all_stories._normalize_first_occurrence_flags`, which
    runs after every story has been written and assigns those fields by
    walking the shipped library deterministically in story-id order.
    """
    report = {"new_words": [], "unknown_grammar": [], "unresolved": []}
    st = BuildState(
        vocab_state=vocab_state,
        grammar_state=grammar_state,
        vocab_index=VocabIndex.build(vocab_state),
        new_word_meanings=spec.get("new_word_meanings", {}),
        minted={},
        report=report,
    )

    def _section(jp: str, en: str) -> dict:
        return {"jp": jp, "en": en, "tokens": tokens_for_text(jp, st)}

    title = _section(spec["title"]["jp"], spec["title"]["en"])
    sentences = []
    for idx, s in enumerate(spec["sentences"]):
        sentences.append({
            "idx": idx,
            "tokens": tokens_for_text(s["jp"], st),
            "gloss_en": s["en"],
        })

    # all_words_used in first-seen order across title→sentences
    all_word_ids: list[str] = []
    seen: set[str] = set()
    for section in [title, *sentences]:
        for t in section["tokens"]:
            wid = t.get("word_id")
            if wid and wid != "<TODO>" and wid not in seen:
                all_word_ids.append(wid)
                seen.add(wid)

    raw = {
        "story_id": spec["story_id"],
        "title": title,
        "new_words": [],     # filled by _normalize_first_occurrence_flags
        "new_grammar": [],   # filled by _normalize_first_occurrence_flags
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
