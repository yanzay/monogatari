#!/usr/bin/env python3
"""
Unified Japanese-language helper module.

Wraps the three lightweight NLP dependencies the authoring tooling now relies on:

  * fugashi + unidic-lite  — morphological analyzer (UniDic-Lite POS, lemmas, readings)
  * jaconv                 — kana ↔ romaji ↔ hiragana/katakana conversion
  * jamdict + jamdict-data — JMdict lookup (English ↔ Japanese dictionary)

Falls back gracefully (with a clear warning) if any of these are not installed,
so the rest of the pipeline keeps working.

Public surface
--------------
    tokenize(text) -> list[Token]
    expected_inflection(base_kana: str, form: str) -> str | None
    derive_kana(surface: str) -> str            # e.g. 猫 -> ねこ
    kana_to_romaji(kana: str) -> str            # e.g. ねこ -> neko
    katakana_to_hiragana / hiragana_to_katakana
    has_kanji(text: str) -> bool
    jmdict_lookup(query: str, max_results: int = 5) -> list[DictEntry]
    JP_OK / which()                             # introspect availability

Token, DictEntry are simple dataclasses with the fields we actually use.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

# ── lazy imports + capability flags ──────────────────────────────────────────
_FUGASHI_OK = False
_JACONV_OK = False
_JAMDICT_OK = False

try:
    import fugashi  # type: ignore
    _TAGGER = fugashi.Tagger()
    _FUGASHI_OK = True
except Exception:
    _TAGGER = None

try:
    import jaconv  # type: ignore
    _JACONV_OK = True
except Exception:
    jaconv = None  # type: ignore

try:
    from jamdict import Jamdict  # type: ignore
    _JAMDICT = Jamdict()
    _JAMDICT_OK = True
except Exception:
    _JAMDICT = None


JP_OK = _FUGASHI_OK and _JACONV_OK and _JAMDICT_OK


def which() -> dict:
    """Report which optional libraries are available."""
    return {"fugashi": _FUGASHI_OK, "jaconv": _JACONV_OK, "jamdict": _JAMDICT_OK}


# ── tokenization ─────────────────────────────────────────────────────────────

@dataclass
class Token:
    surface: str           # 見ます
    lemma: str             # 見る  (dictionary form)
    lemma_kana: str        # みる  (dictionary kana)
    pos1: str              # 動詞 / 名詞 / 助詞 ...
    pos2: str              # 普通名詞 / 格助詞 ...
    reading: str           # ミマス  (full surface kana)
    inflection_form: str   # 連用形-一般 / 終止形 / 命令形 ...
    conj_type: str = ""    # 五段-マ行 / 上一段-マ行 / カ行変格 / サ行変格 / 下一段-バ行 / *
    raw: object = field(default=None, repr=False)


def tokenize(text: str) -> list[Token]:
    """
    Run UniDic-Lite over a string. Returns a list of Token records.

    Note: UniDic-Lite POS tags are Japanese (名詞/動詞/形容詞/助詞/助動詞/...).
    They are deliberately not translated — they are the canonical labels and
    the rest of the pipeline already speaks UniDic.
    """
    if not _FUGASHI_OK:
        return []
    out: list[Token] = []
    for w in _TAGGER(text):
        f = w.feature
        out.append(Token(
            surface=w.surface,
            lemma=getattr(f, "lemma", "") or w.surface,
            lemma_kana=getattr(f, "kana", "") or "",
            pos1=getattr(f, "pos1", "") or "",
            pos2=getattr(f, "pos2", "") or "",
            reading=getattr(f, "kana", "") or "",
            inflection_form=getattr(f, "cForm", "") or "",
            conj_type=getattr(f, "cType", "") or "",
            raw=w,
        ))
    return out


# ── kana / romaji ────────────────────────────────────────────────────────────

_KANJI_RE = re.compile(r"[\u4E00-\u9FFF\u3400-\u4DBF]")


def has_kanji(text: str) -> bool:
    return bool(_KANJI_RE.search(text or ""))


def derive_kana(surface: str) -> str | None:
    """
    For a kanji-bearing surface like 猫, return its hiragana reading via fugashi.
    For a pure-kana surface, return it as hiragana (katakana → hiragana).
    Returns None if fugashi isn't available.
    """
    if not surface:
        return ""
    if not has_kanji(surface):
        return katakana_to_hiragana(surface) if _JACONV_OK else surface
    if not _FUGASHI_OK:
        return None
    toks = tokenize(surface)
    kana = "".join(t.reading or t.surface for t in toks)
    return katakana_to_hiragana(kana) if _JACONV_OK else kana


def kana_to_romaji(kana: str) -> str:
    if not _JACONV_OK or not kana:
        return kana
    return jaconv.kana2alphabet(katakana_to_hiragana(kana))  # type: ignore


def katakana_to_hiragana(s: str) -> str:
    if not _JACONV_OK:
        return s
    return jaconv.kata2hira(s)  # type: ignore


def hiragana_to_katakana(s: str) -> str:
    if not _JACONV_OK:
        return s
    return jaconv.hira2kata(s)  # type: ignore


# ── inflection (a small principled engine) ───────────────────────────────────
#
# We intentionally do NOT delegate inflection generation to UniDic-Lite —
# UniDic gives us *parsing* (analyzing existing text) but not *generation*.
# A small, hand-written conjugation engine covers the forms we actually use
# (polite_nonpast, te, past, polite_past, negative_polite). It is the same
# logic the validator relies on; centralizing it here keeps both in sync.

# Vowel classes for godan て-form / past
_GODAN_T_FORM = {
    "う": "って", "つ": "って", "る": "って",
    "む": "んで", "ぶ": "んで", "ぬ": "んで",
    "く": "いて", "ぐ": "いで",
    "す": "して",
}
_GODAN_PAST = {
    "う": "った", "つ": "った", "る": "った",
    "む": "んだ", "ぶ": "んだ", "ぬ": "んだ",
    "く": "いた", "ぐ": "いだ",
    "す": "した",
}
_GODAN_MASU = {
    "う": "い", "つ": "ち", "る": "り",
    "む": "み", "ぶ": "び", "ぬ": "に",
    "く": "き", "ぐ": "ぎ",
    "す": "し",
}


def expected_inflection(base_kana: str, form: str, verb_class: str = "ichidan") -> str | None:
    """
    Given a dictionary-form kana base (e.g. みる, あるく, する) and a form name,
    compute the expected surface kana.

    Supported forms: polite_nonpast, polite_past, polite_negative,
                     te, past, negative

    Returns None for unsupported combinations — the validator already warns
    in that case rather than blocking, so silent None is the right behavior.
    """
    if not base_kana:
        return None

    # Suru-compounds (勉強する, 散歩する, ...): strip the trailing する/為る
    # and recurse for the irregular suru suffix. The prefix is preserved so
    # 勉強する/polite_nonpast → 勉強します.
    for tail in ("する", "為る"):
        if base_kana.endswith(tail) and len(base_kana) > len(tail):
            prefix = base_kana[: -len(tail)]
            sub = expected_inflection(tail[0] + "る" if tail[0] == "す" else "する",
                                       form, "irregular_suru")
            return (prefix + sub) if sub else None
    # Special verbs
    if base_kana in ("する", "為る"):
        table = {"polite_nonpast": "します", "polite_past": "しました", "polite_negative": "しません",
                 "te": "して", "past": "した", "negative": "しない"}
        return table.get(form)
    if base_kana in ("くる", "来る"):
        table = {"polite_nonpast": "きます", "polite_past": "きました", "polite_negative": "きません",
                 "te": "きて", "past": "きた", "negative": "こない"}
        return table.get(form)
    # 行く is a special godan: te-form is 行って (not the regular 行いて) and
    # past is 行った (not 行いた). Other forms follow the normal godan rules.
    if base_kana in ("いく", "行く"):
        if form in ("te", "te_form"):     return "いって" if base_kana == "いく" else "行って"
        if form in ("past", "ta"):        return "いった" if base_kana == "いく" else "行った"
        # Fall through to standard godan handling for masu/negative/etc.

    last = base_kana[-1]
    stem = base_kana[:-1]

    if verb_class == "ichidan":
        if last != "る":
            return None
        return {
            "polite_nonpast":  stem + "ます",
            "polite_past":     stem + "ました",
            "polite_negative": stem + "ません",
            "te":              stem + "て",
            "past":            stem + "た",
            "negative":        stem + "ない",
        }.get(form)

    if verb_class == "godan":
        if last not in _GODAN_MASU:
            return None
        return {
            "polite_nonpast":  stem + _GODAN_MASU[last] + "ます",
            "polite_past":     stem + _GODAN_MASU[last] + "ました",
            "polite_negative": stem + _GODAN_MASU[last] + "ません",
            "te":              stem + _GODAN_T_FORM[last],
            "past":            stem + _GODAN_PAST[last],
            # negative: う-stem + あ-row + ない (う→わ exception)
            "negative":        stem + ("わ" if last == "う" else _GODAN_MASU[last].translate(str.maketrans("いちりみびにきぎし", "あたらまばなかがさ"))) + "ない",
        }.get(form)

    return None


# ── JMdict lookup ────────────────────────────────────────────────────────────

@dataclass
class DictEntry:
    kanji: list[str]
    kana: list[str]
    senses: list[str]
    pos: list[str]


# ── Verb analysis (UniDic-backed) ────────────────────────────────────────────

# Map UniDic conjugation type prefix → our verb_class taxonomy.
# UniDic cType examples:
#   五段-マ行       → godan         (e.g. 飲む, 読む, 立つ)
#   上一段-マ行     → ichidan       (e.g. 見る)
#   下一段-バ行     → ichidan       (e.g. 食べる, 寝る)
#   カ行変格        → irregular_kuru (来る only)
#   サ行変格        → irregular_suru (する only)
_UNIDIC_CONJ_TO_CLASS = {
    "五段":   "godan",
    "上一段": "ichidan",
    "下一段": "ichidan",
    "カ行変格": "irregular_kuru",
    "サ行変格": "irregular_suru",
}


def _classify_conj(c_type: str) -> str | None:
    """Return our verb_class taxonomy from a UniDic cType, or None if unknown."""
    if not c_type:
        return None
    for prefix, label in _UNIDIC_CONJ_TO_CLASS.items():
        if c_type.startswith(prefix):
            return label
    return None


def analyze_verb(surface: str) -> dict | None:
    """
    Analyze a verb surface (often a polite form like 寝ます) and return
    enough info to populate a vocab definition.

    Returns a dict with:
      - surface         (echo back the input)
      - lemma           (dictionary form, e.g. 寝る; for irregular_suru: 為る)
      - lemma_kana      (hiragana of lemma, e.g. ねる)
      - masu_kana       (hiragana of polite form, e.g. ねます — synthesized)
      - verb_class      (godan / ichidan / irregular_kuru / irregular_suru)
      - is_polite       (True if surface ends in ます)
      - pos1, pos2, conj_type   (raw UniDic tags for diagnostics)

    Returns None if fugashi is unavailable, the surface doesn't tokenize as
    a verb, or the conjugation type can't be classified.

    Handles every verb class including irregulars and suru-compounds:
      analyze_verb("寝ます")     → ichidan, lemma=寝る, masu_kana=ねます
      analyze_verb("読みます")   → godan,   lemma=読む, masu_kana=よみます
      analyze_verb("来ます")     → irregular_kuru, lemma=来る, masu_kana=きます
      analyze_verb("します")     → irregular_suru, lemma=為る, masu_kana=します
      analyze_verb("勉強します") → irregular_suru (compound: 勉強+する)
    """
    if not _FUGASHI_OK or not surface:
        return None
    toks = tokenize(surface)
    if not toks:
        return None

    # Strategy: scan for the first token whose pos1 starts with 動詞 (verb).
    # If the surface is a noun+する compound (勉強します), we'll instead see
    # a noun token (pos1=名詞, pos2 includes サ変可能) followed by します;
    # detect that pattern and return irregular_suru with the noun as lemma.
    # Detect 名詞 + 為る/する compound. UniDic-Lite often labels the noun
    # only as 普通名詞 (no サ変可能 sub-tag), so the structural test —
    # noun immediately followed by する's lemma — is more reliable than
    # depending on a sub-tag that may or may not be present.
    if (
        len(toks) >= 2
        and toks[0].pos1.startswith("名詞")
        and toks[1].lemma in {"為る", "する"}
    ):
        # 勉強+します compound. Lemma is the noun + する.
        noun = toks[0]
        return {
            "surface": surface,
            "lemma": noun.surface + "する",
            "lemma_kana": katakana_to_hiragana(noun.lemma_kana) + "する",
            "masu_kana": katakana_to_hiragana(noun.lemma_kana) + "します",
            "verb_class": "irregular_suru",
            "is_polite": surface.endswith("ます"),
            "pos1": "動詞",
            "pos2": "サ変複合",
            "conj_type": "サ行変格",
        }

    # Plain verb path — find the first verb token.
    verb = next((t for t in toks if t.pos1.startswith("動詞")), None)
    if verb is None:
        return None

    vclass = _classify_conj(verb.conj_type)
    if vclass is None:
        return None

    lemma_kana = katakana_to_hiragana(verb.lemma_kana)
    is_polite = surface.endswith("ます")

    # Synthesize masu_kana from lemma_kana + verb_class.
    if vclass == "ichidan":
        # ねる → ねます ; たべる → たべます
        masu_kana = lemma_kana[:-1] + "ます" if lemma_kana.endswith("る") else lemma_kana + "ます"
    elif vclass == "godan":
        # よむ → よみます ; のむ → のみます ; あるく → あるきます
        masu_kana = expected_inflection(lemma_kana, "polite_nonpast", "godan") or (lemma_kana + "ます")
    elif vclass == "irregular_kuru":
        masu_kana = "きます"
    elif vclass == "irregular_suru":
        # Plain する; for suru-compounds we already returned earlier.
        masu_kana = "します"
    else:
        masu_kana = lemma_kana + "ます"

    return {
        "surface": surface,
        "lemma": verb.lemma,
        "lemma_kana": lemma_kana,
        "masu_kana": masu_kana,
        "verb_class": vclass,
        "is_polite": is_polite,
        "pos1": verb.pos1,
        "pos2": verb.pos2,
        "conj_type": verb.conj_type,
    }


def jmdict_lookup(query: str, max_results: int = 5) -> list[DictEntry]:
    """
    Look up a Japanese or English query in JMdict.

    Pass kanji (猫), kana (ねこ), or English (cat). Returns at most max_results
    DictEntry records.
    """
    if not _JAMDICT_OK or not query:
        return []
    res = _JAMDICT.lookup(query)  # type: ignore
    out: list[DictEntry] = []
    for e in res.entries[:max_results]:
        kanji = [k.text for k in e.kanji_forms]
        kana = [k.text for k in e.kana_forms]
        senses: list[str] = []
        pos_set: list[str] = []
        for s in e.senses:
            text = "; ".join(g.text for g in s.gloss)
            senses.append(text)
            for p in s.pos:
                if p not in pos_set:
                    pos_set.append(p)
        out.append(DictEntry(kanji=kanji, kana=kana, senses=senses, pos=pos_set))
    return out


# ── tiny self-test entry point ───────────────────────────────────────────────

def _selftest() -> None:
    print("── pipeline/jp.py — capability check ──")
    for k, v in which().items():
        print(f"  {k:8s}: {'✓' if v else '✗'}")
    print()
    if _FUGASHI_OK:
        print("tokenize('猫が窓を見ます'):")
        for t in tokenize("猫が窓を見ます"):
            print(f"  {t.surface}  pos={t.pos1}/{t.pos2}  lemma={t.lemma}  reading={t.reading}  cForm={t.inflection_form}")
        print()
        print("derive_kana('猫'):", derive_kana("猫"))
        print("derive_kana('窓の外'):", derive_kana("窓の外"))
    if _JACONV_OK:
        print("kana_to_romaji('ねこ'):", kana_to_romaji("ねこ"))
        print("kana_to_romaji('かえります'):", kana_to_romaji("かえります"))
    print()
    print("expected_inflection('みる','polite_nonpast','ichidan'):", expected_inflection("みる", "polite_nonpast", "ichidan"))
    print("expected_inflection('あるく','te','godan'):", expected_inflection("あるく", "te", "godan"))
    print("expected_inflection('かえる','polite_nonpast','godan'):", expected_inflection("かえる", "polite_nonpast", "godan"))
    print("expected_inflection('くる','te'):", expected_inflection("くる", "te"))
    print()
    if _JAMDICT_OK:
        print("jmdict_lookup('cat')[0:2]:")
        for e in jmdict_lookup("cat", max_results=2):
            print(f"  kanji={e.kanji} kana={e.kana} pos={e.pos}")
            for s in e.senses[:2]:
                print(f"    - {s}")


if __name__ == "__main__":
    _selftest()
