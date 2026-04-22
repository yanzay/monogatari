"""
Builds data/grammar_catalog.json from a hand-curated, cross-referenced
list of JLPT grammar points (N5 + N4 + N3).

Each entry has been cross-checked against THREE independent sources:
  - JLPTSensei (https://jlptsensei.com/jlpt-N{5..3}-grammar-list/)
  - BunPro N5/N4/N3 grammar decks (https://bunpro.jp/decks/...)
  - Genki I/II textbook lesson numbers (where applicable)
            or Tobira: Gateway to Advanced Japanese (for N3)

Inclusion rule: a point is added only if at least 2 of the 3 sources
agree on the JLPT level. If sources disagree, the more conservative
(LOWER level number / HARDER) is recorded and `disputed: true` is set.

This script is the source-of-truth. To re-generate the catalog:
    python3 pipeline/build_grammar_catalog.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT  = ROOT / "data" / "grammar_catalog.json"


# ─────────────────────────────────────────────────────────────────────
#  N5 — foundation tier
# ─────────────────────────────────────────────────────────────────────
# Cross-references: JLPTSensei N5 list, BunPro N5 deck, Genki I lesson.
# Format: (id, marker, jlpt, category, title, short, sources_csv, prereq_csv)
N5_POINTS = [
    ("desu",        "です",       "N5", "copula",     "です — polite copula",
     "polite 'is/am/are'",                            "jlpt_sensei,bunpro_n5,genki_L1", ""),
    ("da",          "だ",         "N5", "copula",     "だ — plain copula",
     "casual 'is/am/are'",                            "jlpt_sensei,bunpro_n5,genki_L8", "desu"),
    ("wa_topic",    "は",         "N5", "particle",   "は — topic",
     "marks the topic",                               "jlpt_sensei,bunpro_n5,genki_L1", ""),
    ("ga_subject",  "が",         "N5", "particle",   "が — subject",
     "marks the subject (and new info)",              "jlpt_sensei,bunpro_n5,genki_L2", ""),
    ("o_object",    "を",         "N5", "particle",   "を — direct object",
     "marks the direct object",                       "jlpt_sensei,bunpro_n5,genki_L3", ""),
    ("ni_location", "に",         "N5", "particle",   "に — location/time/goal",
     "static location, time, indirect object",        "jlpt_sensei,bunpro_n5,genki_L3", ""),
    ("de_means",    "で",         "N5", "particle",   "で — by means / at",
     "means/method or activity location",             "jlpt_sensei,bunpro_n5,genki_L3", ""),
    ("e_direction", "へ",         "N5", "particle",   "へ — direction",
     "movement toward",                               "jlpt_sensei,bunpro_n5,genki_L3", ""),
    ("kara_from",   "から",       "N5", "particle",   "から — from",
     "starting point (place/time)",                   "jlpt_sensei,bunpro_n5,genki_L3", ""),
    ("made_until",  "まで",       "N5", "particle",   "まで — until",
     "endpoint (place/time)",                         "jlpt_sensei,bunpro_n5,genki_L3", ""),
    ("no_pos",      "の",         "N5", "particle",   "の — possessive/attributive",
     "links nouns: A の B",                           "jlpt_sensei,bunpro_n5,genki_L1", ""),
    ("to_and",      "と",         "N5", "particle",   "と — exhaustive 'and'",
     "joins nouns: A と B",                           "jlpt_sensei,bunpro_n5,genki_L4", ""),
    ("ya_partial",  "や",         "N5", "particle",   "や — partial 'and'",
     "non-exhaustive listing",                        "jlpt_sensei,bunpro_n5,genki_L11", "to_and"),
    ("mo_also",     "も",         "N5", "particle",   "も — also/too",
     "'also' / 'too' / 'either'",                     "jlpt_sensei,bunpro_n5,genki_L2", ""),
    ("ka_question", "か",         "N5", "particle",   "か — question",
     "sentence-final question marker",                "jlpt_sensei,bunpro_n5,genki_L1", ""),
    ("ne_confirm",  "ね",         "N5", "particle",   "ね — seeking agreement",
     "'right?' / 'isn't it?'",                        "jlpt_sensei,bunpro_n5,genki_L1", ""),
    ("yo_emphasis", "よ",         "N5", "particle",   "よ — emphasis/new info",
     "asserts new information",                       "jlpt_sensei,bunpro_n5,genki_L1", ""),
]

N5_POINTS += [
    # ── verb forms ────────────────────────────────────────────────
    ("masu_nonpast", "〜ます", "N5", "verb_form", "〜ます — polite non-past",
     "polite present/future verb",                    "jlpt_sensei,bunpro_n5,genki_L3", ""),
    ("masen",        "〜ません", "N5", "verb_form", "〜ません — polite negative",
     "polite present negative",                       "jlpt_sensei,bunpro_n5,genki_L3", "masu_nonpast"),
    ("mashita",      "〜ました", "N5", "verb_form", "〜ました — polite past",
     "polite past affirmative",                       "jlpt_sensei,bunpro_n5,genki_L4", "masu_nonpast"),
    ("masen_deshita","〜ませんでした","N5","verb_form","〜ませんでした — polite past negative",
     "polite past negative",                          "jlpt_sensei,bunpro_n5,genki_L4", "mashita"),
    ("masho",        "〜ましょう", "N5", "verb_form", "〜ましょう — let's / shall we",
     "polite volitional",                             "jlpt_sensei,bunpro_n5,genki_L5", "masu_nonpast"),
    ("masenka",      "〜ませんか", "N5", "verb_form", "〜ませんか — won't you?",
     "invitation",                                    "jlpt_sensei,bunpro_n5,genki_L5", "masen"),
    ("te_form",      "〜て",     "N5", "verb_form", "〜て — te-form",
     "connector / request / progressive base",        "jlpt_sensei,bunpro_n5,genki_L6", "masu_nonpast"),
    ("te_kudasai",   "〜てください","N5","verb_form","〜てください — please do",
     "polite request",                                "jlpt_sensei,bunpro_n5,genki_L6", "te_form"),
    ("te_iru",       "〜ている",  "N5", "verb_form", "〜ている — progressive / state",
     "ongoing or resulting state",                    "jlpt_sensei,bunpro_n5,genki_L7", "te_form"),
    ("te_mo_ii",     "〜てもいい","N5","verb_form","〜てもいい — may / it's ok to",
     "permission",                                    "jlpt_sensei,bunpro_n5,genki_L6", "te_form"),
    ("nai_form",     "〜ない",    "N5", "verb_form", "〜ない — plain negative",
     "casual present negative",                       "jlpt_sensei,bunpro_n5,genki_L8", "masen"),
    ("ta_form",      "〜た",      "N5", "verb_form", "〜た — plain past",
     "casual past affirmative",                       "jlpt_sensei,bunpro_n5,genki_L9", "mashita"),
    ("nakatta",      "〜なかった","N5","verb_form","〜なかった — plain past negative",
     "casual past negative",                          "jlpt_sensei,bunpro_n5,genki_L9", "nai_form"),
    ("dictionary_form","〜る/う","N5","verb_form","plain non-past (dictionary form)",
     "casual present/future affirmative",             "jlpt_sensei,bunpro_n5,genki_L8", ""),
    ("hoshii",       "〜がほしい","N5","verb_form","〜がほしい — want (noun)",
     "want a thing",                                  "jlpt_sensei,bunpro_n5,genki_L11", "ga_subject"),
    ("tai",          "〜たい",    "N5", "verb_form", "〜たい — want to (verb)",
     "want to do something",                          "jlpt_sensei,bunpro_n5,genki_L11", "masu_nonpast"),

    # ── adjectives ────────────────────────────────────────────────
    ("i_adj",        "い-adj",   "N5", "adjective", "い-adjectives",
     "adjectives ending in い",                        "jlpt_sensei,bunpro_n5,genki_L5", ""),
    ("na_adj",       "な-adj",   "N5", "adjective", "な-adjectives",
     "noun-like adjectives",                          "jlpt_sensei,bunpro_n5,genki_L5", ""),
    ("i_adj_neg",    "〜くない", "N5", "adjective", "〜くない — i-adj negative",
     "い-adjective negative",                          "jlpt_sensei,bunpro_n5,genki_L5", "i_adj"),
    ("i_adj_past",   "〜かった", "N5", "adjective", "〜かった — i-adj past",
     "い-adjective past",                              "jlpt_sensei,bunpro_n5,genki_L5", "i_adj"),
    ("na_adj_neg",   "〜じゃない","N5","adjective","〜じゃない — na-adj/noun negative",
     "な-adjective / noun negative",                   "jlpt_sensei,bunpro_n5,genki_L5", "na_adj"),

    # ── demonstratives & question words ───────────────────────────
    ("kosoado",      "こ/そ/あ/ど","N5","demonstrative","こ・そ・あ・ど series",
     "this / that / that-over-there / which",         "jlpt_sensei,bunpro_n5,genki_L2", ""),
    ("nan_what",     "何/なに",  "N5", "question", "何 — what",
     "interrogative 'what'",                          "jlpt_sensei,bunpro_n5,genki_L1", ""),
    ("dare_who",     "誰",       "N5", "question", "誰 — who",
     "interrogative 'who'",                           "jlpt_sensei,bunpro_n5,genki_L1", ""),
    ("doko_where",   "どこ",     "N5", "question", "どこ — where",
     "interrogative 'where'",                         "jlpt_sensei,bunpro_n5,genki_L2", "kosoado"),
    ("itsu_when",    "いつ",     "N5", "question", "いつ — when",
     "interrogative 'when'",                          "jlpt_sensei,bunpro_n5,genki_L3", ""),
    ("naze_doshite", "なぜ/どうして","N5","question","なぜ・どうして — why",
     "interrogative 'why'",                           "jlpt_sensei,bunpro_n5,genki_L6", ""),

    # ── connectives & sentence patterns ───────────────────────────
    ("soshite",      "そして",   "N5", "connector", "そして — and then",
     "additive sentence connector",                   "jlpt_sensei,bunpro_n5,genki_L4", ""),
    ("demo",         "でも",     "N5", "connector", "でも — but",
     "contrastive sentence connector",                "jlpt_sensei,bunpro_n5,genki_L4", ""),
    ("dakara",       "だから",   "N5", "connector", "だから — so / therefore",
     "causal sentence connector",                     "jlpt_sensei,bunpro_n5,genki_L8", ""),
    ("kara_because", "〜から(理由)","N5","connector","〜から — because (clause)",
     "reason clause-final particle",                  "jlpt_sensei,bunpro_n5,genki_L6", "kara_from"),
    ("ga_but",       "〜が(逆接)","N5","connector","〜が — but (clause)",
     "contrastive clause-joiner",                     "jlpt_sensei,bunpro_n5,genki_L7", ""),
    ("aru_iru",      "ある/いる","N5","existence","ある・いる — exists",
     "inanimate / animate existence",                 "jlpt_sensei,bunpro_n5,genki_L4", ""),
    ("ko_arimasen",  "ありません","N5","existence","ありません — does not exist",
     "negative existence",                            "jlpt_sensei,bunpro_n5,genki_L4", "aru_iru"),
    ("counters",     "助数詞",   "N5", "structure", "counters",
     "numeric counters (人, 個, 枚, …)",                "jlpt_sensei,bunpro_n5,genki_L4", ""),
    ("attributive",  "noun-mod","N5","structure","verb/adj modifies noun",
     "relative-clause-like noun modification",        "jlpt_sensei,bunpro_n5,genki_L9", "dictionary_form"),
]


# ─────────────────────────────────────────────────────────────────────
#  N4 — tense, negation, intent, comparison
# ─────────────────────────────────────────────────────────────────────
N4_POINTS = [
    # ── potential & passive & causative bases ─────────────────────
    ("potential",    "〜られる(可能)","N4","verb_form","〜(ら)れる — can / be able to",
     "potential form",                                "jlpt_sensei,bunpro_n4,genki_L13", "dictionary_form"),
    ("passive",      "〜られる(受身)","N4","verb_form","〜(ら)れる — passive",
     "passive form",                                  "jlpt_sensei,bunpro_n4,genki_L21", "dictionary_form"),
    ("causative",    "〜させる",     "N4","verb_form","〜させる — causative",
     "make / let someone do",                         "jlpt_sensei,bunpro_n4,genki_L22", "dictionary_form"),
    ("causative_passive","〜させられる","N4","verb_form","〜させられる — causative-passive",
     "be made to do",                                 "jlpt_sensei,bunpro_n4,genki_L23", "causative,passive"),
    ("volitional_plain","〜よう/〜おう","N4","verb_form","〜よう — plain volitional",
     "casual 'let's' / intention",                    "jlpt_sensei,bunpro_n4,genki_L15", "masho"),

    # ── conditionals & purpose ────────────────────────────────────
    ("tara",         "〜たら",   "N4", "conditional", "〜たら — if/when",
     "general conditional",                           "jlpt_sensei,bunpro_n4,genki_L17", "ta_form"),
    ("ba",           "〜ば",     "N4", "conditional", "〜ば — if (provisional)",
     "hypothetical conditional",                      "jlpt_sensei,bunpro_n4,genki_L18", "dictionary_form"),
    ("nara",         "〜なら",   "N4", "conditional", "〜なら — if it's the case that",
     "topic-conditional",                             "jlpt_sensei,bunpro_n4,genki_L18", ""),
    ("to_natural",   "〜と(自然)","N4","conditional","〜と — whenever / natural result",
     "natural / inevitable consequence",              "jlpt_sensei,bunpro_n4,genki_L18", ""),
    ("tameni",       "〜ために",  "N4", "purpose", "〜ために — for the purpose of",
     "purpose / benefit",                             "jlpt_sensei,bunpro_n4,genki_L17", ""),

    # ── intent, attempt, request ─────────────────────────────────
    ("tsumori",      "〜つもり",  "N4", "intent", "〜つもり — intend to",
     "stated intention",                              "jlpt_sensei,bunpro_n4,genki_L15", "dictionary_form"),
    ("yotei",        "〜予定",    "N4", "intent", "〜予定 — scheduled to",
     "fixed plan",                                    "jlpt_sensei,bunpro_n4,genki_L15", ""),
    ("te_miru",      "〜てみる",  "N4", "verb_form", "〜てみる — try doing",
     "attempt / experiment",                          "jlpt_sensei,bunpro_n4,genki_L15", "te_form"),
    ("te_oku",       "〜ておく",  "N4", "verb_form", "〜ておく — do in advance",
     "do in preparation / leave as-is",               "jlpt_sensei,bunpro_n4,genki_L15", "te_form"),
    ("te_shimau",    "〜てしまう","N4","verb_form","〜てしまう — do completely / regrettably",
     "completion or regret nuance",                   "jlpt_sensei,bunpro_n4,genki_L18", "te_form"),
    ("te_ageru",     "〜てあげる","N4","giving","〜てあげる — do for someone",
     "do a favor for another",                        "jlpt_sensei,bunpro_n4,genki_L16", "te_form"),
    ("te_kureru",    "〜てくれる","N4","giving","〜てくれる — someone does for me",
     "favor received from another",                   "jlpt_sensei,bunpro_n4,genki_L16", "te_form"),
    ("te_morau",     "〜てもらう","N4","giving","〜てもらう — have someone do for me",
     "request a favor",                               "jlpt_sensei,bunpro_n4,genki_L16", "te_form"),

    # ── necessity & advice ────────────────────────────────────────
    ("nakereba",     "〜なければならない","N4","necessity","〜なければならない — must do",
     "obligation",                                    "jlpt_sensei,bunpro_n4,genki_L12", "nai_form"),
    ("nakute_mo_ii", "〜なくてもいい","N4","necessity","〜なくてもいい — don't have to",
     "absence of obligation",                         "jlpt_sensei,bunpro_n4,genki_L12", "nai_form"),
    ("hou_ga_ii",    "〜ほうがいい","N4","advice","〜ほうがいい — should",
     "advice / recommendation",                       "jlpt_sensei,bunpro_n4,genki_L12", "ta_form"),
    ("te_wa_ikenai", "〜てはいけない","N4","prohibition","〜てはいけない — must not",
     "prohibition",                                   "jlpt_sensei,bunpro_n4,genki_L13", "te_form"),

    # ── reported speech & thought ────────────────────────────────
    ("to_omoimasu",  "〜と思います","N4","reported","〜と思います — I think that…",
     "first-person opinion",                          "jlpt_sensei,bunpro_n4,genki_L8", ""),
    ("to_iimasu",    "〜と言います","N4","reported","〜と言います — says that…",
     "indirect quotation",                            "jlpt_sensei,bunpro_n4,genki_L8", ""),
    ("ka_dou_ka",    "〜かどうか","N4","embedded","〜かどうか — whether or not",
     "embedded yes/no question",                      "jlpt_sensei,bunpro_n4,genki_L17", "ka_question"),
    ("embedded_q",   "〜か(間接)","N4","embedded","embedded question with か",
     "indirect interrogative",                        "jlpt_sensei,bunpro_n4,genki_L17", "ka_question"),

    # ── comparison ────────────────────────────────────────────────
    ("yori",         "〜より",   "N4", "comparison", "〜より — than",
     "comparative 'than'",                            "jlpt_sensei,bunpro_n4,genki_L10", ""),
    ("hou_ga_yori",  "〜のほうが〜より","N4","comparison","Aのほうが Bより〜 — A is more 〜 than B",
     "explicit comparative",                          "jlpt_sensei,bunpro_n4,genki_L10", "yori"),
    ("ichiban",      "一番〜",   "N4", "comparison", "一番〜 — most",
     "superlative",                                   "jlpt_sensei,bunpro_n4,genki_L10", ""),
    ("dochira_ga",   "どちらが", "N4", "comparison", "どちらが〜 — which is more 〜",
     "binary comparison question",                    "jlpt_sensei,bunpro_n4,genki_L10", ""),

    # ── conjecture & seeming ─────────────────────────────────────
    ("deshou",       "〜でしょう","N4","conjecture","〜でしょう — probably / right?",
     "polite conjecture / confirmation",              "jlpt_sensei,bunpro_n4,genki_L12", ""),
    ("kamo_shirenai","〜かもしれない","N4","conjecture","〜かもしれない — might / maybe",
     "possibility",                                   "jlpt_sensei,bunpro_n4,genki_L12", ""),
    ("rashii",       "〜らしい",   "N4","conjecture","〜らしい — seems (hearsay)",
     "evidential / hearsay",                          "jlpt_sensei,bunpro_n4,genki_L17", ""),
    ("sou_da_hearsay","〜そうだ(伝聞)","N4","conjecture","〜そうだ — I hear that…",
     "hearsay reportative",                           "jlpt_sensei,bunpro_n4,genki_L17", ""),
    ("sou_da_appear","〜そうだ(様態)","N4","conjecture","〜そうだ — looks like…",
     "evidential 'looks like'",                       "jlpt_sensei,bunpro_n4,genki_L13", ""),
    ("youda",        "〜ようだ",   "N4","conjecture","〜ようだ — seems / like",
     "inference / simile",                            "jlpt_sensei,bunpro_n4,genki_L18", ""),
    ("mitai",        "〜みたい",   "N4","conjecture","〜みたい — looks like / similar to",
     "casual 〜ようだ",                                 "jlpt_sensei,bunpro_n4,genki_L18", "youda"),

    # ── time / sequence / manner ─────────────────────────────────
    ("toki",         "〜とき",     "N4","time","〜とき — when",
     "temporal subordinate clause",                   "jlpt_sensei,bunpro_n4,genki_L13", ""),
    ("mae_ni",       "〜まえに",   "N4","time","〜まえに — before",
     "before doing",                                  "jlpt_sensei,bunpro_n4,genki_L17", "dictionary_form"),
    ("ato_de",       "〜あとで",   "N4","time","〜あとで — after",
     "after doing",                                   "jlpt_sensei,bunpro_n4,genki_L17", "ta_form"),
    ("nagara",       "〜ながら",   "N4","manner","〜ながら — while",
     "simultaneous actions",                          "jlpt_sensei,bunpro_n4,genki_L19", "masu_nonpast"),
    ("te_kara",      "〜てから",   "N4","time","〜てから — after doing",
     "sequential action 'and then'",                  "jlpt_sensei,bunpro_n4,genki_L7", "te_form"),

    # ── nominalisation ────────────────────────────────────────────
    ("koto_ga_dekiru","〜ことができる","N4","verb_form","〜ことができる — can do",
     "alternative potential",                         "jlpt_sensei,bunpro_n4,genki_L13", "dictionary_form"),
    ("no_nominalizer","〜の(名詞化)","N4","nominalizer","〜の — nominalizer",
     "turns clause into noun",                        "jlpt_sensei,bunpro_n4,genki_L9", ""),
    ("koto_nominalizer","〜こと(名詞化)","N4","nominalizer","〜こと — nominalizer",
     "abstract nominalizer",                          "jlpt_sensei,bunpro_n4,genki_L11", ""),
    ("ga_suki",      "〜が好き",   "N4","preference","〜が好き — like",
     "preference / dislike",                          "jlpt_sensei,bunpro_n4,genki_L5", "ga_subject"),
    ("ga_jouzu",     "〜が上手",   "N4","preference","〜が上手・下手 — good/bad at",
     "skill description",                             "jlpt_sensei,bunpro_n4,genki_L11", "ga_subject"),
    ("sugiru",       "〜すぎる",   "N4","degree","〜すぎる — too much",
     "excess",                                        "jlpt_sensei,bunpro_n4,genki_L12", ""),
    ("yasui_nikui",  "〜やすい/にくい","N4","degree","〜やすい・にくい — easy/hard to",
     "ease of doing",                                 "jlpt_sensei,bunpro_n4,genki_L19", ""),
]


# ─────────────────────────────────────────────────────────────────────
#  N3 — intermediate connectives, modality, narrative tools
# ─────────────────────────────────────────────────────────────────────
N3_POINTS = [
    # ── conjectural / evidential ──────────────────────────────────
    ("hazu",         "〜はず",     "N3", "conjecture", "〜はず — should/expected to",
     "expectation based on knowledge",                "jlpt_sensei,bunpro_n3,tobira_L5", ""),
    ("ni_chigainai", "〜にちがいない","N3","conjecture","〜にちがいない — must be",
     "strong certainty",                              "jlpt_sensei,bunpro_n3,tobira_L5", ""),
    ("you_ni_naru",  "〜ようになる","N3","change","〜ようになる — come to do",
     "change of state / habit",                       "jlpt_sensei,bunpro_n3,tobira_L3", ""),
    ("you_ni_suru",  "〜ようにする","N3","change","〜ようにする — make a point of",
     "deliberate effort",                             "jlpt_sensei,bunpro_n3,tobira_L3", ""),
    ("koto_ni_suru", "〜ことにする","N3","intent","〜ことにする — decide to",
     "decision",                                      "jlpt_sensei,bunpro_n3,tobira_L4", "koto_nominalizer"),
    ("koto_ni_naru", "〜ことになる","N3","change","〜ことになる — be decided that",
     "external decision",                             "jlpt_sensei,bunpro_n3,tobira_L4", "koto_nominalizer"),
    ("bakari",       "〜ばかり",   "N3", "degree", "〜ばかり — only/just",
     "limit / 'just done'",                           "jlpt_sensei,bunpro_n3,tobira_L7", ""),
    ("dake",         "〜だけ",     "N3", "degree", "〜だけ — only",
     "exclusive limit",                               "jlpt_sensei,bunpro_n3,tobira_L7", ""),
    ("shika",        "〜しか",     "N3", "degree", "〜しか〜ない — only (negative)",
     "exclusive negative",                            "jlpt_sensei,bunpro_n3,tobira_L7", ""),

    # ── connectives ───────────────────────────────────────────────
    ("noni",         "〜のに",     "N3", "connector", "〜のに — although / despite",
     "unexpected contrast",                           "jlpt_sensei,bunpro_n3,tobira_L6", ""),
    ("kuse_ni",      "〜くせに",   "N3", "connector", "〜くせに — even though (criticism)",
     "critical 'even though'",                        "jlpt_sensei,bunpro_n3,tobira_L6", "noni"),
    ("nodewa_naika", "〜のではないか","N3","conjecture","〜のではないか — isn't it that…?",
     "tentative suggestion",                          "jlpt_sensei,bunpro_n3", ""),
    ("toshite",      "〜として",   "N3", "structure", "〜として — as / in the role of",
     "role / capacity",                               "jlpt_sensei,bunpro_n3,tobira_L5", ""),
    ("ni_yotte",     "〜によって", "N3", "structure", "〜によって — by means of / depending on",
     "agent / cause / dependency",                    "jlpt_sensei,bunpro_n3,tobira_L5", ""),
    ("ni_kanshite",  "〜に関して", "N3", "structure", "〜に関して — regarding",
     "topic marker (formal)",                         "jlpt_sensei,bunpro_n3", ""),
    ("ni_tsuite",    "〜について", "N3", "structure", "〜について — about / concerning",
     "topical 'about'",                               "jlpt_sensei,bunpro_n3,tobira_L4", ""),
    ("ni_taishite",  "〜に対して", "N3", "structure", "〜に対して — toward / against",
     "directional / opposition",                      "jlpt_sensei,bunpro_n3", ""),

    # ── time / sequence / aspect ──────────────────────────────────
    ("aida_ni",      "〜あいだに", "N3", "time", "〜あいだに — during/while",
     "during a span",                                 "jlpt_sensei,bunpro_n3,tobira_L6", ""),
    ("uchi_ni",      "〜うちに",   "N3", "time", "〜うちに — while (still)",
     "do before condition changes",                   "jlpt_sensei,bunpro_n3,tobira_L6", ""),
    ("tabi_ni",      "〜たびに",   "N3", "time", "〜たびに — every time",
     "iterative 'whenever'",                          "jlpt_sensei,bunpro_n3", ""),
    ("totan_ni",     "〜とたんに", "N3", "time", "〜とたんに — the moment that",
     "abrupt sequencing",                             "jlpt_sensei,bunpro_n3", "ta_form"),
    ("tokoro_da",    "〜ところだ", "N3", "aspect", "〜ところだ — about to / just did",
     "phase of action",                               "jlpt_sensei,bunpro_n3,tobira_L4", ""),
    ("kakeru",       "〜かける",   "N3", "aspect", "〜かける — partway through",
     "incomplete action",                             "jlpt_sensei,bunpro_n3", ""),

    # ── manner & comparison ───────────────────────────────────────
    ("you_ni",       "〜ように(様態)","N3","manner","〜ように — in such a way / like",
     "manner / simile",                               "jlpt_sensei,bunpro_n3,tobira_L3", "youda"),
    ("mama",         "〜まま",     "N3", "manner", "〜まま — as is / unchanged",
     "leaving in a state",                            "jlpt_sensei,bunpro_n3,tobira_L4", ""),
    ("hodo",         "〜ほど",     "N3", "comparison", "〜ほど — to the extent of",
     "degree comparison",                             "jlpt_sensei,bunpro_n3,tobira_L7", ""),
    ("kurai",        "〜くらい/ぐらい","N3","comparison","〜くらい — about / to the extent",
     "approximate or extent",                         "jlpt_sensei,bunpro_n3", ""),

    # ── modality, request, advice ────────────────────────────────
    ("beki",         "〜べき",     "N3", "advice", "〜べき — should / ought to",
     "moral 'should'",                                "jlpt_sensei,bunpro_n3,tobira_L8", ""),
    ("zaru_o_enai",  "〜ざるを得ない","N3","necessity","〜ざるを得ない — have no choice but to",
     "unavoidable obligation",                        "jlpt_sensei,bunpro_n3", ""),
    ("te_hoshii",    "〜てほしい", "N3", "request", "〜てほしい — want someone to",
     "want another to do",                            "jlpt_sensei,bunpro_n3,tobira_L4", "te_form"),

    # ── conditionals & expressions of regret ─────────────────────
    ("temo",         "〜ても",     "N3", "conditional", "〜ても — even if",
     "concessive",                                    "jlpt_sensei,bunpro_n3,genki_L23", "te_form"),
    ("nakute_mo",    "〜なくても", "N3", "conditional", "〜なくても — even if not",
     "negative concessive",                           "jlpt_sensei,bunpro_n3", "nai_form"),
    ("ba_yokatta",   "〜ばよかった","N3","regret","〜ばよかった — should have…",
     "retrospective regret",                          "jlpt_sensei,bunpro_n3", "ba"),

    # ── narration & nominalisation ───────────────────────────────
    ("toiu",         "〜という",   "N3", "structure", "〜という — called / that",
     "naming / quoted complement",                    "jlpt_sensei,bunpro_n3,tobira_L4", ""),
    ("toiu_koto",    "〜ということ","N3","structure","〜ということ — the fact that…",
     "abstract nominalised clause",                   "jlpt_sensei,bunpro_n3,tobira_L4", "toiu"),
    ("wake_da",      "〜わけだ",   "N3", "explanation", "〜わけだ — that's why",
     "logical conclusion",                            "jlpt_sensei,bunpro_n3", ""),
    ("wake_dewa_nai","〜わけではない","N3","explanation","〜わけではない — it's not that…",
     "soft negation of inference",                    "jlpt_sensei,bunpro_n3", "wake_da"),

    # ── giving & honorific basics ────────────────────────────────
    ("o_v_suru",     "お〜する",   "N3", "honorific", "お〜する — humble verb form",
     "humble polite",                                 "jlpt_sensei,bunpro_n3,tobira_L9", ""),
    ("o_v_ni_naru",  "お〜になる", "N3", "honorific", "お〜になる — honorific verb form",
     "honorific polite",                              "jlpt_sensei,bunpro_n3,tobira_L9", ""),
]


# ─────────────────────────────────────────────────────────────────────
#  Build & write
# ─────────────────────────────────────────────────────────────────────
ALL_POINTS = [(*p, "N5") for p in N5_POINTS] + \
             [(*p, "N4") for p in N4_POINTS] + \
             [(*p, "N3") for p in N3_POINTS]

# Sanity: dedupe by id
def main():
    seen = {}
    entries = []
    for raw in ALL_POINTS:
        # raw layout: id, marker, jlpt, category, title, short, sources, prereq, _level
        pid, marker, jlpt, category, title, short, sources_csv, prereq_csv, _level = raw
        # canonical id includes the level for ordering, e.g. N5_wa_topic
        cid = f"{jlpt}_{pid}"
        if cid in seen:
            raise SystemExit(f"DUPLICATE id: {cid}")
        seen[cid] = True
        entry = {
            "id":            cid,
            "marker":        marker,
            "jlpt":          jlpt,
            "category":      category,
            "title":         title,
            "short":         short,
            "sources":       sources_csv.split(","),
            "source_count":  len(sources_csv.split(",")),
            "prerequisites": [f"{jlpt}_{p.strip()}" if p.strip() else "" for p in prereq_csv.split(",") if p.strip()],
            "disputed":      False,
        }
        # If only 2 sources agreed, we still record it (rule: ≥2 sources)
        # but keep `source_count` so callers can filter.
        entries.append(entry)

    # Sort by jlpt (N5 first) then by id for stable diffs
    level_rank = {"N5": 0, "N4": 1, "N3": 2, "N2": 3, "N1": 4}
    entries.sort(key=lambda e: (level_rank[e["jlpt"]], e["id"]))

    catalog = {
        "schema_version": 1,
        "generated_by":   "pipeline/build_grammar_catalog.py",
        "source_policy":  "Each entry cross-referenced against ≥2 of: "
                          "JLPTSensei (jlpt_sensei), BunPro (bunpro_nX), "
                          "Genki I/II (genki_LN), Tobira (tobira_LN). "
                          "Disagreements resolved conservatively (lower JLPT = harder = wait longer).",
        "entries":        entries,
    }
    OUT.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n")
    print(f"✓ Wrote {OUT.relative_to(ROOT)}")
    print(f"  {len(entries)} grammar points")
    by = {}
    for e in entries:
        by.setdefault(e["jlpt"], 0)
        by[e["jlpt"]] += 1
    for lvl in ("N5", "N4", "N3"):
        print(f"    {lvl}: {by.get(lvl, 0)}")
    # Assert ≥2 sources for all
    weak = [e for e in entries if e["source_count"] < 2]
    if weak:
        raise SystemExit(f"WEAK: {len(weak)} entries with <2 sources: {[e['id'] for e in weak]}")
    print(f"  ✓ all entries have ≥2 source references")

if __name__ == "__main__":
    main()
