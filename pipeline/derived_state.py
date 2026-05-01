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
