#!/usr/bin/env python3
"""
Semantic-sanity lint and motif-rotation checks for the graded reader.

Added 2026-04-22 as a direct response to a library audit that found the
mechanical validators (closed vocab, closed grammar, length, reuse-quota)
were happily letting through sentences that were nonsense at the level of
meaning, and were happily letting authors write the same window-and-rain
story five times in a row.

These checks are deliberately CONSERVATIVE — they only fire on patterns
we have direct evidence cause real defects in shipped stories. Authors
should never have to fight these rules; if a check here is firing on
otherwise-good prose, the rule itself is too greedy and should be
loosened, not the prose tortured to satisfy it.

Public entry points
-------------------
    semantic_sanity_lint(story, vocab) -> list[Issue]   # Check 11
    motif_rotation_lint(story, prior_stories) -> list[Issue]   # Check 12

Both return a list of `Issue` objects (`severity`, `message`,
`location`). validate.py decides whether each issue is "error" or
"warning"; this module does not import from validate.py to keep the
dependency graph clean.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


# ── Issue type ────────────────────────────────────────────────────────────────

@dataclass
class Issue:
    severity: str       # "error" | "warning"
    message: str
    location: str = ""


# ── Rule tables ───────────────────────────────────────────────────────────────

# Words that lack the faculty for being "quiet" (静か). The audit caught
# `本は静かです` ("the book is quiet") as the canonical nonsense; the rule
# fires only on objects that *cannot* be poetically described as 静か in JP.
#
# IMPORTANT: this list deliberately EXCLUDES nouns that DO take 静か in
# natural Japanese — celestial things (月・星・空), nature (木・花), and
# weather (風・雨) all routinely appear as `Nは静かです` in JP poetry and
# prose. A 静か moon is a stock image, not nonsense. Be very conservative
# here; over-reach causes the rule to flag good prose, which trains
# authors to ignore the rule entirely. The compass: if a JP native
# speaker would write the sentence in a published book, the rule must
# not fire.
INANIMATE_QUIET_NOUN_IDS: frozenset[str] = frozenset({
    # Hand-held / on-the-table objects: cannot meaningfully be 静か in JP.
    # The audit's canonical defects were `本は静かです` and `手紙は静かです`.
    "W00033",   # 本     (book)        — story 8 / story 9 audit defect
    "W00039",   # 手紙   (letter)      — story 10 audit defect
    "W00021",   # 卵     (egg)
    "W00019",   # 朝ごはん (breakfast)
    "W00009",   # お茶   (tea)
    # Furniture: a chair/desk is silent in the trivial sense that it
    # doesn't make noise, but `椅子は静かです` reads as a tautology /
    # nonsense in JP — natives describe the *room/place around* the
    # furniture as 静か, not the furniture itself.
    "W00036",   # 椅子   (chair)
    "W00037",   # 机     (desk)
    # NOTE: 木 (W00007), 花 (W00024), 月 (W00031), 星 (W00032), 空 (W00047),
    # 風 (W00027), 雨 (W00002), 夜 (W00030), 朝 (W00015), 夕方 (W00018),
    # 公園 (W00016) are NOT on this list — they all naturally take 静か
    # in JP poetry and prose (静かな夕方, 静かな公園 etc are stock JP).
    # Be very conservative when adding to this list.
    #
    # FIXED 2026-04-22 (v0.14): the original list mistakenly contained
    # W00018 with the comment "卵 (egg)" — but W00018 is actually 夕方
    # (evening). The id-vs-comment mismatch caused the rule to fire on
    # the perfectly natural sentence `夕方は静かです` (the evening is
    # quiet) during the closer-rotation audit. The real "egg" id W00021
    # has now been substituted in.
})

# Verbs of consumption — used by the "tomorrow's-X-eaten-today" check.
CONSUMPTION_VERB_IDS: frozenset[str] = frozenset({
    "W00010",   # 飲む  (drink)
    "W00020",   # 食べる (eat)
})

# Time/weather facts a narrator ALREADY KNOWS. If a sentence wraps one of
# these in `~と思います` it's almost certainly the audit's "I think it is
# night" defect (story 12 s7) — the speaker is already in the night.
SELF_KNOWN_FACT_NOUN_IDS: frozenset[str] = frozenset({
    # FIXED 2026-04-22 (v0.14): same id-vs-comment mismatch class of bug
    # as INANIMATE_QUIET_NOUN_IDS above. The original list had:
    #   "W00021" commented as "今朝" — actually 卵 (egg)
    #   "W00037" commented as "昨日" — actually 机 (desk)
    #   "W00045" commented as "夕方" — actually そば (side, nearby)
    # The right ids are W00001 (今朝), W00042 (昨日), W00018 (夕方); they
    # have been substituted in. The bug had no observable false-positive
    # impact (none of the wrong ids ever appeared with と思います) but
    # it would have started misfiring as soon as a story tried to write
    # `卵だと思います` etc, which is perfectly fine JP.
    "W00015",   # 朝     (morning)
    "W00030",   # 夜     (night)
    "W00001",   # 今朝   (this morning)
    "W00018",   # 夕方   (evening)
    "W00042",   # 昨日   (yesterday)
    "W00046",   # 明日   (tomorrow)
    "W00002",   # 雨     (rain)
    "W00027",   # 風     (wind)
})

# Grammar IDs we recognise.
GRAMMAR_TO_OMOIMASU = "G014_to_omoimasu"
GRAMMAR_TE_OKU      = "G019_te_oku"
GRAMMAR_NO          = "G015_no_possessive"
GRAMMAR_WA          = "G001_wa_topic"
GRAMMAR_DESU        = "G003_desu"
GRAMMAR_MO          = "G009_mo_also"


# ── Check 11: Semantic-sanity lint ────────────────────────────────────────────

def semantic_sanity_lint(story: dict, vocab: dict | None = None) -> list[Issue]:
    """Run a small battery of conservative semantic-sanity checks.

    Each rule is documented inline. Rules return Issue("error", ...) when
    the JP text reads as nonsense to a native speaker; the rule does not
    fire on the borderline cases.
    """
    issues: list[Issue] = []
    sentences = story.get("sentences", []) or []

    # Set of word_ids that appear in title (so a "motif must be
    # established earlier" check correctly counts the title as established
    # context).
    title_wids: set[str] = set()
    for sec in ("title",):
        sec_obj = story.get(sec) or {}
        for tok in sec_obj.get("tokens", []):
            wid = tok.get("word_id")
            if wid:
                title_wids.add(wid)

    # Build per-sentence content/grammar projections for cheap pattern matching.
    sentence_views: list[dict] = []
    for sent in sentences:
        toks = sent.get("tokens", []) or []
        sentence_views.append({
            "idx": sent.get("idx"),
            "tokens": toks,
            "wids": [t.get("word_id") for t in toks if t.get("word_id")],
            "gids": _all_grammar_ids(toks),
            "surfaces": [t.get("t", "") for t in toks],
            "gloss": sent.get("gloss_en", "") or "",
        })

    # ─ Rule 11.1: inanimate-thing-is-quiet ───────────────────────────────────
    # Pattern: token sequence contains  X(content,is_inanimate)  +  は  +
    # 静か  +  です   anywhere within the same sentence (allow particles in
    # between to cope with topic-marking variations).
    for view in sentence_views:
        toks = view["tokens"]
        for i, tok in enumerate(toks):
            wid = tok.get("word_id")
            if wid not in INANIMATE_QUIET_NOUN_IDS:
                continue
            # Look ahead for は / も / の followed (eventually) by 静か です
            tail = toks[i + 1 : i + 6]
            joined = "".join(t.get("t", "") for t in tail)
            if (
                ("は" in joined or "も" in joined)
                and "静か" in joined
                and ("です" in joined or "だ" in joined)
            ):
                surface = "".join(t.get("t", "") for t in toks)
                issues.append(Issue(
                    severity="error",
                    message=(
                        f"Inanimate '{tok.get('t')}' described as 静か. Objects "
                        f"(books, letters, eggs, doors, the moon, etc.) lack the "
                        f"faculty for silence in Japanese. Anchor 静か to a "
                        f"person, a room, a place, the weather, or an animal "
                        f"instead. (Sentence: 「{surface}」)"
                    ),
                    location=f"sentence {view['idx']}",
                ))

    # ─ Rule 11.2: tomorrow's-X-consumed-today ─────────────────────────────────
    # Pattern (NARROW): 明日 immediately followed by の + (food/drink noun) +
    # …consumption verb…  AND not inside 〜ておく.
    #
    # The narrow form (明日のN) is the actual nonsense — eating tomorrow's
    # specific food today. The broad form (明日もN) means "tomorrow as well
    # I will do X" which is a perfectly natural future-tense statement and
    # MUST NOT trip this rule. The 2026-04-22 audit's bad sentence was
    # `明日の朝ごはんも食べます` (the の form). The fixed version
    # `明日も朝ごはんを食べます` (the も form) is fine.
    for view in sentence_views:
        toks = view["tokens"]
        # Find 明日 followed by の (with no intervening tokens of role 'content').
        ashita_no = False
        for i, t in enumerate(toks):
            if t.get("word_id") != "W00046":   # 明日
                continue
            nxt = toks[i + 1] if i + 1 < len(toks) else None
            if nxt and nxt.get("t") == "の" and nxt.get("grammar_id") == GRAMMAR_NO:
                ashita_no = True
                break
        if not ashita_no:
            continue
        if GRAMMAR_TE_OKU in view["gids"]:
            continue
        for tok in toks:
            wid = tok.get("word_id")
            if wid not in CONSUMPTION_VERB_IDS:
                continue
            inf = tok.get("inflection") or {}
            form = inf.get("form", "")
            if form in ("polite_past", "plain_past", "te"):
                continue
            surface = "".join(t.get("t", "") for t in toks)
            issues.append(Issue(
                severity="error",
                message=(
                    f"Future-of-future tense: 「明日のN」 + a non-past consumption "
                    f"verb. You cannot eat or drink tomorrow's specific food today; "
                    f"the sentence is logically broken. Either change 「明日の」 to "
                    f"「明日も」 (= 'tomorrow as well, I will…'), shift to 〜ておく "
                    f"('I'll go ahead and have some now'), or move the action to a "
                    f"future scene. (Sentence: 「{surface}」)"
                ),
                location=f"sentence {view['idx']}",
            ))
            break

    # ─ Rule 11.3: ~と思います for self-known time/weather ────────────────────
    # Pattern: a sentence uses 〜と思います AND the と-clause embeds a noun
    # (夜 / 朝 / 今朝 / 雨 / 風 / 明日 etc.) that is ALREADY asserted as a
    # FACT elsewhere in the same story. と思います is for inferences and
    # opinions; using it for the speaker's own setting is the "I think it
    # is night" defect from story 12.
    self_known_facts: set[str] = set()
    for view in sentence_views:
        if GRAMMAR_TO_OMOIMASU in view["gids"]:
            continue   # don't count the 〜と思います clause itself
        # Heuristic: if a noun appears in this sentence AND the sentence
        # ends with です/だ (i.e. it's an assertion, not a question), treat
        # the noun as a self-known fact.
        ends_assert = False
        for t in reversed(view["tokens"]):
            if t.get("role") == "punct":
                continue
            if t.get("t") in ("です", "だ", "ます"):
                ends_assert = True
            break
        if not ends_assert:
            continue
        for wid in view["wids"]:
            if wid in SELF_KNOWN_FACT_NOUN_IDS:
                self_known_facts.add(wid)

    for view in sentence_views:
        if GRAMMAR_TO_OMOIMASU not in view["gids"]:
            continue
        toks = view["tokens"]
        cut = next(
            (
                i for i, t in enumerate(toks)
                if t.get("grammar_id") == GRAMMAR_TO_OMOIMASU
            ),
            None,
        )
        if cut is None:
            continue
        embedded = toks[:cut]
        # NARROW: rule fires only if the embedded clause is a *bare* assertion
        # of the self-known noun — i.e. it consists of essentially just
        # `<known-fact-noun> + だ/です` with no other content tokens. The
        # canonical defect is `夜だと思います` ("I think it is night") spoken
        # at night. The benign case is `風の朝だと思います` ("I think it's a
        # windy morning") — the embedded clause carries new descriptive
        # content (modifier + noun + copula), not just a bare time-of-day
        # restatement.
        embedded_content = [t for t in embedded
                            if t.get("role") == "content" and t.get("word_id")]
        if len(embedded_content) > 1:
            continue   # has more than just the known-fact noun → not nonsense
        for t in embedded_content:
            wid = t.get("word_id")
            if wid in SELF_KNOWN_FACT_NOUN_IDS and wid in self_known_facts:
                surface = "".join(tt.get("t", "") for tt in toks)
                issues.append(Issue(
                    severity="error",
                    message=(
                        f"〜と思います embeds the bare known-fact noun "
                        f"'{t.get('t')}', which the story has already asserted "
                        f"as a present-tense fact elsewhere. と思います is for "
                        f"inference, opinion, or guess — not for hedging facts "
                        f"the narrator already knows. Use a plain assertion or "
                        f"add descriptive content (e.g. an adjective + noun) "
                        f"to make the embedded clause an actual evaluation. "
                        f"(Sentence: 「{surface}」)"
                    ),
                    location=f"sentence {view['idx']}",
                ))
                break

    # ─ Rule 11.4: word_id ↔ surface lemma mismatch ────────────────────────────
    # If a token has an inflection.base that doesn't begin with the surface
    # form's first kanji/kana of the lemma the word_id resolves to, it's
    # likely a smuggled-in word (the audit caught this with 行きます tagged
    # word_id W00047 = 空/sora). We don't have a kanji-equivalence map at
    # validation time, but we can catch the gross case: the word_id resolves
    # to a noun but the inflection claims a verb form.
    if vocab and isinstance(vocab.get("words"), dict):
        words_dict = vocab["words"]
        VERB_FORMS = {
            "polite_nonpast", "polite_past", "plain_nonpast", "plain_past",
            "te", "nai", "masu", "tai", "potential", "passive", "causative",
        }
        for view in sentence_views:
            for tok in view["tokens"]:
                inf = tok.get("inflection") or {}
                form = inf.get("form")
                wid  = tok.get("word_id")
                if not (form in VERB_FORMS and wid):
                    continue
                w = words_dict.get(wid)
                if not w:
                    continue
                pos = (w.get("pos") or "").lower()
                if pos and pos in ("noun", "particle", "adjective_na",
                                   "adjective_i", "adverb"):
                    issues.append(Issue(
                        severity="error",
                        message=(
                            f"word_id '{wid}' resolves to a {pos} "
                            f"('{w.get('lemma') or w.get('surface') or '?'}') "
                            f"but the token claims a verb inflection "
                            f"(form='{form}'). You cannot reuse a noun's "
                            f"word_id to smuggle in a verb that isn't in "
                            f"vocab. Restructure with an existing verb, or "
                            f"add the verb the right way (planner.py / "
                            f"lookup.py)."
                        ),
                        location=f"sentence {view['idx']}",
                    ))

    # ─ Rule 11.6: location-を with a noun list joined by と ───────────────────
    # Pattern: a verb of motion that takes location-を (歩く, 走る, 飛ぶ — in
    # this library: 歩きます W00017) is preceded by `Nと N(と N…)を`. The
    # を particle here is *only* legal as a location marker; the noun
    # immediately before を must be a place. と-coordinated lists like
    # `雨と夕方と公園` mix non-traversable items (rain, evening) with the
    # actual place (the park), turning the sentence into "we walk through
    # rain, evening, the park" — confused at best, beginner-grammar broken
    # at worst. The 2026-04-22 closer-rotation audit caught
    # `雨と夕方と公園を歩きます` (story 2 s6).
    #
    # The rule fires only on the strict shape `Aと B(…と)を MOTION-VERB`
    # AND only when at least one of the と-coordinated nouns is not a
    # traversable place (i.e. not in TRAVERSABLE_PLACE_IDS). It is
    # CONSERVATIVE: `公園と外を歩きます` (we walk in the park and outside)
    # is fine because both nouns are places.
    MOTION_VERB_LOCATION_WO_IDS: frozenset[str] = frozenset({
        "W00017",   # 歩く  (walk)
    })
    TRAVERSABLE_PLACE_IDS: frozenset[str] = frozenset({
        "W00016",   # 公園  (park)
        "W00005",   # 外    (outside)
    })
    # Animate nouns can take companion-と (`友達と公園を歩きます` = "I walk
    # in the park WITH a friend"). The と binds only the animate noun and
    # is NOT part of a list-と coordination, even though the surface looks
    # identical. Excluding these from the list-noun collection avoids
    # false-positive errors on perfectly natural sentences. Story 4 s0
    # was the canonical false-positive that surfaced this distinction.
    COMPANION_TO_ANIMATE_IDS: frozenset[str] = frozenset({
        "W00003",   # 私    (I)
        "W00022",   # 友達  (friend)
        "W00028",   # 猫    (cat)
        "W00035",   # 二人  (the two of us — group of people)
    })
    for view in sentence_views:
        toks = view["tokens"]
        for i, tok in enumerate(toks):
            if tok.get("word_id") not in MOTION_VERB_LOCATION_WO_IDS:
                continue
            # Walk backwards from the verb collecting the noun(s) attached
            # to this verb's を-clause. Stop at sentence start, at a
            # punctuation token, or at any non-content/non-particle token
            # other than と / を / の.
            list_nouns: list[dict] = []
            saw_wo = False
            j = i - 1
            while j >= 0:
                t = toks[j]
                role = t.get("role")
                surface = t.get("t", "")
                if role == "punct":
                    break
                if role == "particle":
                    if surface == "を":
                        saw_wo = True
                    elif surface == "と" and saw_wo:
                        # と after we've seen を means we're now collecting
                        # a noun list to the left. Continue.
                        pass
                    elif surface in ("、",):
                        break
                    elif surface in ("は", "が", "に", "で", "から"):
                        # These reset the clause boundary for our purposes.
                        break
                    elif surface == "の":
                        # Possessive の inside a noun phrase — keep going
                        # but don't add it to list_nouns.
                        pass
                    j -= 1
                    continue
                if role == "content" and t.get("word_id") and saw_wo:
                    # Companion-と: an animate noun followed by と (and no
                    # を of its own) is a companion adverbial, not a list
                    # entry. Stop the leftward walk here so we don't claim
                    # the animate noun is part of the location list.
                    if t.get("word_id") in COMPANION_TO_ANIMATE_IDS:
                        # Check that the immediately following token is と
                        # (companion case). If it is, this animate noun
                        # is *not* part of the location-を list — stop
                        # the walk entirely (everything to the left is
                        # also outside the は/を clause).
                        nxt = toks[j + 1] if j + 1 < len(toks) else None
                        if nxt and nxt.get("t") == "と" and nxt.get("role") == "particle":
                            break
                    list_nouns.append(t)
                    j -= 1
                    continue
                # Anything else (aux, adj, …) ends the clause.
                break
            # We need at least 2 nouns and at least one と between them in
            # surface order to call this a "list". Surface check is easier
            # than rebuilding from collected tokens: just look at the slice
            # between the leftmost noun and を for at least one と.
            if len(list_nouns) < 2 or not saw_wo:
                continue
            # Reconstruct token order for the slice we just walked.
            leftmost = min(toks.index(n) for n in list_nouns)
            wo_idx = next(
                k for k in range(leftmost, i)
                if toks[k].get("t") == "を" and toks[k].get("role") == "particle"
            )
            slice_surfaces = [t.get("t", "") for t in toks[leftmost:wo_idx]]
            if "と" not in slice_surfaces:
                continue
            # Now: at least one of the list_nouns must be NOT a traversable
            # place for the rule to fire (otherwise it's a clean "park and
            # outside" coordination, which is fine).
            offending = [
                n for n in list_nouns
                if n.get("word_id") not in TRAVERSABLE_PLACE_IDS
            ]
            if not offending:
                continue
            surface = "".join(t.get("t", "") for t in toks)
            offending_surfaces = "、".join(n.get("t", "") for n in offending)
            issues.append(Issue(
                severity="error",
                message=(
                    f"Verb of motion '{tok.get('t')}' takes location-を, but "
                    f"the を-clause coordinates non-traversable noun(s) "
                    f"({offending_surfaces}) with the place via と. You can "
                    f"walk *through a place*, not through `rain と evening と "
                    f"a park`. Put the non-place nouns in their own clause "
                    f"(e.g. as a backdrop with の, or as a separate sentence) "
                    f"and keep only the actual place before を. "
                    f"(Sentence: 「{surface}」)"
                ),
                location=f"sentence {view['idx']}",
            ))
            break

    # ─ Rule 11.5: lonely scene noun ──────────────────────────────────────────
    # Pattern: a scene-setting noun (rain, wind, moon, star, sky, …) appears
    # in exactly ONE sentence of the story AND is not in title.
    # The original audit case was story 7's `月も雨を見ます` — 雨 was used
    # in exactly one sentence of a stars-and-moon story that never set up
    # rain anywhere else. A noun that genuinely matters to the scene gets
    # echoed at least twice (or appears in the title); a noun that doesn't
    # is decoration and should be cut. Warning, not error — there are
    # legitimate uses (e.g. a closing image), but the warning surfaces the
    # decision to the engagement reviewer.
    SCENE_NOUNS: frozenset[str] = frozenset({
        "W00002",  # 雨
        "W00027",  # 風
        "W00031",  # 月
        "W00032",  # 星
        "W00047",  # 空
    })
    from collections import Counter
    scene_counts: Counter[str] = Counter()
    scene_first_idx: dict[str, int] = {}
    for view in sentence_views:
        for wid in view["wids"]:
            if wid in SCENE_NOUNS:
                scene_counts[wid] += 1
                scene_first_idx.setdefault(wid, view["idx"])
    for wid, count in scene_counts.items():
        if count == 1 and wid not in title_wids:
            idx = scene_first_idx[wid]
            issues.append(Issue(
                severity="warning",
                message=(
                    f"Lonely scene noun '{_lemma_for(vocab, wid)}' appears in "
                    f"exactly one sentence (s{idx}) and is not in the title or "
                    f"the title. A motif that genuinely matters to the scene "
                    f"usually appears at least twice or anchors the title. If "
                    f"this image is decoration, consider cutting it or echoing "
                    f"it earlier so it doesn't read as the 'moon also looks at "
                    f"the rain' anti-pattern."
                ),
                location=f"sentence {idx}",
            ))

    # ─ Rule 11.7: closer noun-pile (NEW 2026-04-28) ────────────────────────
    # Pattern: the LAST sentence of a story is just a list of nouns +
    # です/だ with no verb except the final copula. Form:
    #   N (や | と | 、) N (Adj? N)* です
    # The audit found this in ≥15 stories — it's the LLM author's default
    # closer when nothing concrete happened in the story. Examples:
    #   #6 s7  「雨の朝、猫や花、静かな窓です。」
    #   #20 s8 「外は雪、痛い手紙、温かい朝です。」
    #   #27 s8 「暑い夏、美しい庭、嬉しい一人の朝です。」
    #
    # CONSERVATIVE: rule fires only on the highest-idx (closer) sentence,
    # only when there's NO non-copula verb anywhere in the sentence, and
    # only when there are ≥2 content nouns AND ≥1 list particle (や/と/、).
    #
    # Escape hatches:
    #   - sentence carries G009_mo_also (も) → likely deliberate parallelism
    #   - sentence carries G014_to_omoimasu → it's a quoted/inferential closer
    #     ("I think it's a beautiful evening") which is a different shape
    if sentence_views:
        closer = max(sentence_views, key=lambda v: v["idx"] if v["idx"] is not None else -1)
        toks = closer["tokens"]
        # Strip trailing punct for the verb-presence check.
        meaningful = [t for t in toks if t.get("role") != "punct"]
        if meaningful:
            # Has any verb other than the final copula?
            non_copula_verb = False
            for t in meaningful[:-1]:
                inf = t.get("inflection") or {}
                form = inf.get("form", "")
                if form in ("polite_nonpast", "polite_past", "plain_nonpast",
                            "plain_past", "te", "nai", "masu", "tai",
                            "potential", "passive", "causative"):
                    non_copula_verb = True
                    break
            # Final token must be です/だ (the copula closer shape).
            ends_copula = meaningful[-1].get("t") in ("です", "だ")
            content_nouns = [t for t in toks if t.get("role") == "content" and t.get("word_id")]
            list_particles = [t for t in toks
                              if t.get("role") == "particle" and t.get("t") in ("や", "と", "、")]
            # Also count 、 as content separator even if tagged as punct
            commas_in_pile = sum(1 for t in toks if t.get("t") == "、")
            list_signal = len(list_particles) + commas_in_pile
            mo_escape = GRAMMAR_MO in closer["gids"]
            omoimasu_escape = GRAMMAR_TO_OMOIMASU in closer["gids"]
            if (
                ends_copula
                and not non_copula_verb
                and len(content_nouns) >= 2
                and list_signal >= 1
                and not mo_escape
                and not omoimasu_escape
            ):
                surface = "".join(t.get("t", "") for t in toks)
                issues.append(Issue(
                    severity="error",
                    message=(
                        f"Closer is a noun-pile: a list of nouns + です with no verb. "
                        f"This is the LLM-author's default closer when nothing "
                        f"concrete happened. End the story with an action, a "
                        f"dialogue beat, or a single concrete observation that "
                        f"resolves the arc — not a decorative inventory of the "
                        f"scene. (Sentence: 「{surface}」)"
                    ),
                    location=f"sentence {closer['idx']}",
                ))

    # ─ Rule 11.8: tautological possessive equivalence (NEW 2026-04-28) ──────
    # Pattern: `<N_A> の <N_Y> は <N_B> の <N_Y> です` — same noun on both
    # sides of は + copula, only the possessor changes. Reads "literary,"
    # asserts nothing.
    # Examples from the audit:
    #   #6 s6  「猫の色は、雨の色です。」
    #   #11 s5 「友達の手紙の色は、月の色です。」
    #   #53 s8 「この時計の時間は古いです。」 — borderline; not caught by this rule
    #
    # Escape hatches:
    #   - Y in {名前, 仕事, 家} (W00xxx for these, when present) — meaningful
    #     identity claim (`私の名前は父の名前です` = "I'm named after my father").
    #   - Right-hand side carries an adjective modifier — adds real content.
    EQUIVALENCE_EXEMPT_Y_LEMMAS: frozenset[str] = frozenset({
        "名前",   # name — identity claim is meaningful
        "仕事",   # job
        "家",     # home (literal residence comparison)
    })
    for view in sentence_views:
        toks = view["tokens"]
        # Walk for the pattern: content_A, の, content_Y, は, content_B, の, content_Y, です/だ
        # (allow a comma after は or before content_B)
        # We need to find indices a, no1, y1, wa, b, no2, y2, copula
        n = len(toks)
        for a in range(n - 7):
            t_a = toks[a]
            if t_a.get("role") != "content" or not t_a.get("word_id"):
                continue
            # Skip ahead allowing only the exact shape below
            i = a + 1
            t_no1 = toks[i] if i < n else None
            if not (t_no1 and t_no1.get("t") == "の" and t_no1.get("role") == "particle"):
                continue
            i += 1
            t_y1 = toks[i] if i < n else None
            if not (t_y1 and t_y1.get("role") == "content" and t_y1.get("word_id")):
                continue
            i += 1
            t_wa = toks[i] if i < n else None
            if not (t_wa and t_wa.get("t") == "は" and t_wa.get("role") == "particle"):
                continue
            i += 1
            # Optional comma
            if i < n and toks[i].get("t") == "、":
                i += 1
            t_b = toks[i] if i < n else None
            if not (t_b and t_b.get("role") == "content" and t_b.get("word_id")):
                continue
            i += 1
            t_no2 = toks[i] if i < n else None
            if not (t_no2 and t_no2.get("t") == "の" and t_no2.get("role") == "particle"):
                continue
            i += 1
            t_y2 = toks[i] if i < n else None
            if not (t_y2 and t_y2.get("role") == "content" and t_y2.get("word_id")):
                continue
            i += 1
            t_cop = toks[i] if i < n else None
            if not (t_cop and t_cop.get("t") in ("です", "だ")):
                continue
            # Match conditions:
            #   1. Y on both sides is the same word_id
            #   2. A and B are different word_ids (else not interesting — same as `XのYはXのYです`)
            if t_y1.get("word_id") != t_y2.get("word_id"):
                continue
            if t_a.get("word_id") == t_b.get("word_id"):
                continue
            # Escape: Y is name/job/home (meaningful identity)
            y_lemma = (t_y1.get("t") or "").strip()
            if y_lemma in EQUIVALENCE_EXEMPT_Y_LEMMAS:
                continue
            surface = "".join(t.get("t", "") for t in toks)
            issues.append(Issue(
                severity="error",
                message=(
                    f"Tautological possessive equivalence: "
                    f"「{t_a.get('t')}の{t_y1.get('t')}は{t_b.get('t')}の{t_y2.get('t')}です」 "
                    f"asserts that two possessors share the same property, but "
                    f"the property itself ({t_y1.get('t')}) is named on both "
                    f"sides — the sentence reads profound and means nothing. "
                    f"Replace with a concrete adjective ('the cat is white'), "
                    f"a comparison with new content ('the cat's color is brighter "
                    f"than the rain'), or a different observation. "
                    f"(Sentence: 「{surface}」)"
                ),
                location=f"sentence {view['idx']}",
            ))
            break  # one match per sentence is enough

    # ─ Rule 11.9: bare-known-fact extended (NEW 2026-04-28; loosens 11.3) ───
    # The original rule 11.3 fires only when 〜と思います embeds a CLAUSE OF
    # ONE CONTENT TOKEN that is a self-known fact. The audit shows defects
    # where the embedded clause is `<known-fact-noun> + <evaluative-adj/state> + だ`
    # ALSO ships in real corpora. Loosen as follows:
    #   - Allow embedded clause of up to 2 content tokens
    #   - BUT: at least one must be a self-known fact noun
    #   - AND: the other content token (if any) must be an adjective or
    #     state expression that describes the known noun in a way the
    #     narrator should already know (e.g. 暑い for 夏 in summer)
    # CONSERVATIVE: rule fires only when ALL content tokens are either
    # known-fact nouns or simple non-evaluative descriptors (universal
    # statements like 「夏は暑い」). The benign case (`風の朝だと思います`,
    # which has a NEW descriptive modifier) still has 2+ content tokens
    # and the modifier is NOT a universal-fact pattern, so it doesn't fire.
    #
    # We capture this loosely with a small set of "universal-pairing"
    # tokens that, combined with a known-fact noun, signal a tautology.
    UNIVERSAL_PAIRINGS: frozenset[tuple[str, str]] = frozenset({
        # (known_fact_lemma, descriptor_lemma) — universal facts that the
        # narrator never has to *infer* via 思います.
        ("夏", "暑い"),
        ("冬", "寒い"),
        ("夜", "暗い"),
        ("朝", "明るい"),
        ("雨", "冷たい"),
    })
    for view in sentence_views:
        if GRAMMAR_TO_OMOIMASU not in view["gids"]:
            continue
        toks = view["tokens"]
        cut = next(
            (
                i for i, t in enumerate(toks)
                if t.get("grammar_id") == GRAMMAR_TO_OMOIMASU
            ),
            None,
        )
        if cut is None:
            continue
        embedded = toks[:cut]
        embedded_content = [t for t in embedded
                            if t.get("role") == "content" and t.get("word_id")]
        # Already handled by 11.3: 1-content case
        if len(embedded_content) != 2:
            continue
        # Need both lemmas; check if any (a,b) or (b,a) is a universal pairing
        lemmas = tuple(t.get("t", "") for t in embedded_content)
        if (
            (lemmas[0], lemmas[1]) in UNIVERSAL_PAIRINGS
            or (lemmas[1], lemmas[0]) in UNIVERSAL_PAIRINGS
        ):
            surface = "".join(tt.get("t", "") for tt in toks)
            issues.append(Issue(
                severity="error",
                message=(
                    f"〜と思います embeds a universal-pairing assertion "
                    f"({lemmas[0]} + {lemmas[1]}). Things like '夏は暑い' or "
                    f"'夜は暗い' are universal facts; a narrator standing in "
                    f"summer doesn't *infer* that summer is hot. Use a plain "
                    f"assertion, or hedge something genuinely uncertain "
                    f"(another person's feelings, a future event). "
                    f"(Sentence: 「{surface}」)"
                ),
                location=f"sentence {view['idx']}",
            ))

    # ─ Rule 11.10: misapplied-quiet adverbial (NEW 2026-04-28; loosens 11.1) ─
    # The original 11.1 fires on  `INANIMATE は 静か です`. The audit found
    # the same defect dressed in adverbial form: `INANIMATE は 静かに <verb>`
    # where the inanimate noun is the subject of the adverb.
    #   #6 s3 「猫は静かに雨の色を見ます。」 — but cat is animate (excluded)
    #   The defective pattern is 「<inanimate> は 静かに ...」
    # CONSERVATIVE: same noun list as 11.1 (does NOT pull in 雨/月/星/空/風 —
    # those remain valid pathetic-fallacy in JP). Only fires on the same
    # objects 11.1 already considers nonsense.
    for view in sentence_views:
        toks = view["tokens"]
        for i, tok in enumerate(toks):
            wid = tok.get("word_id")
            if wid not in INANIMATE_QUIET_NOUN_IDS:
                continue
            # Need: <noun> は <0..3 tokens> 静かに  (must be 静か + に, not 静か + です)
            tail = toks[i + 1 : i + 7]
            joined = "".join(t.get("t", "") for t in tail)
            if "は" in joined and "静かに" in joined:
                # Make sure this isn't already caught by 11.1 (静か + です/だ)
                # i.e. 静かに + verb, not 静か + です
                if "静かです" in joined or "静かだ" in joined:
                    continue
                surface = "".join(t.get("t", "") for t in toks)
                issues.append(Issue(
                    severity="error",
                    message=(
                        f"Inanimate '{tok.get('t')}' described as acting 静かに "
                        f"(quietly). Books, letters, eggs, chairs etc. cannot "
                        f"perform actions quietly because they cannot perform "
                        f"actions at all. Either change the subject to an "
                        f"animate one, or drop the 静かに modifier. "
                        f"(Sentence: 「{surface}」)"
                    ),
                    location=f"sentence {view['idx']}",
                ))
                break  # one inanimate-quiet-adverb error per sentence

    return issues


# ── Check 12: Motif-rotation lint (library-level, warning only) ───────────────

def motif_rotation_lint(
    story: dict,
    prior_stories: Iterable[dict],
    *,
    overlap_threshold: float = 0.55,
    look_back: int = 3,
) -> list[Issue]:
    """Warn if this story shares too much vocabulary with any of the
    previous `look_back` stories.

    The score is Jaccard overlap of *content* word_ids. A score of ≥
    `overlap_threshold` means the story is essentially recycling a setting
    with one variable swapped — the exact pattern the audit flagged in
    stories 11–14 (rain + cat + letter + window, four times in a row).

    Warning only: the engagement reviewer surfaces these and decides
    whether the continuation is justified (e.g. cat returning in story 9
    is fine; rain-and-window appearing for the seventh time is not).
    """
    issues: list[Issue] = []
    this_wids = _content_wids(story)
    if not this_wids:
        return issues
    # Sort prior stories by id descending; take the most recent `look_back`.
    sorted_priors = sorted(
        prior_stories,
        key=lambda s: s.get("story_id", 0),
        reverse=True,
    )[:look_back]
    for prior in sorted_priors:
        prior_wids = _content_wids(prior)
        if not prior_wids:
            continue
        inter = this_wids & prior_wids
        union = this_wids | prior_wids
        if not union:
            continue
        jaccard = len(inter) / len(union)
        if jaccard >= overlap_threshold:
            issues.append(Issue(
                severity="warning",
                message=(
                    f"Vocabulary overlap with story_{prior.get('story_id')} is "
                    f"{jaccard:.0%} (Jaccard, content tokens). The two stories "
                    f"share {sorted(inter)[:8]}{'…' if len(inter) > 8 else ''}. "
                    f"Consider a setting / theme rotation; the library should "
                    f"feel like a sequence of *different* small worlds, not "
                    f"the same scene with one variable swapped."
                ),
                location="story",
            ))
    return issues


# ── Helpers ───────────────────────────────────────────────────────────────────

def _all_grammar_ids(tokens: list[dict]) -> set[str]:
    out: set[str] = set()
    for t in tokens:
        gid = t.get("grammar_id")
        if gid:
            out.add(gid)
        inf = t.get("inflection") or {}
        gid2 = inf.get("grammar_id")
        if gid2:
            out.add(gid2)
    return out


def _content_wids(story: dict) -> set[str]:
    wids: set[str] = set()
    for sent in story.get("sentences", []) or []:
        for tok in sent.get("tokens", []) or []:
            if tok.get("role") == "content":
                wid = tok.get("word_id")
                if wid:
                    wids.add(wid)
    return wids


def _lemma_for(vocab: dict | None, wid: str) -> str:
    if not vocab or not isinstance(vocab.get("words"), dict):
        return wid
    w = vocab["words"].get(wid) or {}
    return w.get("lemma") or w.get("surface") or wid
