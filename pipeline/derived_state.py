"""Single source of truth for *derived* grammar-state attributions.

Why this module exists
----------------------
`intro_in_story` and `last_seen_story` for grammar points are NOT genuine
state. They are derived from the corpus:

    intro_in_story[gid]     == min(story_id where gid appears in tokens)
    last_seen_story[gid]    == max(story_id where gid appears in tokens)

For ~6 weeks they were treated as stored mutable fields on
`data/grammar_state.json::points[gid]`, which produced:

  * Drift after every re-ship (the §2 state_updater code only patched
    when the field was None, so a moved attribution never updated).
  * A copy-paste reconciliation runbook in AGENTS.md (now removed).
  * Multiple repair scripts (`reconcile_grammar_intros.py`,
    `backfill_grammar_intros.py`).
  * A test (`test_grammar_intro_in_story_matches_corpus_first_use`)
    whose only job was to detect the drift the storage made possible.

Phase A of the derive-on-read refactor (2026-05-01) makes this module
the *only* place either field is computed. Every consumer — Python
pipeline + Svelte reader (via the manifest projection in
`build_manifest.py`) — calls this function or reads its projection.
The fields are no longer written to `grammar_state.json`.

Vocabulary `first_story` / `last_seen_story` get the same treatment in
Phase B; deliberately scoped out of Phase A because the consumer
surface is ~2x larger.
"""
from __future__ import annotations

from typing import Iterable, TypedDict

from _paths import iter_stories


class GrammarAttribution(TypedDict):
    intro_in_story:  int | None
    last_seen_story: int | None


def _walk_grammar_ids(story: dict) -> Iterable[str]:
    """Yield every grammar_id referenced by any token in a story.

    Walks both the top-level `grammar_id` field and the legacy
    `inflection.grammar_id` path. Title tokens count: a particle that
    debuts in a title genuinely debuts there (mirrors the rule
    state_updater used to apply for last_seen_story bookkeeping).
    """
    title = story.get("title")
    if isinstance(title, dict):
        for tok in title.get("tokens") or []:
            gid = tok.get("grammar_id")
            if gid:
                yield gid
            infl_gid = (tok.get("inflection") or {}).get("grammar_id")
            if infl_gid:
                yield infl_gid
    for sent in story.get("sentences") or []:
        for tok in sent.get("tokens") or []:
            gid = tok.get("grammar_id")
            if gid:
                yield gid
            infl_gid = (tok.get("inflection") or {}).get("grammar_id")
            if infl_gid:
                yield infl_gid


def derive_grammar_attributions(
    stories: Iterable[tuple[int, dict]] | None = None,
) -> dict[str, GrammarAttribution]:
    """Return {gid: {intro_in_story, last_seen_story}} from the corpus.

    Args:
      stories: optional iterable of (story_id, story_dict) pairs. If
        None, walks the on-disk `stories/` directory via
        `_paths.iter_stories()`. Pass an explicit iterable to derive
        attributions for a hypothetical / in-memory corpus (used by
        the gauntlet to preview ship effects on a not-yet-written
        story).

    Returns:
      Dict keyed by grammar_id. Every gid that appears in at least
      one story has a record. Points that never appear in the corpus
      are NOT in the result — callers that want a "all known points"
      view must left-join against `data/grammar_state.json::points`.
    """
    if stories is None:
        stories = iter_stories()

    intro: dict[str, int] = {}
    last:  dict[str, int] = {}
    # Iterate in story_id order so intro stays the *first* (min) and
    # last keeps overwriting up to the *last* (max).
    for sid, story in sorted(stories, key=lambda x: x[0]):
        for gid in _walk_grammar_ids(story):
            if gid not in intro:
                intro[gid] = sid
            last[gid] = sid

    return {
        gid: GrammarAttribution(
            intro_in_story=intro[gid],
            last_seen_story=last[gid],
        )
        for gid in intro  # intro and last share keys by construction
    }


def grammar_attribution_for(
    gid: str,
    attributions: dict[str, GrammarAttribution] | None = None,
) -> GrammarAttribution:
    """Convenience: look up one gid, returning a None/None record if absent.

    Most callers want a uniform shape regardless of whether the point
    has been introduced yet. Pass `attributions` to avoid re-walking
    the corpus on every call.
    """
    if attributions is None:
        attributions = derive_grammar_attributions()
    return attributions.get(
        gid,
        GrammarAttribution(intro_in_story=None, last_seen_story=None),
    )


def is_introduced(
    gid: str,
    attributions: dict[str, GrammarAttribution] | None = None,
) -> bool:
    """True iff the grammar point has appeared in at least one shipped story."""
    return grammar_attribution_for(gid, attributions)["intro_in_story"] is not None


# ─────────────────────────────────────────────────────────────────────────────
# Vocab attributions (Phase B — 2026-05-01)
# ─────────────────────────────────────────────────────────────────────────────


class VocabAttribution(TypedDict):
    # NOTE: vocab uses STRING form ("story_N") historically, while
    # grammar uses int. Phase B preserves the string form so existing
    # consumers (WordPopup display, vocab route filter) continue to
    # work without per-call coercion. Reader code already handles both
    # `number` and `string` types defensively (see VocabIndexRow).
    first_story:     str | None
    last_seen_story: str | None
    occurrences:     int


def _walk_word_ids(story: dict) -> Iterable[str]:
    """Yield every word_id referenced by any token in a story.

    Walks both title and sentence tokens. A word_id can appear once per
    occurrence; callers that want occurrence counts should not dedupe.
    Function-class mints (conjunctions) appear with both word_id and
    grammar_id on the same token; both walks emit them.
    """
    title = story.get("title")
    if isinstance(title, dict):
        for tok in title.get("tokens") or []:
            wid = tok.get("word_id")
            if wid:
                yield wid
    for sent in story.get("sentences") or []:
        for tok in sent.get("tokens") or []:
            wid = tok.get("word_id")
            if wid:
                yield wid


def derive_vocab_attributions(
    stories: Iterable[tuple[int, dict]] | None = None,
) -> dict[str, VocabAttribution]:
    """Return {wid: {first_story, last_seen_story, occurrences}} from corpus.

    Schema mirrors `derive_grammar_attributions` but with vocab-specific
    semantics:
      first_story:     "story_<min N where wid appears>" (str, matches
                       the historical vocab_state convention).
      last_seen_story: "story_<max N where wid appears>" (str, same).
      occurrences:     total count across all stories. Unlike the
                       grammar derivation, this carries pedagogical
                       weight (drives reinforcement debt analysis) and
                       must NOT dedupe per story.

    Args:
      stories: optional iterable of (story_id, story_dict). If None,
        walks `stories/` via `_paths.iter_stories()`.

    Returns:
      Dict keyed by word_id. Words that never appear in the corpus are
      NOT in the result; callers wanting an "all known words" view must
      left-join against `data/vocab_state.json::words`.
    """
    if stories is None:
        stories = iter_stories()

    first: dict[str, int] = {}
    last:  dict[str, int] = {}
    counts: dict[str, int] = {}
    for sid, story in sorted(stories, key=lambda x: x[0]):
        for wid in _walk_word_ids(story):
            if wid not in first:
                first[wid] = sid
            last[wid] = sid
            counts[wid] = counts.get(wid, 0) + 1

    return {
        wid: VocabAttribution(
            first_story=f"story_{first[wid]}",
            last_seen_story=f"story_{last[wid]}",
            occurrences=counts[wid],
        )
        for wid in first
    }


def vocab_attribution_for(
    wid: str,
    attributions: dict[str, VocabAttribution] | None = None,
) -> VocabAttribution:
    """Convenience: look up one wid, returning a None/None/0 record if absent."""
    if attributions is None:
        attributions = derive_vocab_attributions()
    return attributions.get(
        wid,
        VocabAttribution(first_story=None, last_seen_story=None, occurrences=0),
    )
