"""Lexical difficulty signals for the Monogatari authoring pipeline.

This module is the single source of truth for "is this word too hard for
a story at position N in the corpus?" It exists because the corpus
already enforces a *grammar* tier ladder (N5 → N4 → N3 …) via
`pipeline/grammar_progression.py` and `validate.py` Check 3.x — but had
no equivalent gate on *vocabulary* difficulty. The bug it prevents:
shipping a story where a structurally simple sentence quietly introduces
a JLPT-N2-or-rarer noun (the canonical example: 包丁 "kitchen knife"
in an early bootstrap story).

Two complementary signals are consulted:

1. **JLPT level** from the bundled `data/jlpt_vocab.json` (sourced from
   stephenmk/yomitan-jlpt-vocab, the Tanos JLPT lists, jmdict-aligned).
   Authoritative when present. Levels are ints 5..1 where 5=N5 (most
   basic) and 1=N1 (most advanced). A word with no JLPT entry is
   "unknown — falls back to nf-band."

2. **JMdict nf-band** from `jamdict` (the Mainichi news-corpus
   frequency band, `nf01` = top 500, `nf48` = ranks 23,500–24,000).
   Used as the secondary signal when a word is missing from the JLPT
   list. A missing nf-band means the word doesn't appear in the
   first 24,000 ranks of the news corpus — treated as "very rare."

Per-story tier caps (the "gentle" progression — see AGENTS.md
"Lexical difficulty cap" section once it lands):

  Story 1–10  (bootstrap)   → max JLPT = N5,  max nf = nf06 (~rank 3,000)
  Story 11–25                → max JLPT = N4,  max nf = nf12 (~rank 6,000)
  Story 26–50                → max JLPT = N3,  max nf = nf24 (~rank 12,000)
  Story 51+                  → max JLPT = N2,  max nf = nf48 (any)

A word PASSES the cap if it satisfies EITHER signal — i.e. it has a
JLPT level ≤ tier-cap-level OR an nf-band ≤ tier-cap-nf. This is the
"belt-and-suspenders" approach the user picked: a word can be JLPT-N2
but if it's also `nf02` (e.g. 政府 "government"), it's fine in any
story; conversely, a word can be missing from JLPT but if it's
`nf04`, that's still common enough to pass.

Override: a story spec MAY list up to 1 above-cap word in its
top-level `lexical_overrides: ["surface", ...]` field. The override
must be acknowledged in the spec's `intent` field (so the author had
to think about it). The gauntlet's `vocab_difficulty` step warns on
override use; the validator counts how many overrides a story has and
refuses ≥2.
"""

from __future__ import annotations

import functools
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# --- Tier cap progression ---------------------------------------------------
# Each tier maps a story_id range to (max_jlpt_level, max_nf_band).
# `max_jlpt_level` is the int level threshold: 5 means "N5 only";
# 4 means "N4 or N5", etc. (Lower number = more advanced.)
# `max_nf_band` is the nf bucket integer: 6 means "nf01..nf06";
# 48 means "any nf-band is fine".

TIER_TABLE: list[tuple[int, int, int, int]] = [
    # (story_id_min, story_id_max, max_jlpt_level, max_nf_band)
    (1, 10, 5, 6),    # bootstrap: N5-only or top ~3,000
    (11, 25, 4, 12),  # ≤N4 or top ~6,000
    (26, 50, 3, 24),  # ≤N3 or top ~12,000
    (51, 10**9, 2, 48),  # ≤N2 or anywhere in news-frequency corpus
]

MAX_OVERRIDES_PER_STORY = 2  # raised from 1 → 2 on 2026-04-29 evening: bootstrap stories
                              # often need to introduce a domain (kitchen scene = 皿+包丁,
                              # garden scene = a tree + a flower) where the second above-cap
                              # mint is genuinely scene-grounding rather than indulgent. Two
                              # is still tight enough to discipline the author — a story
                              # asking for ≥3 overrides should split the scene.


@dataclass
class Difficulty:
    """Computed difficulty signal for a single word.

    Fields:
      jlpt: int level 5..1 if known, else None (unknown).
      nf_band: int 1..48 if the word has an nf-band tag, else None.
      common_tags: tuple of JMdict primary commonness tags
        (news1, ichi1, spec1, gai1, news2, ichi2, spec2, gai2).
      source: short string describing which signal was consulted.
    """

    jlpt: int | None
    nf_band: int | None
    common_tags: tuple[str, ...]
    source: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "jlpt": self.jlpt,
            "nf_band": self.nf_band,
            "common_tags": list(self.common_tags),
        }


@dataclass
class CapDecision:
    """Result of evaluating a Difficulty against a story-tier cap."""

    above_cap: bool
    reason: str  # human-readable explanation, useful in brief/error messages
    cap_jlpt: int
    cap_nf: int


# --- Data loading -----------------------------------------------------------

_JLPT_PATH_DEFAULT = Path(__file__).resolve().parent.parent / "data" / "jlpt_vocab.json"


@functools.lru_cache(maxsize=1)
def _load_jlpt(path: str | None = None) -> dict[str, Any]:
    p = Path(path) if path else _JLPT_PATH_DEFAULT
    if not p.exists():
        # Soft-fail: the difficulty checker is advisory if the data file
        # is missing. Callers should treat all words as "unknown".
        return {"by_jmdict_seq": {}, "by_kanji": {}, "by_kana": {}}
    return json.loads(p.read_text(encoding="utf-8"))


# --- Lookup helpers ---------------------------------------------------------

_NF_RE = re.compile(r"^nf(\d+)$")
_PRIMARY_COMMON_TAGS = frozenset({"news1", "ichi1", "spec1", "gai1"})


def _extract_nf_band(tags: list[str] | tuple[str, ...]) -> int | None:
    bands: list[int] = []
    for t in tags:
        m = _NF_RE.match(t)
        if m:
            bands.append(int(m.group(1)))
    return min(bands) if bands else None


def _jamdict_lookup(
    surface: str, kana: str
) -> tuple[int | None, tuple[str, ...], tuple[str, ...]]:
    """Return (best_nf_band, primary_common_tags, matching_jmdict_seqs).

    Picks the lowest nf band found across kanji forms matching `surface`
    AND kana forms matching `kana` on the same entry. Falls back to a
    looser match (any kanji form matching, or any kana form matching)
    if the strict match returns nothing.

    Returns ``(None, (), ())`` if jamdict is not importable or no entry
    matches — both are non-fatal.

    The `matching_jmdict_seqs` tuple lets `lookup_difficulty` cross-
    reference the JLPT-by-seq map, which avoids homograph collisions
    like 店|みせ (N5) vs 店|てん (N1).
    """
    try:
        from jamdict import Jamdict  # type: ignore  # noqa: F401
    except Exception:  # pragma: no cover - optional in test envs
        return None, (), ()

    try:
        jam = _jamdict_singleton()
        result = jam.lookup(surface or kana)
    except Exception:  # pragma: no cover
        return None, (), ()

    # Detect when the caller's "surface" is itself pure kana (no kanji
    # form, e.g. りんご, バナナ). For such words, jmdict entries may
    # have kanji_forms=[林檎] but the user-facing word never uses them
    # — we should match on the kana side and ignore the kanji form.
    surface_is_kana = bool(surface) and not any(
        "\u4e00" <= c <= "\u9fff" for c in surface
    )

    nf_bands: list[int] = []
    common: set[str] = set()
    seqs: list[str] = []
    for entry in result.entries:
        kanji_match = (not surface) or surface_is_kana or any(
            kf.text == surface for kf in entry.kanji_forms
        )
        kana_match = (not kana) or any(
            kn.text == kana or kn.text == surface for kn in entry.kana_forms
        )
        # If the caller's surface is kana, only the kana side needs to match.
        if surface_is_kana:
            if not kana_match:
                continue
        # Strict: only count entries whose kanji AND kana match (when both given).
        elif surface and kana and not (kanji_match and kana_match):
            continue
        elif surface and not kana and not kanji_match:
            continue
        elif kana and not surface and not kana_match:
            continue
        seqs.append(str(entry.idseq))
        for kf in entry.kanji_forms:
            if not surface or kf.text == surface:
                pri = list(kf.pri)
                nf = _extract_nf_band(pri)
                if nf is not None:
                    nf_bands.append(nf)
                common |= {t for t in pri if t in _PRIMARY_COMMON_TAGS}
        for kn in entry.kana_forms:
            if not kana or kn.text == kana or kn.text == surface:
                pri = list(kn.pri)
                nf = _extract_nf_band(pri)
                if nf is not None:
                    nf_bands.append(nf)
                common |= {t for t in pri if t in _PRIMARY_COMMON_TAGS}
    return (
        min(nf_bands) if nf_bands else None,
        tuple(sorted(common)),
        tuple(seqs),
    )


@functools.lru_cache(maxsize=1)
def _jamdict_singleton():  # pragma: no cover - thin wrapper
    from jamdict import Jamdict  # type: ignore

    return Jamdict()


@functools.lru_cache(maxsize=4096)
def lookup_difficulty(
    surface: str,
    kana: str = "",
    jmdict_seq: str | int | None = None,
    *,
    jlpt_path: str | None = None,
) -> Difficulty:
    """Compute the difficulty signal for a single word.

    Lookup order for JLPT level:
      1. by jmdict_seq if provided
      2. by exact kanji/surface match
      3. by exact kana match

    nf-band and commonness tags come from jamdict.
    """
    data = _load_jlpt(jlpt_path)
    by_seq = data.get("by_jmdict_seq", {})
    by_kanji = data.get("by_kanji", {})
    by_kana = data.get("by_kana", {})
    by_kanji_kana = data.get("by_kanji_kana", {})

    # Run jamdict first so we have matching jmdict_seqs to disambiguate
    # homographs (e.g. 店|みせ N5 vs 店|てん N1).
    nf_band, common_tags, matching_seqs = _jamdict_lookup(surface, kana)

    jlpt: int | None = None
    src: list[str] = []

    def _set_jlpt(level: int, source_label: str) -> None:
        nonlocal jlpt
        # Lowest (most basic) level wins. JLPT level integers run 5..1
        # where 5 is N5 (most basic). "Basic wins" means we want the
        # MAX integer when picking among candidates.
        if jlpt is None or level > jlpt:
            jlpt = level
            src.insert(0, f"jlpt(N{level} via {source_label})")
        else:
            src.append(f"jlpt-also(N{level} via {source_label})")

    # 1. Explicit jmdict_seq passed in by caller.
    if jmdict_seq is not None:
        seq_str = str(jmdict_seq)
        if seq_str in by_seq:
            _set_jlpt(int(by_seq[seq_str]), f"caller-seq={seq_str}")
    # 2. Disambiguated kanji|kana key (the right one for most cases).
    if surface or kana:
        key = f"{surface}|{kana}"
        if key in by_kanji_kana:
            _set_jlpt(int(by_kanji_kana[key]), f"kanji-kana={key}")
    # 3. Kana-only entry (for words with no kanji form like りんご, バナナ).
    if not surface and kana:
        key = f"|{kana}"
        if key in by_kanji_kana:
            _set_jlpt(int(by_kanji_kana[key]), f"kana-only={kana}")
    # 4. Cross-reference jamdict matching seqs to JLPT-by-seq.
    for seq in matching_seqs:
        if seq in by_seq:
            _set_jlpt(int(by_seq[seq]), f"jamdict-seq={seq}")
    # 5. Loose fallbacks (may be wrong for homographs — last resort).
    if jlpt is None and surface and surface in by_kanji:
        _set_jlpt(int(by_kanji[surface]), f"kanji-only={surface}")
    if jlpt is None and kana and kana in by_kana:
        _set_jlpt(int(by_kana[kana]), f"kana-loose={kana}")
    if jlpt is None and surface and surface in by_kana:
        _set_jlpt(int(by_kana[surface]), f"kana-as-surface={surface}")

    if nf_band is not None:
        src.append(f"nf{nf_band:02d}")
    if common_tags:
        src.append("common(" + "/".join(common_tags) + ")")

    return Difficulty(
        jlpt=jlpt,
        nf_band=nf_band,
        common_tags=common_tags,
        source=";".join(src) if src else "unknown",
    )


# --- Cap evaluation ---------------------------------------------------------


def tier_cap(story_id: int) -> tuple[int, int]:
    """Return (max_jlpt_level, max_nf_band) for a given story_id."""
    for lo, hi, jlpt_max, nf_max in TIER_TABLE:
        if lo <= story_id <= hi:
            return jlpt_max, nf_max
    # Fallback (shouldn't happen — last row is open-ended)
    return TIER_TABLE[-1][2], TIER_TABLE[-1][3]


def evaluate_cap(diff: Difficulty, story_id: int) -> CapDecision:
    """Decide whether `diff` is within the story-tier cap.

    A word PASSES if it satisfies EITHER:
      (a) its JLPT level is known and ≤ cap_jlpt (i.e. level int ≥ cap_jlpt
          since 5 is most basic), OR
      (b) its nf_band is known and ≤ cap_nf.

    Otherwise it's flagged above-cap. Words with NO known signal at all
    (no JLPT entry, no nf band, no commonness tag) are treated as
    above-cap with reason "no frequency signal — likely very rare."
    """
    cap_jlpt, cap_nf = tier_cap(story_id)
    jlpt_ok = diff.jlpt is not None and diff.jlpt >= cap_jlpt
    nf_ok = diff.nf_band is not None and diff.nf_band <= cap_nf
    # "Basic-vocab list" rescue. The JLPT list (Tanos / yomitan-jlpt-vocab)
    # has well-known gaps for common everyday words like りんご, バナナ,
    # かばん that were never JLPT-tested but ARE basic vocab. JMdict
    # carries an `ichi1` tag (Ichimango basic-vocab list) for these.
    # If a word has `ichi1` AND no JLPT level (genuinely unknown, not
    # "we know it's hard"), treat it as if it were N5. This avoids
    # false positives without weakening the rule for genuinely rare
    # words (which lack both `ichi1` AND a low nf-band).
    if (
        diff.jlpt is None
        and "ichi1" in diff.common_tags
    ):
        jlpt_ok = True
        diff = Difficulty(
            jlpt=diff.jlpt,
            nf_band=diff.nf_band,
            common_tags=diff.common_tags,
            source=diff.source + ";rescue(ichi1≈N5)",
        )
    if jlpt_ok or nf_ok:
        which = []
        if jlpt_ok and diff.jlpt is not None:
            which.append(f"JLPT N{diff.jlpt} ≤ N{cap_jlpt} cap")
        elif jlpt_ok:
            which.append(f"basic-vocab list (ichi1) — treated as ≤N5")
        if nf_ok:
            which.append(f"nf{diff.nf_band:02d} ≤ nf{cap_nf:02d} cap")
        return CapDecision(
            above_cap=False,
            reason="passes via " + " and ".join(which),
            cap_jlpt=cap_jlpt,
            cap_nf=cap_nf,
        )

    # Above cap. Pick the most informative failure reason.
    bits = []
    if diff.jlpt is not None:
        bits.append(f"JLPT N{diff.jlpt} > N{cap_jlpt} cap for story {story_id}")
    elif diff.nf_band is not None:
        bits.append(
            f"no JLPT level; nf{diff.nf_band:02d} > nf{cap_nf:02d} cap for story {story_id}"
        )
    else:
        bits.append(
            f"no frequency signal at all (not in JLPT list, no nf-band tag) — "
            f"likely very rare; story {story_id} cap is N{cap_jlpt}/nf{cap_nf:02d}"
        )
    return CapDecision(
        above_cap=True,
        reason="; ".join(bits),
        cap_jlpt=cap_jlpt,
        cap_nf=cap_nf,
    )


# --- Convenience for callers (vocab records / spec evaluation) --------------


def difficulty_from_vocab_record(word: dict[str, Any]) -> Difficulty:
    """Build a Difficulty from a `vocab_state.words[wid]` record.

    If the record has cached `jlpt` / `nf_band` / `common_tags` fields
    (set at mint time by text_to_story._ensure_word), use them directly
    to avoid a jamdict round-trip. Otherwise call `lookup_difficulty`.
    """
    if any(k in word for k in ("jlpt", "nf_band", "common_tags")):
        return Difficulty(
            jlpt=word.get("jlpt"),
            nf_band=word.get("nf_band"),
            common_tags=tuple(word.get("common_tags", ())),
            source="cached",
        )
    return lookup_difficulty(
        surface=word.get("surface", ""),
        kana=word.get("kana", ""),
    )


def is_above_tier(word: dict[str, Any], story_id: int) -> CapDecision:
    """Convenience: difficulty_from_vocab_record + evaluate_cap."""
    return evaluate_cap(difficulty_from_vocab_record(word), story_id)
