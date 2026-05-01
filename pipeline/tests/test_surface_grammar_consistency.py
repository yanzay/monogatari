"""Class A: Surface ↔ grammar_id semantic consistency tests.

These exist because we discovered, during the April 2026 grammar audit,
that の had been silently mis-tagged as N5_wa_topic in 22 places, な
as N5_desu in 3 places, and で as N5_ni_location in 1 place.

The original validator caught none of these because every token HAD a
grammar_id; just the wrong one. These tests are the permanent guard.
"""
from __future__ import annotations
import pytest
from collections import defaultdict

from _helpers import iter_tokens

# ── Forbidden surface ↔ grammar_id pairs ─────────────────────────────────
# Surface MUST NEVER be tagged with this grammar_id.
# Format: (role, surface) → set of forbidden grammar_ids
FORBIDDEN_PAIRS: dict[tuple[str, str], set[str]] = {
    ("particle", "の"): {"N5_wa_topic"},     # の is possessive (G015), not topic
    ("particle", "な"): {"N5_desu"},         # な is na-adj attributive (G016), not copula
    # Note: で can be N5_ni_location ONLY when it's actually に misspelled — but it never is.
    # で should always be N5_de_means in our scope.
    ("particle", "で"): {"N5_ni_location"},
}

# ── Required surface ↔ grammar_id pairs ─────────────────────────────────
# Surface MUST always be tagged with this grammar_id (when role matches).
EXPECTED_PAIRS: dict[tuple[str, str], str] = {
    ("particle", "の"): "N5_no_pos",
    ("particle", "な"): "N5_na_adj",
    ("particle", "で"): "N5_de_means",
    ("particle", "は"): "N5_wa_topic",
    ("particle", "を"): "N5_o_object",
    ("particle", "に"): "N5_ni_location",
    ("particle", "も"): "N5_mo_also",
    ("particle", "や"): "N5_ya_partial",
    # と has TWO valid meanings (and-list G010, quote-particle G014) — handled separately
    # です/だ/でした collapse into N5_desu / N5_mashita — handled separately
    ("aux", "そして"): "N5_soshite",
    ("particle", "そして"): "N5_soshite",
}

# ── Surfaces that may legitimately have multiple grammar_ids ─────────────
POLYSEMOUS: dict[tuple[str, str], set[str]] = {
    ("particle", "と"): {"N5_to_and", "N4_to_omoimasu", "N4_to_iimasu"},  # and-list vs quote / says
    ("particle", "から"): {"N5_kara_from", "N5_kara_because"},  # noun-from vs clause-because
    ("particle", "が"): {"N5_ga_subject", "N5_ga_but"},  # subject marker vs clause-but (v0.22)
    ("aux", "です"): {"N5_desu"},
    ("aux", "だ"): {"N5_desu", "N5_da"},  # plain copula (G024 added v0.16)
    ("aux", "でした"): {"N5_desu", "N5_mashita"},  # past copula
    ("aux", "ます"): {"N5_desu", "N5_masu_nonpast"},  # politeness aux
    ("aux", "ました"): {"N5_mashita"},
}


def test_no_forbidden_surface_grammar_pairs(stories):
    """Catches the の-as-G001 bug class."""
    violations = []
    for story in stories:
        for sec, sent_idx, tok_idx, tok in iter_tokens(story):
            role = tok.get("role")
            surface = tok.get("t", "")
            gid = tok.get("grammar_id")
            if not gid:
                continue
            forbidden = FORBIDDEN_PAIRS.get((role, surface))
            if forbidden and gid in forbidden:
                violations.append(
                    f"{story['_id']}: '{surface}' ({role}) tagged as {gid} "
                    f"(forbidden — should be {EXPECTED_PAIRS.get((role, surface), '?')})"
                )
    assert not violations, "Forbidden surface↔grammar_id pairs found:\n  " + "\n  ".join(violations)


def test_expected_surface_grammar_pairs(stories):
    """Surface should map to its expected grammar_id (or one of its polysemous options)."""
    violations = []
    for story in stories:
        for sec, sent_idx, tok_idx, tok in iter_tokens(story):
            role = tok.get("role")
            surface = tok.get("t", "")
            gid = tok.get("grammar_id")
            key = (role, surface)
            if key in POLYSEMOUS:
                allowed = POLYSEMOUS[key]
                if gid and gid not in allowed:
                    violations.append(
                        f"{story['_id']}: '{surface}' ({role}) tagged as {gid} "
                        f"(allowed: {sorted(allowed)})"
                    )
            elif key in EXPECTED_PAIRS:
                expected = EXPECTED_PAIRS[key]
                if gid and gid != expected:
                    violations.append(
                        f"{story['_id']}: '{surface}' ({role}) tagged as {gid} "
                        f"(expected {expected})"
                    )
    assert not violations, "Unexpected surface↔grammar_id pairs:\n  " + "\n  ".join(violations)


def test_no_surface_with_inconsistent_tags_across_corpus(stories):
    """If '私' (or any surface) is tagged with grammar_id X in one story, it should
    be tagged with X in every other story too (within polysemous bounds).
    """
    surface_to_gids: dict[tuple[str, str], dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for story in stories:
        for sec, sent_idx, tok_idx, tok in iter_tokens(story):
            role = tok.get("role")
            surface = tok.get("t", "")
            gid = tok.get("grammar_id")
            if gid and role in ("particle", "aux"):
                surface_to_gids[(role, surface)][gid].append(story["_id"])

    inconsistencies = []
    for (role, surface), gid_to_stories in surface_to_gids.items():
        if (role, surface) in POLYSEMOUS:
            continue  # known polysemous
        if len(gid_to_stories) > 1:
            details = ", ".join(f"{g}({len(s)})" for g, s in gid_to_stories.items())
            inconsistencies.append(f"{role}/'{surface}' has {len(gid_to_stories)} different tags: {details}")

    assert not inconsistencies, (
        "Surfaces tagged with multiple different grammar_ids across the corpus:\n  "
        + "\n  ".join(inconsistencies)
    )
